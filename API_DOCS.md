# Faster Whisper API Documentation (High-Scale Async)

High-performance, asynchronous audio transcription service powered by Faster-Whisper, FastAPI, Celery, and Redis. Engineered for high availability and concurrent workloads.

## Base URL
* **Local Development**: `http://localhost:4001`
* **Production**: `https://<your-domain>`
* **Flower Monitoring Dashboard**: `http://localhost:5555`

---

## Authentication
All API endpoints (except `/health`) require Bearer token authentication:
```http
Authorization: Bearer <API_SECRET>
```

---

## Endpoints

### 1. Health Check
Quick non-blocking health probe.
* **URL**: `/health`
* **Method**: `GET`
* **Auth**: None
* **Response**:
  ```json
  {
    "status": "ok",
    "mode": "async",
    "redis": "connected"
  }
  ```

---

### 2. Direct S3 Upload (Zero-API-Load Flow - Recommended for High Scale)
Request a presigned URL to upload audio directly to storage (S3 / Cloudflare R2 / MinIO), completely bypassing the API server's network bandwidth.
* **URL**: `/transcribe/upload-url`
* **Method**: `POST` or `GET`
* **Parameters**: `filename` (e.g. `recording.mp3`), `content_type` (e.g. `audio/mpeg`)
* **Response (`200 OK`)**:
  ```json
  {
    "upload_url": "https://<bucket>.<s3-endpoint>/uploads/uuid.mp3?X-Amz-Signature=...",
    "file_key": "uploads/uuid.mp3",
    "expires_in_seconds": 3600,
    "message": "Upload file to upload_url via HTTP PUT, then pass file_key to /transcribe."
  }
  ```

---

### 3. Submit Audio for Transcription
Enqueues a background transcription task using either a direct multipart audio file OR a previously uploaded `s3_key`.
* **URL**: `/transcribe`
* **Method**: `POST`
* **Content-Type**: `multipart/form-data`
* **Limits**: Max file size 100MB | Rate limit: 120 req/minute
* **Supported Formats**: `.mp3`, `.wav`, `.m4a`, `.aac`, `.ogg`, `.flac`, `.webm`, `.wma`
* **Parameters (Form Data)**:
  * `file` *(optional if s3_key provided)*: Audio file to transcribe
  * `s3_key` *(optional if file provided)*: S3 storage key returned by `/transcribe/upload-url`
  * `webhook_url` *(optional)*: URL to receive a POST request with the result when transcription completes
  * `language` *(optional)*: Language code (e.g., `en`, `es`, `fr`, `de`, `auto`)
  * `initial_prompt` *(optional)*: Contextual prompt to guide Whisper
  * `vad_filter` *(optional, default: true)*: Voice Activity Detection filter
  * `output_format` *(optional, default: json)*: `json`, `srt`, `vtt`, or `txt`

* **Response (`200 OK`)**:
  ```json
  {
    "job_id": "8f8b89cf-4a11-4775-9c8e-fb86de12a4ec",
    "status": "queued",
    "message": "Transcription started. Connect to stream_url, poll /status/{job_id}, or await webhook.",
    "stream_url": "/jobs/8f8b89cf-4a11-4775-9c8e-fb86de12a4ec/events",
    "webhook_url": "https://your-domain.com/api/transcribe-webhook"
  }
  ```


---

### 3. Real-Time Result Streaming (Recommended)
Subscribes to Server-Sent Events (SSE) to receive instant task updates without polling.
* **URL**: `/jobs/{job_id}/events`
* **Method**: `GET`
* **Headers**: `Accept: text/event-stream`
* **Auth**: `Bearer <API_SECRET>`
* **Stream Events**:
  ```text
  data: {"status": "subscribed", "job_id": "8f8b89cf-4a11-4775-9c8e-fb86de12a4ec"}

  data: {"status": "processing", "job_id": "8f8b89cf-4a11-4775-9c8e-fb86de12a4ec"}

  data: {"status": "completed", "result": {"text": "...", "duration": 12.5, "process_time": 1.45, "segments": [...]}}
  ```

---

### 4. Poll Task Status (Backward Compatible)
Polls the job status until completion.
* **URL**: `/status/{job_id}`
* **Method**: `GET`
* **Auth**: `Bearer <API_SECRET>`
* **Responses**:
  * **Pending**: `{"job_id": "...", "status": "pending"}`
  * **Processing**: `{"job_id": "...", "status": "processing"}`
  * **Completed**:
    ```json
    {
      "job_id": "...",
      "status": "completed",
      "result": {
        "text": "Transcribed text content.",
        "duration": 14.2,
        "process_time": 1.12,
        "real_time_factor": 0.079,
        "language": "en",
        "language_probability": 0.99,
        "segments": [
          { "start": 0.0, "end": 4.5, "text": "Transcribed text" },
          { "start": 4.5, "end": 14.2, "text": "content." }
        ]
      }
    }
    ```
  * **Failed**: `{"job_id": "...", "status": "failed", "error": "Error message"}`

---

## Client Integration Examples

### JavaScript (Using SSE Stream - Best Performance)
```javascript
async function transcribeWithStream(file, apiSecret) {
  const formData = new FormData();
  formData.append("file", file);

  // 1. Submit file
  const postRes = await fetch("http://localhost:4001/transcribe", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiSecret}` },
    body: formData,
  });
  const { job_id, stream_url } = await postRes.json();

  // 2. Listen via Server-Sent Events (Zero Polling Overhead)
  return new Promise((resolve, reject) => {
    const eventSource = new EventSource(`http://localhost:4001${stream_url}`);
    
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.status === "completed") {
        eventSource.close();
        resolve(data.result);
      } else if (data.status === "failed") {
        eventSource.close();
        reject(new Error(data.error));
      }
    };

    eventSource.onerror = (err) => {
      eventSource.close();
      reject(err);
    };
  });
}
```

---

## Deployment & Scaling

Run the stack using Docker Compose:
```bash
docker compose up -d
```

Scale worker capacity based on CPU resources:
```bash
docker compose up -d --scale worker=4
```

