import os
import time
import json
import logging
from celery import Celery
from celery.signals import worker_process_init
import redis
from faster_whisper import WhisperModel
import httpx

from storage import download_audio_file, cleanup_audio_file
from audio_splitter import split_audio_into_chunks, cleanup_chunk_dir

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
CPU_THREADS = int(os.getenv("CPU_THREADS", "2"))

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

# Redis client for pub/sub notifications and progressive job state
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

def transcribe_audio_segment(
    audio_path: str,
    vad_filter: bool = True,
    initial_prompt: str = None,
    language: str = None
):
    """Helper that runs inference on a single audio file and returns (transcript_list, full_text_list, info)."""
    if model is None:
        load_model()

    segments, info = model.transcribe(
        audio_path,
        beam_size=1,
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
        transcript.append({
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
            "text": segment.text.strip()
        })
        full_text.append(segment.text.strip())

    return transcript, full_text, info

@celery_app.task(
    name="transcribe_chunk_task",
    bind=True,
    time_limit=1800,
    soft_time_limit=1600,
    max_retries=3
)
def transcribe_chunk_task(
    self,
    chunk_info: dict,
    job_id: str,
    vad_filter: bool = True,
    initial_prompt: str = None,
    language: str = None,
    output_format: str = "json",
    webhook_url: str = None,
    original_audio_path: str = None,
    s3_key: str = None
):
    """
    Worker task to transcribe an individual chunk in parallel.
    Shifts timestamps by start_offset, updates Redis progress, and publishes SSE events.
    """
    chunk_index = chunk_info["chunk_index"]
    start_offset = chunk_info.get("start_offset", 0.0)
    chunk_file = chunk_info["file_path"]

    logger.info(f"[{job_id}] Processing chunk {chunk_index} (offset: {start_offset}s, path: {chunk_file})...")
    start_time = time.time()

    try:
        raw_transcript, raw_text, info = transcribe_audio_segment(
            chunk_file,
            vad_filter=vad_filter,
            initial_prompt=initial_prompt,
            language=language
        )

        # Shift timestamps relative to the whole audio file
        shifted_segments = []
        for seg in raw_transcript:
            shifted_segments.append({
                "start": round(seg["start"] + start_offset, 2),
                "end": round(seg["end"] + start_offset, 2),
                "text": seg["text"]
            })

        chunk_process_time = round(time.time() - start_time, 2)
        chunk_text = " ".join(raw_text).strip()

        chunk_result = {
            "chunk_index": chunk_index,
            "start_offset": start_offset,
            "duration": chunk_info.get("duration", 0.0),
            "process_time": chunk_process_time,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "segments": shifted_segments,
            "text": chunk_text
        }

        r = get_redis_client()
        # Save this chunk's results into the Redis hash for this job
        r.hset(f"job_chunks:{job_id}", str(chunk_index), json.dumps(chunk_result))

        # Atomically increment completed chunks
        completed_count = r.hincrby(f"job_state:{job_id}", "completed_chunks", 1)
        total_chunks = int(r.hget(f"job_state:{job_id}", "total_chunks") or 1)
        progress_pct = min(100.0, round((completed_count / total_chunks) * 100.0, 1))

        # Update job progress in Redis
        r.hset(f"job_state:{job_id}", mapping={
            "progress": str(progress_pct),
            "language": info.language
        })

        # Broadcast progressive chunk completed event to SSE listeners
        chunk_event = {
            "type": "chunk_completed",
            "job_id": job_id,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "progress_percent": progress_pct,
            "text": chunk_text,
            "segments": shifted_segments
        }
        r.publish(f"job_events:{job_id}", json.dumps(chunk_event))
        logger.info(f"[{job_id}] Chunk {chunk_index + 1}/{total_chunks} completed in {chunk_process_time}s ({progress_pct}% done).")

        # If all chunks are completed, finalize the job
        if completed_count >= total_chunks:
            logger.info(f"[{job_id}] All {total_chunks} chunks completed! Finalizing unified transcript...")
            finalize_chunked_job(
                job_id=job_id,
                total_chunks=total_chunks,
                output_format=output_format,
                webhook_url=webhook_url,
                original_audio_path=original_audio_path,
                s3_key=s3_key
            )

        return chunk_result

    except Exception as e:
        logger.error(f"[{job_id}] Error in chunk {chunk_index}: {e}", exc_info=True)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=5)

        # Fatal failure for this job
        r = get_redis_client()
        failure_payload = {"status": "failed", "job_id": job_id, "error": f"Chunk {chunk_index} failed: {str(e)}"}
        r.hset(f"job_state:{job_id}", mapping={"status": "failed", "error": str(e)})
        r.publish(f"job_events:{job_id}", json.dumps(failure_payload))
        cleanup_chunk_dir(job_id)
        if webhook_url:
            send_webhook(webhook_url, failure_payload)
        raise e

def finalize_chunked_job(
    job_id: str,
    total_chunks: int,
    output_format: str = "json",
    webhook_url: str = None,
    original_audio_path: str = None,
    s3_key: str = None
):
    """
    Aggregates all chunk results into a single final transcript, publishes completion event,
    updates Celery result, and cleans up chunk files.
    """
    r = get_redis_client()
    raw_chunks = r.hgetall(f"job_chunks:{job_id}")

    all_segments = []
    all_texts = []
    total_audio_duration = 0.0
    detected_language = "en"
    lang_prob = 1.0

    # Sort chunks by chunk_index
    sorted_indices = sorted([int(k) for k in raw_chunks.keys()])
    for idx in sorted_indices:
        chunk_data = json.loads(raw_chunks[str(idx)])
        all_segments.extend(chunk_data.get("segments", []))
        if chunk_data.get("text"):
            all_texts.append(chunk_data["text"])
        total_audio_duration += chunk_data.get("duration", 0.0)
        detected_language = chunk_data.get("language", detected_language)
        lang_prob = chunk_data.get("language_probability", lang_prob)

    joined_text = " ".join(all_texts).strip()

    job_start_time = float(r.hget(f"job_state:{job_id}", "start_time") or time.time())
    total_process_time = round(time.time() - job_start_time, 2)
    rtf = round(total_process_time / max(total_audio_duration, 0.001), 3)

    result = {
        "status": "completed",
        "job_id": job_id,
        "language": detected_language,
        "language_probability": lang_prob,
        "duration": round(total_audio_duration, 2),
        "process_time": total_process_time,
        "real_time_factor": rtf,
        "format": output_format,
        "chunks_processed": len(sorted_indices)
    }

    if output_format == "srt":
        result["text"] = generate_srt(all_segments)
    elif output_format == "vtt":
        result["text"] = generate_vtt(all_segments)
    elif output_format == "txt":
        result["text"] = joined_text
    else:
        result["text"] = joined_text
        result["segments"] = all_segments
        result["format"] = "json"

    # Persist completed state to Redis
    r.hset(f"job_state:{job_id}", mapping={
        "status": "completed",
        "progress": "100.0",
        "result": json.dumps(result)
    })
    # Also set Celery result in backend so AsyncResult(job_id) returns SUCCESS
    try:
        celery_app.backend.store_result(job_id, result, state="SUCCESS")
    except Exception as b_err:
        logger.warning(f"Could not store Celery backend result for {job_id}: {b_err}")

    # Broadcast final completion event
    final_event = {"status": "completed", "job_id": job_id, "result": result}
    r.publish(f"job_events:{job_id}", json.dumps(final_event))

    # Send webhook if configured
    if webhook_url:
        send_webhook(webhook_url, final_event)

    # Cleanup temporary chunks directory and downloaded audio
    cleanup_chunk_dir(job_id)
    if original_audio_path:
        cleanup_audio_file(original_audio_path, s3_key=s3_key)

    logger.info(f"[{job_id}] Full transcription finalized in {total_process_time}s for {total_audio_duration:.1f}s audio (RTF: {rtf}).")
    return result

@celery_app.task(
    name="transcribe_task",
    bind=True,
    time_limit=1800,
    soft_time_limit=1600
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
    """
    Main entrypoint: Probes audio duration.
    - If audio <= 10 minutes: transcribes directly as a single task.
    - If audio > 10 minutes: slices into ~10-minute chunks and dispatches parallel chunk sub-tasks.
    """
    if model is None:
        load_model()

    task_id = self.request.id
    logger.info(f"Starting orchestrator task {task_id} for input: {file_path or s3_key}")
    start_time = time.time()
    r = get_redis_client()

    # Resolve local audio path (downloads from S3 if needed)
    resolved_local_path = None
    try:
        resolved_local_path = download_audio_file(s3_key or file_path)
    except Exception as dl_err:
        logger.error(f"Failed to resolve audio file for task {task_id}: {dl_err}", exc_info=True)
        failure_payload = {"status": "failed", "error": f"Audio fetch error: {str(dl_err)}", "job_id": task_id}
        r.hset(f"job_state:{task_id}", mapping={"status": "failed", "error": str(dl_err)})
        send_webhook(webhook_url, failure_payload)
        return failure_payload

    # Initialize job state in Redis
    r.hset(f"job_state:{task_id}", mapping={
        "status": "processing",
        "progress": "0.0",
        "start_time": str(start_time),
        "job_id": task_id
    })
    r.publish(f"job_events:{task_id}", json.dumps({"status": "processing", "job_id": task_id, "progress": 0.0}))

    try:
        # Split audio into chunks (or return single chunk if <= 10 min)
        chunks = split_audio_into_chunks(
            file_path=resolved_local_path,
            job_id=task_id,
            target_chunk_seconds=600.0,
            chunk_threshold_seconds=600.0
        )
        total_chunks = len(chunks)

        # Path A: Single chunk (Short audio <= 10 minutes)
        if total_chunks == 1 and chunks[0].get("is_single"):
            logger.info(f"[{task_id}] Short audio path (single chunk, <= 10 minutes).")
            r.hset(f"job_state:{task_id}", mapping={"total_chunks": "1", "completed_chunks": "0"})
            
            # Execute directly in current worker
            transcript, full_text, info = transcribe_audio_segment(
                resolved_local_path,
                vad_filter=vad_filter,
                initial_prompt=initial_prompt,
                language=language
            )

            process_time = round(time.time() - start_time, 2)
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
                "format": output_format
            }

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

            r.hset(f"job_state:{task_id}", mapping={
                "status": "completed",
                "progress": "100.0",
                "result": json.dumps(result)
            })
            r.publish(f"job_events:{task_id}", json.dumps({"status": "completed", "result": result}))

            if webhook_url:
                send_webhook(webhook_url, {"job_id": task_id, "status": "completed", "result": result})

            cleanup_audio_file(resolved_local_path, s3_key=s3_key)
            logger.info(f"[{task_id}] Completed successfully in {process_time}s (Audio: {audio_duration}s, RTF: {rtf})")
            return result

        # Path B: Long audio (> 10 minutes) - Dispatch parallel chunk sub-tasks
        logger.info(f"[{task_id}] Long audio path: Dispatching {total_chunks} chunks to worker pool...")
        r.hset(f"job_state:{task_id}", mapping={
            "total_chunks": str(total_chunks),
            "completed_chunks": "0"
        })

        for chunk_meta in chunks:
            transcribe_chunk_task.apply_async(
                kwargs={
                    "chunk_info": chunk_meta,
                    "job_id": task_id,
                    "vad_filter": vad_filter,
                    "initial_prompt": initial_prompt,
                    "language": language,
                    "output_format": output_format,
                    "webhook_url": webhook_url,
                    "original_audio_path": resolved_local_path,
                    "s3_key": s3_key
                }
            )

        return {
            "status": "processing",
            "job_id": task_id,
            "total_chunks": total_chunks,
            "message": f"Long audio split into {total_chunks} chunks. Transcribing progressively."
        }

    except Exception as e:
        logger.error(f"Error orchestrating task {task_id}: {e}", exc_info=True)
        failure_payload = {"status": "failed", "job_id": task_id, "error": str(e)}
        r.hset(f"job_state:{task_id}", mapping={"status": "failed", "error": str(e)})
        r.publish(f"job_events:{task_id}", json.dumps(failure_payload))
        cleanup_chunk_dir(task_id)
        cleanup_audio_file(resolved_local_path, s3_key=s3_key)
        if webhook_url:
            send_webhook(webhook_url, failure_payload)
        return failure_payload