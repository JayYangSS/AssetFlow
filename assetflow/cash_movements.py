from datetime import date
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

from sqlmodel import Session, select

from assetflow.domain import SUPPORTED_BROKERS, SUPPORTED_CURRENCIES
from assetflow.models import Transaction


CASH_MOVEMENT_TYPES = {"cash_in", "cash_out", "dividend", "fee", "adjustment"}
NEGATIVE_CASH_MOVEMENT_TYPES = {"cash_out", "fee"}


def create_cash_movement(
    session: Session,
    *,
    broker: str,
    account_alias: str | None,
    trade_type: str,
    trade_date: date,
    currency: str,
    amount: Decimal,
    idempotency_key: str | None = None,
) -> Transaction:
    if broker not in SUPPORTED_BROKERS:
        raise ValueError(f"Unsupported broker: {broker}")
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported currency: {currency}")
    if trade_type not in CASH_MOVEMENT_TYPES:
        raise ValueError(f"Unsupported cash movement type: {trade_type}")

    net_amount = _normalize_decimal(_signed_net_amount(trade_type, amount))
    dedupe_key = _manual_cash_dedupe_key(idempotency_key)
    existing = session.exec(select(Transaction).where(Transaction.dedupe_key == dedupe_key)).first()
    if existing is not None:
        return existing

    transaction = Transaction(
        broker=broker,
        account_alias=account_alias,
        symbol="CASH",
        security_name="Cash",
        trade_type=trade_type,
        trade_date=trade_date,
        quantity=Decimal("0"),
        price=Decimal("0"),
        net_amount=net_amount,
        currency=currency,
        source_upload_id=None,
        source_ocr_result_id=None,
        source_candidate_id=None,
        dedupe_key=dedupe_key,
        confidence=1.0,
    )
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return transaction


def _signed_net_amount(trade_type: str, amount: Decimal) -> Decimal:
    if trade_type in NEGATIVE_CASH_MOVEMENT_TYPES:
        return -abs(amount)
    if trade_type == "adjustment":
        return amount
    return abs(amount)


def _normalize_decimal(value: Decimal) -> Decimal:
    return value.normalize()


def _manual_cash_dedupe_key(idempotency_key: str | None) -> str:
    if idempotency_key is None or not idempotency_key.strip():
        return f"manual-cash:{uuid4().hex}"
    hashed_key = sha256(idempotency_key.encode("utf-8")).hexdigest()
    return f"manual-cash:idempotent:{hashed_key}"
