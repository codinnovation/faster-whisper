# Frontend Migration Guide: Async Transcription

The backend transcription service has been upgraded to an **Asynchronous Architecture** with non-blocking streaming and Server-Sent Events (SSE) to easily handle 1000+ concurrent users without timeouts.

---

## Supported Integration Patterns

You can integrate using either **Option A (SSE Real-Time Push - Recommended)** or **Option B (Polling - Supported)**.

### Option A: Server-Sent Events (Zero Polling Overhead)
1. `POST /transcribe` -> Returns `{"job_id": "abc-123", "status": "queued", "stream_url": "/jobs/abc-123/events"}`.
2. Connect to `http://<host>:4001/jobs/abc-123/events` using `EventSource`.
3. Event arrives instantly with `status: "completed"` and transcription data.

### Option B: Polling (Simple & Universal)
1. `POST /transcribe` -> Returns `{"job_id": "abc-123", "status": "queued"}`.
2. Poll `GET /status/abc-123` every 2 seconds until status is `completed` or `failed`.

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

/**
 * Transcribes an audio file with asynchronous polling and timeout safeguards.
 */
export async function transcribeAudio(
  fileUri: string,
  apiBaseUrl: string = "http://localhost:4001",
  apiSecret?: string,
  maxWaitSeconds: number = 180
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

  // 2. Poll status every 2 seconds
  while (Date.now() - startTime < maxWaitSeconds * 1000) {
    await new Promise((resolve) => setTimeout(resolve, 2000));

    const statusRes = await fetch(`${apiBaseUrl}/status/${job_id}`, { headers });
    if (!statusRes.ok) continue;

    const statusData = await statusRes.json();

    if (statusData.status === "completed" && statusData.result) {
      return statusData.result;
    }

    if (statusData.status === "failed") {
      throw new Error(`Transcription failed: ${statusData.error || "Unknown worker error"}`);
    }
  }

  throw new Error(`Transcription timed out after ${maxWaitSeconds} seconds.`);
}
```

