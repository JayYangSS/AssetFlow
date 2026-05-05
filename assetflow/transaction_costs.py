from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP


CENT = Decimal("0.01")
HK_STAMP_DUTY_UNIT = Decimal("1")

HTSC_GLOBAL_HK_COMMISSION = Decimal("0")

# HKEX/IRD ordinary Hong Kong stock trade rates checked on 2026-05-05.
HK_SFC_TRANSACTION_LEVY_RATE = Decimal("0.000027")
HK_AFRC_TRANSACTION_LEVY_RATE = Decimal("0.0000015")
HK_TRADING_FEE_RATE = Decimal("0.0000565")
HK_STAMP_DUTY_RATE = Decimal("0.001")
HK_STOCK_SETTLEMENT_FEE_RATE = Decimal("0.000042")


@dataclass(frozen=True)
class TransactionCostEstimate:
    gross_amount: Decimal | None
    net_amount: Decimal | None
    commission: Decimal | None
    fees: Decimal | None


def estimate_transaction_costs(
    *,
    broker: str,
    market: str | None,
    trade_type: str | None,
    quantity: Decimal | None,
    price: Decimal | None,
    gross_amount: Decimal | None,
    net_amount: Decimal | None,
    commission: Decimal | None,
    fees: Decimal | None,
) -> TransactionCostEstimate:
    gross = _resolve_gross_amount(quantity=quantity, price=price, gross_amount=gross_amount)
    if broker != "htsc_global" or market != "HK" or trade_type not in {"buy", "sell"} or gross is None:
        return TransactionCostEstimate(gross, net_amount, commission, fees)

    estimated_commission = commission if commission is not None else HTSC_GLOBAL_HK_COMMISSION
    estimated_fees = fees if fees is not None else estimate_hk_stock_fees(gross)
    estimated_net_amount = net_amount
    if estimated_net_amount is None:
        estimated_net_amount = _cash_change(
            trade_type=trade_type,
            gross_amount=gross,
            commission=estimated_commission,
            fees=estimated_fees,
        )
    return TransactionCostEstimate(gross, estimated_net_amount, estimated_commission, estimated_fees)


def estimate_hk_stock_fees(gross_amount: Decimal) -> Decimal:
    gross = abs(gross_amount)
    return (
        _round_cent(gross * HK_SFC_TRANSACTION_LEVY_RATE)
        + _round_cent(gross * HK_AFRC_TRANSACTION_LEVY_RATE)
        + _round_cent(gross * HK_TRADING_FEE_RATE)
        + _round_hkd_dollar_up(gross * HK_STAMP_DUTY_RATE)
        + _round_cent(gross * HK_STOCK_SETTLEMENT_FEE_RATE)
    )


def _resolve_gross_amount(
    *,
    quantity: Decimal | None,
    price: Decimal | None,
    gross_amount: Decimal | None,
) -> Decimal | None:
    if gross_amount is not None:
        return abs(gross_amount)
    if quantity is None or price is None:
        return None
    return abs(quantity * price)


def _cash_change(
    *,
    trade_type: str,
    gross_amount: Decimal,
    commission: Decimal,
    fees: Decimal,
) -> Decimal:
    total_cost = commission + fees
    if trade_type == "buy":
        return -(gross_amount + total_cost)
    return gross_amount - total_cost


def _round_cent(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _round_hkd_dollar_up(value: Decimal) -> Decimal:
    return value.quantize(HK_STAMP_DUTY_UNIT, rounding=ROUND_CEILING)
