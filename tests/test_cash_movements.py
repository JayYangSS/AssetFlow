from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import select

from assetflow.api import create_app
from assetflow.models import Transaction


def test_cash_movement_cash_in_creates_positive_manual_transaction(settings, session) -> None:
    app = create_app(settings=settings, session=session)
    client = TestClient(app)

    response = client.post(
        "/api/cash/movements",
        json={
            "broker": "htsc_global",
            "trade_type": "cash_in",
            "trade_date": "2026-05-04",
            "currency": "USD",
            "amount": "-123.45",
        },
    )

    assert response.status_code == 200
    transaction = session.exec(select(Transaction)).one()
    assert response.json() == {"transaction_id": transaction.id}
    assert transaction.symbol == "CASH"
    assert transaction.security_name == "Cash"
    assert transaction.quantity == Decimal("0")
    assert transaction.price == Decimal("0")
    assert transaction.net_amount == Decimal("123.45")
    assert transaction.source_upload_id is None
    assert transaction.source_ocr_result_id is None
    assert transaction.source_candidate_id is None
    assert transaction.confidence == 1.0


def test_cash_movement_cash_out_creates_negative_manual_transaction(settings, session) -> None:
    app = create_app(settings=settings, session=session)
    client = TestClient(app)

    response = client.post(
        "/api/cash/movements",
        json={
            "broker": "htsc_global",
            "trade_type": "cash_out",
            "trade_date": "2026-05-04",
            "currency": "USD",
            "amount": "123.45",
        },
    )

    assert response.status_code == 200
    transaction = session.exec(select(Transaction)).one()
    assert transaction.net_amount == Decimal("-123.45")


def test_cash_movement_default_creates_distinct_transactions_for_equivalent_decimal_amounts(settings, session) -> None:
    app = create_app(settings=settings, session=session)
    client = TestClient(app)
    payload = {
        "broker": "htsc_global",
        "trade_type": "cash_in",
        "trade_date": "2026-05-04",
        "currency": "USD",
        "amount": "123.45",
    }

    first = client.post("/api/cash/movements", json=payload)
    second = client.post("/api/cash/movements", json={**payload, "amount": "123.450"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() != first.json()
    transactions = session.exec(select(Transaction)).all()
    assert len(transactions) == 2
    assert len({tx.dedupe_key for tx in transactions}) == 2


def test_cash_movement_explicit_idempotency_key_returns_existing_transaction(settings, session) -> None:
    app = create_app(settings=settings, session=session)
    client = TestClient(app)
    payload = {
        "broker": "htsc_global",
        "trade_type": "cash_in",
        "trade_date": "2026-05-04",
        "currency": "USD",
        "amount": "123.45",
        "idempotency_key": "form-submit-123",
    }

    first = client.post("/api/cash/movements", json=payload)
    second = client.post("/api/cash/movements", json={**payload, "amount": "999.99"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    transactions = session.exec(select(Transaction)).all()
    assert len(transactions) == 1
    assert transactions[0].net_amount == Decimal("123.45")
    assert "form-submit-123" not in transactions[0].dedupe_key


def test_cash_movement_different_idempotency_keys_create_distinct_transactions(settings, session) -> None:
    app = create_app(settings=settings, session=session)
    client = TestClient(app)
    payload = {
        "broker": "htsc_global",
        "trade_type": "cash_in",
        "trade_date": "2026-05-04",
        "currency": "USD",
        "amount": "123.45",
    }

    first = client.post("/api/cash/movements", json={**payload, "idempotency_key": "submit-a"})
    second = client.post("/api/cash/movements", json={**payload, "idempotency_key": "submit-b"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() != first.json()
    assert len(session.exec(select(Transaction)).all()) == 2


def test_cash_movement_adjustment_preserves_amount_sign(settings, session) -> None:
    app = create_app(settings=settings, session=session)
    client = TestClient(app)

    response = client.post(
        "/api/cash/movements",
        json={
            "broker": "htsc_global",
            "trade_type": "adjustment",
            "trade_date": "2026-05-04",
            "currency": "USD",
            "amount": "-12.34",
        },
    )

    assert response.status_code == 200
    transaction = session.exec(select(Transaction)).one()
    assert transaction.net_amount == Decimal("-12.34")
