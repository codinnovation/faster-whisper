import os
import time
from celery import Celery
from faster_whisper import WhisperModel

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
MODEL_SIZE = os.getenv("MODEL_SIZE", "base")
DEVICE = os.getenv("DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("COMPUTE_TYPE", "int8")

# Initialize Celery
celery_app = Celery("transcriber", broker=REDIS_URL, backend=REDIS_URL)

# Global model variable
model = None

def load_model():
    global model
    if model is None:
        print(f"Loading model: {MODEL_SIZE} on {DEVICE} with {COMPUTE_TYPE}...")
        try:
            model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
            print("Model loaded successfully.")
        except Exception as e:
            print(f"CRITICAL ERROR: Could not load model: {e}")
            raise e

@celery_app.task(name="transcribe_task", bind=True)
def transcribe_task(self, file_path, vad_filter=True, initial_prompt=None, language=None):
    # Ensure model is loaded
    if model is None:
        load_model()

    try:
        print(f"Starting transcription for {file_path}")
        start_time = time.time()
        
        segments, info = model.transcribe(
            file_path, 
            beam_size=5,
            vad_filter=vad_filter,
            vad_parameters=dict(min_silence_duration_ms=500),
            initial_prompt=initial_prompt,
            language=language
        )
        
        transcript = []
        full_text = ""
        for segment in segments:
            transcript.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip()
            })
            full_text += segment.text + " "
            
        process_time = time.time() - start_time
        
        # Clean up the file after processing
        if os.path.exists(file_path):
            os.remove(file_path)

        return {
            "status": "completed",
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "process_time": process_time,
            "text": full_text.strip(),
            "segments": transcript
        }

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return {"status": "failed", "error": str(e)}
