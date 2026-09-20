import os
import uuid
import logging
from typing import Optional, Tuple

logger = logging.getLogger("storage")

S3_BUCKET = os.getenv("S3_BUCKET")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")  # e.g., https://<account>.r2.cloudflarestorage.com or http://minio:9000
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/data")

_s3_client = None

def is_s3_enabled() -> bool:
    """Returns True if S3/R2 storage is configured with valid credentials."""
    return bool(
        S3_BUCKET
        and AWS_ACCESS_KEY_ID
        and AWS_SECRET_ACCESS_KEY
        and not AWS_ACCESS_KEY_ID.startswith("your_")
    )

def get_s3_client():
    """Initializes and caches the boto3 S3 client."""
    global _s3_client
    if _s3_client is None:
        import boto3
        from botocore.config import Config

        client_kwargs = {
            "service_name": "s3",
            "region_name": AWS_REGION,
            "aws_access_key_id": AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
            "config": Config(signature_version="s3v4"),
        }
        if S3_ENDPOINT_URL:
            client_kwargs["endpoint_url"] = S3_ENDPOINT_URL

        _s3_client = boto3.client(**client_kwargs)
    return _s3_client

def generate_presigned_upload_url(
    filename: str,
    content_type: str = "audio/mpeg",
    expires_in: int = 3600
) -> Tuple[str, str]:
    """
    Generates an S3 presigned PUT URL so clients can upload audio directly to S3.
    Returns (upload_url, file_key).
    """
    if not is_s3_enabled():
        raise RuntimeError("S3 storage is not configured on this server.")

    s3 = get_s3_client()
    ext = os.path.splitext(filename)[1].lower() or ".mp3"
    file_key = f"uploads/{uuid.uuid4()}{ext}"

    params = {
        "Bucket": S3_BUCKET,
        "Key": file_key,
        "ContentType": content_type
    }

    upload_url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params=params,
        ExpiresIn=expires_in
    )

    logger.info(f"Generated presigned upload URL for key: {file_key}")
    return upload_url, file_key

def download_audio_file(file_key_or_path: str, target_dir: str = UPLOAD_DIR) -> str:
    """
    Resolves an audio file for worker processing.
    If file_key_or_path is an S3 key, downloads to target_dir and returns the local path.
    If it's an existing local path, returns it directly.
    """
    # 1. Local path check
    if os.path.isabs(file_key_or_path) and os.path.exists(file_key_or_path):
        return file_key_or_path

    # 2. S3 key check
    if is_s3_enabled():
        s3 = get_s3_client()
        clean_key = file_key_or_path.replace(f"s3://{S3_BUCKET}/", "")
        safe_filename = os.path.basename(clean_key)
        local_dest = os.path.join(target_dir, f"dl_{safe_filename}")

        logger.info(f"Downloading {clean_key} from S3 bucket {S3_BUCKET} to {local_dest}...")
        s3.download_file(S3_BUCKET, clean_key, local_dest)
        return local_dest

    raise FileNotFoundError(f"Audio file '{file_key_or_path}' could not be resolved locally or from S3.")

def cleanup_audio_file(local_path: str, s3_key: Optional[str] = None):
    """Safely removes local temporary file and optionally S3 object."""
    if local_path and os.path.exists(local_path):
        try:
            os.remove(local_path)
            logger.debug(f"Removed local file: {local_path}")
        except OSError as e:
            logger.error(f"Failed to remove local file {local_path}: {e}")

    if s3_key and is_s3_enabled() and os.getenv("DELETE_S3_AFTER_PROCESSING", "false").lower() == "true":
        try:
            s3 = get_s3_client()
            clean_key = s3_key.replace(f"s3://{S3_BUCKET}/", "")
            s3.delete_object(Bucket=S3_BUCKET, Key=clean_key)
            logger.info(f"Deleted S3 object: {clean_key}")
        except Exception as e:
            logger.error(f"Failed to delete S3 object {s3_key}: {e}")
