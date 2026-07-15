"""Object storage boundary: AWS S3 (boto3) when configured, local disk fallback
for zero-dependency development. Evidence, imports and exports all pass through
here — never the API filesystem elsewhere.

Evidence is laid out for easy human tracking, mirrored on local disk and S3:
    {assessment-slug}-{id8}/{candidate-email}/webcam/{uuid}.jpg      periodic snapshots
    {assessment-slug}-{id8}/{candidate-email}/violations/{uuid}.jpg  full-screen on violation
"""

import base64
import re
from pathlib import Path

from .config import get_settings
from .models.base import new_id


def _local_dir() -> Path:
    path = Path(get_settings().local_storage_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "assessment"


def _safe_email(email: str) -> str:
    cleaned = re.sub(r"[^a-z0-9@._-]+", "_", (email or "unknown").lower())
    # neutralize any path-traversal sequence (".." never appears in a real email)
    return cleaned.replace("..", "_")


def evidence_prefix(
    assessment_title: str, assessment_id: str, candidate_email: str, subdir: str
) -> str:
    """Browsable prefix: {slug}-{id8}/{email}/{subdir}. The short id keeps
    same-titled assessments from colliding while staying readable."""
    folder = f"{slugify(assessment_title)}-{assessment_id[:8]}"
    return f"{folder}/{_safe_email(candidate_email)}/{subdir}"


def make_key(prefix: str, extension: str) -> str:
    return f"{prefix}/{new_id()}.{extension.lstrip('.')}"


def _s3_client(settings):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint or None,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )


def _use_s3(settings) -> bool:
    return bool(settings.s3_endpoint or settings.s3_access_key)


def put_object(key: str, content: bytes) -> str:
    settings = get_settings()
    if _use_s3(settings):
        # S3 keys with "/" render as nested folders in the console — same layout
        _s3_client(settings).put_object(Bucket=settings.s3_bucket, Key=key, Body=content)
        return key
    # local: preserve the real nested directory structure for easy browsing
    target = _local_dir() / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return key


def get_object(key: str) -> bytes | None:
    settings = get_settings()
    if _use_s3(settings):
        try:
            response = _s3_client(settings).get_object(Bucket=settings.s3_bucket, Key=key)
            return response["Body"].read()
        except Exception:
            return None
    target = _local_dir() / key
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
