from datetime import datetime
from decimal import Decimal

from sqlmodel import select

from assetflow.models import PositionSnapshot, ReconciliationIssue, Transaction
from assetflow.reconciliation import reconcile_positions


def test_reconcile_matching_position_creates_no_issue(session) -> None:
    session.add(Transaction(
        broker="htsc_global",
        market="HK",
        symbol="00700",
        security_name="腾讯控股",
        trade_type="buy",
        trade_date=datetime(2026, 5, 1).date(),
        quantity=Decimal("100"),
        price=Decimal("350"),
        net_amount=Decimal("-35000"),
        currency="HKD",
        source_upload_id=1,
        source_ocr_result_id=1,
        source_candidate_id=1,
        dedupe_key="match",
        confidence=0.99,
    ))
    session.add(PositionSnapshot(
        upload_id=1,
        ocr_result_id=1,
        broker="htsc_global",
        market="HK",
        symbol="00700",
        quantity=Decimal("100"),
        currency="HKD",
        snapshot_at=datetime(2026, 5, 1, 16),
        confidence=0.95,
    ))
    session.commit()

    count = reconcile_positions(session, broker="htsc_global")

    assert count == 0
    assert session.exec(select(ReconciliationIssue)).all() == []


def test_reconcile_mismatch_creates_issue(session) -> None:
    session.add(Transaction(
        broker="htsc_global",
        market="HK",
        symbol="00700",
        security_name="腾讯控股",
        trade_type="buy",
        trade_date=datetime(2026, 5, 1).date(),
        quantity=Decimal("100"),
        price=Decimal("350"),
        net_amount=Decimal("-35000"),
        currency="HKD",
        source_upload_id=1,
        source_ocr_result_id=1,
        source_candidate_id=1,
        dedupe_key="mismatch",
        confidence=0.99,
    ))
    session.add(PositionSnapshot(
        upload_id=1,
        ocr_result_id=1,
        broker="htsc_global",
        market="HK",
        symbol="00700",
        quantity=Decimal("80"),
        currency="HKD",
        snapshot_at=datetime(2026, 5, 1, 16),
        confidence=0.95,
    ))
    session.commit()

    count = reconcile_positions(session, broker="htsc_global")

    issue = session.exec(select(ReconciliationIssue)).one()
    assert count == 1
    assert issue.expected_value == Decimal("100.000000")
    assert issue.observed_value == Decimal("80.000000")


def test_reconcile_skips_position_snapshot_without_quantity(session) -> None:
    session.add(PositionSnapshot(
        upload_id=1,
        ocr_result_id=1,
        broker="htsc_global",
        market="HK",
        symbol="00700",
        quantity=None,
        currency="HKD",
        snapshot_at=datetime(2026, 5, 1, 16),
        confidence=0.95,
    ))
    session.commit()

    count = reconcile_positions(session, broker="htsc_global")

    assert count == 0
    assert session.exec(select(ReconciliationIssue)).all() == []
