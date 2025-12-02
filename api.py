from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from celery.result import AsyncResult
from worker import celery_app, transcribe_task
import os
import shutil
import uuid

app = FastAPI(title="Faster Whisper API (Async)")

# Directory for shared storage
UPLOAD_DIR = "/app/data"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.get("/health")
def health_check():
    # Check Redis connection
    try:
        # Ping workers to see if any are alive
        ping = celery_app.control.ping(timeout=0.5)
        redis_status = "connected" if ping else "waiting_for_workers"
    except Exception as e:
        redis_status = f"error: {str(e)}"
        
    return {"status": "ok", "mode": "async", "redis": redis_status}

@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    initial_prompt: str = None,
    vad_filter: bool = True
):
    # Create a unique filename
    filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    try:
        # Save uploaded file to shared volume
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Push task to Celery
        task = transcribe_task.delay(file_path, vad_filter, initial_prompt)
        
        return {
            "job_id": task.id,
            "status": "queued",
            "message": "Transcription started. Poll /status/{job_id} for results."
        }

    except Exception as e:
        # Log the full error to stdout so it shows in Docker logs
        print(f"TRANSCRIPTION ERROR: {str(e)}")
        
        # Clean up if save failed
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
                
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    try:
        task_result = AsyncResult(job_id, app=celery_app)
        
        if task_result.state == 'PENDING':
            return {"job_id": job_id, "status": "pending"}
        elif task_result.state == 'STARTED':
            return {"job_id": job_id, "status": "processing"}
        elif task_result.state == 'SUCCESS':
            return {"job_id": job_id, "status": "completed", "result": task_result.result}
        elif task_result.state == 'FAILURE':
            return {"job_id": job_id, "status": "failed", "error": str(task_result.result)}
        else:
            return {"job_id": job_id, "status": task_result.state}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Status Check Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)