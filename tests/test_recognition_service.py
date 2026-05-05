from pathlib import Path
from datetime import date, time
from decimal import Decimal

from sqlmodel import select

from assetflow.models import CandidateTransaction, OcrResult, PositionSnapshot, Transaction
from assetflow.recognition.providers import FixtureVisionProvider
from assetflow.recognition.schemas import RecognizedScreenshot, RecognizedTransaction
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


def test_process_trade_result_skips_duplicate_candidates_in_same_ocr_result(settings, session) -> None:
    upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "trade.png", "image/png", b"\x89PNG\r\n\x1a\nabc")
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition/trade_history.json"))
    result = RecognizedScreenshot(
        screenshot_type="trade_history",
        confidence=0.96,
        transactions=[
            RecognizedTransaction(
                broker="htsc_global",
                market="HK",
                symbol="02015",
                security_name="Li Auto-W",
                trade_type="buy",
                trade_date="2026-04-24",
                trade_time="09:42:00",
                quantity=Decimal("100"),
                price=Decimal("71"),
                currency="HKD",
                confidence=0.75,
            ),
            RecognizedTransaction(
                broker="htsc_global",
                market="HK",
                symbol="02015",
                security_name="Li Auto-W",
                trade_type="buy",
                trade_date="2026-04-24",
                trade_time="09:42:00",
                quantity=Decimal("100"),
                price=Decimal("71"),
                currency="HKD",
                confidence=0.75,
            ),
        ],
    )

    process_recognition_result(session, upload, provider, result)

    candidates = session.exec(select(CandidateTransaction)).all()
    assert len(candidates) == 1
    assert candidates[0].symbol == "02015"


def test_process_trade_result_defaults_htsc_hk_costs_when_missing(settings, session) -> None:
    upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "trade.png", "image/png", b"\x89PNG\r\n\x1a\nabc")
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition/trade_history.json"))
    result = RecognizedScreenshot(
        screenshot_type="trade_history",
        confidence=0.96,
        transactions=[
            RecognizedTransaction(
                broker="htsc_global",
                market="HK",
                symbol="02015",
                security_name="Li Auto-W",
                trade_type="buy",
                trade_date="2026-04-24",
                trade_time="09:42:00",
                quantity=Decimal("100"),
                price=Decimal("71"),
                currency="HKD",
                confidence=0.75,
            )
        ],
    )

    process_recognition_result(session, upload, provider, result)

    candidate = session.exec(select(CandidateTransaction)).one()
    assert candidate.gross_amount == Decimal("7100.000000")
    assert candidate.commission == Decimal("0.000000")
    assert candidate.fees == Decimal("8.900000")
    assert candidate.net_amount == Decimal("-7108.900000")


def test_process_trade_result_skips_duplicate_candidates_across_uploads(settings, session) -> None:
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition/trade_history.json"))
    result = RecognizedScreenshot(
        screenshot_type="trade_history",
        confidence=0.96,
        transactions=[
            RecognizedTransaction(
                broker="htsc_global",
                market="HK",
                symbol="02015",
                security_name="Li Auto-W",
                trade_type="buy",
                trade_date="2026-04-24",
                trade_time="09:42:00",
                quantity=Decimal("100"),
                price=Decimal("71"),
                currency="HKD",
                confidence=0.75,
            )
        ],
    )
    first_upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "first.png", "image/png", b"\x89PNG\r\n\x1a\nfirst")
    second_upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "second.png", "image/png", b"\x89PNG\r\n\x1a\nsecond")

    process_recognition_result(session, first_upload, provider, result)
    process_recognition_result(session, second_upload, provider, result)

    candidates = session.exec(select(CandidateTransaction)).all()
    assert len(candidates) == 1
    assert candidates[0].upload_id == first_upload.id


def test_process_trade_result_skips_candidate_when_transaction_exists(settings, session) -> None:
    upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "trade.png", "image/png", b"\x89PNG\r\n\x1a\nabc")
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition/trade_history.json"))
    result = RecognizedScreenshot(
        screenshot_type="trade_history",
        confidence=0.96,
        transactions=[
            RecognizedTransaction(
                broker="htsc_global",
                market="HK",
                symbol="02015",
                security_name="Li Auto-W",
                trade_type="buy",
                trade_date="2026-04-24",
                trade_time="09:42:00",
                quantity=Decimal("100"),
                price=Decimal("71"),
                net_amount=Decimal("-7100"),
                currency="HKD",
                confidence=0.75,
            )
        ],
    )
    session.add(
        Transaction(
            broker="htsc_global",
            market="HK",
            symbol="02015",
            security_name="Li Auto-W",
            trade_type="buy",
            trade_date=date(2026, 4, 24),
            trade_time=time(9, 42),
            quantity=Decimal("100"),
            price=Decimal("71"),
            net_amount=Decimal("-7100"),
            currency="HKD",
            source_upload_id=upload.id,
            source_ocr_result_id=1,
            source_candidate_id=1,
            dedupe_key="existing-transaction",
            confidence=0.75,
        )
    )
    session.commit()

    process_recognition_result(session, upload, provider, result)

    assert session.exec(select(CandidateTransaction)).all() == []


def test_process_position_result_creates_snapshot(settings, session) -> None:
    upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "position.png", "image/png", b"\x89PNG\r\n\x1a\nxyz")
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition/positions.json"))
    result = provider.recognize(Path(upload.image_path), "htsc_global")

    process_recognition_result(session, upload, provider, result)

    snapshot = session.exec(select(PositionSnapshot)).one()
    assert snapshot.symbol == "00700"
    assert snapshot.quantity == 100
