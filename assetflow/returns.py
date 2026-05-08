from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, time
from decimal import Decimal
from typing import Iterable

from assetflow.models import Transaction


RETURN_TRADE_TYPES = ("buy", "sell", "dividend", "fee")
ZERO = Decimal("0")


@dataclass
class ReturnSummary:
    currency: str
    realized_pnl: Decimal = ZERO
    dividends: Decimal = ZERO
    extra_fees: Decimal = ZERO
    sell_proceeds: Decimal = ZERO
    matched_cost: Decimal = ZERO
    sell_quantity: Decimal = ZERO
    unmatched_quantity: Decimal = ZERO
    transaction_count: int = 0
    incomplete_count: int = 0

    @property
    def total_return(self) -> Decimal:
        return self.realized_pnl + self.dividends - self.extra_fees

    def as_dict(self) -> dict[str, Decimal | str | int]:
        data = asdict(self)
        data["total_return"] = self.total_return
        return data


@dataclass
class _Lot:
    quantity: Decimal
    cost: Decimal


def summarize_returns(transactions: Iterable[Transaction]) -> list[ReturnSummary]:
    summaries: dict[str, ReturnSummary] = {}
    lots: dict[tuple[str, str | None, str | None, str, str], deque[_Lot]] = defaultdict(deque)

    for tx in sorted(transactions, key=_sort_key):
        trade_type = (tx.trade_type or "").lower()
        if trade_type not in RETURN_TRADE_TYPES:
            continue

        currency = tx.currency
        summary = summaries.setdefault(currency, ReturnSummary(currency=currency))
        summary.transaction_count += 1

        if trade_type == "buy":
            _record_buy(tx, summary, lots)
        elif trade_type == "sell":
            _record_sell(tx, summary, lots)
        elif trade_type == "dividend":
            _record_dividend(tx, summary)
        elif trade_type == "fee":
            _record_fee(tx, summary)

    return [summaries[currency] for currency in sorted(summaries)]


def _sort_key(tx: Transaction) -> tuple[object, object, object, int]:
    return (
        tx.trade_date,
        tx.trade_time or time.min,
        tx.created_at or datetime.min,
        tx.id or 0,
    )


def _lot_key(tx: Transaction) -> tuple[str, str | None, str | None, str, str]:
    return (tx.broker, tx.account_alias, tx.market, tx.symbol, tx.currency)


def _record_buy(
    tx: Transaction,
    summary: ReturnSummary,
    lots: dict[tuple[str, str | None, str | None, str, str], deque[_Lot]],
) -> None:
    quantity = tx.quantity
    cost = _buy_cost(tx)
    if quantity is None or quantity <= ZERO or cost is None or cost <= ZERO:
        summary.incomplete_count += 1
        return

    lots[_lot_key(tx)].append(_Lot(quantity=quantity, cost=cost))


def _record_sell(
    tx: Transaction,
    summary: ReturnSummary,
    lots: dict[tuple[str, str | None, str | None, str, str], deque[_Lot]],
) -> None:
    quantity = tx.quantity
    proceeds = _sell_proceeds(tx)
    if quantity is None or quantity <= ZERO or proceeds is None:
        summary.incomplete_count += 1
        return

    summary.sell_quantity += quantity
    summary.sell_proceeds += proceeds

    remaining = quantity
    matched_quantity = ZERO
    matched_cost = ZERO
    queue = lots[_lot_key(tx)]

    while remaining > ZERO and queue:
        lot = queue[0]
        matched = min(remaining, lot.quantity)
        cost = lot.cost * matched / lot.quantity

        matched_quantity += matched
        matched_cost += cost
        remaining -= matched
        lot.quantity -= matched
        lot.cost -= cost

        if lot.quantity == ZERO:
            queue.popleft()

    if remaining > ZERO:
        summary.unmatched_quantity += remaining

    if matched_quantity > ZERO:
        matched_proceeds = proceeds * matched_quantity / quantity
        summary.realized_pnl += matched_proceeds - matched_cost
        summary.matched_cost += matched_cost


def _record_dividend(tx: Transaction, summary: ReturnSummary) -> None:
    if tx.net_amount is None:
        summary.incomplete_count += 1
        return

    summary.dividends += tx.net_amount


def _record_fee(tx: Transaction, summary: ReturnSummary) -> None:
    if tx.net_amount is None:
        summary.incomplete_count += 1
        return

    summary.extra_fees += abs(tx.net_amount)


def _buy_cost(tx: Transaction) -> Decimal | None:
    if tx.net_amount is not None:
        return abs(tx.net_amount)

    costs = _commission_and_fees(tx)
    if tx.gross_amount is not None:
        return abs(tx.gross_amount) + costs

    if tx.quantity is not None and tx.price is not None:
        return abs(tx.quantity * tx.price) + costs

    return None


def _sell_proceeds(tx: Transaction) -> Decimal | None:
    if tx.net_amount is not None:
        return tx.net_amount

    costs = _commission_and_fees(tx)
    if tx.gross_amount is not None:
        return abs(tx.gross_amount) - costs

    if tx.quantity is not None and tx.price is not None:
        return abs(tx.quantity * tx.price) - costs

    return None


def _commission_and_fees(tx: Transaction) -> Decimal:
    return (tx.commission or ZERO) + (tx.fees or ZERO)
