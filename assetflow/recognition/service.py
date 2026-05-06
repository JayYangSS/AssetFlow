from datetime import date, time

from sqlmodel import Session, select

from assetflow.domain import build_dedupe_key
from assetflow.models import CandidateTransaction, CashSnapshot, OcrResult, PositionSnapshot, Transaction, Upload
from assetflow.position_snapshots import hide_shifted_current_cost_fields
from assetflow.recognition.providers import VisionProvider
from assetflow.recognition.schemas import RecognizedScreenshot, RecognizedTransaction
from assetflow.transaction_costs import estimate_transaction_costs


CandidateIdentity = tuple[str, str | None, str, date, time]
PositionIdentity = tuple[str, str | None, str | None, str, str]


def _candidate_identity(item: RecognizedTransaction) -> CandidateIdentity | None:
    if item.symbol is None or item.trade_date is None or item.trade_time is None:
        return None
    return (item.broker, item.account_alias, item.symbol, item.trade_date, item.trade_time)


def _candidate_identity_exists(session: Session, identity: CandidateIdentity) -> bool:
    broker, account_alias, symbol, trade_date, trade_time = identity
    account_filter = (
        CandidateTransaction.account_alias.is_(None)
        if account_alias is None
        else CandidateTransaction.account_alias == account_alias
    )
    existing_candidate = session.exec(
        select(CandidateTransaction).where(
            CandidateTransaction.broker == broker,
            account_filter,
            CandidateTransaction.symbol == symbol,
            CandidateTransaction.trade_date == trade_date,
            CandidateTransaction.trade_time == trade_time,
        )
    ).first()
    if existing_candidate is not None:
        return True
    transaction_account_filter = (
        Transaction.account_alias.is_(None) if account_alias is None else Transaction.account_alias == account_alias
    )
    return (
        session.exec(
            select(Transaction).where(
                Transaction.broker == broker,
                transaction_account_filter,
                Transaction.symbol == symbol,
                Transaction.trade_date == trade_date,
                Transaction.trade_time == trade_time,
            )
        ).first()
        is not None
    )


def _position_identity(item) -> PositionIdentity:
    return (item.broker, item.account_alias, item.market, item.symbol, item.currency)


def _latest_position_snapshot(session: Session, identity: PositionIdentity) -> PositionSnapshot | None:
    broker, account_alias, market, symbol, currency = identity
    account_filter = (
        PositionSnapshot.account_alias.is_(None)
        if account_alias is None
        else PositionSnapshot.account_alias == account_alias
    )
    market_filter = PositionSnapshot.market.is_(None) if market is None else PositionSnapshot.market == market
    return session.exec(
        select(PositionSnapshot)
        .where(
            PositionSnapshot.broker == broker,
            account_filter,
            market_filter,
            PositionSnapshot.symbol == symbol,
            PositionSnapshot.currency == currency,
        )
        .order_by(PositionSnapshot.snapshot_at.desc(), PositionSnapshot.id.desc())
    ).first()


def _merge_value(new_value, old_value):
    return new_value if new_value is not None else old_value


def _looks_like_shifted_current_cost_merge(previous: PositionSnapshot, item) -> bool:
    return (
        item.quantity is None
        and item.market_value is None
        and item.daily_pnl is None
        and item.cost_price is not None
        and item.market_price is not None
        and item.unrealized_pnl is not None
        and previous.quantity == item.cost_price
        and previous.market_value == item.market_price
        and previous.daily_pnl == item.unrealized_pnl
    )


def _previous_for_position_merge(previous: PositionSnapshot | None, item) -> PositionSnapshot | None:
    if previous is None:
        return None
    if _looks_like_shifted_current_cost_merge(previous, item):
        values = {name: getattr(previous, name) for name in PositionSnapshot.model_fields}
        values.update(quantity=None, market_value=None, daily_pnl=None)
        return PositionSnapshot(**values)
    return hide_shifted_current_cost_fields(previous)


def process_recognition_result(
    session: Session,
    upload: Upload,
    provider: VisionProvider,
    result: RecognizedScreenshot,
) -> OcrResult:
    raw_json = result.model_dump_json()
    ocr = OcrResult(
        upload_id=upload.id,
        provider=provider.provider_name,
        model=provider.model_name,
        screenshot_type=result.screenshot_type,
        confidence=result.confidence,
        raw_json=raw_json,
        normalized_json=raw_json,
    )
    session.add(ocr)
    session.commit()
    session.refresh(ocr)

    seen_identities: set[CandidateIdentity] = set()
    for item in result.transactions:
        identity = _candidate_identity(item)
        if identity is not None:
            if identity in seen_identities or _candidate_identity_exists(session, identity):
                continue
            seen_identities.add(identity)
        costs = estimate_transaction_costs(
            broker=item.broker,
            market=item.market,
            trade_type=item.trade_type,
            quantity=item.quantity,
            price=item.price,
            gross_amount=item.gross_amount,
            net_amount=item.net_amount,
            commission=item.commission,
            fees=item.fees,
        )
        candidate = CandidateTransaction(
            upload_id=upload.id,
            ocr_result_id=ocr.id,
            broker=item.broker,
            account_alias=item.account_alias,
            market=item.market,
            symbol=item.symbol,
            security_name=item.security_name,
            trade_type=item.trade_type,
            trade_date=item.trade_date,
            trade_time=item.trade_time,
            quantity=item.quantity,
            price=item.price,
            gross_amount=costs.gross_amount,
            net_amount=costs.net_amount,
            commission=costs.commission,
            fees=costs.fees,
            currency=item.currency,
            position_balance_after=item.position_balance_after,
            dedupe_key=build_dedupe_key(
                broker=item.broker,
                account_alias=item.account_alias,
                trade_date=item.trade_date,
                trade_time=item.trade_time,
                symbol=item.symbol,
                trade_type=item.trade_type,
                quantity=item.quantity,
                price=item.price,
                net_amount=costs.net_amount,
                currency=item.currency,
            ),
            confidence=item.confidence,
            review_status="pending",
        )
        session.add(candidate)

    for item in result.positions:
        previous = _previous_for_position_merge(_latest_position_snapshot(session, _position_identity(item)), item)
        session.add(
            PositionSnapshot(
                upload_id=upload.id,
                ocr_result_id=ocr.id,
                broker=item.broker,
                account_alias=item.account_alias,
                market=item.market,
                symbol=item.symbol,
                security_name=_merge_value(item.security_name, previous.security_name if previous else None),
                quantity=_merge_value(item.quantity, previous.quantity if previous else None),
                available_quantity=_merge_value(
                    item.available_quantity, previous.available_quantity if previous else None
                ),
                cost_price=_merge_value(item.cost_price, previous.cost_price if previous else None),
                market_price=_merge_value(item.market_price, previous.market_price if previous else None),
                market_value=_merge_value(item.market_value, previous.market_value if previous else None),
                daily_pnl=_merge_value(item.daily_pnl, previous.daily_pnl if previous else None),
                unrealized_pnl=_merge_value(item.unrealized_pnl, previous.unrealized_pnl if previous else None),
                currency=item.currency,
                snapshot_at=item.snapshot_at,
                confidence=item.confidence,
            )
        )

    for item in result.cash:
        session.add(
            CashSnapshot(
                upload_id=upload.id,
                ocr_result_id=ocr.id,
                broker=item.broker,
                account_alias=item.account_alias,
                currency=item.currency,
                cash_balance=item.cash_balance,
                available_cash=item.available_cash,
                frozen_cash=item.frozen_cash,
                market_value=item.market_value,
                total_assets=item.total_assets,
                snapshot_at=item.snapshot_at,
                confidence=item.confidence,
            )
        )

    upload.status = "recognized"
    session.add(upload)
    session.commit()
    return ocr
