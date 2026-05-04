from pathlib import Path

from sqlmodel import select

from assetflow.models import CandidateTransaction, OcrResult, Transaction, Upload
from assetflow.upload_pipeline import process_uploaded_image


PNG_BYTES = b"\x89PNG\r\n\x1a\nabc"


def test_upload_pipeline_processes_new_upload(settings, session) -> None:
    result = process_uploaded_image(
        session=session,
        settings=settings,
        broker="htsc_global",
        source="web",
        filename="trade.png",
        content_type="image/png",
        data=PNG_BYTES,
        account_alias=None,
    )

    assert result.upload.status == "recognized"
    assert result.auto_confirmed == 1
    assert result.reconciliation_created == 0
    assert session.exec(select(Upload)).one().source == "web"
    assert session.exec(select(OcrResult)).one().screenshot_type == "trade_history"
    assert session.exec(select(CandidateTransaction)).one().symbol == "00700"
    assert session.exec(select(Transaction)).one().symbol == "00700"


def test_upload_pipeline_skips_duplicate_upload(settings, session) -> None:
    first = process_uploaded_image(
        session=session,
        settings=settings,
        broker="htsc_global",
        source="web",
        filename="first.png",
        content_type="image/png",
        data=PNG_BYTES,
    )
    second = process_uploaded_image(
        session=session,
        settings=settings,
        broker="htsc_global",
        source="web",
        filename="second.png",
        content_type="image/png",
        data=PNG_BYTES,
    )

    assert first.upload.status == "recognized"
    assert second.upload.status == "duplicate"
    assert second.upload.duplicate_of_upload_id == first.upload.id
    assert second.auto_confirmed == 0
    assert len(session.exec(select(OcrResult)).all()) == 1
    assert len(session.exec(select(Transaction)).all()) == 1
