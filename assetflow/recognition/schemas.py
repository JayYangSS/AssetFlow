from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


ScreenshotType = Literal["trade_history", "positions", "cash", "unknown"]


class RecognizedTransaction(BaseModel):
    broker: str
    account_alias: str | None = None
    market: str | None = None
    symbol: str | None = None
    security_name: str | None = None
    trade_type: str | None = None
    trade_date: date | None = None
    trade_time: time | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    gross_amount: Decimal | None = None
    net_amount: Decimal | None = None
    commission: Decimal | None = None
    fees: Decimal | None = None
    currency: str | None = None
    position_balance_after: Decimal | None = None
    confidence: float = 0.0


class RecognizedPosition(BaseModel):
    broker: str
    account_alias: str | None = None
    market: str | None = None
    symbol: str
    security_name: str | None = None
    quantity: Decimal
    available_quantity: Decimal | None = None
    cost_price: Decimal | None = None
    market_price: Decimal | None = None
    market_value: Decimal | None = None
    daily_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    currency: str
    snapshot_at: datetime
    confidence: float = 0.0


class RecognizedCash(BaseModel):
    broker: str
    account_alias: str | None = None
    currency: str
    cash_balance: Decimal | None = None
    available_cash: Decimal | None = None
    frozen_cash: Decimal | None = None
    market_value: Decimal | None = None
    total_assets: Decimal | None = None
    snapshot_at: datetime
    confidence: float = 0.0


class RecognizedScreenshot(BaseModel):
    screenshot_type: ScreenshotType
    confidence: float = Field(ge=0.0, le=1.0)
    transactions: list[RecognizedTransaction] = Field(default_factory=list)
    positions: list[RecognizedPosition] = Field(default_factory=list)
    cash: list[RecognizedCash] = Field(default_factory=list)
