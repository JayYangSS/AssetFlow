from datetime import date, time
from decimal import Decimal

from assetflow.models import Transaction
from assetflow.returns import summarize_returns


def _tx(
    *,
    key: str,
    trade_type: str,
    trade_date: date,
    quantity: str = "0",
    price: str = "0",
    net_amount: str | None,
    gross_amount: str | None = None,
    broker: str = "htsc_global",
    account_alias: str | None = None,
    market: str | None = "HK",
    symbol: str = "00700",
    security_name: str = "Tencent",
    currency: str = "HKD",
    trade_time: time | None = None,
    commission: str | None = None,
    fees: str | None = None,
) -> Transaction:
    return Transaction(
        broker=broker,
        account_alias=account_alias,
        market=market,
        symbol=symbol,
        security_name=security_name,
        trade_type=trade_type,
        trade_date=trade_date,
        trade_time=trade_time,
        quantity=Decimal(quantity),
        price=Decimal(price),
        gross_amount=Decimal(gross_amount) if gross_amount is not None else None,
        net_amount=Decimal(net_amount) if net_amount is not None else None,
        commission=Decimal(commission) if commission is not None else None,
        fees=Decimal(fees) if fees is not None else None,
        currency=currency,
        dedupe_key=key,
        confidence=0.95,
    )


def test_summarize_returns_uses_fifo_and_includes_dividends_and_standalone_fees() -> None:
    summaries = summarize_returns(
        [
            _tx(
                key="buy",
                trade_type="buy",
                trade_date=date(2026, 1, 2),
                quantity="100",
                price="10",
                net_amount="-1008",
                fees="8",
            ),
            _tx(
                key="sell",
                trade_type="sell",
                trade_date=date(2026, 2, 3),
                quantity="40",
                price="12",
                net_amount="480",
                fees="5",
            ),
            _tx(
                key="dividend",
                trade_type="dividend",
                trade_date=date(2026, 3, 4),
                net_amount="12",
            ),
            _tx(
                key="fee",
                trade_type="fee",
                trade_date=date(2026, 3, 5),
                net_amount="-3",
                symbol="CASH",
                security_name="Cash",
            ),
        ]
    )

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.currency == "HKD"
    assert summary.realized_pnl == Decimal("76.8")
    assert summary.dividends == Decimal("12")
    assert summary.extra_fees == Decimal("3")
    assert summary.total_return == Decimal("85.8")
    assert summary.sell_proceeds == Decimal("480")
    assert summary.matched_cost == Decimal("403.2")
    assert summary.sell_quantity == Decimal("40")
    assert summary.unmatched_quantity == Decimal("0")
    assert summary.transaction_count == 4
    assert summary.incomplete_count == 0


def test_summarize_returns_matches_sell_across_multiple_buy_lots() -> None:
    summaries = summarize_returns(
        [
            _tx(key="buy-1", trade_type="buy", trade_date=date(2026, 1, 1), quantity="10", price="10", net_amount="-100"),
            _tx(key="buy-2", trade_type="buy", trade_date=date(2026, 1, 2), quantity="10", price="20", net_amount="-200"),
            _tx(key="sell", trade_type="sell", trade_date=date(2026, 1, 3), quantity="15", price="30", net_amount="450"),
        ]
    )

    summary = summaries[0]
    assert summary.realized_pnl == Decimal("250.0")
    assert summary.matched_cost == Decimal("200.0")
    assert summary.sell_proceeds == Decimal("450")
    assert summary.unmatched_quantity == Decimal("0")


def test_summarize_returns_marks_unmatched_sell_quantity_without_estimating_profit() -> None:
    summaries = summarize_returns(
        [
            _tx(key="buy", trade_type="buy", trade_date=date(2026, 1, 1), quantity="10", price="10", net_amount="-100"),
            _tx(key="sell", trade_type="sell", trade_date=date(2026, 1, 2), quantity="15", price="20", net_amount="300"),
        ]
    )

    summary = summaries[0]
    assert summary.realized_pnl == Decimal("100.0")
    assert summary.sell_proceeds == Decimal("300")
    assert summary.matched_cost == Decimal("100")
    assert summary.unmatched_quantity == Decimal("5")


def test_summarize_returns_groups_by_currency() -> None:
    summaries = summarize_returns(
        [
            _tx(key="hkd-dividend", trade_type="dividend", trade_date=date(2026, 1, 1), net_amount="8", currency="HKD"),
            _tx(key="usd-dividend", trade_type="dividend", trade_date=date(2026, 1, 1), net_amount="2", currency="USD"),
        ]
    )

    assert [(item.currency, item.total_return) for item in summaries] == [
        ("HKD", Decimal("8")),
        ("USD", Decimal("2")),
    ]


def test_summarize_returns_isolates_lots_by_full_lot_key() -> None:
    summaries = summarize_returns(
        [
            _tx(key="other-broker", trade_type="buy", trade_date=date(2026, 1, 1), quantity="1", net_amount="-1000", broker="other"),
            _tx(key="other-account", trade_type="buy", trade_date=date(2026, 1, 1), quantity="1", net_amount="-1000", account_alias="margin"),
            _tx(key="other-market", trade_type="buy", trade_date=date(2026, 1, 1), quantity="1", net_amount="-1000", market="US"),
            _tx(key="other-symbol", trade_type="buy", trade_date=date(2026, 1, 1), quantity="1", net_amount="-1000", symbol="AAPL"),
            _tx(key="other-currency", trade_type="buy", trade_date=date(2026, 1, 1), quantity="1", net_amount="-1000", currency="USD"),
            _tx(key="matching-buy", trade_type="buy", trade_date=date(2026, 1, 2), quantity="1", net_amount="-10"),
            _tx(key="matching-sell", trade_type="sell", trade_date=date(2026, 1, 3), quantity="1", net_amount="30"),
        ]
    )

    hkd_summary = next(item for item in summaries if item.currency == "HKD")
    usd_summary = next(item for item in summaries if item.currency == "USD")
    assert hkd_summary.realized_pnl == Decimal("20")
    assert hkd_summary.matched_cost == Decimal("10")
    assert hkd_summary.unmatched_quantity == Decimal("0")
    assert usd_summary.realized_pnl == Decimal("0")


def test_summarize_returns_falls_back_to_gross_amount_for_cost_and_proceeds() -> None:
    summaries = summarize_returns(
        [
            _tx(
                key="buy",
                trade_type="buy",
                trade_date=date(2026, 1, 1),
                quantity="10",
                gross_amount="100",
                net_amount=None,
                commission="2",
                fees="3",
            ),
            _tx(
                key="sell",
                trade_type="sell",
                trade_date=date(2026, 1, 2),
                quantity="5",
                gross_amount="75",
                net_amount=None,
                commission="1",
                fees="2",
            ),
        ]
    )

    summary = summaries[0]
    assert summary.sell_proceeds == Decimal("72")
    assert summary.matched_cost == Decimal("52.5")
    assert summary.realized_pnl == Decimal("19.5")


def test_summarize_returns_falls_back_to_quantity_times_price_for_cost_and_proceeds() -> None:
    summaries = summarize_returns(
        [
            _tx(
                key="buy",
                trade_type="buy",
                trade_date=date(2026, 1, 1),
                quantity="10",
                price="10",
                net_amount=None,
                commission="2",
                fees="3",
            ),
            _tx(
                key="sell",
                trade_type="sell",
                trade_date=date(2026, 1, 2),
                quantity="4",
                price="20",
                net_amount=None,
                commission="1",
                fees="2",
            ),
        ]
    )

    summary = summaries[0]
    assert summary.sell_proceeds == Decimal("77")
    assert summary.matched_cost == Decimal("42")
    assert summary.realized_pnl == Decimal("35")


def test_summarize_returns_ignores_missing_trade_type() -> None:
    tx = _tx(key="legacy", trade_type="buy", trade_date=date(2026, 1, 1), quantity="1", net_amount="-10")
    tx.trade_type = None

    assert summarize_returns([tx]) == []
