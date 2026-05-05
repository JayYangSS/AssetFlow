from datetime import date, time
from decimal import Decimal
from hashlib import sha256


SUPPORTED_BROKERS = {"htsc_global"}
SUPPORTED_CURRENCIES = {"CNY", "HKD", "USD"}
TEMPLATE_TRADE_TYPES = {"buy": "买入", "sell": "卖出"}
ALL_TRADE_TYPES = TEMPLATE_TRADE_TYPES | {
    "dividend": "分红",
    "cash_in": "转入",
    "cash_out": "转出",
    "fee": "费用",
    "adjustment": "调整",
}


def calculate_hash(data: bytes) -> str:
    return sha256(data).hexdigest()


def _format_dedupe_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def build_dedupe_key(
    *,
    broker: str,
    account_alias: str | None,
    trade_date: date | None,
    trade_time: time | None,
    symbol: str | None,
    trade_type: str | None,
    quantity: Decimal | None,
    price: Decimal | None,
    net_amount: Decimal | None,
    currency: str | None,
) -> str:
    parts = [
        broker,
        account_alias or "",
        trade_date.isoformat() if trade_date else "",
        trade_time.isoformat() if trade_time else "",
        symbol or "",
        trade_type or "",
        _format_dedupe_decimal(quantity),
        _format_dedupe_decimal(price),
        _format_dedupe_decimal(net_amount),
        currency or "",
    ]
    return sha256("|".join(parts).encode("utf-8")).hexdigest()
