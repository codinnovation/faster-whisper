# Installation Guide

## Step-by-Step Setup

### 1. Install Dependencies

First, activate your virtual environment and install all dependencies:

```powershell
cd "D:\CODE - REPO\faster-whisper"
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

This will install:
- faster-whisper (core ML model)
- fastapi + uvicorn (web framework)
- celery + redis (task queue)
- slowapi (rate limiting)
- aiofiles (async I/O)
- prometheus-client (metrics)
- flower (monitoring)

### 2. Start Redis Server

**Option A: Using Docker (Recommended)**
```powershell
docker run -d -p 6379:6379 --name whisper-redis redis:7-alpine
```

**Option B: Install Redis locally**
- Download from: https://github.com/microsoftarchive/redis/releases
- Or use WSL: `wsl sudo service redis-server start`

**Verify Redis is running:**
```powershell
# Test connection
docker exec whisper-redis redis-cli ping
# Should return: PONG
```

### 3. Start Celery Worker

Open a **new terminal** and run:

```powershell
cd "D:\CODE - REPO\faster-whisper"
.\venv\Scripts\Activate.ps1
celery -A celery_worker worker --loglevel=info --concurrency=2 --pool=solo
```

**Note**: Use `--pool=solo` on Windows. For Linux/Mac, you can use the default pool.

You should see:
```
[INFO/MainProcess] Connected to redis://localhost:6379/0
[INFO/MainProcess] mingle: searching for neighbors
[INFO/MainProcess] mingle: all alone
[INFO/MainProcess] celery@hostname ready.
```

### 4. Start API Server

Open **another new terminal** and run:

```powershell
cd "D:\CODE - REPO\faster-whisper"
.\venv\Scripts\Activate.ps1
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### 5. Test the API

Open **another terminal** and test:

```powershell
# Health check
curl http://localhost:8000/health

# Stats
curl http://localhost:8000/stats

# Submit a transcription job (replace with your audio file)
curl -X POST "http://localhost:8000/transcribe" -F "file=@sample_audio.mp3"
```

Expected response:
```json
{
  "job_id": "abc123-def456-...",
  "status": "queued",
  "message": "Transcription job submitted successfully"
}
```

### 6. Check Job Status

```powershell
# Replace JOB_ID with the actual job_id from step 5
curl http://localhost:8000/status/JOB_ID
```

### 7. Get Result

```powershell
curl http://localhost:8000/result/JOB_ID
```

---

## Troubleshooting

### Issue: ModuleNotFoundError
**Solution**: Make sure you installed all dependencies:
```powershell
pip install -r requirements.txt
```

### Issue: Cannot connect to Redis
**Error**: `ConnectionError: Error 10061 connecting to localhost:6379`

**Solution**: Make sure Redis is running:
```powershell
docker ps | Select-String whisper-redis
```

If not running:
```powershell
docker start whisper-redis
```

### Issue: Celery worker not starting on Windows
**Error**: `ValueError: not enough values to unpack`

**Solution**: Use the `--pool=solo` flag:
```powershell
celery -A celery_worker worker --loglevel=info --concurrency=2 --pool=solo
```

### Issue: Port 8000 already in use
**Solution**: Kill the process or use a different port:
```powershell
# Use different port
uvicorn api:app --reload --host 0.0.0.0 --port 8001

# Or kill existing process
netstat -ano | Select-String ":8000"
# Find the PID and kill it
taskkill /PID <PID> /F
```

### Issue: File upload fails
**Error**: `413 File too large`

**Solution**: Increase MAX_FILE_SIZE_MB in .env or environment:
```powershell
$env:MAX_FILE_SIZE_MB = "200"
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

### Issue: Worker crashes during transcription
**Error**: Out of memory

**Solution**: Use smaller model or reduce concurrency:
```powershell
# Use smaller model
$env:MODEL_SIZE = "tiny"

# Reduce concurrency
celery -A celery_worker worker --loglevel=info --concurrency=1 --pool=solo
```

---

## Using Docker Compose (Production)

For production deployment, use Docker Compose:

### 1. Build and Start
```powershell
docker-compose up -d --build
```

### 2. Check Status
```powershell
docker-compose ps
```

### 3. View Logs
```powershell
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f worker
```

### 4. Scale Workers
```powershell
docker-compose up -d --scale worker=5
```

### 5. Test
```powershell
curl http://localhost/health
```

### 6. Access Monitoring
- **API**: http://localhost
- **Flower**: http://localhost:5555
- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090

### 7. Stop Services
```powershell
docker-compose down
```

---

## Environment Variables

Create a `.env` file in the project root:

```bash
# Model Configuration
MODEL_SIZE=base
DEVICE=cpu
COMPUTE_TYPE=int8

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# API Configuration
UPLOAD_DIR=./uploads
MAX_FILE_SIZE_MB=100
WORKERS=4
```

---

## Verification Checklist

- [ ] Python 3.10+ installed
- [ ] Virtual environment activated
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Redis server running
- [ ] Celery worker running
- [ ] API server running
- [ ] Health check returns "ok"
- [ ] Can submit transcription job
- [ ] Can check job status
- [ ] Can retrieve result

---

## Next Steps

1. **Test with real audio files**
   - Place audio files in the project directory
   - Submit transcription jobs
   - Monitor progress in Celery worker logs

2. **Enable monitoring**
   - Access Flower: http://localhost:5555 (if using Docker Compose)
   - Check metrics: http://localhost:8000/metrics

3. **Scale for production**
   - Use Docker Compose for multi-worker setup
   - Configure Nginx load balancing
   - Set up Prometheus + Grafana monitoring

4. **Optimize performance**
   - Enable GPU if available (`DEVICE=cuda`)
   - Adjust worker concurrency
   - Tune rate limiting
   - Configure caching

---

## Common Commands

### Start Services (Local)
```powershell
# Terminal 1: Redis
docker run -d -p 6379:6379 --name whisper-redis redis:7-alpine

# Terminal 2: Celery
.\venv\Scripts\Activate.ps1
celery -A celery_worker worker --loglevel=info --concurrency=2 --pool=solo

# Terminal 3: API
.\venv\Scripts\Activate.ps1
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

### Stop Services (Local)
```powershell
# Stop API: Ctrl+C in terminal
# Stop Celery: Ctrl+C in terminal
# Stop Redis:
docker stop whisper-redis
```

### Start Services (Docker Compose)
```powershell
docker-compose up -d
```

### Stop Services (Docker Compose)
```powershell
docker-compose down
```

---

## Support

If you encounter issues:
1. Check the logs in each terminal
2. Verify Redis connection: `docker exec whisper-redis redis-cli ping`
3. Check Celery worker status in Flower (if using Docker Compose)
4. Review error messages in the API response
5. Consult [DEPLOYMENT.md](DEPLOYMENT.md) for detailed documentation
