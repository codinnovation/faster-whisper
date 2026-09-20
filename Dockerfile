FROM python:3.10-slim

# Install system dependencies (ffmpeg is required for Whisper, curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create unprivileged user and ensure shared storage folder permissions
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app /home/appuser

USER appuser

# Default environment variables
ENV MODEL_SIZE=base
ENV DEVICE=cpu
ENV COMPUTE_TYPE=int8
ENV PORT=4001
ENV WORKERS=4

# Expose API port
EXPOSE 4001

# Production command: Gunicorn managing UvicornWorker processes
CMD ["sh", "-c", "gunicorn api:app --workers ${WORKERS:-4} --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-4001} --timeout 120 --keep-alive 5 --access-logfile - --error-logfile -"]

