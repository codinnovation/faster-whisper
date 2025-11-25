# Faster Whisper API Documentation

This API provides a simple interface for transcribing audio files using the Faster Whisper model. It is designed to be deployed on platforms like Coolify using Docker.

## Base URL
When running locally: `http://localhost:8000`
When deployed: `https://<your-coolify-domain>`

---

## Endpoints

### 1. Health Check
Check if the API is running and the model is loaded.

- **URL**: `/health`
- **Method**: `GET`
- **Response**:
  ```json
  {
    "status": "ok",
    "model": "tiny",
    "device": "cpu"
  }
  ```

### 2. Transcribe Audio
Upload an audio file to get its transcription.

- **URL**: `/transcribe`
- **Method**: `POST`
- **Content-Type**: `multipart/form-data`
- **Body**:
  - `file`: The audio file to transcribe (mp3, wav, m4a, etc.)

- **Response**:
  ```json
  {
    "language": "en",
    "language_probability": 0.99,
    "duration": 12.5,
    "process_time": 0.45,
    "text": "This is the transcribed text from the audio file.",
    "segments": [
      {
        "start": 0.0,
        "end": 5.0,
        "text": "This is the transcribed"
      },
      {
        "start": 5.0,
        "end": 12.5,
        "text": "text from the audio file."
      }
    ]
  }
  ```

---

## Code Examples

### cURL (Terminal)
```bash
curl -X POST "http://localhost:8000/transcribe" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@/path/to/your/audio.mp3"
```

### Python (requests)
```python
import requests

url = "http://localhost:8000/transcribe"
file_path = "audio.mp3"

with open(file_path, "rb") as f:
    files = {"file": f}
    response = requests.post(url, files=files)

if response.status_code == 200:
    data = response.json()
    print(f"Language: {data['language']}")
    print(f"Transcription: {data['text']}")
else:
    print(f"Error: {response.text}")
```

### JavaScript / TypeScript (Fetch API)
```javascript
const transcribeAudio = async (file) => {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch("http://localhost:8000/transcribe", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Error: ${response.statusText}`);
    }

    const result = await response.json();
    console.log("Transcription:", result.text);
    return result;
  } catch (error) {
    console.error("Failed to transcribe:", error);
  }
};

// Usage with a file input element
// const fileInput = document.querySelector('input[type="file"]');
// transcribeAudio(fileInput.files[0]);
```

---

## Deployment (Coolify)

1.  **Push to Git**: Commit and push this code to your GitHub/GitLab repository.
2.  **Create Service**: In Coolify, create a new resource from your Git repository.
3.  **Configuration**:
    - **Build Pack**: Docker
    - **Port**: 8000
4.  **Environment Variables** (Optional):
    - `MODEL_SIZE`: `tiny` (default), `base`, `small`, `medium`, `large-v3`
    - `DEVICE`: `cpu` (default) or `cuda` (if GPU available)
    - `COMPUTE_TYPE`: `int8` (default) or `float16`
