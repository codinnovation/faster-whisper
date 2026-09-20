import os
import time
import uuid
import secrets
import asyncio
import aiofiles
import logging
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Security, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from celery.result import AsyncResult
import redis.asyncio as aioredis
from worker import celery_app, transcribe_task
from storage import is_s3_enabled, generate_presigned_upload_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [pid:%(process)d] %(message)s"
)
logger = logging.getLogger("api")

app = FastAPI(
    title="Faster Whisper API (Async & High Scale)",
    version="2.1.0",
    description="High-availability asynchronous transcription service supporting 1000+ concurrent users."
)
security = HTTPBearer()

# Configuration
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/data")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
API_SECRET = os.getenv("API_SECRET")
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "100"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
MAX_QUEUE_DEPTH = int(os.getenv("MAX_QUEUE_DEPTH", "1000"))
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".webm", ".wma"}

os.makedirs(UPLOAD_DIR, exist_ok=True)

# Async Redis connection for pub/sub, rate limiting, and health checks
redis_async_client = aioredis.from_url(REDIS_URL, decode_responses=True)

# Security Dependency with Constant-Time Comparison
async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    expected_token = os.getenv("API_SECRET")

    if not expected_token:
        logger.warning("SECURITY WARNING: API_SECRET not set in environment. Allowing request.")
        return token

    # secrets.compare_digest prevents timing attacks
    if not secrets.compare_digest(token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )

    # Sliding window rate limiter per token
    if RATE_LIMIT_PER_MINUTE > 0:
        minute_bucket = int(time.time() // 60)
        rate_key = f"rate_limit:{token[:12]}:{minute_bucket}"
        current_count = await redis_async_client.incr(rate_key)
        if current_count == 1:
            await redis_async_client.expire(rate_key, 65)
        if current_count > RATE_LIMIT_PER_MINUTE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {RATE_LIMIT_PER_MINUTE} requests per minute."
            )

    return token

@app.get("/health")
async def health_check():
    """Non-blocking health check. Avoids broadcast pings to Celery workers."""
    try:
        await redis_async_client.ping()
        redis_status = "connected"
    except Exception as e:
        logger.error(f"Health check Redis ping failed: {e}")
        redis_status = f"unhealthy: {str(e)}"

    queue_depth = 0
    try:
        queue_depth = await redis_async_client.llen("celery")
    except Exception:
        pass

    is_healthy = redis_status == "connected"
    return {
        "status": "ok" if is_healthy else "degraded",
        "mode": "async",
        "redis": redis_status,
        "queue_depth": queue_depth,
        "s3_storage": is_s3_enabled()
    }

@app.post("/transcribe/upload-url", dependencies=[Depends(verify_token)])
@app.get("/transcribe/upload-url", dependencies=[Depends(verify_token)])
async def get_presigned_upload_url(filename: str = "audio.mp3", content_type: str = "audio/mpeg"):
    """
    Returns an S3 Presigned Upload URL for direct client-to-storage upload.
    Bypasses API server network bandwidth and disk entirely.
    """
    if not is_s3_enabled():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="S3 storage is not configured on this server. Use multipart direct upload."
        )

    try:
        upload_url, file_key = generate_presigned_upload_url(filename=filename, content_type=content_type)
        return {
            "upload_url": upload_url,
            "file_key": file_key,
            "expires_in_seconds": 3600,
            "message": "Upload file to upload_url via HTTP PUT, then pass file_key to /transcribe."
        }
    except Exception as e:
        logger.error(f"Failed to generate presigned upload URL: {e}")
        raise HTTPException(status_code=500, detail=f"Presigned URL generation failed: {str(e)}")

@app.post("/transcribe", dependencies=[Depends(verify_token)])
async def transcribe_audio(
    file: UploadFile = File(None),
    s3_key: str = Form(None),
    webhook_url: str = Form(None),
    initial_prompt: str = Form(None),
    vad_filter: bool = Form(True),
    language: str = Form(None),
    output_format: str = Form("json")
):
    # Check queue backpressure
    try:
        current_queue = await redis_async_client.llen("celery")
        if current_queue >= MAX_QUEUE_DEPTH:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Transcription queue capacity reached ({current_queue} jobs). Please retry shortly."
            )
    except HTTPException:
        raise
    except Exception as q_err:
        logger.warning(f"Could not check queue depth: {q_err}")

    # Ensure either file or s3_key is supplied
    if not file and not s3_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either a multipart 'file' or an 's3_key' must be provided."
        )

    job_id = str(uuid.uuid4())
    file_path = None

    # Path A: Direct file upload
    if file:
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported audio format '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )

        safe_filename = f"{job_id}{ext}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)

        try:
            bytes_written = 0
            max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024

            async with aiofiles.open(file_path, "wb") as buffer:
                while chunk := await file.read(1024 * 1024):
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"Audio file exceeds maximum size limit of {MAX_FILE_SIZE_MB}MB"
                        )
                    await buffer.write(chunk)
        except HTTPException:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            raise
        except Exception as e:
            logger.error(f"Upload write error for job {job_id}: {e}", exc_info=True)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            raise HTTPException(status_code=500, detail=f"Failed to save audio file: {str(e)}")

    # Enqueue task to Celery with explicit job_id
    transcribe_task.apply_async(
        args=[file_path, vad_filter, initial_prompt, language, output_format, webhook_url, s3_key],
        task_id=job_id
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Transcription started. Connect to stream_url, poll /status/{job_id}, or await webhook.",
        "stream_url": f"/jobs/{job_id}/events",
        "webhook_url": webhook_url
    }


@app.get("/status/{job_id}", dependencies=[Depends(verify_token)])
async def get_status(job_id: str):
    """Polling status endpoint (maintained for 100% backward compatibility)."""
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
            return {"job_id": job_id, "status": task_result.state.lower()}
    except Exception as e:
        logger.error(f"Status check error for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Status Check Error: {str(e)}")

@app.get("/jobs/{job_id}/events", dependencies=[Depends(verify_token)])
async def stream_job_events(job_id: str):
    """
    Server-Sent Events (SSE) push endpoint.
    Eliminates client polling by streaming status updates in real time via Redis Pub/Sub.
    """
    async def event_generator():
        # Check if already completed before subscribing
        task_result = AsyncResult(job_id, app=celery_app)
        if task_result.state == 'SUCCESS':
            import json
            yield f"data: {json.dumps({'status': 'completed', 'result': task_result.result})}\n\n"
            return
        elif task_result.state == 'FAILURE':
            import json
            yield f"data: {json.dumps({'status': 'failed', 'error': str(task_result.result)})}\n\n"
            return

        pubsub = redis_async_client.pubsub()
        channel = f"job_events:{job_id}"
        await pubsub.subscribe(channel)

        yield f"data: {{\"status\": \"subscribed\", \"job_id\": \"{job_id}\"}}\n\n"

        try:
            # 10 minute timeout on subscription
            async with asyncio.timeout(600):
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        data = message["data"]
                        yield f"data: {data}\n\n"
                        # Terminate SSE stream if final event received
                        if '"completed"' in data or '"failed"' in data:
                            break
        except asyncio.TimeoutError:
            yield "data: {\"status\": \"timeout\", \"message\": \"Stream timed out after 10 minutes\"}\n\n"
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=4001)