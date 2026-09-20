FROM python:3.10-slim

# Install system dependencies (ffmpeg is required for Whisper, curl for healthchecks, gcc/python3-dev for builds)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure shared data directory exists with write permissions
RUN mkdir -p /app/data && chmod 777 /app/data

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

