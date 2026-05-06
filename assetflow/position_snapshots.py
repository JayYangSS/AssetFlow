from decimal import Decimal

from assetflow.models import PositionSnapshot


def complete_position_value_triplet(
    *,
    quantity: Decimal | None,
    market_price: Decimal | None,
    market_value: Decimal | None,
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    if quantity is not None and market_price is not None and market_value is None:
        market_value = quantity * market_price
    elif quantity is not None and quantity != 0 and market_price is None and market_value is not None:
        market_price = market_value / quantity
    elif quantity is None and market_price is not None and market_price != 0 and market_value is not None:
        quantity = market_value / market_price
    return quantity, market_price, market_value


def _same_decimal(left: Decimal | None, right: Decimal | None) -> bool:
    return left is not None and right is not None and left == right


def looks_like_shifted_current_cost_snapshot(snapshot: PositionSnapshot) -> bool:
    return (
        _same_decimal(snapshot.quantity, snapshot.cost_price)
        and _same_decimal(snapshot.market_value, snapshot.market_price)
        and _same_decimal(snapshot.daily_pnl, snapshot.unrealized_pnl)
    )


def hide_shifted_current_cost_fields(snapshot: PositionSnapshot) -> PositionSnapshot:
    if not looks_like_shifted_current_cost_snapshot(snapshot):
        return snapshot
    values = {name: getattr(snapshot, name) for name in PositionSnapshot.model_fields}
    values.update(quantity=None, market_value=None, daily_pnl=None)
    return PositionSnapshot(**values)
