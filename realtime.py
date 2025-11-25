import sounddevice as sd
import numpy as np
import queue
import sys
from faster_whisper import WhisperModel

# Configuration
MODEL_SIZE = "tiny"     # tiny, base, small, medium, large-v3
DEVICE = "cuda"         # cuda or cpu
COMPUTE_TYPE = "float16" # float16 for cuda, int8 for cpu
SAMPLE_RATE = 16000     # Whisper expects 16kHz
BLOCK_SIZE = 4000       # Audio chunk size
THRESHOLD = 0.02        # Silence threshold (adjust if too sensitive)
SILENCE_DURATION = 1.0  # Seconds of silence to trigger transcription

q = queue.Queue()

def callback(indata, frames, time, status):
    """This is called (from a separate thread) for each audio block."""
    if status:
        print(status, file=sys.stderr)
    q.put(indata.copy())

def main():
    print(f"Loading {MODEL_SIZE} model on {DEVICE}...")
    try:
        model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    except Exception as e:
        print(f"Error loading on {DEVICE}: {e}")
        print("Falling back to CPU...")
        model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")

    print("\nListening... (Press Ctrl+C to stop)")
    print("-" * 50)

    # Accumulate audio here
    audio_buffer = np.array([], dtype=np.float32)
    silence_counter = 0
    
    # Start recording
    with sd.InputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE, channels=1, callback=callback):
        while True:
            # Get new data from queue
            while not q.empty():
                data = q.get()
                # Flatten to 1D array
                data = data.flatten().astype(np.float32)
                audio_buffer = np.concatenate((audio_buffer, data))

            # Check volume to detect silence
            if len(audio_buffer) > 0:
                # Look at the last chunk of data for volume
                last_chunk = audio_buffer[-BLOCK_SIZE:] if len(audio_buffer) > BLOCK_SIZE else audio_buffer
                volume = np.linalg.norm(last_chunk) / len(last_chunk)
                
                if volume < THRESHOLD:
                    silence_counter += (BLOCK_SIZE / SAMPLE_RATE)
                else:
                    silence_counter = 0

                # If we have enough audio and enough silence, transcribe
                # We want at least 1 second of audio to transcribe
                duration = len(audio_buffer) / SAMPLE_RATE
                
                if duration > 1.0 and silence_counter > SILENCE_DURATION:
                    # Transcribe
                    # print("Transcribing...") # Debug
                    segments, info = model.transcribe(audio_buffer, beam_size=5)
                    
                    text = ""
                    for segment in segments:
                        text += segment.text
                    
                    if text.strip():
                        print(f"You said: {text.strip()}")
                    
                    # Reset buffer
                    audio_buffer = np.array([], dtype=np.float32)
                    silence_counter = 0
            
            # Sleep briefly to avoid 100% CPU usage in this loop
            sd.sleep(100)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
