import os
import time
import json
import logging
from celery import Celery
from celery.signals import worker_process_init
import redis
from faster_whisper import WhisperModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [pid:%(process)d] %(message)s"
)
logger = logging.getLogger("worker")

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
MODEL_SIZE = os.getenv("MODEL_SIZE", "base")
DEVICE = os.getenv("DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("COMPUTE_TYPE", "int8")
CPU_THREADS = int(os.getenv("CPU_THREADS", "4"))

# Initialize Celery
celery_app = Celery("transcriber", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    result_expires=7200,          # Retain results for 2 hours
    worker_prefetch_multiplier=1, # Fair distribution among workers
    broker_connection_retry_on_startup=True,
    task_track_started=True,
)

# Global model instance
model = None

# Redis client for pub/sub notifications
redis_sync_client = None

def get_redis_client():
    global redis_sync_client
    if redis_sync_client is None:
        redis_sync_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return redis_sync_client

def load_model():
    """Initializes and loads the WhisperModel into process memory."""
    global model
    if model is None:
        logger.info(f"Loading Whisper model '{MODEL_SIZE}' on {DEVICE} ({COMPUTE_TYPE}, {CPU_THREADS} threads)...")
        try:
            model = WhisperModel(
                MODEL_SIZE,
                device=DEVICE,
                compute_type=COMPUTE_TYPE,
                cpu_threads=CPU_THREADS,
                num_workers=1
            )
            logger.info("Whisper model loaded successfully.")
        except Exception as e:
            logger.critical(f"FATAL: Could not load Whisper model: {e}", exc_info=True)
            raise e

@worker_process_init.connect
def init_worker_process(**kwargs):
    """Pre-warm model when the Celery worker process starts, avoiding first-request latency penalty."""
    logger.info("Worker process initialized. Pre-warming Whisper model...")
    load_model()

def format_timestamp(seconds: float):
    """Formats seconds to SRT/VTT timestamp format."""
    seconds = float(seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds_rem = seconds % 60
    milliseconds = int((seconds_rem - int(seconds_rem)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{int(seconds_rem):02d},{milliseconds:03d}"

def generate_srt(segments):
    output = ""
    for i, segment in enumerate(segments, start=1):
        start = format_timestamp(segment['start'])
        end = format_timestamp(segment['end'])
        output += f"{i}\n{start} --> {end}\n{segment['text']}\n\n"
    return output

def generate_vtt(segments):
    output = "WEBVTT\n\n"
    for segment in segments:
        start = format_timestamp(segment['start']).replace(',', '.')
        end = format_timestamp(segment['end']).replace(',', '.')
        output += f"{start} --> {end}\n{segment['text']}\n\n"
    return output

from storage import download_audio_file, cleanup_audio_file
import httpx

def send_webhook(webhook_url: str, payload: dict, max_retries: int = 3):
    """Sends transcription completion payload to client webhook with retries."""
    if not webhook_url:
        return

    logger.info(f"Dispatching webhook to {webhook_url}...")
    for attempt in range(1, max_retries + 1):
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(webhook_url, json=payload)
                if res.is_success:
                    logger.info(f"Webhook delivered successfully to {webhook_url} (HTTP {res.status_code})")
                    return
                logger.warning(f"Webhook delivery attempt {attempt} returned HTTP {res.status_code}")
        except Exception as err:
            logger.warning(f"Webhook delivery attempt {attempt} failed: {err}")
        time.sleep(2 ** attempt)

    logger.error(f"Failed to deliver webhook to {webhook_url} after {max_retries} attempts.")

@celery_app.task(
    name="transcribe_task",
    bind=True,
    time_limit=600,       # Kill task if it exceeds 10 minutes (prevents deadlocks)
    soft_time_limit=540   # Soft timeout at 9 minutes for graceful failure
)
def transcribe_task(
    self,
    file_path,
    vad_filter=True,
    initial_prompt=None,
    language=None,
    output_format="json",
    webhook_url=None,
    s3_key=None
):
    # Ensure model is ready (fallback if worker_process_init wasn't triggered)
    if model is None:
        load_model()

    task_id = self.request.id
    logger.info(f"Starting transcription task {task_id} for input: {file_path or s3_key}")
    start_time = time.time()

    # Resolve local audio path (downloads from S3 if needed)
    resolved_local_path = None
    try:
        resolved_local_path = download_audio_file(s3_key or file_path)
    except Exception as dl_err:
        logger.error(f"Failed to resolve audio file for task {task_id}: {dl_err}", exc_info=True)
        failure_payload = {"status": "failed", "error": f"Audio fetch error: {str(dl_err)}", "job_id": task_id}
        send_webhook(webhook_url, failure_payload)
        return failure_payload

    # Notify subscribers that processing has begun
    try:
        r = get_redis_client()
        r.publish(f"job_events:{task_id}", json.dumps({"status": "processing", "job_id": task_id}))
    except Exception as notify_err:
        logger.warning(f"Could not publish start event: {notify_err}")

    try:
        segments, info = model.transcribe(
            resolved_local_path,
            beam_size=1,                      # Fast inference
            best_of=1,
            temperature=0,
            condition_on_previous_text=False,
            vad_filter=vad_filter,
            vad_parameters=dict(
                min_silence_duration_ms=500,
                threshold=0.5,
                min_speech_duration_ms=250
            ),
            initial_prompt=initial_prompt,
            language=language
        )

        transcript = []
        full_text = []
        for segment in segments:
            segment_data = {
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip()
            }
            transcript.append(segment_data)
            full_text.append(segment.text.strip())

        process_time = round(time.time() - start_time, 3)
        audio_duration = round(info.duration, 2)
        rtf = round(process_time / max(audio_duration, 0.001), 3)
        joined_text = " ".join(full_text).strip()

        result = {
            "status": "completed",
            "job_id": task_id,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "duration": audio_duration,
            "process_time": process_time,
            "real_time_factor": rtf,
            "format": output_format,
        }

        # Format output
        if output_format == "srt":
            result["text"] = generate_srt(transcript)
        elif output_format == "vtt":
            result["text"] = generate_vtt(transcript)
        elif output_format == "txt":
            result["text"] = joined_text
        else:
            result["text"] = joined_text
            result["segments"] = transcript
            result["format"] = "json"

        # Publish completion event to Redis Pub/Sub for SSE/WebSockets listeners
        try:
            r = get_redis_client()
            r.publish(f"job_events:{task_id}", json.dumps({"status": "completed", "result": result}))
        except Exception as pub_err:
            logger.warning(f"Could not publish completion event: {pub_err}")

        # Dispatch webhook if provided
        if webhook_url:
            send_webhook(webhook_url, {"job_id": task_id, "status": "completed", "result": result})

        logger.info(f"Task {task_id} completed successfully in {process_time}s (Audio: {audio_duration}s, RTF: {rtf})")
        return result

    except Exception as e:
        logger.error(f"Error processing task {task_id} on {resolved_local_path}: {e}", exc_info=True)
        failure_payload = {"status": "failed", "job_id": task_id, "error": str(e)}
        try:
            r = get_redis_client()
            r.publish(f"job_events:{task_id}", json.dumps(failure_payload))
        except Exception:
            pass

        if webhook_url:
            send_webhook(webhook_url, failure_payload)

        return failure_payload

    finally:
        # Guaranteed cleanup of local file
        cleanup_audio_file(resolved_local_path, s3_key=s3_key)
