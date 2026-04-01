import os
import time
from celery import Celery
from faster_whisper import WhisperModel

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
MODEL_SIZE = os.getenv("MODEL_SIZE", "base")
DEVICE = os.getenv("DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("COMPUTE_TYPE", "int8")
CPU_THREADS = int(os.getenv("CPU_THREADS", "4"))

# Initialize Celery
celery_app = Celery("transcriber", broker=REDIS_URL, backend=REDIS_URL)

# Configure for high load
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    result_expires=3600,  # Results expire after 1 hour
    worker_prefetch_multiplier=1,  # Fair distribution
    broker_connection_retry_on_startup=True,
)

# Global model variable
model = None

def load_model():
    global model
    if model is None:
        print(f"Loading model: {MODEL_SIZE} on {DEVICE} with {COMPUTE_TYPE}...")
        try:
            model = WhisperModel(
                MODEL_SIZE, 
                device=DEVICE, 
                compute_type=COMPUTE_TYPE,
                cpu_threads=CPU_THREADS,
                num_workers=1
            )
            print("Model loaded successfully.")
        except Exception as e:
            print(f"CRITICAL ERROR: Could not load model: {e}")
            raise e

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

@celery_app.task(name="transcribe_task", bind=True)
def transcribe_task(self, file_path, vad_filter=True, initial_prompt=None, language=None, output_format="json"):
    # Ensure model is loaded
    if model is None:
        load_model()

    try:
        print(f"Starting transcription for {file_path}")
        start_time = time.time()
        
        segments, info = model.transcribe(
            file_path, 
            beam_size=1,                      # FASTER: was 5, now takes best guess immediately
            best_of=1,                         # FASTER: was 5, no longer explores multiple candidates
            temperature=0,                     # FASTER: skips internal retry/fallback logic
            condition_on_previous_text=False,  # FASTER: no longer feeds previous text as context
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
        full_text = ""
        for segment in segments:
            segment_data = {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip()
            }
            
            transcript.append(segment_data)
            full_text += segment.text + " "
            
        process_time = time.time() - start_time
        
        # Clean up the file after processing
        if os.path.exists(file_path):
            os.remove(file_path)

        result = {
            "status": "completed",
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "process_time": process_time,
        }

        # Format output
        if output_format == "srt":
            result["text"] = generate_srt(transcript)
            result["format"] = "srt"
        elif output_format == "vtt":
            result["text"] = generate_vtt(transcript)
            result["format"] = "vtt"
        elif output_format == "txt":
            result["text"] = full_text.strip()
            result["format"] = "txt"
        else:
            result["text"] = full_text.strip()
            result["segments"] = transcript
            result["format"] = "json"
            
        return result

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return {"status": "failed", "error": str(e)}