from decimal import Decimal

from assetflow.transaction_costs import estimate_transaction_costs


def test_estimate_htsc_hk_buy_defaults_to_zero_commission_and_hk_fees() -> None:
    estimate = estimate_transaction_costs(
        broker="htsc_global",
        market="HK",
        trade_type="buy",
        quantity=Decimal("100"),
        price=Decimal("71"),
        gross_amount=None,
        net_amount=None,
        commission=None,
        fees=None,
    )

    assert estimate.gross_amount == Decimal("7100")
    assert estimate.commission == Decimal("0")
    assert estimate.fees == Decimal("8.90")
    assert estimate.net_amount == Decimal("-7108.90")


def test_estimate_htsc_hk_sell_subtracts_default_fees_from_cash_change() -> None:
    estimate = estimate_transaction_costs(
        broker="htsc_global",
        market="HK",
        trade_type="sell",
        quantity=Decimal("100"),
        price=Decimal("71"),
        gross_amount=None,
        net_amount=None,
        commission=None,
        fees=None,
    )

    assert estimate.gross_amount == Decimal("7100")
    assert estimate.commission == Decimal("0")
    assert estimate.fees == Decimal("8.90")
    assert estimate.net_amount == Decimal("7091.10")


def test_estimate_preserves_recognized_cash_change_when_present() -> None:
    estimate = estimate_transaction_costs(
        broker="htsc_global",
        market="HK",
        trade_type="buy",
        quantity=Decimal("100"),
        price=Decimal("71"),
        gross_amount=None,
        net_amount=Decimal("-7110"),
        commission=None,
        fees=None,
    )

    assert estimate.commission == Decimal("0")
    assert estimate.fees == Decimal("8.90")
    assert estimate.net_amount == Decimal("-7110")


def test_estimate_preserves_recognized_commission_and_fees() -> None:
    estimate = estimate_transaction_costs(
        broker="htsc_global",
        market="HK",
        trade_type="buy",
        quantity=Decimal("100"),
        price=Decimal("71"),
        gross_amount=None,
        net_amount=None,
        commission=Decimal("15"),
        fees=Decimal("8"),
    )

    assert estimate.commission == Decimal("15")
    assert estimate.fees == Decimal("8")
    assert estimate.net_amount == Decimal("-7123")
