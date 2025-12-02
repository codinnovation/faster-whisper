"""
Celery worker for distributed transcription tasks
Handles long-running Whisper transcription jobs in background
"""
import os
import hashlib
from celery import Celery
from faster_whisper import WhisperModel
from typing import Dict, Any
import json

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_DB = os.getenv("REDIS_DB", "0")
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# Celery app configuration
celery_app = Celery(
    "whisper_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max
    task_soft_time_limit=3300,  # 55 minutes soft limit
    worker_prefetch_multiplier=1,  # Don't prefetch tasks (one at a time)
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks (prevent memory leaks)
)

# Model configuration
MODEL_SIZE = os.getenv("MODEL_SIZE", "base")
DEVICE = os.getenv("DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("COMPUTE_TYPE", "int8")

# Initialize model (loaded once per worker)
model = None

def get_model():
    """Lazy load model to avoid loading in main process"""
    global model
    if model is None:
        model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    return model

def calculate_file_hash(file_path: str) -> str:
    """Calculate SHA256 hash of file for caching"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

@celery_app.task(bind=True, name="transcribe_audio")
def transcribe_audio_task(
    self,
    file_path: str,
    vad_filter: bool = True,
    initial_prompt: str = None,
    language: str = None
) -> Dict[str, Any]:
    """
    Background task for audio transcription
    
    Args:
        file_path: Path to audio file
        vad_filter: Enable voice activity detection
        initial_prompt: Optional prompt for better accuracy
        language: Optional language code
    
    Returns:
        Dict containing transcription results
    """
    try:
        # Update task state
        self.update_state(state='PROCESSING', meta={'status': 'Loading model'})
        
        # Get model instance
        whisper_model = get_model()
        
        # Calculate file hash for potential caching
        file_hash = calculate_file_hash(file_path)
        
        self.update_state(state='PROCESSING', meta={
            'status': 'Transcribing audio',
            'file_hash': file_hash
        })
        
        # Transcribe audio
        segments, info = whisper_model.transcribe(
            file_path,
            beam_size=5,
            vad_filter=vad_filter,
            vad_parameters=dict(min_silence_duration_ms=500),
            initial_prompt=initial_prompt,
            language=language
        )
        
        # Collect results
        transcription_segments = []
        full_text = ""
        
        for segment in segments:
            segment_data = {
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip(),
                "confidence": round(segment.avg_logprob, 2) if hasattr(segment, 'avg_logprob') else None
            }
            transcription_segments.append(segment_data)
            full_text += segment.text.strip() + " "
        
        result = {
            "status": "completed",
            "text": full_text.strip(),
            "segments": transcription_segments,
            "language": info.language,
            "language_probability": round(info.language_probability, 2),
            "duration": round(info.duration, 2),
            "file_hash": file_hash
        }
        
        return result
        
    except Exception as e:
        # Clean error handling
        self.update_state(
            state='FAILURE',
            meta={'status': 'Error', 'error': str(e)}
        )
        raise

@celery_app.task(name="cleanup_old_files")
def cleanup_old_files_task(directory: str, max_age_hours: int = 24):
    """
    Periodic task to cleanup old temporary files
    
    Args:
        directory: Directory to clean
        max_age_hours: Maximum age of files in hours
    """
    import time
    from pathlib import Path
    
    cleaned_count = 0
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    try:
        for file_path in Path(directory).glob("*"):
            if file_path.is_file():
                file_age = current_time - file_path.stat().st_mtime
                if file_age > max_age_seconds:
                    file_path.unlink()
                    cleaned_count += 1
        
        return {"cleaned_files": cleaned_count}
    except Exception as e:
        return {"error": str(e), "cleaned_files": cleaned_count}

# Periodic task schedule (optional - configure via Celery Beat)
celery_app.conf.beat_schedule = {
    'cleanup-temp-files-every-hour': {
        'task': 'cleanup_old_files',
        'schedule': 3600.0,  # Every hour
        'args': ('./uploads', 24)
    },
}
