from datetime import date, datetime, time
from decimal import Decimal

from fastapi.testclient import TestClient

from assetflow.api import create_app
from assetflow.models import CashSnapshot, CandidateTransaction, PositionSnapshot, Transaction, Upload


def test_dashboard_summary_returns_core_counts_and_latest_snapshots(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="positions.png",
        content_hash="positions",
        image_path=str(settings.upload_dir / "positions.png"),
        mime_type="image/png",
        file_size_bytes=10,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    session.add(
        CandidateTransaction(
            upload_id=upload.id,
            ocr_result_id=1,
            broker="htsc_global",
            market="HK",
            symbol="02015",
            security_name="Li Auto-W",
            trade_type="buy",
            trade_date=date(2026, 4, 24),
            trade_time=time(9, 42),
            quantity=Decimal("100"),
            price=Decimal("71"),
            currency="HKD",
            dedupe_key="candidate",
            confidence=0.75,
            review_status="needs_review",
        )
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
            dedupe_key="tx",
            confidence=0.95,
        )
    )
    session.add(
        PositionSnapshot(
            upload_id=upload.id,
            ocr_result_id=1,
            broker="htsc_global",
            market="HK",
            symbol="02015",
            security_name="Li Auto-W",
            quantity=Decimal("100"),
            market_price=Decimal("80"),
            market_value=Decimal("8000"),
            unrealized_pnl=Decimal("900"),
            currency="HKD",
            snapshot_at=datetime(2026, 5, 4, 10, 0),
            confidence=0.9,
        )
    )
    session.add(
        CashSnapshot(
            upload_id=upload.id,
            ocr_result_id=1,
            broker="htsc_global",
            currency="HKD",
            cash_balance=Decimal("1200"),
            available_cash=Decimal("1200"),
            snapshot_at=datetime(2026, 5, 4, 10, 0),
            confidence=0.9,
        )
    )
    session.commit()

    client = TestClient(create_app(settings=settings, session=session))
    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["pending_review_count"] == 1
    assert body["cash_by_currency"]["HKD"] == "1200.000000"
    assert body["position_value_by_currency"]["HKD"] == "8000.000000"
    assert body["recent_transactions"][0]["symbol"] == "02015"
    assert body["recent_uploads"][0]["original_filename"] == "positions.png"


def test_transactions_api_filters_by_currency(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="trade.png",
        content_hash="trade",
        image_path=str(settings.upload_dir / "trade.png"),
        mime_type="image/png",
        file_size_bytes=10,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    for symbol, currency, key in [("02015", "HKD", "hkd"), ("AAPL", "USD", "usd")]:
        session.add(
            Transaction(
                broker="htsc_global",
                market="HK" if currency == "HKD" else "US",
                symbol=symbol,
                security_name=symbol,
                trade_type="buy",
                trade_date=date(2026, 5, 1),
                quantity=Decimal("1"),
                price=Decimal("10"),
                net_amount=Decimal("-10"),
                currency=currency,
                source_upload_id=upload.id,
                source_ocr_result_id=1,
                source_candidate_id=1,
                dedupe_key=key,
                confidence=0.9,
            )
        )
    session.commit()

    client = TestClient(create_app(settings=settings, session=session))
    response = client.get("/api/transactions", params={"currency": "HKD"})

    assert response.status_code == 200
    body = response.json()
    assert [item["symbol"] for item in body] == ["02015"]
