from collections import defaultdict
from decimal import Decimal

from sqlmodel import Session, select

from assetflow.models import PositionSnapshot, ReconciliationIssue, Transaction


def _signed_quantity(transaction: Transaction) -> Decimal:
    if transaction.trade_type == "buy":
        return transaction.quantity
    if transaction.trade_type == "sell":
        return -transaction.quantity
    return Decimal("0")


def reconcile_positions(session: Session, broker: str, account_alias: str | None = None) -> int:
    tx_query = select(Transaction).where(Transaction.broker == broker)
    snap_query = select(PositionSnapshot).where(PositionSnapshot.broker == broker)
    if account_alias is not None:
        tx_query = tx_query.where(Transaction.account_alias == account_alias)
        snap_query = snap_query.where(PositionSnapshot.account_alias == account_alias)

    expected: dict[tuple[str | None, str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    for tx in session.exec(tx_query).all():
        expected[(tx.market, tx.symbol, tx.currency)] += _signed_quantity(tx)

    latest: dict[tuple[str | None, str, str], PositionSnapshot] = {}
    for snapshot in session.exec(snap_query).all():
        key = (snapshot.market, snapshot.symbol, snapshot.currency)
        if key not in latest or snapshot.snapshot_at > latest[key].snapshot_at:
            latest[key] = snapshot

    created = 0
    for key, snapshot in latest.items():
        expected_quantity = expected.get(key, Decimal("0"))
        if expected_quantity == snapshot.quantity:
            continue
        issue = ReconciliationIssue(
            broker=broker,
            account_alias=account_alias,
            issue_type="position_quantity_mismatch",
            market=snapshot.market,
            symbol=snapshot.symbol,
            currency=snapshot.currency,
            expected_value=expected_quantity,
            observed_value=snapshot.quantity,
            difference=snapshot.quantity - expected_quantity,
            source_snapshot_id=snapshot.id,
            status="open",
        )
        session.add(issue)
        created += 1

    session.commit()
    return created
