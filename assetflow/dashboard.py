from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlmodel import Session, select

from assetflow.models import CashSnapshot, CandidateTransaction, PositionSnapshot, Transaction, Upload


def _decimal_map_to_strings(values: dict[str, Decimal]) -> dict[str, str]:
    return {key: str(value) for key, value in values.items()}


def _latest_positions(session: Session) -> list[PositionSnapshot]:
    snapshots = session.exec(select(PositionSnapshot)).all()
    latest: dict[tuple[str, str | None, str | None, str, str], PositionSnapshot] = {}
    for snapshot in snapshots:
        key = (snapshot.broker, snapshot.account_alias, snapshot.market, snapshot.symbol, snapshot.currency)
        if key not in latest or snapshot.snapshot_at > latest[key].snapshot_at:
            latest[key] = snapshot
    return sorted(latest.values(), key=lambda item: (item.market or "", item.symbol))


def _latest_cash(session: Session) -> list[CashSnapshot]:
    snapshots = session.exec(select(CashSnapshot)).all()
    latest: dict[tuple[str, str | None, str], CashSnapshot] = {}
    for snapshot in snapshots:
        key = (snapshot.broker, snapshot.account_alias, snapshot.currency)
        if key not in latest or snapshot.snapshot_at > latest[key].snapshot_at:
            latest[key] = snapshot
    return sorted(latest.values(), key=lambda item: item.currency)


def _upload_payload(upload: Upload) -> dict[str, object]:
    return {
        "id": upload.id,
        "created_at": upload.created_at,
        "broker": upload.broker,
        "account_alias": upload.account_alias,
        "source": upload.source,
        "original_filename": upload.original_filename,
        "mime_type": upload.mime_type,
        "file_size_bytes": upload.file_size_bytes,
        "status": upload.status,
        "duplicate_of_upload_id": upload.duplicate_of_upload_id,
    }


def dashboard_summary(session: Session) -> dict[str, object]:
    positions = _latest_positions(session)
    cash = _latest_cash(session)
    cash_by_currency: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in cash:
        cash_by_currency[item.currency] += item.cash_balance or Decimal("0")
    position_value_by_currency: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in positions:
        position_value_by_currency[item.currency] += item.market_value or Decimal("0")
    pending_review_count = session.exec(
        select(func.count(CandidateTransaction.id)).where(
            CandidateTransaction.review_status.in_(["pending", "needs_review"])
        )
    ).one()
    recent_transactions = session.exec(select(Transaction).order_by(Transaction.created_at.desc()).limit(10)).all()
    latest_uploads = session.exec(select(Upload).order_by(Upload.created_at.desc()).limit(10)).all()
    recent_uploads = [_upload_payload(upload) for upload in latest_uploads]
    return {
        "pending_review_count": pending_review_count,
        "cash_by_currency": _decimal_map_to_strings(cash_by_currency),
        "position_value_by_currency": _decimal_map_to_strings(position_value_by_currency),
        "recent_transactions": recent_transactions,
        "recent_uploads": recent_uploads,
    }


def list_transactions(
    session: Session,
    *,
    currency: str | None = None,
    symbol: str | None = None,
    trade_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[Transaction]:
    query = select(Transaction)
    if currency:
        query = query.where(Transaction.currency == currency)
    if symbol:
        query = query.where(Transaction.symbol == symbol)
    if trade_type:
        query = query.where(Transaction.trade_type == trade_type)
    if date_from:
        query = query.where(Transaction.trade_date >= date_from)
    if date_to:
        query = query.where(Transaction.trade_date <= date_to)
    return session.exec(query.order_by(Transaction.trade_date.desc(), Transaction.created_at.desc())).all()


def latest_positions(session: Session) -> list[PositionSnapshot]:
    return _latest_positions(session)


def latest_cash(session: Session) -> list[CashSnapshot]:
    return _latest_cash(session)


def recent_uploads(session: Session) -> list[dict[str, object]]:
    uploads = session.exec(select(Upload).order_by(Upload.created_at.desc()).limit(50)).all()
    return [_upload_payload(upload) for upload in uploads]
