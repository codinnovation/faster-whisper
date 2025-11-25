import os
import time
from faster_whisper import WhisperModel

# Configuration
MODEL_SIZE = "tiny"  # Options: tiny, base, small, medium, large-v3
DEVICE = "cuda"      # "cuda" for GPU, "cpu" for CPU
COMPUTE_TYPE = "float16" # "float16" for GPU, "int8" for CPU

INPUT_DIR = "input_audio"
OUTPUT_DIR = "output_transcripts"

def format_timestamp(seconds):
    """Converts seconds to SRT timestamp format (HH:MM:SS,mmm)"""
    whole_seconds = int(seconds)
    milliseconds = int((seconds - whole_seconds) * 1000)
    
    hours = whole_seconds // 3600
    minutes = (whole_seconds % 3600) // 60
    seconds = whole_seconds % 60
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def write_srt(segments, file_path):
    """Writes segments to an SRT file"""
    with open(file_path, "w", encoding="utf-8") as f:
        for i, segment in enumerate(segments, start=1):
            start_time = format_timestamp(segment.start)
            end_time = format_timestamp(segment.end)
            text = segment.text.strip()
            
            f.write(f"{i}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{text}\n\n")

def write_txt(segments, file_path):
    """Writes segments to a plain text file"""
    with open(file_path, "w", encoding="utf-8") as f:
        for segment in segments:
            f.write(segment.text.strip() + " ")

def main():
    # 1. Initialize Model
    print(f"Loading {MODEL_SIZE} model on {DEVICE}...")
    try:
        model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    except Exception as e:
        print(f"Error loading on {DEVICE}: {e}")
        if DEVICE == "cuda":
            print("Falling back to CPU...")
            model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        else:
            return

    # 2. Process Files
    audio_extensions = ('.mp3', '.wav', '.m4a', '.mp4', '.mkv', '.flac')
    files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(audio_extensions)]

    if not files:
        print(f"No audio files found in '{INPUT_DIR}'. Please add some files.")
        return

    print(f"Found {len(files)} files to transcribe.")

    for filename in files:
        input_path = os.path.join(INPUT_DIR, filename)
        base_name = os.path.splitext(filename)[0]
        
        print(f"\nTranscribing: {filename}...")
        start_time = time.time()
        
        # Transcribe
        segments, info = model.transcribe(input_path, beam_size=5)
        
        # We need to convert the generator to a list to iterate over it multiple times 
        # OR just iterate once and write to both files. 
        # faster-whisper returns a generator, so we iterate once.
        
        srt_path = os.path.join(OUTPUT_DIR, f"{base_name}.srt")
        txt_path = os.path.join(OUTPUT_DIR, f"{base_name}.txt")
        
        # Collect all segments to write to both formats
        all_segments = list(segments)
        
        write_srt(all_segments, srt_path)
        write_txt(all_segments, txt_path)
        
        elapsed = time.time() - start_time
        print(f"Done in {elapsed:.2f}s.")
        print(f"Saved to: {OUTPUT_DIR}")

if __name__ == "__main__":
    # Ensure directories exist
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    main()
