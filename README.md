# Faster Whisper API

A production-ready REST API for audio transcription using OpenAI's Whisper model via the faster-whisper library. Optimized for deployment on Coolify.

## 🚀 Features

- **Fast Transcription**: Uses faster-whisper for optimized performance
- **Multiple Languages**: Auto-detect or specify language
- **Translation**: Translate audio to English
- **Timestamps**: Word-level and segment-level timestamps
- **Voice Activity Detection**: Automatic silence removal
- **REST API**: Easy-to-use HTTP endpoints
- **Docker Ready**: Containerized for easy deployment
- **Health Checks**: Built-in monitoring endpoints

## 📋 Prerequisites

- Docker (for deployment)
- Python 3.11+ (for local development)
- Coolify instance (for production deployment)

## 🏃 Quick Start

### Option 1: Deploy to Coolify (Recommended)

1. **Create a new service in Coolify**
   - Go to your Coolify dashboard
   - Click "New Resource" → "Docker Compose" or "Dockerfile"
   - Connect your Git repository

2. **Configure environment variables in Coolify**
   ```
   PORT=8000
   WHISPER_MODEL_SIZE=base
   WHISPER_DEVICE=cpu
   WHISPER_COMPUTE_TYPE=int8
   ```

3. **Set the port**
   - Set the exposed port to `8000`

4. **Deploy**
   - Click "Deploy"
   - Wait for the build to complete (first build takes longer as it downloads the model)

5. **Access your API**
   - Your API will be available at the URL provided by Coolify
   - Visit `/docs` for interactive API documentation

### Option 2: Local Development with Docker

```bash
# Clone the repository
git clone <your-repo-url>
cd faster-whisper

# Build and run with Docker Compose
docker-compose up -d

# Check logs
docker-compose logs -f

# Stop the service
docker-compose down
```

### Option 3: Local Development without Docker

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

## 📡 API Usage

### Health Check
```bash
curl http://localhost:8000/health
```

### Transcribe Audio
```bash
curl -X POST "http://localhost:8000/transcribe" \
  -F "file=@audio.mp3" \
  -F "language=en" \
  -F "task=transcribe"
```

### With Python
```python
import requests

url = "http://localhost:8000/transcribe"
files = {"file": open("audio.mp3", "rb")}
data = {
    "language": "en",  # Optional: auto-detect if not provided
    "task": "transcribe",  # or "translate" to translate to English
    "beam_size": 5,
    "vad_filter": True,
    "word_timestamps": False
}

response = requests.post(url, files=files, data=data)
result = response.json()

print(result["text"])  # Full transcription
print(result["segments"])  # Segments with timestamps
```

### With JavaScript/Node.js
```javascript
const FormData = require('form-data');
const fs = require('fs');
const axios = require('axios');

const form = new FormData();
form.append('file', fs.createReadStream('audio.mp3'));
form.append('language', 'en');
form.append('task', 'transcribe');

axios.post('http://localhost:8000/transcribe', form, {
  headers: form.getHeaders()
})
.then(response => {
  console.log(response.data.text);
})
.catch(error => {
  console.error(error);
});
```

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Server port |
| `WHISPER_MODEL_SIZE` | `base` | Model size: `tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3` |
| `WHISPER_DEVICE` | `cpu` | Device: `cpu` or `cuda` (for GPU) |
| `WHISPER_COMPUTE_TYPE` | `int8` | Compute type: `int8`, `float16`, `float32` |

### Model Sizes

| Model | Parameters | Required VRAM | Relative Speed |
|-------|-----------|---------------|----------------|
| tiny | 39M | ~1 GB | ~32x |
| base | 74M | ~1 GB | ~16x |
| small | 244M | ~2 GB | ~6x |
| medium | 769M | ~5 GB | ~2x |
| large-v2 | 1550M | ~10 GB | 1x |
| large-v3 | 1550M | ~10 GB | 1x |

**Recommendation for Coolify**: Start with `base` model for good balance of speed and accuracy.

## 🔧 Coolify Deployment Guide

### Step-by-Step Instructions

1. **Login to Coolify**
   - Access your Coolify dashboard

2. **Create New Resource**
   - Click "+ New Resource"
   - Select "Public Repository" or connect your private Git repository

3. **Configure Build**
   - **Build Pack**: Dockerfile
   - **Dockerfile Location**: `./Dockerfile`
   - **Port**: `8000`

4. **Environment Variables**
   Add these in the Environment tab:
   ```
   WHISPER_MODEL_SIZE=base
   WHISPER_DEVICE=cpu
   WHISPER_COMPUTE_TYPE=int8
   ```

5. **Resource Allocation**
   - **Memory**: Minimum 2GB RAM (4GB recommended for base model)
   - **CPU**: 1-2 cores recommended
   - **Storage**: 5GB for model cache

6. **Persistent Storage** (Optional but recommended)
   - Add a volume mount for model caching:
   - Mount path: `/root/.cache/huggingface`
   - This prevents re-downloading models on each deployment

7. **Health Check**
   - Path: `/health`
   - Port: `8000`
   - Interval: 30s

8. **Deploy**
   - Click "Deploy"
   - First deployment takes 5-10 minutes (downloading model)
   - Subsequent deployments are faster

9. **Test Your Deployment**
   ```bash
   # Replace with your Coolify URL
   curl https://your-app.coolify.io/health
   ```

10. **Access API Documentation**
    - Visit `https://your-app.coolify.io/docs`
    - Interactive Swagger UI for testing

## 📊 API Endpoints

### `GET /`
Root endpoint with API information

### `GET /health`
Health check endpoint for monitoring

### `POST /transcribe`
Transcribe audio file

**Parameters:**
- `file` (required): Audio file (mp3, wav, m4a, flac, etc.)
- `language` (optional): Language code (e.g., 'en', 'es', 'fr')
- `task` (optional): 'transcribe' or 'translate' (default: 'transcribe')
- `beam_size` (optional): Beam size for decoding (default: 5)
- `vad_filter` (optional): Enable VAD (default: true)
- `word_timestamps` (optional): Include word timestamps (default: false)

**Response:**
```json
{
  "success": true,
  "text": "Full transcription text",
  "segments": [
    {
      "start": 0.0,
      "end": 2.5,
      "text": "Segment text"
    }
  ],
  "language": "en",
  "language_probability": 0.99,
  "duration": 10.5,
  "metadata": {
    "model": "base",
    "task": "transcribe",
    "beam_size": 5,
    "vad_filter": true
  }
}
```

## 🎯 Supported Audio Formats

- MP3
- WAV
- M4A
- FLAC
- OGG
- WEBM
- And more (anything FFmpeg supports)

## 🌍 Supported Languages

Whisper supports 99+ languages including:
- English (en)
- Spanish (es)
- French (fr)
- German (de)
- Chinese (zh)
- Japanese (ja)
- And many more...

Leave `language` parameter empty for auto-detection.

## 🐛 Troubleshooting

### Docker Build Fails with ffmpeg Installation

**Problem**: Build fails with "exit code: 1" during ffmpeg installation or takes extremely long.

**Solution**: The Dockerfile has been optimized to use `--no-install-recommends` which prevents installing 277 unnecessary GUI packages. If you still have issues:

1. **Use the minimal Dockerfile**:
   ```bash
   # In Coolify, change Dockerfile location to:
   ./Dockerfile.minimal
   ```

2. **Or build locally first** to test:
   ```bash
   docker build -t faster-whisper-test .
   ```

3. **Check Coolify logs** for the specific error and increase build timeout if needed.

### Model not loading
- Check memory allocation (minimum 2GB for base model)
- Verify environment variables are set correctly
- Check logs: `docker-compose logs -f`

### Slow transcription
- Use smaller model (`tiny` or `base`)
- Enable VAD filter to skip silence
- Consider GPU deployment for faster processing

### Out of memory
- Reduce model size
- Increase container memory limit
- Use `int8` compute type

### Connection refused
- Verify port 8000 is exposed
- Check firewall settings
- Ensure health check is passing

## 📈 Performance Tips

1. **Use VAD Filter**: Automatically removes silence, speeds up processing
2. **Choose Right Model**: Balance accuracy vs speed based on your needs
3. **Cache Models**: Use persistent storage to avoid re-downloading
4. **Batch Processing**: Process multiple files sequentially
5. **GPU Acceleration**: Use CUDA for 2-3x speed improvement

## 🔒 Security Considerations

- Add authentication middleware for production
- Limit file upload size (default: 100MB)
- Implement rate limiting
- Use HTTPS in production
- Validate file types before processing

## 📝 License

MIT License - feel free to use in your projects!

## 🤝 Support

For issues or questions:
1. Check the `/docs` endpoint for API documentation
2. Review logs: `docker-compose logs -f`
3. Verify environment variables
4. Check Coolify deployment logs

## 🎉 You're All Set!

Your Faster Whisper API is ready to use. Visit `/docs` for interactive API documentation and testing.
