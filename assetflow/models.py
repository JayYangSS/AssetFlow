from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Column, Numeric, Text
from sqlmodel import Field, SQLModel


Money = Decimal


def money_column() -> Column:
    return Column(Numeric(20, 6), nullable=True)


class Upload(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    broker: str
    account_alias: str | None = None
    source: str
    original_filename: str
    content_hash: str = Field(index=True)
    image_path: str
    mime_type: str
    file_size_bytes: int
    status: str
    duplicate_of_upload_id: int | None = Field(default=None, foreign_key="upload.id")


class OcrResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    upload_id: int = Field(foreign_key="upload.id")
    provider: str
    model: str
    screenshot_type: str
    confidence: float
    raw_json: str = Field(sa_column=Column(Text))
    normalized_json: str = Field(sa_column=Column(Text))
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CandidateTransaction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    upload_id: int = Field(foreign_key="upload.id")
    ocr_result_id: int = Field(foreign_key="ocrresult.id")
    broker: str
    account_alias: str | None = None
    market: str | None = None
    symbol: str | None = None
    security_name: str | None = None
    trade_type: str | None = None
    trade_date: date | None = None
    trade_time: time | None = None
    quantity: Decimal | None = Field(default=None, sa_column=money_column())
    price: Decimal | None = Field(default=None, sa_column=money_column())
    gross_amount: Decimal | None = Field(default=None, sa_column=money_column())
    net_amount: Decimal | None = Field(default=None, sa_column=money_column())
    commission: Decimal | None = Field(default=None, sa_column=money_column())
    fees: Decimal | None = Field(default=None, sa_column=money_column())
    currency: str | None = None
    position_balance_after: Decimal | None = Field(default=None, sa_column=money_column())
    dedupe_key: str
    confidence: float
    review_status: str
    review_notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    confirmed_transaction_id: int | None = Field(default=None, foreign_key="transaction.id")


class Transaction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    broker: str
    account_alias: str | None = None
    market: str | None = None
    symbol: str
    security_name: str
    trade_type: str
    trade_date: date
    trade_time: time | None = None
    quantity: Decimal = Field(sa_column=Column(Numeric(20, 6), nullable=False))
    price: Decimal = Field(sa_column=Column(Numeric(20, 6), nullable=False))
    gross_amount: Decimal | None = Field(default=None, sa_column=money_column())
    net_amount: Decimal = Field(sa_column=Column(Numeric(20, 6), nullable=False))
    commission: Decimal | None = Field(default=None, sa_column=money_column())
    fees: Decimal | None = Field(default=None, sa_column=money_column())
    currency: str
    position_balance_after: Decimal | None = Field(default=None, sa_column=money_column())
    source_upload_id: int | None = Field(default=None, foreign_key="upload.id")
    source_ocr_result_id: int | None = Field(default=None, foreign_key="ocrresult.id")
    source_candidate_id: int | None = Field(default=None, foreign_key="candidatetransaction.id")
    dedupe_key: str = Field(index=True, unique=True)
    confidence: float
    status: str = "confirmed"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PositionSnapshot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    upload_id: int = Field(foreign_key="upload.id")
    ocr_result_id: int = Field(foreign_key="ocrresult.id")
    broker: str
    account_alias: str | None = None
    market: str | None = None
    symbol: str
    security_name: str | None = None
    quantity: Decimal = Field(sa_column=Column(Numeric(20, 6), nullable=False))
    available_quantity: Decimal | None = Field(default=None, sa_column=money_column())
    cost_price: Decimal | None = Field(default=None, sa_column=money_column())
    market_price: Decimal | None = Field(default=None, sa_column=money_column())
    market_value: Decimal | None = Field(default=None, sa_column=money_column())
    unrealized_pnl: Decimal | None = Field(default=None, sa_column=money_column())
    currency: str
    snapshot_at: datetime
    confidence: float
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CashSnapshot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    upload_id: int = Field(foreign_key="upload.id")
    ocr_result_id: int = Field(foreign_key="ocrresult.id")
    broker: str
    account_alias: str | None = None
    currency: str
    cash_balance: Decimal | None = Field(default=None, sa_column=money_column())
    available_cash: Decimal | None = Field(default=None, sa_column=money_column())
    frozen_cash: Decimal | None = Field(default=None, sa_column=money_column())
    market_value: Decimal | None = Field(default=None, sa_column=money_column())
    total_assets: Decimal | None = Field(default=None, sa_column=money_column())
    snapshot_at: datetime
    confidence: float
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReconciliationIssue(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    broker: str
    account_alias: str | None = None
    issue_type: str
    market: str | None = None
    symbol: str | None = None
    currency: str
    expected_value: Decimal | None = Field(default=None, sa_column=money_column())
    observed_value: Decimal | None = Field(default=None, sa_column=money_column())
    difference: Decimal | None = Field(default=None, sa_column=money_column())
    source_snapshot_id: int | None = Field(default=None, foreign_key="positionsnapshot.id")
    status: str = "open"
    resolution_notes: str | None = None


class ExportJob(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    export_type: str
    broker: str | None = None
    account_alias: str | None = None
    currency: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    template_path: str
    output_path: str | None = None
    row_count: int = 0
    status: str
    error_message: str | None = None
