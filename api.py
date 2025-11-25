from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel
import os
import shutil
import uuid
import time

app = FastAPI(title="Faster Whisper API")

# Configuration via Environment Variables
MODEL_SIZE = os.getenv("MODEL_SIZE", "base")
DEVICE = os.getenv("DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("COMPUTE_TYPE", "int8")

print(f"Loading model: {MODEL_SIZE} on {DEVICE} with {COMPUTE_TYPE}...")
try:
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    print("Model loaded successfully.")
except Exception as e:
    print(f"CRITICAL ERROR: Could not load model: {e}")
    model = None

@app.get("/health")
def health_check():
    if model is None:
        return JSONResponse(status_code=503, content={"status": "error", "message": "Model not loaded"})
    return {"status": "ok", "model": MODEL_SIZE, "device": DEVICE}

@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    initial_prompt: str = None,
    vad_filter: bool = True
):
    if model is None:
        raise HTTPException(status_code=503, detail="Model is not loaded")

    # Create a temporary file
    temp_filename = f"temp_{uuid.uuid4()}_{file.filename}"
    
    try:
        # Save uploaded file
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        start_time = time.time()
        
        # Transcribe
        # vad_filter=True is CRITICAL for classrooms to ignore background noise/silence
        segments, info = model.transcribe(
            temp_filename, 
            beam_size=5,
            vad_filter=vad_filter,
            min_silence_duration_ms=500,
            initial_prompt=initial_prompt
        )
        
        # Collect results
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
        
        return {
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "process_time": process_time,
            "text": full_text.strip(),
            "segments": transcript
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # Clean up
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
