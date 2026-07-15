"""Object storage boundary: AWS S3 (boto3) when configured, local disk fallback
for zero-dependency development. Evidence, imports and exports all pass through
here — never the API filesystem elsewhere."""

import base64
from pathlib import Path

import structlog

from .config import get_settings
from .models.base import new_id

log = structlog.get_logger()


def _local_dir() -> Path:
    path = Path(get_settings().local_storage_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_key(prefix: str, extension: str) -> str:
    return f"{prefix}/{new_id()}.{extension.lstrip('.')}"


def _local_target(key: str) -> Path:
    safe_name = key.replace("/", "__").replace("\\", "__").replace("..", "_")
    return _local_dir() / safe_name


def _s3_client(settings):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint or None,
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
    )


def put_object(key: str, content: bytes) -> str:
    settings = get_settings()
    if settings.s3_endpoint or settings.s3_access_key:
        try:
            _s3_client(settings).put_object(Bucket=settings.s3_bucket, Key=key, Body=content)
            return key
        except Exception as exc:
            log.warning("s3_put_failed_using_local_fallback", key=key, error=str(exc))
    _local_target(key).write_bytes(content)
    return key


def get_object(key: str) -> bytes | None:
    settings = get_settings()
    if settings.s3_endpoint or settings.s3_access_key:
        try:
            response = _s3_client(settings).get_object(Bucket=settings.s3_bucket, Key=key)
            return response["Body"].read()
        except Exception as exc:
            log.warning("s3_get_failed_using_local_fallback", key=key, error=str(exc))
    target = _local_target(key)
    return target.read_bytes() if target.exists() else None


def put_base64_image(prefix: str, data_url: str) -> str:
    """Accepts a data URL or bare base64 JPEG/PNG payload; returns object key."""
    if "," in data_url and data_url.startswith("data:"):
        header, encoded = data_url.split(",", 1)
        extension = "png" if "png" in header else "jpg"
    else:
        encoded, extension = data_url, "jpg"
    content = base64.b64decode(encoded, validate=True)
    key = make_key(prefix, extension)
    put_object(key, content)
    return key
