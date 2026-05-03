from pathlib import Path

from sqlmodel import Session, select

from assetflow.config import Settings
from assetflow.domain import SUPPORTED_BROKERS, calculate_hash
from assetflow.models import Upload


class InvalidUploadError(ValueError):
    pass


ALLOWED_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/heic": ".heic",
    "image/heif": ".heif",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _validate_upload(broker: str, content_type: str, data: bytes) -> str:
    if broker not in SUPPORTED_BROKERS:
        raise InvalidUploadError(f"Unsupported broker: {broker}")
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise InvalidUploadError(f"Unsupported image type: {content_type}")
    if not data:
        raise InvalidUploadError("Empty upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidUploadError("Upload exceeds 10MB limit")
    return ALLOWED_CONTENT_TYPES[content_type]


def store_upload(
    session: Session,
    settings: Settings,
    broker: str,
    source: str,
    filename: str,
    content_type: str,
    data: bytes,
    account_alias: str | None = None,
) -> Upload:
    suffix = _validate_upload(broker, content_type, data)
    content_hash = calculate_hash(data)
    existing = session.exec(select(Upload).where(Upload.content_hash == content_hash)).first()
    image_path = settings.upload_dir / f"{content_hash}{suffix}"
    settings.ensure_directories()

    if existing is None:
        image_path.write_bytes(data)
        status = "stored"
        duplicate_of_upload_id = None
    else:
        status = "duplicate"
        duplicate_of_upload_id = existing.id

    upload = Upload(
        broker=broker,
        account_alias=account_alias,
        source=source,
        original_filename=Path(filename).name,
        content_hash=content_hash,
        image_path=str(image_path),
        mime_type=content_type,
        file_size_bytes=len(data),
        status=status,
        duplicate_of_upload_id=duplicate_of_upload_id,
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    return upload
