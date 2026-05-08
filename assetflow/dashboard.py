from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, func
from sqlmodel import Session, select

from assetflow.cash_movements import CASH_MOVEMENT_TYPES
from assetflow.models import CashSnapshot, CandidateTransaction, PositionSnapshot, Transaction, Upload
from assetflow.position_snapshots import hide_shifted_current_cost_fields
from assetflow.returns import RETURN_TRADE_TYPES, summarize_returns


CASH_MOVEMENT_TYPE_VALUES = tuple(sorted(CASH_MOVEMENT_TYPES))


def _decimal_map_to_strings(values: dict[str, Decimal]) -> dict[str, str]:
    return {key: str(value) for key, value in values.items()}


def _decimal_to_string(value: Decimal) -> str:
    return str(value)


def _return_decimal_to_string(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.000001")))


def _asset_totals_payload(
    cash_by_currency: dict[str, Decimal],
    position_value_by_currency: dict[str, Decimal],
) -> list[dict[str, str]]:
    payload = []
    for currency in sorted(set(cash_by_currency) | set(position_value_by_currency)):
        cash_balance = cash_by_currency.get(currency, Decimal("0"))
        position_value = position_value_by_currency.get(currency, Decimal("0"))
        payload.append(
            {
                "currency": currency,
                "position_value": _decimal_to_string(position_value),
                "cash_balance": _decimal_to_string(cash_balance),
                "total_assets": _decimal_to_string(position_value + cash_balance),
            }
        )
    return payload


def _latest_positions(session: Session) -> list[PositionSnapshot]:
    latest_timestamp = (
        select(
            PositionSnapshot.broker,
            PositionSnapshot.account_alias,
            PositionSnapshot.market,
            PositionSnapshot.symbol,
            PositionSnapshot.currency,
            func.max(PositionSnapshot.snapshot_at).label("snapshot_at"),
        )
        .group_by(
            PositionSnapshot.broker,
            PositionSnapshot.account_alias,
            PositionSnapshot.market,
            PositionSnapshot.symbol,
            PositionSnapshot.currency,
        )
        .subquery()
    )
    latest_id = (
        select(
            PositionSnapshot.broker,
            PositionSnapshot.account_alias,
            PositionSnapshot.market,
            PositionSnapshot.symbol,
            PositionSnapshot.currency,
            func.max(PositionSnapshot.id).label("id"),
        )
        .join(
            latest_timestamp,
            and_(
                PositionSnapshot.broker == latest_timestamp.c.broker,
                PositionSnapshot.account_alias.is_not_distinct_from(latest_timestamp.c.account_alias),
                PositionSnapshot.market.is_not_distinct_from(latest_timestamp.c.market),
                PositionSnapshot.symbol == latest_timestamp.c.symbol,
                PositionSnapshot.currency == latest_timestamp.c.currency,
                PositionSnapshot.snapshot_at == latest_timestamp.c.snapshot_at,
            ),
        )
        .group_by(
            PositionSnapshot.broker,
            PositionSnapshot.account_alias,
            PositionSnapshot.market,
            PositionSnapshot.symbol,
            PositionSnapshot.currency,
        )
        .subquery()
    )
    positions = session.exec(
        select(PositionSnapshot)
        .join(latest_id, PositionSnapshot.id == latest_id.c.id)
        .order_by(PositionSnapshot.market, PositionSnapshot.symbol)
    ).all()
    return [hide_shifted_current_cost_fields(position) for position in positions]


def _latest_cash(session: Session) -> list[CashSnapshot]:
    latest_timestamp = (
        select(
            CashSnapshot.broker,
            CashSnapshot.account_alias,
            CashSnapshot.currency,
            func.max(CashSnapshot.snapshot_at).label("snapshot_at"),
        )
        .group_by(CashSnapshot.broker, CashSnapshot.account_alias, CashSnapshot.currency)
        .subquery()
    )
    latest_id = (
        select(
            CashSnapshot.broker,
            CashSnapshot.account_alias,
            CashSnapshot.currency,
            func.max(CashSnapshot.id).label("id"),
        )
        .join(
            latest_timestamp,
            and_(
                CashSnapshot.broker == latest_timestamp.c.broker,
                CashSnapshot.account_alias.is_not_distinct_from(latest_timestamp.c.account_alias),
                CashSnapshot.currency == latest_timestamp.c.currency,
                CashSnapshot.snapshot_at == latest_timestamp.c.snapshot_at,
            ),
        )
        .group_by(CashSnapshot.broker, CashSnapshot.account_alias, CashSnapshot.currency)
        .subquery()
    )
    return session.exec(
        select(CashSnapshot)
        .join(latest_id, CashSnapshot.id == latest_id.c.id)
        .order_by(CashSnapshot.currency)
    ).all()


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
        if item.market_value is not None:
            position_value_by_currency[item.currency] += item.market_value
    pending_review_count = session.exec(
        select(func.count(CandidateTransaction.id)).where(
            CandidateTransaction.review_status.in_(["pending", "needs_review"])
        )
    ).one()
    recent_transactions = list_transactions(session, limit=10)
    latest_uploads = session.exec(select(Upload).order_by(Upload.created_at.desc()).limit(10)).all()
    recent_uploads = [_upload_payload(upload) for upload in latest_uploads]
    return {
        "pending_review_count": pending_review_count,
        "cash_by_currency": _decimal_map_to_strings(cash_by_currency),
        "position_value_by_currency": _decimal_map_to_strings(position_value_by_currency),
        "asset_totals": _asset_totals_payload(cash_by_currency, position_value_by_currency),
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
    limit: int = 100,
) -> list[Transaction]:
    limit = min(max(limit, 1), 500)
    query = select(Transaction).where(~Transaction.trade_type.in_(CASH_MOVEMENT_TYPE_VALUES))
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
    return session.exec(query.order_by(Transaction.trade_date.desc(), Transaction.created_at.desc()).limit(limit)).all()


def transaction_profit_summary(
    session: Session,
    *,
    currency: str | None = None,
    symbol: str | None = None,
) -> list[dict[str, object]]:
    query = select(Transaction).where(Transaction.trade_type.in_(RETURN_TRADE_TYPES))
    if currency:
        query = query.where(Transaction.currency == currency)
    if symbol:
        query = query.where(Transaction.symbol == symbol)
    transactions = session.exec(
        query.order_by(Transaction.trade_date, Transaction.trade_time, Transaction.created_at, Transaction.id)
    ).all()
    return [_return_summary_payload(summary) for summary in summarize_returns(transactions)]


def _return_summary_payload(summary) -> dict[str, object]:
    values = summary.as_dict()
    return {
        "currency": values["currency"],
        "total_return": _return_decimal_to_string(values["total_return"]),
        "realized_pnl": _return_decimal_to_string(values["realized_pnl"]),
        "dividends": _return_decimal_to_string(values["dividends"]),
        "extra_fees": _return_decimal_to_string(values["extra_fees"]),
        "sell_proceeds": _return_decimal_to_string(values["sell_proceeds"]),
        "matched_cost": _return_decimal_to_string(values["matched_cost"]),
        "sell_quantity": _return_decimal_to_string(values["sell_quantity"]),
        "unmatched_quantity": _decimal_to_string(values["unmatched_quantity"]),
        "transaction_count": values["transaction_count"],
        "incomplete_count": values["incomplete_count"],
    }


def list_cash_movements(
    session: Session,
    *,
    currency: str | None = None,
    limit: int = 100,
) -> list[Transaction]:
    limit = min(max(limit, 1), 500)
    query = select(Transaction).where(Transaction.trade_type.in_(CASH_MOVEMENT_TYPE_VALUES))
    if currency:
        query = query.where(Transaction.currency == currency)
    return session.exec(
        query.order_by(Transaction.trade_date.desc(), Transaction.trade_time.desc(), Transaction.created_at.desc()).limit(limit)
    ).all()


def cash_movement_summary(session: Session) -> list[dict[str, object]]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    counts: dict[str, int] = defaultdict(int)
    transactions = session.exec(select(Transaction).where(Transaction.trade_type.in_(CASH_MOVEMENT_TYPE_VALUES))).all()
    for transaction in transactions:
        totals[transaction.currency] += transaction.net_amount
        counts[transaction.currency] += 1
    return [
        {
            "currency": currency,
            "cumulative_cash_change": _decimal_to_string(totals[currency]),
            "transaction_count": counts[currency],
        }
        for currency in sorted(totals)
    ]


def latest_positions(session: Session) -> list[PositionSnapshot]:
    return _latest_positions(session)


def latest_cash(session: Session) -> list[CashSnapshot]:
    return _latest_cash(session)


def recent_uploads(session: Session) -> list[dict[str, object]]:
    uploads = session.exec(select(Upload).order_by(Upload.created_at.desc()).limit(50)).all()
    return [_upload_payload(upload) for upload in uploads]
