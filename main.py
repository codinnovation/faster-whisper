from faster_whisper import WhisperModel
import os

def main():
    model_size = "tiny"
    print(f"Loading {model_size} model...")
    
    # Run on GPU with FP16
    # If you don't have a GPU, change device="cpu" and compute_type="int8"
    try:
        model = WhisperModel(model_size, device="cuda", compute_type="float16")
        print("Model loaded successfully on CUDA!")
    except Exception as e:
        print(f"Could not load on CUDA: {e}")
        print("Falling back to CPU...")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        print("Model loaded successfully on CPU!")

    print("\nSetup is complete and working!")
    print("To transcribe a file, you can use:")
    print("segments, info = model.transcribe('audio.mp3', beam_size=5)")

if __name__ == "__main__":
    main()
