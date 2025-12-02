# Quick Start Commands

## Local Development

### Start Redis
```powershell
docker run -d -p 6379:6379 --name whisper-redis redis:7-alpine
```

### Activate Virtual Environment
```powershell
cd "D:\CODE - REPO\faster-whisper"
.\venv\Scripts\Activate.ps1
```

### Install Dependencies
```powershell
pip install -r requirements.txt
```

### Start Celery Worker
```powershell
celery -A celery_worker worker --loglevel=info --concurrency=2 --pool=solo
```

### Start API Server (in new terminal)
```powershell
.\venv\Scripts\Activate.ps1
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

### Test the API
```powershell
# Health check
curl http://localhost:8000/health

# Stats
curl http://localhost:8000/stats

# Submit transcription (replace with your audio file)
curl -X POST "http://localhost:8000/transcribe" -F "file=@audio.mp3"
```

---

## Production Deployment (Docker Compose)

### Build and Start All Services
```powershell
docker-compose up -d --build
```

### Scale Workers
```powershell
# Scale to 5 workers
docker-compose up -d --scale worker=5

# Scale to 10 workers
docker-compose up -d --scale worker=10
```

### View Logs
```powershell
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f worker
docker-compose logs -f api
```

### Check Service Status
```powershell
docker-compose ps
```

### Stop Services
```powershell
docker-compose down
```

### Clean Everything (including volumes)
```powershell
docker-compose down -v
```

---

## Monitoring

### Access Monitoring Tools
- **API**: http://localhost:8000 or http://localhost (via Nginx)
- **Flower** (Celery Monitor): http://localhost:5555
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)

### API Endpoints
```powershell
# Health check
curl http://localhost/health

# Statistics
curl http://localhost/stats

# Metrics (Prometheus format)
curl http://localhost/metrics

# Submit job
curl -X POST "http://localhost/transcribe" -F "file=@audio.mp3"

# Check status (replace JOB_ID)
curl http://localhost/status/JOB_ID

# Get result (replace JOB_ID)
curl http://localhost/result/JOB_ID
```

---

## Configuration

### Environment Variables
Edit `.env` file or set in docker-compose.yml:

```bash
MODEL_SIZE=base        # tiny, base, small, medium, large-v3
DEVICE=cpu             # cpu or cuda
COMPUTE_TYPE=int8      # int8, float16, float32
MAX_FILE_SIZE_MB=100
WORKERS=4              # API worker processes
```

### GPU Support
```yaml
# In docker-compose.yml, add to worker service:
worker:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

---

## Troubleshooting

### Check Redis Connection
```powershell
docker-compose exec redis redis-cli ping
# Should return: PONG
```

### Check Celery Workers
```powershell
docker-compose exec api celery -A celery_worker inspect active
```

### View Worker Logs
```powershell
docker-compose logs -f worker
```

### Restart Services
```powershell
docker-compose restart worker
docker-compose restart api
```

### Clear Redis Cache
```powershell
docker-compose exec redis redis-cli FLUSHALL
```

---

## Performance Tips

### For 5000+ Users
1. **Scale workers**: `docker-compose up -d --scale worker=10`
2. **Use GPU**: Set `DEVICE=cuda` in .env
3. **Increase API workers**: Set `WORKERS=8` in .env
4. **Add more API instances**: Uncomment additional api servers in nginx.conf
5. **Monitor**: Watch Flower dashboard for bottlenecks

### Optimal Configuration
- **CPU-only**: 10-15 workers, base/small model
- **With GPU**: 3-5 workers per GPU, medium/large model
- **Memory**: 2GB per worker minimum
- **Redis**: 4-8GB memory allocation

---

## Load Testing

### Using Apache Bench
```powershell
ab -n 1000 -c 100 http://localhost/health
```

### Using Python Client
```powershell
python example_client.py
```

---

## Backup and Maintenance

### Backup Redis Data
```powershell
docker-compose exec redis redis-cli SAVE
docker cp whisper-redis:/data/dump.rdb ./backup/
```

### Cleanup Old Files
Files are auto-cleaned every hour by Celery Beat.
Manual cleanup:
```powershell
docker-compose exec api python -c "from celery_worker import cleanup_old_files_task; cleanup_old_files_task('./uploads', 24)"
```

---

## Security Checklist

- [ ] Change Grafana admin password
- [ ] Enable Redis password (update redis config)
- [ ] Configure CORS properly (not `*`)
- [ ] Add API authentication
- [ ] Enable HTTPS (add SSL to Nginx)
- [ ] Protect /metrics endpoint
- [ ] Set up firewall rules
- [ ] Regular dependency updates
