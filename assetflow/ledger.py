from sqlmodel import Session, select

from assetflow.domain import SUPPORTED_CURRENCIES, TEMPLATE_TRADE_TYPES
from assetflow.models import CandidateTransaction, Transaction


REQUIRED_FIELDS = (
    "symbol",
    "security_name",
    "trade_type",
    "trade_date",
    "quantity",
    "price",
    "net_amount",
    "currency",
)


def candidate_is_complete(candidate: CandidateTransaction) -> bool:
    return all(getattr(candidate, field) is not None for field in REQUIRED_FIELDS)


def candidate_can_auto_confirm(candidate: CandidateTransaction, min_confidence: float) -> bool:
    if candidate.review_status != "pending":
        return False
    if candidate.confidence < min_confidence:
        return False
    if not candidate_is_complete(candidate):
        return False
    if candidate.currency not in SUPPORTED_CURRENCIES:
        return False
    if candidate.trade_type not in TEMPLATE_TRADE_TYPES:
        return False
    if candidate.trade_type == "buy" and candidate.net_amount >= 0:
        return False
    if candidate.trade_type == "sell" and candidate.net_amount <= 0:
        return False
    return True


def confirm_candidate(session: Session, candidate_id: int) -> Transaction:
    candidate = session.get(CandidateTransaction, candidate_id)
    if candidate is None:
        raise ValueError(f"Candidate not found: {candidate_id}")
    existing = session.exec(select(Transaction).where(Transaction.dedupe_key == candidate.dedupe_key)).first()
    if existing is not None:
        candidate.review_status = "duplicate"
        candidate.confirmed_transaction_id = existing.id
        session.add(candidate)
        session.commit()
        return existing
    if not candidate_is_complete(candidate):
        candidate.review_status = "needs_review"
        candidate.review_notes = "Missing required fields"
        session.add(candidate)
        session.commit()
        raise ValueError("Candidate is missing required fields")

    transaction = Transaction(
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
        dedupe_key=candidate.dedupe_key,
        confidence=candidate.confidence,
    )
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    candidate.review_status = "confirmed"
    candidate.confirmed_transaction_id = transaction.id
    session.add(candidate)
    session.commit()
    return transaction


def auto_confirm_candidates(session: Session, min_confidence: float = 0.90) -> int:
    candidates = session.exec(select(CandidateTransaction).where(CandidateTransaction.review_status == "pending")).all()
    count = 0
    for candidate in candidates:
        if candidate_can_auto_confirm(candidate, min_confidence):
            confirm_candidate(session, candidate.id)
            count += 1
        else:
            candidate.review_status = "needs_review"
            session.add(candidate)
    session.commit()
    return count
