from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel
import tempfile
import os
import logging
from typing import Optional
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Faster Whisper API",
    description="Audio transcription API using Faster Whisper",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this based on your needs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration from environment variables
MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")  # tiny, base, small, medium, large-v2, large-v3
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")  # cpu or cuda
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")  # int8, float16, float32

# Initialize Whisper model
logger.info(f"Loading Whisper model: {MODEL_SIZE} on {DEVICE} with {COMPUTE_TYPE}")
try:
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    logger.info("Model loaded successfully")
except Exception as e:
    logger.error(f"Failed to load model: {e}")
    model = None


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Faster Whisper API",
        "version": "1.0.0",
        "status": "running",
        "model": MODEL_SIZE,
        "device": DEVICE,
        "endpoints": {
            "health": "/health",
            "transcribe": "/transcribe",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    return {
        "status": "healthy",
        "model": MODEL_SIZE,
        "device": DEVICE,
        "compute_type": COMPUTE_TYPE
    }


@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    task: str = Form("transcribe"),  # transcribe or translate
    beam_size: int = Form(5),
    vad_filter: bool = Form(True),
    word_timestamps: bool = Form(False)
):
    """
    Transcribe audio file to text
    
    Parameters:
    - file: Audio file (mp3, wav, m4a, etc.)
    - language: Language code (e.g., 'en', 'es', 'fr'). Auto-detect if not provided
    - task: 'transcribe' or 'translate' (translate to English)
    - beam_size: Beam size for decoding (default: 5)
    - vad_filter: Enable voice activity detection (default: True)
    - word_timestamps: Include word-level timestamps (default: False)
    """
    
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    # Save uploaded file temporarily
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name
        
        logger.info(f"Processing file: {file.filename} ({len(content)} bytes)")
        
        # Transcribe
        segments, info = model.transcribe(
            tmp_file_path,
            language=language,
            task=task,
            beam_size=beam_size,
            vad_filter=vad_filter,
            word_timestamps=word_timestamps
        )
        
        # Process segments
        transcription_segments = []
        full_text = []
        
        for segment in segments:
            segment_data = {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip()
            }
            
            if word_timestamps and hasattr(segment, 'words'):
                segment_data["words"] = [
                    {
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                        "probability": word.probability
                    }
                    for word in segment.words
                ]
            
            transcription_segments.append(segment_data)
            full_text.append(segment.text.strip())
        
        # Clean up temporary file
        os.unlink(tmp_file_path)
        
        # Return response
        return JSONResponse({
            "success": True,
            "text": " ".join(full_text),
            "segments": transcription_segments,
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "metadata": {
                "model": MODEL_SIZE,
                "task": task,
                "beam_size": beam_size,
                "vad_filter": vad_filter
            }
        })
        
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        # Clean up temporary file if it exists
        if 'tmp_file_path' in locals() and os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


if __name__ == "__main__":
    # Run the application
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
