"""
Simple test script for the Faster Whisper API
"""
import requests
import sys

# Configuration
API_URL = "http://localhost:8000"

def test_health():
    """Test health endpoint"""
    print("Testing health endpoint...")
    try:
        response = requests.get(f"{API_URL}/health")
        if response.status_code == 200:
            print("✓ Health check passed")
            print(f"  Response: {response.json()}")
            return True
        else:
            print(f"✗ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Health check error: {e}")
        return False

def test_root():
    """Test root endpoint"""
    print("\nTesting root endpoint...")
    try:
        response = requests.get(f"{API_URL}/")
        if response.status_code == 200:
            print("✓ Root endpoint working")
            print(f"  Response: {response.json()}")
            return True
        else:
            print(f"✗ Root endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Root endpoint error: {e}")
        return False

def test_transcribe(audio_file_path):
    """Test transcription endpoint"""
    print(f"\nTesting transcription with file: {audio_file_path}")
    try:
        with open(audio_file_path, 'rb') as f:
            files = {'file': f}
            data = {
                'task': 'transcribe',
                'beam_size': 5,
                'vad_filter': True
            }
            response = requests.post(f"{API_URL}/transcribe", files=files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            print("✓ Transcription successful")
            print(f"  Text: {result['text'][:100]}...")
            print(f"  Language: {result['language']}")
            print(f"  Duration: {result['duration']}s")
            print(f"  Segments: {len(result['segments'])}")
            return True
        else:
            print(f"✗ Transcription failed: {response.status_code}")
            print(f"  Error: {response.text}")
            return False
    except FileNotFoundError:
        print(f"✗ Audio file not found: {audio_file_path}")
        return False
    except Exception as e:
        print(f"✗ Transcription error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("Faster Whisper API Test Suite")
    print("=" * 50)
    
    # Test basic endpoints
    health_ok = test_health()
    root_ok = test_root()
    
    # Test transcription if audio file provided
    if len(sys.argv) > 1:
        audio_file = sys.argv[1]
        transcribe_ok = test_transcribe(audio_file)
    else:
        print("\n⚠ Skipping transcription test (no audio file provided)")
        print("  Usage: python test_api.py <path_to_audio_file>")
        transcribe_ok = None
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    print(f"Health Check: {'✓ PASS' if health_ok else '✗ FAIL'}")
    print(f"Root Endpoint: {'✓ PASS' if root_ok else '✗ FAIL'}")
    if transcribe_ok is not None:
        print(f"Transcription: {'✓ PASS' if transcribe_ok else '✗ FAIL'}")
    
    # Exit code
    if health_ok and root_ok and (transcribe_ok is None or transcribe_ok):
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed")
        sys.exit(1)
