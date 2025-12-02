"""
Example client for the distributed Faster Whisper API
Demonstrates job submission and polling pattern
"""
import requests
import time
from pathlib import Path
from typing import Optional, Dict, Any

class WhisperClient:
    def __init__(self, base_url: str = "http://localhost"):
        self.base_url = base_url.rstrip('/')
    
    def transcribe_file(
        self, 
        file_path: str,
        vad_filter: bool = True,
        initial_prompt: Optional[str] = None,
        language: Optional[str] = None,
        poll_interval: int = 2,
        timeout: int = 600
    ) -> Dict[str, Any]:
        """
        Transcribe audio file and wait for result
        
        Args:
            file_path: Path to audio file
            vad_filter: Enable voice activity detection
            initial_prompt: Optional prompt for better accuracy
            language: Optional language code (e.g., 'en', 'es')
            poll_interval: Seconds between status checks
            timeout: Maximum wait time in seconds
        
        Returns:
            Transcription result dictionary
        """
        # Submit job
        print(f"Uploading file: {file_path}")
        job_id = self.submit_job(file_path, vad_filter, initial_prompt, language)
        print(f"Job submitted: {job_id}")
        
        # Poll for completion
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self.get_status(job_id)
            state = status.get('status', 'unknown')
            
            print(f"Status: {state}")
            
            if state == 'success':
                result = self.get_result(job_id)
                print("Transcription completed!")
                return result
            elif state == 'failure':
                error = status.get('error', 'Unknown error')
                raise Exception(f"Transcription failed: {error}")
            
            time.sleep(poll_interval)
        
        raise TimeoutError(f"Transcription timed out after {timeout} seconds")
    
    def submit_job(
        self,
        file_path: str,
        vad_filter: bool = True,
        initial_prompt: Optional[str] = None,
        language: Optional[str] = None
    ) -> str:
        """Submit transcription job"""
        with open(file_path, 'rb') as f:
            files = {'file': (Path(file_path).name, f)}
            data = {
                'vad_filter': vad_filter,
            }
            if initial_prompt:
                data['initial_prompt'] = initial_prompt
            if language:
                data['language'] = language
            
            response = requests.post(
                f"{self.base_url}/transcribe",
                files=files,
                data=data,
                timeout=60
            )
            response.raise_for_status()
            return response.json()['job_id']
    
    def get_status(self, job_id: str) -> Dict[str, Any]:
        """Get job status"""
        response = requests.get(f"{self.base_url}/status/{job_id}")
        response.raise_for_status()
        return response.json()
    
    def get_result(self, job_id: str) -> Dict[str, Any]:
        """Get completed result"""
        response = requests.get(f"{self.base_url}/result/{job_id}")
        response.raise_for_status()
        return response.json()
    
    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        """Cancel a job"""
        response = requests.delete(f"{self.base_url}/job/{job_id}")
        response.raise_for_status()
        return response.json()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get API statistics"""
        response = requests.get(f"{self.base_url}/stats")
        response.raise_for_status()
        return response.json()
    
    def health_check(self) -> Dict[str, Any]:
        """Check API health"""
        response = requests.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()


# Example usage
if __name__ == "__main__":
    client = WhisperClient("http://localhost")
    
    # Health check
    health = client.health_check()
    print("Health:", health)
    
    # Transcribe a file
    try:
        result = client.transcribe_file(
            "sample_audio.mp3",
            vad_filter=True,
            language="en"
        )
        
        print("\n=== Transcription Result ===")
        print(f"Language: {result['language']}")
        print(f"Duration: {result['duration']}s")
        print(f"\nText: {result['text']}")
        print(f"\nSegments: {len(result['segments'])}")
        
        for i, segment in enumerate(result['segments'][:3], 1):
            print(f"  {i}. [{segment['start']}s - {segment['end']}s]: {segment['text']}")
    
    except Exception as e:
        print(f"Error: {e}")
