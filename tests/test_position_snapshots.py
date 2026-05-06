from decimal import Decimal

from assetflow.position_snapshots import complete_position_value_triplet


def test_complete_position_value_triplet_fills_market_value() -> None:
    quantity, market_price, market_value = complete_position_value_triplet(
        quantity=Decimal("9"),
        market_price=Decimal("388.43"),
        market_value=None,
    )

    assert quantity == Decimal("9")
    assert market_price == Decimal("388.43")
    assert market_value == Decimal("3495.87")


def test_complete_position_value_triplet_fills_market_price() -> None:
    quantity, market_price, market_value = complete_position_value_triplet(
        quantity=Decimal("9"),
        market_price=None,
        market_value=Decimal("3495.87"),
    )

    assert quantity == Decimal("9")
    assert market_price == Decimal("388.43")
    assert market_value == Decimal("3495.87")


def test_complete_position_value_triplet_fills_quantity() -> None:
    quantity, market_price, market_value = complete_position_value_triplet(
        quantity=None,
        market_price=Decimal("640.20"),
        market_value=Decimal("3841.20"),
    )

    assert quantity == Decimal("6")
    assert market_price == Decimal("640.20")
    assert market_value == Decimal("3841.20")


def test_complete_position_value_triplet_does_not_divide_by_zero() -> None:
    quantity, market_price, market_value = complete_position_value_triplet(
        quantity=None,
        market_price=Decimal("0"),
        market_value=Decimal("3841.20"),
    )

    assert quantity is None
    assert market_price == Decimal("0")
    assert market_value == Decimal("3841.20")
