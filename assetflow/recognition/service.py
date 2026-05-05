from datetime import date, time

from sqlmodel import Session, select

from assetflow.domain import build_dedupe_key
from assetflow.models import CandidateTransaction, CashSnapshot, OcrResult, PositionSnapshot, Transaction, Upload
from assetflow.recognition.providers import VisionProvider
from assetflow.recognition.schemas import RecognizedScreenshot, RecognizedTransaction


CandidateIdentity = tuple[str, str | None, str, date, time]


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
            gross_amount=item.gross_amount,
            net_amount=item.net_amount,
            commission=item.commission,
            fees=item.fees,
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
                net_amount=item.net_amount,
                currency=item.currency,
            ),
            confidence=item.confidence,
            review_status="pending",
        )
        session.add(candidate)

    for item in result.positions:
        session.add(
            PositionSnapshot(
                upload_id=upload.id,
                ocr_result_id=ocr.id,
                broker=item.broker,
                account_alias=item.account_alias,
                market=item.market,
                symbol=item.symbol,
                security_name=item.security_name,
                quantity=item.quantity,
                available_quantity=item.available_quantity,
                cost_price=item.cost_price,
                market_price=item.market_price,
                market_value=item.market_value,
                unrealized_pnl=item.unrealized_pnl,
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
