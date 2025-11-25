# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install only essential system dependencies
# Install ffmpeg-related libraries without GUI dependencies
# Also install build tools needed for PyAV compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    pkg-config \
    gcc \
    python3-dev \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libavdevice-dev \
    libavfilter-dev \
    libswscale-dev \
    libswresample-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV WHISPER_MODEL_SIZE=base
ENV WHISPER_DEVICE=cpu
ENV WHISPER_COMPUTE_TYPE=int8
ENV DEBIAN_FRONTEND=noninteractive

# Expose port
EXPOSE 8000

# Health check (using a simpler method that doesn't require requests library)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the application
CMD ["python", "app.py"]
