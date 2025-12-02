from fastapi import FastAPI, UploadFile, File, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import aiofiles
import os
import shutil
import uuid
import time
import redis
from celery.result import AsyncResult
from celery_worker import celery_app, transcribe_audio_task
from prometheus_client import Counter, Histogram, Gauge, generate_latest
import json
from pathlib import Path
from typing import Optional

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Faster Whisper API - Production Scale")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "100"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# Create upload directory
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

# Redis connection for caching
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

# Prometheus metrics
request_counter = Counter('transcription_requests_total', 'Total transcription requests')
request_in_progress = Gauge('transcription_requests_in_progress', 'Requests currently in progress')
request_duration = Histogram('transcription_request_duration_seconds', 'Request duration in seconds')
queue_depth = Gauge('transcription_queue_depth', 'Number of tasks in queue')
cache_hits = Counter('transcription_cache_hits', 'Number of cache hits')
cache_misses = Counter('transcription_cache_misses', 'Number of cache misses')

print("Faster Whisper API initialized in distributed mode")


@app.get("/health")
def health_check():
    """Health check endpoint with Redis and Celery status"""
    try:
        # Check Redis connection
        redis_client.ping()
        redis_ok = True
    except:
        redis_ok = False
    
    # Check Celery workers
    celery_stats = celery_app.control.inspect().stats()
    celery_ok = celery_stats is not None and len(celery_stats) > 0
    
    status = "ok" if redis_ok and celery_ok else "degraded"
    
    return {
        "status": status,
        "redis": "connected" if redis_ok else "disconnected",
        "celery_workers": len(celery_stats) if celery_stats else 0,
        "timestamp": time.time()
    }

@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint"""
    # Update queue depth gauge
    celery_stats = celery_app.control.inspect().active()
    if celery_stats:
        total_active = sum(len(tasks) for tasks in celery_stats.values())
        queue_depth.set(total_active)
    
    return generate_latest()


@app.post("/transcribe")
@limiter.limit("10/minute")  # Rate limit: 10 requests per minute per IP
async def transcribe_audio(
    request: Request,
    file: UploadFile = File(...),
    initial_prompt: Optional[str] = None,
    vad_filter: bool = True,
    language: Optional[str] = None
):
    """
    Submit audio file for transcription (async job-based)
    Returns job_id for status checking
    """
    request_counter.inc()
    request_in_progress.inc()
    
    try:
        # Validate file size
        file_content = await file.read()
        file_size = len(file_content)
        
        if file_size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max size: {MAX_FILE_SIZE_MB}MB"
            )
        
        if file_size == 0:
            raise HTTPException(status_code=400, detail="Empty file uploaded")
        
        # Validate file type
        allowed_extensions = ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.mp4', '.webm']
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
            )
        
        # Generate unique filename
        file_id = str(uuid.uuid4())
        temp_filename = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
        
        # Save file asynchronously
        async with aiofiles.open(temp_filename, 'wb') as f:
            await f.write(file_content)
        
        # Submit to Celery queue
        task = transcribe_audio_task.apply_async(
            args=[temp_filename],
            kwargs={
                'vad_filter': vad_filter,
                'initial_prompt': initial_prompt,
                'language': language
            }
        )
        
        # Store job metadata in Redis
        job_metadata = {
            'job_id': task.id,
            'filename': file.filename,
            'file_size': file_size,
            'submitted_at': time.time(),
            'file_path': temp_filename
        }
        redis_client.setex(
            f"job:{task.id}",
            86400,  # 24 hour expiry
            json.dumps(job_metadata)
        )
        
        return {
            "job_id": task.id,
            "status": "queued",
            "message": "Transcription job submitted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")
    finally:
        request_in_progress.dec()

@app.get("/status/{job_id}")
@limiter.limit("60/minute")  # Higher limit for status checks
async def check_status(request: Request, job_id: str):
    """
    Check transcription job status
    """
    try:
        # Get task result
        task_result = AsyncResult(job_id, app=celery_app)
        
        # Get job metadata from Redis
        metadata_json = redis_client.get(f"job:{job_id}")
        metadata = json.loads(metadata_json) if metadata_json else {}
        
        response = {
            "job_id": job_id,
            "status": task_result.state.lower(),
            "filename": metadata.get('filename', 'unknown')
        }
        
        if task_result.state == 'PENDING':
            response['message'] = 'Job is queued or does not exist'
        elif task_result.state == 'PROCESSING':
            response['message'] = 'Transcription in progress'
            if task_result.info:
                response['info'] = task_result.info
        elif task_result.state == 'SUCCESS':
            response['result'] = task_result.result
            response['message'] = 'Transcription completed'
        elif task_result.state == 'FAILURE':
            response['error'] = str(task_result.info)
            response['message'] = 'Transcription failed'
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking status: {str(e)}")

@app.get("/result/{job_id}")
@limiter.limit("60/minute")
async def get_result(request: Request, job_id: str):
    """
    Get completed transcription result with caching
    """
    try:
        # Check cache first
        cache_key = f"result:{job_id}"
        cached_result = redis_client.get(cache_key)
        
        if cached_result:
            cache_hits.inc()
            return json.loads(cached_result)
        
        cache_misses.inc()
        
        # Get from Celery
        task_result = AsyncResult(job_id, app=celery_app)
        
        if task_result.state != 'SUCCESS':
            raise HTTPException(
                status_code=404,
                detail=f"Result not available. Status: {task_result.state}"
            )
        
        result = task_result.result
        
        # Cache result for 1 hour
        redis_client.setex(cache_key, 3600, json.dumps(result))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving result: {str(e)}")

@app.delete("/job/{job_id}")
@limiter.limit("20/minute")
async def cancel_job(request: Request, job_id: str):
    """
    Cancel a pending or running job
    """
    try:
        task_result = AsyncResult(job_id, app=celery_app)
        
        if task_result.state in ['PENDING', 'PROCESSING']:
            celery_app.control.revoke(job_id, terminate=True)
            
            # Clean up file
            metadata_json = redis_client.get(f"job:{job_id}")
            if metadata_json:
                metadata = json.loads(metadata_json)
                file_path = metadata.get('file_path')
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            
            # Clean up Redis
            redis_client.delete(f"job:{job_id}")
            
            return {"message": "Job cancelled successfully", "job_id": job_id}
        else:
            return {"message": f"Job cannot be cancelled. Status: {task_result.state}"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cancelling job: {str(e)}")

@app.get("/stats")
@limiter.limit("30/minute")
async def get_stats(request: Request):
    """
    Get API statistics and worker status
    """
    try:
        # Celery worker stats
        celery_stats = celery_app.control.inspect().stats()
        active_tasks = celery_app.control.inspect().active()
        
        worker_count = len(celery_stats) if celery_stats else 0
        active_count = sum(len(tasks) for tasks in active_tasks.values()) if active_tasks else 0
        
        # Redis stats
        redis_info = redis_client.info()
        
        return {
            "workers": {
                "count": worker_count,
                "active_tasks": active_count
            },
            "redis": {
                "connected_clients": redis_info.get('connected_clients', 0),
                "used_memory_human": redis_info.get('used_memory_human', 'unknown')
            },
            "upload_dir": {
                "path": UPLOAD_DIR,
                "file_count": len(list(Path(UPLOAD_DIR).glob("*")))
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting stats: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)