/**
 * Interface for the transcription response
 */
export interface TranscriptionSegment {
  start: number;
  end: number;
  text: string;
}

export interface TranscriptionResponse {
  language: string;
  language_probability: number;
  duration: number;
  process_time: number;
  text: string;
  segments: TranscriptionSegment[];
}

/**
 * Transcribes an audio file using the Faster Whisper API.
 * 
 * @param fileUri - The local URI of the audio file (e.g., 'file:///...')
 * @param fileName - The name of the file (e.g., 'recording.m4a')
 * @param fileType - The MIME type of the file (e.g., 'audio/m4a')
 * @returns Promise resolving to the TranscriptionResponse
 */
export const transcribeAudio = async (
  fileUri: string, 
  fileName: string = 'recording.m4a', 
  fileType: string = 'audio/m4a'
): Promise<TranscriptionResponse> => {
  
  const API_URL = "https://faster.codinnovations.com/transcribe";

  const formData = new FormData();
  
  // React Native requires this specific object structure for file uploads
  formData.append('file', {
    uri: fileUri,
    name: fileName,
    type: fileType,
  } as any); // Cast to any because standard FormData types don't include React Native's specific file object

  // Optional: Add prompt to help with context (e.g., "Lecture about Physics")
  // formData.append('initial_prompt', 'This is a university lecture.');

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      body: formData,
      headers: {
        // IMPORTANT: Do NOT set 'Content-Type': 'multipart/form-data' manually!
        // The browser/React Native network layer sets this automatically with the correct boundary.
        'Accept': 'application/json',
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Transcription failed (${response.status}): ${errorText}`);
    }

    const data: TranscriptionResponse = await response.json();
    return data;

  } catch (error) {
    console.error('Transcription Error:', error);
    throw error;
  }
};
