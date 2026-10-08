# Quick Start Guide: How to Transcribe Audio

This guide gives you the simplest, step-by-step instructions on how to use the API to transcribe audio (from 10-second voice notes up to 2-hour recordings).

---

## The 2 Endpoints You Need

To transcribe audio, you only need **2 requests**:
1. **`POST /transcribe`**: Upload your audio $\rightarrow$ You receive a `job_id`.
2. **`GET /status/{job_id}`** (or `/jobs/{job_id}/events`): Check progress and get the finished text.

---

## Authentication
Every request requires your `API_SECRET` in the header:
```http
Authorization: Bearer YOUR_API_SECRET_HERE
```
*(Find your secret in your `.env` file under `API_SECRET`)*

---

## Method 1: Simple Polling (Easiest to Implement)

Use this method if you want standard HTTP requests.

### Step 1: Upload the Audio
Send your audio file to `POST /transcribe`:

#### Using cURL (Terminal):
```bash
curl -X POST "http://localhost:4001/transcribe" \
  -H "Authorization: Bearer YOUR_API_SECRET_HERE" \
  -F "file=@my_recording.m4a"
```

#### What You Get Back:
```json
{
  "job_id": "8f8b89cf-4a11-4775-9c8e-fb86de12a4ec",
  "status": "queued",
  "stream_url": "/jobs/8f8b89cf-4a11-4775-9c8e-fb86de12a4ec/events"
}
```
👉 **Save this `job_id`.**

---

### Step 2: Check the Status (Poll every 2–3 seconds)
Send a GET request to `GET /status/{job_id}`:

#### Using cURL:
```bash
curl -X GET "http://localhost:4001/status/8f8b89cf-4a11-4775-9c8e-fb86de12a4ec" \
  -H "Authorization: Bearer YOUR_API_SECRET_HERE"
```

#### While It's Still Transcribing:
You get live progress:
```json
{
  "job_id": "8f8b89cf-4a11-4775-9c8e-fb86de12a4ec",
  "status": "processing",
  "progress": 25.0,
  "completed_chunks": 3,
  "total_chunks": 12
}
```
*(Your frontend can show a progress bar: `25%` done)*

#### When It Finishes:
```json
{
  "job_id": "8f8b89cf-4a11-4775-9c8e-fb86de12a4ec",
  "status": "completed",
  "result": {
    "text": "Hello, welcome to today's meeting...",
    "duration": 7200.0,
    "process_time": 840.5,
    "language": "en",
    "segments": [
      { "start": 0.0, "end": 4.5, "text": "Hello, welcome to today's meeting..." }
    ]
  }
}
```
*(Your text is in `result.text`)*

---

## Method 2: Live Streaming (Best User Experience)

With this method, text appears on the screen in real-time as each 10-minute chunk finishes.

1. **Upload the audio** just like Step 1 $\rightarrow$ Get `job_id`.
2. **Listen to the live stream** using `EventSource` on `GET /jobs/{job_id}/events`.

### JavaScript / TypeScript Example:
```javascript
const jobId = "8f8b89cf-4a11-4775-9c8e-fb86de12a4ec";
const eventSource = new EventSource(`http://localhost:4001/jobs/${jobId}/events`);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);

  // 1. A 10-minute chunk just finished!
  if (data.type === "chunk_completed") {
    console.log(`Progress: ${data.progress_percent}%`);
    console.log(`New Text: ${data.text}`);
    // Append data.text to your screen!
  }

  // 2. The entire 2-hour file is 100% finished!
  if (data.status === "completed") {
    console.log("Full Completed Transcript:", data.result.text);
    eventSource.close(); // Close stream
  }

  // 3. Error occurred
  if (data.status === "failed") {
    console.error("Transcription failed:", data.error);
    eventSource.close();
  }
};
```

---

## Method 3: Cloudflare R2 / S3 Direct Upload (Best for Slow Internet)

If users have slow internet and you don't want 30 MB files uploading through your API server:

1. **Get an upload URL:**
   ```bash
   curl "http://localhost:4001/transcribe/upload-url?filename=audio.m4a" \
     -H "Authorization: Bearer YOUR_API_SECRET_HERE"
   ```
   *Returns:* `upload_url` and `file_key`.

2. **Upload directly to cloud storage (PUT request):**
   ```bash
   curl -X PUT -T "my_recording.m4a" "THE_UPLOAD_URL"
   ```

3. **Start transcription using the `file_key`:**
   ```bash
   curl -X POST "http://localhost:4001/transcribe" \
     -H "Authorization: Bearer YOUR_API_SECRET_HERE" \
     -F "s3_key=uploads/uuid.m4a"
   ```
4. Check status with `GET /status/{job_id}`.

---

## Summary Cheat Sheet

| I want to... | What to call | What to pass | What I get back |
|---|---|---|---|
| **Start transcription** | `POST /transcribe` | Multipart `file` (or `s3_key`) | `{ "job_id": "...", "status": "queued" }` |
| **Check progress** | `GET /status/{job_id}` | Bearer Token in header | `{ "status": "processing", "progress": 50.0 }` |
| **Get final transcript** | `GET /status/{job_id}` | Bearer Token in header | `{ "status": "completed", "result": { "text": "..." } }` |
| **Stream live text** | `GET /jobs/{job_id}/events` | `EventSource` connection | Stream of incoming text chunks |
