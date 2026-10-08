import os
import re
import shutil
import subprocess
import logging
from typing import List, Dict, Any

logger = logging.getLogger("audio_splitter")

def probe_audio_duration(file_path: str) -> float:
    """
    Returns the duration of the audio file in seconds using ffprobe.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        logger.error(f"Failed to probe duration for {file_path} via ffprobe: {e}")
        raise RuntimeError(f"Could not determine audio duration: {str(e)}")

def find_silence_points(
    file_path: str,
    min_silence_len: float = 0.3,
    noise_threshold: str = "-30dB"
) -> List[float]:
    """
    Scans the audio file for silence boundaries using ffmpeg's silencedetect filter.
    Returns a sorted list of timestamps (in seconds) representing mid-silence pause points.
    """
    cmd = [
        "ffmpeg",
        "-i", file_path,
        "-af", f"silencedetect=noise={noise_threshold}:d={min_silence_len}",
        "-f", "null",
        "-"
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        output = result.stderr

        silence_starts = []
        silence_ends = []

        for line in output.splitlines():
            if "silence_start:" in line:
                m = re.search(r"silence_start:\s*([0-9.]+)", line)
                if m:
                    silence_starts.append(float(m.group(1)))
            elif "silence_end:" in line:
                m = re.search(r"silence_end:\s*([0-9.]+)", line)
                if m:
                    silence_ends.append(float(m.group(1)))

        midpoints = []
        for i in range(min(len(silence_starts), len(silence_ends))):
            midpoints.append((silence_starts[i] + silence_ends[i]) / 2.0)

        logger.info(f"Detected {len(midpoints)} silence pause points in {file_path}")
        return sorted(midpoints)
    except Exception as e:
        logger.warning(f"Silence detection failed, defaulting to regular intervals: {e}")
        return []

def find_best_split_point(
    target_time: float,
    silence_points: List[float],
    search_window: float = 15.0
) -> float:
    """
    Finds the closest silence midpoint within [target_time - search_window, target_time + search_window].
    If no silence is found in the window, returns the exact target_time.
    """
    best_point = target_time
    min_distance = search_window + 1.0

    for pt in silence_points:
        distance = abs(pt - target_time)
        if distance <= search_window and distance < min_distance:
            min_distance = distance
            best_point = pt

    return best_point

def split_audio_into_chunks(
    file_path: str,
    job_id: str,
    base_dir: str = "/app/data",
    target_chunk_seconds: float = 600.0,   # 10 minutes default
    chunk_threshold_seconds: float = 600.0  # Files <= 10 min are not split
) -> List[Dict[str, Any]]:
    """
    Probes audio duration and splits files longer than chunk_threshold_seconds into ~10-minute chunks.
    Outputs standardized 16kHz mono 16-bit PCM WAV chunks for maximum Whisper inference efficiency.
    Returns a list of chunk metadata dictionaries.
    """
    duration = probe_audio_duration(file_path)
    logger.info(f"Total audio duration for job {job_id}: {duration:.2f} seconds ({duration / 60:.1f} minutes)")

    # Bypass splitting for short audio
    if duration <= chunk_threshold_seconds:
        logger.info(f"Audio duration ({duration:.2f}s) <= threshold ({chunk_threshold_seconds}s). Skipping splitting.")
        return [{
            "chunk_index": 0,
            "total_chunks": 1,
            "file_path": file_path,
            "start_offset": 0.0,
            "duration": duration,
            "is_single": True
        }]

    # Create dedicated chunk directory for this job
    chunk_dir = os.path.join(base_dir, "chunks", job_id)
    os.makedirs(chunk_dir, exist_ok=True)

    # Detect natural speech pauses
    silence_points = find_silence_points(file_path)

    # Calculate split cut points
    cut_points = [0.0]
    current_time = 0.0

    while current_time + target_chunk_seconds < duration:
        target_cut = current_time + target_chunk_seconds
        actual_cut = find_best_split_point(target_cut, silence_points, search_window=15.0)

        # Guard against zero or negative progress
        if actual_cut <= current_time + 60.0:  # Minimum chunk length of 60 seconds
            actual_cut = target_cut

        cut_points.append(actual_cut)
        current_time = actual_cut

    cut_points.append(duration)
    logger.info(f"Splitting job {job_id} into {len(cut_points) - 1} chunks at boundaries: {cut_points}")

    chunks_metadata = []
    total_chunks = len(cut_points) - 1

    for idx in range(total_chunks):
        start_t = cut_points[idx]
        end_t = cut_points[idx + 1]
        chunk_duration = end_t - start_t

        chunk_filename = f"chunk_{idx:03d}.wav"
        chunk_file_path = os.path.join(chunk_dir, chunk_filename)

        cmd = [
            "ffmpeg",
            "-y",
            "-ss", f"{start_t:.3f}",
            "-to", f"{end_t:.3f}",
            "-i", file_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            chunk_file_path
        ]

        logger.info(f"Exporting chunk {idx + 1}/{total_chunks}: {start_t:.1f}s to {end_t:.1f}s -> {chunk_filename}")
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

        chunks_metadata.append({
            "chunk_index": idx,
            "total_chunks": total_chunks,
            "file_path": chunk_file_path,
            "start_offset": round(start_t, 3),
            "duration": round(chunk_duration, 3),
            "is_single": False
        })

    return chunks_metadata

def cleanup_chunk_dir(job_id: str, base_dir: str = "/app/data"):
    """Removes the temporary chunks folder for the specified job."""
    chunk_dir = os.path.join(base_dir, "chunks", job_id)
    if os.path.exists(chunk_dir):
        try:
            shutil.rmtree(chunk_dir, ignore_errors=True)
            logger.info(f"Successfully cleaned up chunk directory: {chunk_dir}")
        except Exception as e:
            logger.warning(f"Could not delete chunk directory {chunk_dir}: {e}")
