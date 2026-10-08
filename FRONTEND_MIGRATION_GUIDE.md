# Frontend Migration Guide: Async & Long-Audio Progressive Transcription

The backend transcription service supports **Asynchronous Architecture** with non-blocking streaming and Server-Sent Events (SSE) to handle short voice notes as well as **long recordings up to 2 hours** with progressive chunking.

---

## Supported Integration Patterns

You can integrate using either **Option A (SSE Real-Time Push - Recommended for Progressive Streaming)** or **Option B (Polling with Progress Tracking)**.

### Option A: Server-Sent Events (Real-Time Progressive Push - Recommended)
1. `POST /transcribe` -> Returns `{"job_id": "abc-123", "status": "queued", "stream_url": "/jobs/abc-123/events"}`.
2. Connect to `http://<host>:4001/jobs/abc-123/events` using `EventSource`.
3. Intermediate events arrive as chunks complete:
   ```json
   {
     "type": "chunk_completed",
     "chunk_index": 0,
     "total_chunks": 12,
     "progress_percent": 8.3,
     "text": "First 10 minutes of audio...",
     "segments": [...]
   }
   ```
4. Final completion event arrives when all chunks finish:
   ```json
   {
     "status": "completed",
     "result": { ... }
   }
   ```

### Option B: Polling with Progress Bar
1. `POST /transcribe` -> Returns `{"job_id": "abc-123", "status": "queued"}`.
2. Poll `GET /status/abc-123` every 2–3 seconds.
   * While processing: Returns `{"status": "processing", "progress": 25.0, "completed_chunks": 3, "total_chunks": 12}`.
   * When complete: Returns `{"status": "completed", "result": { ... }}`.

---

## Ready-to-Use TypeScript Implementation (`transcribeService.ts`)

```typescript
export interface TranscriptionSegment {
  start: number;
  end: number;
  text: string;
}

export interface TranscriptionResponse {
  status: string;
  language: string;
  language_probability: number;
  duration: number;
  process_time: number;
  real_time_factor?: number;
  text: string;
  segments?: TranscriptionSegment[];
}

export interface ProgressiveStatus {
  status: string;
  progress: number;
  completed_chunks?: number;
  total_chunks?: number;
}

/**
 * Transcribes an audio file with asynchronous polling, timeout safeguards, and progress tracking.
 * Works seamlessly for short clips and long files up to 2 hours.
 */
export async function transcribeAudio(
  fileUri: string,
  apiBaseUrl: string = "http://localhost:4001",
  apiSecret?: string,
  maxWaitSeconds: number = 1800, // 30 minutes default for long files
  onProgress?: (status: ProgressiveStatus) => void
): Promise<TranscriptionResponse> {
  const formData = new FormData();

  // Format for React Native / Expo or Web
  // @ts-ignore
  formData.append("file", {
    uri: fileUri,
    type: "audio/m4a",
    name: "audio.m4a",
  });

  const headers: Record<string, string> = {};
  if (apiSecret) {
    headers["Authorization"] = `Bearer ${apiSecret}`;
  }

  // 1. Submit audio to queue
  const submitRes = await fetch(`${apiBaseUrl}/transcribe`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!submitRes.ok) {
    const errText = await submitRes.text();
    throw new Error(`Upload failed (${submitRes.status}): ${errText}`);
  }

  const { job_id } = await submitRes.json();
  const startTime = Date.now();

  // 2. Poll status every 2.5 seconds
  while (Date.now() - startTime < maxWaitSeconds * 1000) {
    await new Promise((resolve) => setTimeout(resolve, 2500));

    const statusRes = await fetch(`${apiBaseUrl}/status/${job_id}`, { headers });
    if (!statusRes.ok) continue;

    const statusData = await statusRes.json();

    if (onProgress && statusData.progress !== undefined) {
      onProgress({
        status: statusData.status,
        progress: statusData.progress,
        completed_chunks: statusData.completed_chunks,
        total_chunks: statusData.total_chunks,
      });
    }

    if (statusData.status === "completed" && statusData.result) {
      return statusData.result;
    }

    if (statusData.status === "failed") {
      throw new Error(`Transcription failed: ${statusData.error || "Unknown worker error"}`);
    }
  }

  throw new Error(`Transcription timed out after ${maxWaitSeconds} seconds.`);
}

/**
 * Listen to real-time progressive transcription via SSE.
 * Appends text chunks as they finish without waiting for the full 2-hour file.
 */
export function listenToTranscriptionEvents(
  jobId: string,
  apiBaseUrl: string = "http://localhost:4001",
  onChunk: (chunk: { text: string; progress: number; chunk_index: number }) => void,
  onComplete: (result: TranscriptionResponse) => void,
  onError: (error: string) => void
): () => void {
  const eventSource = new EventSource(`${apiBaseUrl}/jobs/${jobId}/events`);

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);

      if (data.type === "chunk_completed") {
        onChunk({
          text: data.text,
          progress: data.progress_percent,
          chunk_index: data.chunk_index,
        });
      } else if (data.status === "completed" && data.result) {
        onComplete(data.result);
        eventSource.close();
      } else if (data.status === "failed") {
        onError(data.error || "Transcription failed");
        eventSource.close();
      }
    } catch (e) {
      console.warn("Could not parse SSE message", e);
    }
  };

  eventSource.onerror = (err) => {
    console.error("SSE connection error", err);
  };

  // Return unsubscribe cleanup function
  return () => {
    eventSource.close();
  };
}
```
