from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session

from assetflow.config import Settings
from assetflow.ledger import auto_confirm_candidates
from assetflow.models import Upload
from assetflow.recognition.providers import make_provider
from assetflow.recognition.service import process_recognition_result
from assetflow.reconciliation import reconcile_positions
from assetflow.uploads import store_upload


@dataclass(frozen=True)
class UploadPipelineResult:
    upload: Upload
    auto_confirmed: int
    reconciliation_created: int


def process_uploaded_image(
    *,
    session: Session,
    settings: Settings,
    broker: str,
    source: str,
    filename: str,
    content_type: str,
    data: bytes,
    account_alias: str | None = None,
) -> UploadPipelineResult:
    upload = store_upload(
        session=session,
        settings=settings,
        broker=broker,
        source=source,
        filename=filename,
        content_type=content_type,
        data=data,
        account_alias=account_alias,
    )
    auto_confirmed = 0
    reconciliation_created = 0
    if upload.status != "duplicate":
        provider = make_provider(settings)
        recognition = provider.recognize(Path(upload.image_path), broker)
        process_recognition_result(session, upload, provider, recognition)
        auto_confirmed = auto_confirm_candidates(session)
        reconciliation_created = reconcile_positions(session, broker=broker, account_alias=account_alias)
        session.refresh(upload)
    return UploadPipelineResult(
        upload=upload,
        auto_confirmed=auto_confirmed,
        reconciliation_created=reconciliation_created,
    )
