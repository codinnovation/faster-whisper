# Frontend Migration Guide: Async Transcription

The backend transcription service has been upgraded to an **Asynchronous Architecture** to handle high load (5000+ users). 

## Changes Required
You need to update `transcribeService.ts` to handle the new "Polling" flow.

### 1. New API Flow
*   **Old**: `POST /transcribe` -> Waited 10s -> Returned Result.
*   **New**: 
    1.  `POST /transcribe` -> Returns `{"job_id": "abc-123", "status": "queued"}` immediately.
    2.  `GET /status/abc-123` -> Returns `{"status": "processing"}`.
    3.  `GET /status/abc-123` -> Returns `{"status": "completed", "result": { ...transcription data... }}`.

### 2. Prompt for AI/Developer
Copy and paste the following prompt to update your frontend code:

---

**Prompt:**
> I have updated my backend to use an Asynchronous Job Queue. Please refactor `transcribeService.ts` to implement polling.
>
> **Requirements:**
> 1. Update `transcribeAudio` to:
>    - Send the `POST /transcribe` request as before.
>    - Receive a `job_id` from the response.
>    - Enter a loop to poll `GET /status/{job_id}` every 2 seconds.
>    - If status is `pending` or `processing`, continue polling.
>    - If status is `completed`, resolve the promise with the `result` object (which matches the old `TranscriptionResponse` interface).
>    - If status is `failed`, throw an error.
>    - Add a timeout (e.g., 30 seconds) to stop polling if it takes too long.
>
> **API Contract:**
> - **POST /transcribe**: Returns `{ "job_id": string, "status": "queued" }`
> - **GET /status/{id}**: Returns `{ "job_id": string, "status": "pending" | "processing" | "completed" | "failed", "result"?: TranscriptionResponse, "error"?: string }`

---
