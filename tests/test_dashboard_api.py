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
    assert "image_path" not in body["recent_uploads"][0]
    assert "content_hash" not in body["recent_uploads"][0]


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


def test_transactions_api_defaults_to_bounded_result_set(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="many-trades.png",
        content_hash="many-trades",
        image_path=str(settings.upload_dir / "many-trades.png"),
        mime_type="image/png",
        file_size_bytes=10,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    for index in range(101):
        session.add(
            Transaction(
                broker="htsc_global",
                market="US",
                symbol=f"T{index:03d}",
                security_name=f"T{index:03d}",
                trade_type="buy",
                trade_date=date(2026, 5, 1),
                quantity=Decimal("1"),
                price=Decimal("10"),
                net_amount=Decimal("-10"),
                currency="USD",
                source_upload_id=upload.id,
                source_ocr_result_id=1,
                source_candidate_id=1,
                dedupe_key=f"bounded-{index}",
                confidence=0.9,
            )
        )
    session.commit()

    client = TestClient(create_app(settings=settings, session=session))
    response = client.get("/api/transactions")

    assert response.status_code == 200
    assert len(response.json()) == 100


def test_latest_positions_keeps_same_symbol_across_markets(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="positions.png",
        content_hash="positions-markets",
        image_path=str(settings.upload_dir / "positions.png"),
        mime_type="image/png",
        file_size_bytes=10,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    for market in ["HK", "US"]:
        session.add(
            PositionSnapshot(
                upload_id=upload.id,
                ocr_result_id=1,
                broker="htsc_global",
                market=market,
                symbol="XYZ",
                security_name="Cross Listed",
                quantity=Decimal("10"),
                market_value=Decimal("100"),
                currency="USD",
                snapshot_at=datetime(2026, 5, 4, 10, 0),
                confidence=0.9,
            )
        )
    session.commit()

    client = TestClient(create_app(settings=settings, session=session))
    response = client.get("/api/positions/latest")

    assert response.status_code == 200
    body = response.json()
    assert [(item["market"], item["symbol"]) for item in body] == [("HK", "XYZ"), ("US", "XYZ")]


def test_latest_cash_returns_newest_snapshot_for_account_currency(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        account_alias="main",
        source="web",
        original_filename="cash.png",
        content_hash="cash-latest",
        image_path=str(settings.upload_dir / "cash.png"),
        mime_type="image/png",
        file_size_bytes=10,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    for balance, snapshot_at in [
        (Decimal("100"), datetime(2026, 5, 3, 10, 0)),
        (Decimal("250"), datetime(2026, 5, 4, 10, 0)),
    ]:
        session.add(
            CashSnapshot(
                upload_id=upload.id,
                ocr_result_id=1,
                broker="htsc_global",
                account_alias="main",
                currency="HKD",
                cash_balance=balance,
                available_cash=balance,
                snapshot_at=snapshot_at,
                confidence=0.9,
            )
        )
    session.commit()

    client = TestClient(create_app(settings=settings, session=session))
    response = client.get("/api/cash/latest")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["cash_balance"] == "250.000000"


def test_latest_positions_breaks_snapshot_time_ties_by_greatest_id(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="position-tie.png",
        content_hash="position-tie",
        image_path=str(settings.upload_dir / "position-tie.png"),
        mime_type="image/png",
        file_size_bytes=10,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    for market_value in [Decimal("100"), Decimal("250")]:
        session.add(
            PositionSnapshot(
                upload_id=upload.id,
                ocr_result_id=1,
                broker="htsc_global",
                market="HK",
                symbol="02015",
                security_name="Li Auto-W",
                quantity=Decimal("10"),
                market_value=market_value,
                currency="HKD",
                snapshot_at=datetime(2026, 5, 4, 10, 0),
                confidence=0.9,
            )
        )
    session.commit()

    client = TestClient(create_app(settings=settings, session=session))
    response = client.get("/api/positions/latest")
    summary_response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["market_value"] == "250.000000"
    assert summary_response.status_code == 200
    assert summary_response.json()["position_value_by_currency"]["HKD"] == "250.000000"


def test_latest_positions_hides_shifted_current_cost_fields(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="position-shifted.png",
        content_hash="position-shifted",
        image_path=str(settings.upload_dir / "position-shifted.png"),
        mime_type="image/png",
        file_size_bytes=10,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    session.add(
        PositionSnapshot(
            upload_id=upload.id,
            ocr_result_id=1,
            broker="htsc_global",
            market="HK",
            symbol="00700",
            security_name="Tencent",
            quantity=Decimal("489.552"),
            cost_price=Decimal("489.552"),
            market_price=Decimal("472.200"),
            market_value=Decimal("472.200"),
            daily_pnl=Decimal("-1735.20"),
            unrealized_pnl=Decimal("-1735.20"),
            currency="HKD",
            snapshot_at=datetime(2026, 5, 5, 10, 0),
            confidence=0.75,
        )
    )
    session.commit()

    client = TestClient(create_app(settings=settings, session=session))
    response = client.get("/api/positions/latest")
    summary_response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["quantity"] is None
    assert body[0]["market_value"] is None
    assert body[0]["daily_pnl"] is None
    assert body[0]["market_price"] == "472.200000"
    assert body[0]["cost_price"] == "489.552000"
    assert body[0]["unrealized_pnl"] == "-1735.200000"
    assert summary_response.status_code == 200
    assert "HKD" not in summary_response.json()["position_value_by_currency"]


def test_latest_cash_breaks_snapshot_time_ties_by_greatest_id(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        account_alias="main",
        source="web",
        original_filename="cash-tie.png",
        content_hash="cash-tie",
        image_path=str(settings.upload_dir / "cash-tie.png"),
        mime_type="image/png",
        file_size_bytes=10,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    for balance in [Decimal("100"), Decimal("250")]:
        session.add(
            CashSnapshot(
                upload_id=upload.id,
                ocr_result_id=1,
                broker="htsc_global",
                account_alias="main",
                currency="HKD",
                cash_balance=balance,
                available_cash=balance,
                snapshot_at=datetime(2026, 5, 4, 10, 0),
                confidence=0.9,
            )
        )
    session.commit()

    client = TestClient(create_app(settings=settings, session=session))
    response = client.get("/api/cash/latest")
    summary_response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["cash_balance"] == "250.000000"
    assert summary_response.status_code == 200
    assert summary_response.json()["cash_by_currency"]["HKD"] == "250.000000"


def test_uploads_api_hides_local_storage_fields(settings, session) -> None:
    session.add(
        Upload(
            broker="htsc_global",
            source="web",
            original_filename="trade.png",
            content_hash="private-hash",
            image_path=str(settings.upload_dir / "trade.png"),
            mime_type="image/png",
            file_size_bytes=10,
            status="recognized",
        )
    )
    session.commit()

    client = TestClient(create_app(settings=settings, session=session))
    response = client.get("/api/uploads")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["original_filename"] == "trade.png"
    assert "image_path" not in body[0]
    assert "content_hash" not in body[0]


def test_dashboard_summary_includes_asset_totals_by_currency(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="assets.png",
        content_hash="asset-totals",
        image_path=str(settings.upload_dir / "assets.png"),
        mime_type="image/png",
        file_size_bytes=10,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    session.add(
        PositionSnapshot(
            upload_id=upload.id,
            ocr_result_id=1,
            broker="htsc_global",
            market="HK",
            symbol="00700",
            security_name="Tencent",
            quantity=Decimal("100"),
            market_value=Decimal("8000"),
            currency="HKD",
            snapshot_at=datetime(2026, 5, 7, 10, 0),
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
            snapshot_at=datetime(2026, 5, 7, 10, 0),
            confidence=0.9,
        )
    )
    session.add(
        CashSnapshot(
            upload_id=upload.id,
            ocr_result_id=1,
            broker="htsc_global",
            currency="USD",
            cash_balance=Decimal("300"),
            snapshot_at=datetime(2026, 5, 7, 10, 0),
            confidence=0.9,
        )
    )
    session.commit()

    client = TestClient(create_app(settings=settings, session=session))
    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    assert response.json()["asset_totals"] == [
        {
            "currency": "HKD",
            "position_value": "8000.000000",
            "cash_balance": "1200.000000",
            "total_assets": "9200.000000",
        },
        {
            "currency": "USD",
            "position_value": "0",
            "cash_balance": "300.000000",
            "total_assets": "300.000000",
        },
    ]


def test_transaction_profit_summary_returns_dividends_fees_and_fifo_pnl(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="returns.png",
        content_hash="return-summary",
        image_path=str(settings.upload_dir / "returns.png"),
        mime_type="image/png",
        file_size_bytes=10,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    for tx in [
        Transaction(
            broker="htsc_global",
            market="HK",
            symbol="00700",
            security_name="Tencent",
            trade_type="buy",
            trade_date=date(2026, 1, 2),
            quantity=Decimal("100"),
            price=Decimal("10"),
            net_amount=Decimal("-1008"),
            fees=Decimal("8"),
            currency="HKD",
            dedupe_key="summary-buy",
            confidence=0.95,
        ),
        Transaction(
            broker="htsc_global",
            market="HK",
            symbol="00700",
            security_name="Tencent",
            trade_type="sell",
            trade_date=date(2026, 2, 3),
            quantity=Decimal("40"),
            price=Decimal("12"),
            net_amount=Decimal("480"),
            fees=Decimal("5"),
            currency="HKD",
            dedupe_key="summary-sell",
            confidence=0.95,
        ),
        Transaction(
            broker="htsc_global",
            market="HK",
            symbol="00700",
            security_name="Tencent",
            trade_type="dividend",
            trade_date=date(2026, 3, 4),
            quantity=Decimal("0"),
            price=Decimal("0"),
            net_amount=Decimal("12"),
            currency="HKD",
            dedupe_key="summary-dividend",
            confidence=0.95,
        ),
        Transaction(
            broker="htsc_global",
            symbol="CASH",
            security_name="Cash",
            trade_type="fee",
            trade_date=date(2026, 3, 5),
            quantity=Decimal("0"),
            price=Decimal("0"),
            net_amount=Decimal("-3"),
            currency="HKD",
            dedupe_key="summary-fee",
            confidence=0.95,
        ),
    ]:
        session.add(tx)
    session.commit()

    from assetflow.dashboard import transaction_profit_summary

    summaries = transaction_profit_summary(session)

    assert summaries == [
        {
            "currency": "HKD",
            "total_return": "85.800000",
            "realized_pnl": "76.800000",
            "dividends": "12.000000",
            "extra_fees": "3.000000",
            "sell_proceeds": "480.000000",
            "matched_cost": "403.200000",
            "sell_quantity": "40.000000",
            "unmatched_quantity": "0",
            "transaction_count": 4,
            "incomplete_count": 0,
        }
    ]
