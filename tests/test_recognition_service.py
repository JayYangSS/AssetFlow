from pathlib import Path

from sqlmodel import select

from assetflow.models import CandidateTransaction, OcrResult, PositionSnapshot
from assetflow.recognition.providers import FixtureVisionProvider
from assetflow.recognition.service import process_recognition_result
from assetflow.uploads import store_upload


def test_fixture_provider_loads_normalized_trade_response() -> None:
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition/trade_history.json"))

    result = provider.recognize(image_path=Path("unused.png"), broker="htsc_global")

    assert result.screenshot_type == "trade_history"
    assert result.transactions[0].symbol == "00700"
    assert result.transactions[0].currency == "HKD"


def test_process_trade_result_creates_candidate(settings, session) -> None:
    upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "trade.png", "image/png", b"\x89PNG\r\n\x1a\nabc")
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition/trade_history.json"))
    result = provider.recognize(Path(upload.image_path), "htsc_global")

    process_recognition_result(session, upload, provider, result)

    ocr = session.exec(select(OcrResult)).one()
    candidate = session.exec(select(CandidateTransaction)).one()
    assert ocr.screenshot_type == "trade_history"
    assert candidate.symbol == "00700"
    assert candidate.review_status == "pending"


def test_process_position_result_creates_snapshot(settings, session) -> None:
    upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "position.png", "image/png", b"\x89PNG\r\n\x1a\nxyz")
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition/positions.json"))
    result = provider.recognize(Path(upload.image_path), "htsc_global")

    process_recognition_result(session, upload, provider, result)

    snapshot = session.exec(select(PositionSnapshot)).one()
    assert snapshot.symbol == "00700"
    assert snapshot.quantity == 100
