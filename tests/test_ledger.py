from decimal import Decimal
from pathlib import Path

from sqlmodel import select

import pytest

from assetflow.ledger import auto_confirm_candidates, confirm_candidate
from assetflow.models import CandidateTransaction, Transaction
from assetflow.recognition.providers import FixtureVisionProvider
from assetflow.recognition.schemas import RecognizedScreenshot, RecognizedTransaction
from assetflow.recognition.service import process_recognition_result
from assetflow.uploads import store_upload


def _load_candidate(settings, session, fixture: str = "trade_history.json") -> CandidateTransaction:
    upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "trade.png", "image/png", b"\x89PNG\r\n\x1a\nabc")
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition") / fixture)
    result = provider.recognize(Path(upload.image_path), "htsc_global")
    process_recognition_result(session, upload, provider, result)
    return session.exec(select(CandidateTransaction)).one()


def test_auto_confirm_high_confidence_candidate(settings, session) -> None:
    _load_candidate(settings, session)

    confirmed = auto_confirm_candidates(session, min_confidence=0.90)

    transaction = session.exec(select(Transaction)).one()
    assert confirmed == 1
    assert transaction.symbol == "00700"
    assert transaction.status == "confirmed"


def test_confirm_candidate_does_not_duplicate(settings, session) -> None:
    candidate = _load_candidate(settings, session)

    first = confirm_candidate(session, candidate.id)
    second = confirm_candidate(session, candidate.id)

    assert first.id == second.id
    assert len(session.exec(select(Transaction)).all()) == 1


def test_confirm_candidate_second_call_keeps_confirmed_status(settings, session) -> None:
    candidate = _load_candidate(settings, session)

    first = confirm_candidate(session, candidate.id)
    second = confirm_candidate(session, candidate.id)

    session.refresh(candidate)
    assert first.id == second.id
    assert candidate.review_status == "confirmed"
    assert candidate.confirmed_transaction_id == first.id
    assert len(session.exec(select(Transaction)).all()) == 1


def test_confirm_candidate_rejects_ignored_candidate(settings, session) -> None:
    candidate = _load_candidate(settings, session)
    candidate.review_status = "ignored"
    session.add(candidate)
    session.commit()

    with pytest.raises(ValueError):
        confirm_candidate(session, candidate.id)

    session.refresh(candidate)
    assert candidate.review_status == "ignored"
    assert session.exec(select(Transaction)).all() == []


def test_auto_confirm_dedupes_same_trade_with_different_decimal_scales(settings, session) -> None:
    upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "trade.png", "image/png", b"\x89PNG\r\n\x1a\nabc")
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition/trade_history.json"))
    result = RecognizedScreenshot(
        screenshot_type="trade_history",
        confidence=0.96,
        transactions=[
            RecognizedTransaction(
                broker="htsc_global",
                market="HK",
                symbol="00700",
                security_name="Tencent Holdings",
                trade_type="buy",
                trade_date="2026-05-01",
                trade_time="10:10:10",
                quantity=Decimal("100"),
                price=Decimal("350.12"),
                net_amount=Decimal("-35035"),
                currency="HKD",
                confidence=0.97,
            ),
            RecognizedTransaction(
                broker="htsc_global",
                market="HK",
                symbol="00700",
                security_name="Tencent Holdings",
                trade_type="buy",
                trade_date="2026-05-01",
                trade_time="10:10:10",
                quantity=Decimal("100.000000"),
                price=Decimal("350.1200"),
                net_amount=Decimal("-35035.0000"),
                currency="HKD",
                confidence=0.97,
            ),
        ],
    )

    process_recognition_result(session, upload, provider, result)
    auto_confirm_candidates(session, min_confidence=0.90)

    transactions = session.exec(select(Transaction)).all()
    candidates = session.exec(select(CandidateTransaction)).all()
    assert len(transactions) == 1
    assert [candidate.review_status for candidate in candidates] == ["confirmed"]


def test_confirm_candidate_detects_existing_trade_when_dedupe_key_differs(settings, session) -> None:
    candidate = _load_candidate(settings, session)
    existing = Transaction(
        broker=candidate.broker,
        account_alias=candidate.account_alias,
        market=candidate.market,
        symbol=candidate.symbol,
        security_name=candidate.security_name,
        trade_type=candidate.trade_type,
        trade_date=candidate.trade_date,
        trade_time=candidate.trade_time,
        quantity=candidate.quantity,
        price=candidate.price,
        gross_amount=candidate.gross_amount,
        net_amount=candidate.net_amount,
        commission=candidate.commission,
        fees=candidate.fees,
        currency=candidate.currency,
        position_balance_after=candidate.position_balance_after,
        source_upload_id=candidate.upload_id,
        source_ocr_result_id=candidate.ocr_result_id,
        source_candidate_id=candidate.id,
        dedupe_key="legacy-decimal-format-key",
        confidence=candidate.confidence,
    )
    session.add(existing)
    session.commit()
    session.refresh(existing)

    confirmed = confirm_candidate(session, candidate.id)
    session.refresh(candidate)

    assert confirmed.id == existing.id
    assert len(session.exec(select(Transaction)).all()) == 1
    assert candidate.review_status == "duplicate"


def test_auto_confirm_dedupes_same_symbol_at_same_trade_time(settings, session) -> None:
    upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "trade.png", "image/png", b"\x89PNG\r\n\x1a\nabc")
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition/trade_history.json"))
    result = RecognizedScreenshot(
        screenshot_type="trade_history",
        confidence=0.96,
        transactions=[
            RecognizedTransaction(
                broker="htsc_global",
                market="HK",
                symbol="00700",
                security_name="Tencent Holdings",
                trade_type="buy",
                trade_date="2026-05-01",
                trade_time="10:10:10",
                quantity=Decimal("100"),
                price=Decimal("350.12"),
                net_amount=Decimal("-35035"),
                currency="HKD",
                confidence=0.97,
            ),
            RecognizedTransaction(
                broker="htsc_global",
                market="HK",
                symbol="00700",
                security_name="Tencent Holdings",
                trade_type="buy",
                trade_date="2026-05-01",
                trade_time="10:10:10",
                quantity=Decimal("200"),
                price=Decimal("351.00"),
                net_amount=Decimal("-70220"),
                currency="HKD",
                confidence=0.97,
            ),
        ],
    )

    process_recognition_result(session, upload, provider, result)
    auto_confirm_candidates(session, min_confidence=0.90)

    transactions = session.exec(select(Transaction)).all()
    candidates = session.exec(select(CandidateTransaction)).all()
    assert len(transactions) == 1
    assert [candidate.review_status for candidate in candidates] == ["confirmed"]


def test_auto_confirm_dedupes_same_symbol_at_same_trade_time_across_uploads(settings, session) -> None:
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
                confidence=0.97,
            )
        ],
    )
    first_upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "first.png", "image/png", b"\x89PNG\r\n\x1a\nfirst")
    second_upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "second.png", "image/png", b"\x89PNG\r\n\x1a\nsecond")

    process_recognition_result(session, first_upload, provider, result)
    auto_confirm_candidates(session, min_confidence=0.90)
    process_recognition_result(session, second_upload, provider, result)
    auto_confirm_candidates(session, min_confidence=0.90)

    transactions = session.exec(select(Transaction)).all()
    candidates = session.exec(select(CandidateTransaction)).all()
    assert len(transactions) == 1
    assert [candidate.review_status for candidate in candidates] == ["confirmed"]


def test_confirm_candidate_dedupes_same_symbol_at_same_trade_time_before_completeness_check(settings, session) -> None:
    complete_candidate = _load_candidate(settings, session)
    existing = confirm_candidate(session, complete_candidate.id)
    incomplete_candidate = CandidateTransaction(
        upload_id=complete_candidate.upload_id,
        ocr_result_id=complete_candidate.ocr_result_id,
        broker=complete_candidate.broker,
        account_alias=complete_candidate.account_alias,
        market=complete_candidate.market,
        symbol=complete_candidate.symbol,
        security_name=complete_candidate.security_name,
        trade_type=complete_candidate.trade_type,
        trade_date=complete_candidate.trade_date,
        trade_time=complete_candidate.trade_time,
        quantity=complete_candidate.quantity,
        price=complete_candidate.price,
        net_amount=None,
        currency=complete_candidate.currency,
        dedupe_key="incomplete-duplicate",
        confidence=complete_candidate.confidence,
        review_status="pending",
    )
    session.add(incomplete_candidate)
    session.commit()
    session.refresh(incomplete_candidate)

    confirmed = confirm_candidate(session, incomplete_candidate.id)
    session.refresh(incomplete_candidate)

    assert confirmed.id == existing.id
    assert len(session.exec(select(Transaction)).all()) == 1
    assert incomplete_candidate.review_status == "duplicate"
