from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel
import tempfile
import os
import logging
from typing import Optional
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Faster Whisper API", version="1.0.0")

# Initialize model at startup
logger.info("Loading Whisper model...")
model = WhisperModel("base", device="cpu", compute_type="int8")
logger.info("Model loaded successfully!")

class TranscriptionResponse(BaseModel):
    text: str
    segments: list
    language: str
    duration: float

@app.get("/")
def read_root():
    return {"message": "Faster Whisper API is running!", "endpoints": ["/transcribe", "/health"]}

@app.get("/health")
def health_check():
    return {"status": "healthy", "model": "base", "device": "cpu"}

@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = None,
    task: Optional[str] = "transcribe"
):
    # Validate file type
    allowed_extensions = ['.wav', '.mp3', '.m4a', '.flac', '.opus', '.ogg', '.webm']
    file_extension = os.path.splitext(file.filename)[1].lower()
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed types: {', '.join(allowed_extensions)}"
        )
    
    # Save uploaded file temporarily
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        logger.info(f"Processing file: {file.filename}")
        
        # Transcribe with faster-whisper
        segments, info = model.transcribe(
            tmp_path,
            beam_size=5,
            language=language,
            task=task,
            vad_filter=True,  # Voice activity detection
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        
        # Collect all segments
        segment_list = []
        full_text = []
        
        for segment in segments:
            seg_dict = {
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip()
            }
            segment_list.append(seg_dict)
            full_text.append(segment.text.strip())
        
        # Prepare response
        response = TranscriptionResponse(
            text=" ".join(full_text),
            segments=segment_list,
            language=info.language,
            duration=round(info.duration, 2)
        )
        
        logger.info(f"Transcription completed. Language: {info.language}, Duration: {info.duration}s")
        
        return response
        
    except Exception as e:
        logger.error(f"Error during transcription: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    
    finally:
        # Clean up temporary file
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)

@app.post("/transcribe-url")
async def transcribe_from_url(url: str, language: Optional[str] = None):
    """Transcribe audio from a URL"""
    # This is a placeholder - you can implement URL downloading if needed
    return {"message": "URL transcription not implemented yet", "url": url}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)