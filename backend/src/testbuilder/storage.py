"""Object storage boundary: AWS S3 (boto3) when configured, local disk fallback
for zero-dependency development. Evidence, imports and exports all pass through
here — never the API filesystem elsewhere."""

import base64
from pathlib import Path

from .config import get_settings
from .models.base import new_id


def _local_dir() -> Path:
    path = Path(get_settings().local_storage_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_key(prefix: str, extension: str) -> str:
    return f"{prefix}/{new_id()}.{extension.lstrip('.')}"


def put_object(key: str, content: bytes) -> str:
    settings = get_settings()
    if settings.s3_endpoint or settings.s3_access_key:
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint or None,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
        )
        client.put_object(Bucket=settings.s3_bucket, Key=key, Body=content)
        return key
    target = _local_dir() / key.replace("/", "__")
    target.write_bytes(content)
    return key


def get_object(key: str) -> bytes | None:
    settings = get_settings()
    if settings.s3_endpoint or settings.s3_access_key:
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint or None,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
        )
        try:
            response = client.get_object(Bucket=settings.s3_bucket, Key=key)
            return response["Body"].read()
        except Exception:
            return None
    target = _local_dir() / key.replace("/", "__")
    return target.read_bytes() if target.exists() else None


def put_base64_image(prefix: str, data_url: str) -> str:
    """Accepts a data URL or bare base64 JPEG/PNG payload; returns object key."""
    if "," in data_url and data_url.startswith("data:"):
        header, encoded = data_url.split(",", 1)
        extension = "png" if "png" in header else "jpg"
    else:
        encoded, extension = data_url, "jpg"
    content = base64.b64decode(encoded)
    key = make_key(prefix, extension)
    put_object(key, content)
    return key
