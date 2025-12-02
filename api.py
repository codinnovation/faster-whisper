from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel
import os
import shutil
import uuid
import time
import asyncio
import concurrent.futures

app = FastAPI(title="Faster Whisper API")

# Configuration via Environment Variables
MODEL_SIZE = os.getenv("MODEL_SIZE", "base")
DEVICE = os.getenv("DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("COMPUTE_TYPE", "int8")
# Limit concurrent transcriptions to prevent OOM. 
# On CPU, 2-4 is reasonable. On GPU, usually 1-2 per GPU depending on VRAM.
MAX_CONCURRENT_TRANSCRIPTIONS = int(os.getenv("MAX_CONCURRENT_TRANSCRIPTIONS", "2"))

print(f"Loading model: {MODEL_SIZE} on {DEVICE} with {COMPUTE_TYPE}...")
try:
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    print("Model loaded successfully.")
except Exception as e:
    print(f"CRITICAL ERROR: Could not load model: {e}")
    model = None

# Concurrency Control
transcription_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TRANSCRIPTIONS)
# Thread pool for offloading blocking inference
executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TRANSCRIPTIONS)

@app.get("/health")
def health_check():
    if model is None:
        return JSONResponse(status_code=503, content={"status": "error", "message": "Model not loaded"})
    
    # Check if we have available slots
    if transcription_semaphore.locked():
        return JSONResponse(
            status_code=503, 
            content={
                "status": "busy", 
                "message": "Server is at maximum capacity",
                "active_jobs": MAX_CONCURRENT_TRANSCRIPTIONS
            }
        )
        
    return {"status": "ok", "model": MODEL_SIZE, "device": DEVICE}

def run_transcription(temp_filename, vad_filter, initial_prompt):
    """
    Blocking function to run transcription and consume the generator.
    Must be run in a separate thread.
    """
    segments, info = model.transcribe(
        temp_filename, 
        beam_size=5,
        vad_filter=vad_filter,
        vad_parameters=dict(min_silence_duration_ms=500),
        initial_prompt=initial_prompt
    )
    
    # Consume the generator to ensure inference happens here
    transcript = []
    full_text = ""
    for segment in segments:
        transcript.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip()
        })
        full_text += segment.text + " "
        
    return transcript, full_text.strip(), info

@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    initial_prompt: str = None,
    vad_filter: bool = True
):
    if model is None:
        raise HTTPException(status_code=503, detail="Model is not loaded")

    # Fail fast if server is busy
    if transcription_semaphore.locked():
        raise HTTPException(
            status_code=503, 
            detail="Server is busy. Please try again later."
        )

    # Create a temporary file
    temp_filename = f"temp_{uuid.uuid4()}_{file.filename}"
    
    try:
        # Save uploaded file
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        start_time = time.time()
        
        # Acquire semaphore to track active jobs
        async with transcription_semaphore:
            loop = asyncio.get_running_loop()
            # Run the blocking transcription in a separate thread
            transcript, full_text, info = await loop.run_in_executor(
                executor,
                run_transcription,
                temp_filename,
                vad_filter,
                initial_prompt
            )
            
        process_time = time.time() - start_time
        
        return {
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "process_time": process_time,
            "text": full_text,
            "segments": transcript
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # Clean up
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except:
                pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)