# Screenshot Investment Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the AssetFlow MVP that receives iPhone screenshots over LAN, recognizes 华泰涨乐全球通交易/持仓/资金截图, stores a local SQLite ledger, reconciles snapshots, and exports confirmed transactions using `导入模板.xlsx`.

**Architecture:** A small Python FastAPI service owns upload, review, reconciliation, and export endpoints. SQLModel models map directly to SQLite tables, while broker-specific recognition lives behind a provider interface so tests can use a deterministic fixture provider and production can use OpenAI vision. Export uses openpyxl to copy the user's workbook template, validate headers, clear the example row, and write confirmed transactions from row 2.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, SQLModel, Pydantic Settings, OpenAI Python SDK, Pillow, openpyxl, pytest, FastAPI TestClient.

---

## Reference Inputs

- Design spec: `docs/superpowers/specs/2026-05-02-screenshot-investment-ledger-design.md`
- User template: `C:\Users\jiyang\Downloads\导入模板.xlsx`
- OpenAI image input docs: https://platform.openai.com/docs/guides/images-vision
- OpenAI structured outputs docs: https://platform.openai.com/docs/guides/structured-outputs

## File Structure

Create these files:

- `.gitignore`: ignore local databases, uploaded screenshots, exports, environment files, Python caches.
- `.env.example`: document local configuration.
- `README.md`: local run instructions and iPhone Shortcut payload shape.
- `pyproject.toml`: project metadata, dependencies, and pytest configuration.
- `assetflow/__init__.py`: package marker.
- `assetflow/config.py`: settings loaded from environment.
- `assetflow/db.py`: SQLite engine/session helpers and schema creation.
- `assetflow/models.py`: SQLModel table definitions.
- `assetflow/domain.py`: pure Python enums, dataclasses, validation helpers, dedupe-key generation.
- `assetflow/uploads.py`: image validation, hash calculation, file storage, duplicate upload handling.
- `assetflow/recognition/schemas.py`: Pydantic schemas for normalized recognition output.
- `assetflow/recognition/providers.py`: provider interface, fixture provider, OpenAI provider.
- `assetflow/recognition/service.py`: convert recognition output into candidate transactions and snapshots.
- `assetflow/ledger.py`: candidate validation, auto-confirmation, review actions.
- `assetflow/reconciliation.py`: derive holdings from transactions and compare with snapshots.
- `assetflow/exporters/xlsx_template.py`: template validation and xlsx writing.
- `assetflow/api.py`: FastAPI routes.
- `assetflow/main.py`: app entry point for Uvicorn.
- `tests/conftest.py`: isolated temp settings, DB, and app fixtures.
- `tests/fixtures/recognition/trade_history.json`: fixture recognition response.
- `tests/fixtures/recognition/positions.json`: fixture recognition response.
- `tests/fixtures/recognition/cash.json`: fixture recognition response.
- `tests/test_config_db.py`: config and schema smoke tests.
- `tests/test_uploads.py`: upload validation, hash, duplicate behavior.
- `tests/test_recognition_service.py`: fixture recognition to ledger candidates/snapshots.
- `tests/test_ledger.py`: auto-confirm and review rules.
- `tests/test_reconciliation.py`: position mismatch detection.
- `tests/test_xlsx_export.py`: template export behavior.
- `tests/test_api.py`: end-to-end API tests with fixture recognizer.
- `docs/ios-shortcut.md`: exact iPhone Shortcut setup steps.

Modify these files:

- `docs/superpowers/specs/2026-05-02-screenshot-investment-ledger-design.md`: no behavior edits expected; add an implementation-plan link only after all tests pass.

## Implementation Tasks

### Task 1: Project Skeleton, Dependencies, And Settings

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `assetflow/__init__.py`
- Create: `assetflow/config.py`
- Test: `tests/test_config_db.py`

- [ ] **Step 1: Write the failing settings test**

Create `tests/test_config_db.py` with this initial content:

```python
from pathlib import Path

from assetflow.config import Settings


def test_settings_builds_data_directories(tmp_path: Path) -> None:
    settings = Settings(
        assetflow_data_dir=tmp_path / "data",
        assetflow_upload_token="secret-token",
        assetflow_recognition_provider="fixture",
    )

    assert settings.upload_dir == tmp_path / "data" / "uploads"
    assert settings.export_dir == tmp_path / "data" / "exports"
    assert settings.database_url == f"sqlite:///{tmp_path / 'data' / 'assetflow.db'}"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
pytest tests/test_config_db.py::test_settings_builds_data_directories -v
```

Expected: FAIL because `assetflow.config` does not exist.

- [ ] **Step 3: Add package, dependencies, and settings**

Create `pyproject.toml`:

```toml
[project]
name = "assetflow"
version = "0.1.0"
description = "Local screenshot-driven investment ledger"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.30.0",
  "sqlmodel>=0.0.22",
  "pydantic-settings>=2.4.0",
  "python-multipart>=0.0.9",
  "pillow>=10.4.0",
  "openpyxl>=3.1.5",
  "openai>=1.50.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3.0",
  "httpx>=0.27.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Create `.gitignore`:

```gitignore
.env
.venv/
__pycache__/
.pytest_cache/
*.pyc
data/
exports/
uploads/
*.db
*.sqlite
*.xlsx.tmp
```

Create `.env.example`:

```dotenv
ASSETFLOW_DATA_DIR=./data
ASSETFLOW_UPLOAD_TOKEN=change-me
ASSETFLOW_HOST=0.0.0.0
ASSETFLOW_PORT=8787
ASSETFLOW_RECOGNITION_PROVIDER=fixture
ASSETFLOW_OPENAI_MODEL=gpt-4.1-mini
OPENAI_API_KEY=
```

Create `assetflow/__init__.py`:

```python
__all__ = ["__version__"]

__version__ = "0.1.0"
```

Create `assetflow/config.py`:

```python
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    assetflow_data_dir: Path = Field(default=Path("data"))
    assetflow_upload_token: str = Field(min_length=8)
    assetflow_host: str = "0.0.0.0"
    assetflow_port: int = 8787
    assetflow_recognition_provider: str = "fixture"
    assetflow_openai_model: str = "gpt-4.1-mini"
    openai_api_key: str | None = None

    @property
    def upload_dir(self) -> Path:
        return self.assetflow_data_dir / "uploads"

    @property
    def export_dir(self) -> Path:
        return self.assetflow_data_dir / "exports"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.assetflow_data_dir / 'assetflow.db'}"

    def ensure_directories(self) -> None:
        self.assetflow_data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)
```

Create `README.md`:

```markdown
# AssetFlow

AssetFlow is a local screenshot-driven investment ledger. The MVP receives iPhone Shortcut uploads on the same Wi-Fi network, recognizes 华泰涨乐全球通 screenshots, stores a SQLite ledger, reconciles positions, and exports transactions using the provided xlsx template.

## Local Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn assetflow.main:app --host 0.0.0.0 --port 8787
```

The upload endpoint is `POST /api/uploads/ios-shortcut`.
```

- [ ] **Step 4: Run the settings test**

Run:

```powershell
pytest tests/test_config_db.py::test_settings_builds_data_directories -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add .gitignore .env.example README.md pyproject.toml assetflow/__init__.py assetflow/config.py tests/test_config_db.py
git commit -m "chore: scaffold assetflow project"
```

### Task 2: Database Models And Session Helpers

**Files:**
- Create: `assetflow/db.py`
- Create: `assetflow/models.py`
- Modify: `tests/test_config_db.py`

- [ ] **Step 1: Add failing database schema test**

Append to `tests/test_config_db.py`:

```python
from sqlmodel import Session, select

from assetflow.db import create_db_and_tables, make_engine
from assetflow.models import Upload


def test_create_db_and_tables_allows_upload_insert(tmp_path: Path) -> None:
    settings = Settings(
        assetflow_data_dir=tmp_path / "data",
        assetflow_upload_token="secret-token",
        assetflow_recognition_provider="fixture",
    )
    settings.ensure_directories()
    engine = make_engine(settings.database_url)
    create_db_and_tables(engine)

    with Session(engine) as session:
        upload = Upload(
            broker="htsc_global",
            source="ios_shortcut",
            original_filename="sample.png",
            content_hash="abc123",
            image_path=str(tmp_path / "data" / "uploads" / "sample.png"),
            mime_type="image/png",
            file_size_bytes=12,
            status="stored",
        )
        session.add(upload)
        session.commit()

        saved = session.exec(select(Upload)).one()

    assert saved.content_hash == "abc123"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
pytest tests/test_config_db.py::test_create_db_and_tables_allows_upload_insert -v
```

Expected: FAIL because `assetflow.db` and `assetflow.models` do not exist.

- [ ] **Step 3: Implement database helpers**

Create `assetflow/db.py`:

```python
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.engine import Engine


def make_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def create_db_and_tables(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)


def session_scope(engine: Engine) -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
```

Create `assetflow/models.py`:

```python
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
    source_upload_id: int = Field(foreign_key="upload.id")
    source_ocr_result_id: int = Field(foreign_key="ocrresult.id")
    source_candidate_id: int = Field(foreign_key="candidatetransaction.id")
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
```

- [ ] **Step 4: Run database tests**

Run:

```powershell
pytest tests/test_config_db.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add assetflow/db.py assetflow/models.py tests/test_config_db.py
git commit -m "feat: add sqlite ledger models"
```

### Task 3: Upload Storage, Validation, Hashing, And Duplicates

**Files:**
- Create: `assetflow/domain.py`
- Create: `assetflow/uploads.py`
- Create: `tests/conftest.py`
- Create: `tests/test_uploads.py`

- [ ] **Step 1: Write failing upload tests**

Create `tests/conftest.py`:

```python
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlmodel import Session

from assetflow.config import Settings
from assetflow.db import create_db_and_tables, make_engine


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    value = Settings(
        assetflow_data_dir=tmp_path / "data",
        assetflow_upload_token="secret-token",
        assetflow_recognition_provider="fixture",
    )
    value.ensure_directories()
    return value


@pytest.fixture
def session(settings: Settings) -> Generator[Session, None, None]:
    engine = make_engine(settings.database_url)
    create_db_and_tables(engine)
    with Session(engine) as db:
        yield db
```

Create `tests/test_uploads.py`:

```python
from assetflow.uploads import InvalidUploadError, store_upload


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + (b"0" * 64)


def test_store_upload_saves_image_and_hash(settings, session) -> None:
    upload = store_upload(
        session=session,
        settings=settings,
        broker="htsc_global",
        source="ios_shortcut",
        filename="trade.png",
        content_type="image/png",
        data=PNG_BYTES,
    )

    assert upload.id is not None
    assert upload.status == "stored"
    assert upload.content_hash
    assert settings.upload_dir.joinpath(upload.content_hash + ".png").exists()


def test_store_upload_marks_duplicate(settings, session) -> None:
    first = store_upload(session, settings, "htsc_global", "ios_shortcut", "a.png", "image/png", PNG_BYTES)
    second = store_upload(session, settings, "htsc_global", "ios_shortcut", "b.png", "image/png", PNG_BYTES)

    assert second.status == "duplicate"
    assert second.duplicate_of_upload_id == first.id


def test_store_upload_rejects_non_image(settings, session) -> None:
    try:
        store_upload(session, settings, "htsc_global", "ios_shortcut", "note.txt", "text/plain", b"hello")
    except InvalidUploadError as exc:
        assert "Unsupported image type" in str(exc)
    else:
        raise AssertionError("Expected InvalidUploadError")
```

- [ ] **Step 2: Run upload tests to verify failure**

Run:

```powershell
pytest tests/test_uploads.py -v
```

Expected: FAIL because `assetflow.uploads` does not exist.

- [ ] **Step 3: Implement domain helpers and upload service**

Create `assetflow/domain.py`:

```python
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
        str(quantity) if quantity is not None else "",
        str(price) if price is not None else "",
        str(net_amount) if net_amount is not None else "",
        currency or "",
    ]
    return sha256("|".join(parts).encode("utf-8")).hexdigest()
```

Create `assetflow/uploads.py`:

```python
from pathlib import Path

from sqlmodel import Session, select

from assetflow.config import Settings
from assetflow.domain import SUPPORTED_BROKERS, calculate_hash
from assetflow.models import Upload


class InvalidUploadError(ValueError):
    pass


ALLOWED_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/heic": ".heic",
    "image/heif": ".heif",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _validate_upload(broker: str, content_type: str, data: bytes) -> str:
    if broker not in SUPPORTED_BROKERS:
        raise InvalidUploadError(f"Unsupported broker: {broker}")
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise InvalidUploadError(f"Unsupported image type: {content_type}")
    if not data:
        raise InvalidUploadError("Empty upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidUploadError("Upload exceeds 10MB limit")
    return ALLOWED_CONTENT_TYPES[content_type]


def store_upload(
    session: Session,
    settings: Settings,
    broker: str,
    source: str,
    filename: str,
    content_type: str,
    data: bytes,
    account_alias: str | None = None,
) -> Upload:
    suffix = _validate_upload(broker, content_type, data)
    content_hash = calculate_hash(data)
    existing = session.exec(select(Upload).where(Upload.content_hash == content_hash)).first()
    image_path = settings.upload_dir / f"{content_hash}{suffix}"
    settings.ensure_directories()

    if existing is None:
        image_path.write_bytes(data)
        status = "stored"
        duplicate_of_upload_id = None
    else:
        status = "duplicate"
        duplicate_of_upload_id = existing.id

    upload = Upload(
        broker=broker,
        account_alias=account_alias,
        source=source,
        original_filename=Path(filename).name,
        content_hash=content_hash,
        image_path=str(image_path),
        mime_type=content_type,
        file_size_bytes=len(data),
        status=status,
        duplicate_of_upload_id=duplicate_of_upload_id,
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    return upload
```

- [ ] **Step 4: Run upload tests**

Run:

```powershell
pytest tests/test_uploads.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add assetflow/domain.py assetflow/uploads.py tests/conftest.py tests/test_uploads.py
git commit -m "feat: store screenshot uploads"
```

### Task 4: Recognition Schemas, Fixture Provider, And OpenAI Provider

**Files:**
- Create: `assetflow/recognition/__init__.py`
- Create: `assetflow/recognition/schemas.py`
- Create: `assetflow/recognition/providers.py`
- Create: `tests/fixtures/recognition/trade_history.json`
- Create: `tests/fixtures/recognition/positions.json`
- Create: `tests/fixtures/recognition/cash.json`
- Create: `tests/test_recognition_service.py`

- [ ] **Step 1: Write failing provider tests**

Create `tests/fixtures/recognition/trade_history.json`:

```json
{
  "screenshot_type": "trade_history",
  "confidence": 0.96,
  "transactions": [
    {
      "broker": "htsc_global",
      "market": "HK",
      "symbol": "00700",
      "security_name": "腾讯控股",
      "trade_type": "buy",
      "trade_date": "2026-05-01",
      "trade_time": "10:10:10",
      "quantity": "100",
      "price": "350.1200",
      "gross_amount": "-35012.0000",
      "net_amount": "-35035.0000",
      "commission": "15.0000",
      "fees": "8.0000",
      "currency": "HKD",
      "position_balance_after": "100",
      "confidence": 0.97
    }
  ],
  "positions": [],
  "cash": []
}
```

Create `tests/fixtures/recognition/positions.json`:

```json
{
  "screenshot_type": "positions",
  "confidence": 0.95,
  "transactions": [],
  "positions": [
    {
      "broker": "htsc_global",
      "market": "HK",
      "symbol": "00700",
      "security_name": "腾讯控股",
      "quantity": "100",
      "available_quantity": "100",
      "market_price": "351.0000",
      "market_value": "35100.0000",
      "currency": "HKD",
      "snapshot_at": "2026-05-01T15:59:00",
      "confidence": 0.95
    }
  ],
  "cash": []
}
```

Create `tests/fixtures/recognition/cash.json`:

```json
{
  "screenshot_type": "cash",
  "confidence": 0.94,
  "transactions": [],
  "positions": [],
  "cash": [
    {
      "broker": "htsc_global",
      "currency": "HKD",
      "cash_balance": "12000.0000",
      "available_cash": "11900.0000",
      "total_assets": "47100.0000",
      "snapshot_at": "2026-05-01T16:00:00",
      "confidence": 0.94
    }
  ]
}
```

Create `tests/test_recognition_service.py`:

```python
from pathlib import Path

from assetflow.recognition.providers import FixtureVisionProvider


def test_fixture_provider_loads_normalized_trade_response() -> None:
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition/trade_history.json"))

    result = provider.recognize(image_path=Path("unused.png"), broker="htsc_global")

    assert result.screenshot_type == "trade_history"
    assert result.transactions[0].symbol == "00700"
    assert result.transactions[0].currency == "HKD"
```

- [ ] **Step 2: Run provider test to verify failure**

Run:

```powershell
pytest tests/test_recognition_service.py::test_fixture_provider_loads_normalized_trade_response -v
```

Expected: FAIL because recognition package does not exist.

- [ ] **Step 3: Implement schemas and providers**

Create `assetflow/recognition/__init__.py`:

```python
__all__ = []
```

Create `assetflow/recognition/schemas.py`:

```python
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
```

Create `assetflow/recognition/providers.py`:

```python
import base64
import json
from pathlib import Path
from typing import Protocol

from openai import OpenAI

from assetflow.config import Settings
from assetflow.recognition.schemas import RecognizedScreenshot


class VisionProvider(Protocol):
    provider_name: str
    model_name: str

    def recognize(self, image_path: Path, broker: str) -> RecognizedScreenshot:
        ...


class FixtureVisionProvider:
    provider_name = "fixture"
    model_name = "fixture-json"

    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path

    def recognize(self, image_path: Path, broker: str) -> RecognizedScreenshot:
        data = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        return RecognizedScreenshot.model_validate(data)


class OpenAIVisionProvider:
    provider_name = "openai"

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when ASSETFLOW_RECOGNITION_PROVIDER=openai")
        self.model_name = settings.assetflow_openai_model
        self.client = OpenAI(api_key=settings.openai_api_key)

    def recognize(self, image_path: Path, broker: str) -> RecognizedScreenshot:
        image_bytes = image_path.read_bytes()
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        prompt = (
            "你是投资交易截图结构化助手。只输出符合 schema 的字段。"
            f"券商标识是 {broker}。"
            "识别截图类型为 trade_history、positions、cash 或 unknown。"
            "金额、数量、价格必须保留原始精度；无法确定的字段用 null；不要编造。"
        )
        response = self.client.responses.parse(
            model=self.model_name,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": f"data:image/png;base64,{image_b64}"},
                    ],
                }
            ],
            text_format=RecognizedScreenshot,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ValueError("OpenAI response did not include parsed recognition output")
        return parsed


def make_provider(settings: Settings) -> VisionProvider:
    if settings.assetflow_recognition_provider == "fixture":
        return FixtureVisionProvider(Path("tests/fixtures/recognition/trade_history.json"))
    if settings.assetflow_recognition_provider == "openai":
        return OpenAIVisionProvider(settings)
    raise ValueError(f"Unsupported recognition provider: {settings.assetflow_recognition_provider}")
```

- [ ] **Step 4: Run provider test**

Run:

```powershell
pytest tests/test_recognition_service.py::test_fixture_provider_loads_normalized_trade_response -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add assetflow/recognition tests/fixtures/recognition tests/test_recognition_service.py
git commit -m "feat: add recognition provider interface"
```

### Task 5: Recognition Persistence And Candidate Creation

**Files:**
- Create: `assetflow/recognition/service.py`
- Modify: `tests/test_recognition_service.py`

- [ ] **Step 1: Add failing persistence tests**

Append to `tests/test_recognition_service.py`:

```python
from pathlib import Path

from sqlmodel import select

from assetflow.models import CandidateTransaction, OcrResult, PositionSnapshot
from assetflow.recognition.service import process_recognition_result
from assetflow.uploads import store_upload


def test_process_trade_result_creates_candidate(settings, session) -> None:
    upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "trade.png", "image/png", b"\x89PNG\r\n\x1a\nabc")
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition/trade_history.json"))
    result = provider.recognize(Path(upload.image_path), "htsc_global")

    process_recognition_result(session, upload, provider, result)

    ocr = session.exec(select(OcrResult)).one()
    candidate = session.exec(select(CandidateTransaction)).one()
    assert ocr.screenshot_type == "trade_history"
    assert candidate.symbol == "00700"
    assert candidate.review_status == "pending"


def test_process_position_result_creates_snapshot(settings, session) -> None:
    upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "position.png", "image/png", b"\x89PNG\r\n\x1a\nxyz")
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition/positions.json"))
    result = provider.recognize(Path(upload.image_path), "htsc_global")

    process_recognition_result(session, upload, provider, result)

    snapshot = session.exec(select(PositionSnapshot)).one()
    assert snapshot.symbol == "00700"
    assert snapshot.quantity == 100
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
pytest tests/test_recognition_service.py -v
```

Expected: FAIL because `process_recognition_result` does not exist.

- [ ] **Step 3: Implement recognition persistence**

Create `assetflow/recognition/service.py`:

```python
import json

from sqlmodel import Session

from assetflow.domain import build_dedupe_key
from assetflow.models import CandidateTransaction, CashSnapshot, OcrResult, PositionSnapshot, Upload
from assetflow.recognition.providers import VisionProvider
from assetflow.recognition.schemas import RecognizedScreenshot


def process_recognition_result(
    session: Session,
    upload: Upload,
    provider: VisionProvider,
    result: RecognizedScreenshot,
) -> OcrResult:
    raw_json = result.model_dump_json()
    ocr = OcrResult(
        upload_id=upload.id,
        provider=provider.provider_name,
        model=provider.model_name,
        screenshot_type=result.screenshot_type,
        confidence=result.confidence,
        raw_json=raw_json,
        normalized_json=raw_json,
    )
    session.add(ocr)
    session.commit()
    session.refresh(ocr)

    for item in result.transactions:
        candidate = CandidateTransaction(
            upload_id=upload.id,
            ocr_result_id=ocr.id,
            broker=item.broker,
            account_alias=item.account_alias,
            market=item.market,
            symbol=item.symbol,
            security_name=item.security_name,
            trade_type=item.trade_type,
            trade_date=item.trade_date,
            trade_time=item.trade_time,
            quantity=item.quantity,
            price=item.price,
            gross_amount=item.gross_amount,
            net_amount=item.net_amount,
            commission=item.commission,
            fees=item.fees,
            currency=item.currency,
            position_balance_after=item.position_balance_after,
            dedupe_key=build_dedupe_key(
                broker=item.broker,
                account_alias=item.account_alias,
                trade_date=item.trade_date,
                trade_time=item.trade_time,
                symbol=item.symbol,
                trade_type=item.trade_type,
                quantity=item.quantity,
                price=item.price,
                net_amount=item.net_amount,
                currency=item.currency,
            ),
            confidence=item.confidence,
            review_status="pending",
        )
        session.add(candidate)

    for item in result.positions:
        session.add(
            PositionSnapshot(
                upload_id=upload.id,
                ocr_result_id=ocr.id,
                broker=item.broker,
                account_alias=item.account_alias,
                market=item.market,
                symbol=item.symbol,
                security_name=item.security_name,
                quantity=item.quantity,
                available_quantity=item.available_quantity,
                cost_price=item.cost_price,
                market_price=item.market_price,
                market_value=item.market_value,
                unrealized_pnl=item.unrealized_pnl,
                currency=item.currency,
                snapshot_at=item.snapshot_at,
                confidence=item.confidence,
            )
        )

    for item in result.cash:
        session.add(
            CashSnapshot(
                upload_id=upload.id,
                ocr_result_id=ocr.id,
                broker=item.broker,
                account_alias=item.account_alias,
                currency=item.currency,
                cash_balance=item.cash_balance,
                available_cash=item.available_cash,
                frozen_cash=item.frozen_cash,
                market_value=item.market_value,
                total_assets=item.total_assets,
                snapshot_at=item.snapshot_at,
                confidence=item.confidence,
            )
        )

    upload.status = "recognized"
    session.add(upload)
    session.commit()
    return ocr
```

- [ ] **Step 4: Run recognition tests**

Run:

```powershell
pytest tests/test_recognition_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add assetflow/recognition/service.py tests/test_recognition_service.py
git commit -m "feat: persist recognition results"
```

### Task 6: Ledger Auto-Confirmation And Review Actions

**Files:**
- Create: `assetflow/ledger.py`
- Create: `tests/test_ledger.py`

- [ ] **Step 1: Write failing ledger tests**

Create `tests/test_ledger.py`:

```python
from pathlib import Path

from sqlmodel import select

from assetflow.ledger import auto_confirm_candidates, confirm_candidate
from assetflow.models import CandidateTransaction, Transaction
from assetflow.recognition.providers import FixtureVisionProvider
from assetflow.recognition.service import process_recognition_result
from assetflow.uploads import store_upload


def _load_candidate(settings, session, fixture: str = "trade_history.json") -> CandidateTransaction:
    upload = store_upload(session, settings, "htsc_global", "ios_shortcut", "trade.png", "image/png", b"\x89PNG\r\n\x1a\nabc")
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition") / fixture)
    result = provider.recognize(Path(upload.image_path), "htsc_global")
    process_recognition_result(session, upload, provider, result)
    return session.exec(select(CandidateTransaction)).one()


def test_auto_confirm_high_confidence_candidate(settings, session) -> None:
    _load_candidate(settings, session)

    confirmed = auto_confirm_candidates(session, min_confidence=0.90)

    transaction = session.exec(select(Transaction)).one()
    assert confirmed == 1
    assert transaction.symbol == "00700"
    assert transaction.status == "confirmed"


def test_confirm_candidate_does_not_duplicate(settings, session) -> None:
    candidate = _load_candidate(settings, session)

    first = confirm_candidate(session, candidate.id)
    second = confirm_candidate(session, candidate.id)

    assert first.id == second.id
    assert len(session.exec(select(Transaction)).all()) == 1
```

- [ ] **Step 2: Run ledger tests to verify failure**

Run:

```powershell
pytest tests/test_ledger.py -v
```

Expected: FAIL because `assetflow.ledger` does not exist.

- [ ] **Step 3: Implement ledger rules**

Create `assetflow/ledger.py`:

```python
from sqlmodel import Session, select

from assetflow.domain import SUPPORTED_CURRENCIES, TEMPLATE_TRADE_TYPES
from assetflow.models import CandidateTransaction, Transaction


REQUIRED_FIELDS = (
    "symbol",
    "security_name",
    "trade_type",
    "trade_date",
    "quantity",
    "price",
    "net_amount",
    "currency",
)


def candidate_is_complete(candidate: CandidateTransaction) -> bool:
    return all(getattr(candidate, field) is not None for field in REQUIRED_FIELDS)


def candidate_can_auto_confirm(candidate: CandidateTransaction, min_confidence: float) -> bool:
    if candidate.review_status != "pending":
        return False
    if candidate.confidence < min_confidence:
        return False
    if not candidate_is_complete(candidate):
        return False
    if candidate.currency not in SUPPORTED_CURRENCIES:
        return False
    if candidate.trade_type not in TEMPLATE_TRADE_TYPES:
        return False
    if candidate.trade_type == "buy" and candidate.net_amount >= 0:
        return False
    if candidate.trade_type == "sell" and candidate.net_amount <= 0:
        return False
    return True


def confirm_candidate(session: Session, candidate_id: int) -> Transaction:
    candidate = session.get(CandidateTransaction, candidate_id)
    if candidate is None:
        raise ValueError(f"Candidate not found: {candidate_id}")
    existing = session.exec(select(Transaction).where(Transaction.dedupe_key == candidate.dedupe_key)).first()
    if existing is not None:
        candidate.review_status = "duplicate"
        candidate.confirmed_transaction_id = existing.id
        session.add(candidate)
        session.commit()
        return existing
    if not candidate_is_complete(candidate):
        candidate.review_status = "needs_review"
        candidate.review_notes = "Missing required fields"
        session.add(candidate)
        session.commit()
        raise ValueError("Candidate is missing required fields")

    transaction = Transaction(
        broker=candidate.broker,
        account_alias=candidate.account_alias,
        market=candidate.market,
        symbol=candidate.symbol,
        security_name=candidate.security_name,
        trade_type=candidate.trade_type,
        trade_date=candidate.trade_date,
        trade_time=candidate.trade_time,
        quantity=candidate.quantity,
        price=candidate.price,
        gross_amount=candidate.gross_amount,
        net_amount=candidate.net_amount,
        commission=candidate.commission,
        fees=candidate.fees,
        currency=candidate.currency,
        position_balance_after=candidate.position_balance_after,
        source_upload_id=candidate.upload_id,
        source_ocr_result_id=candidate.ocr_result_id,
        source_candidate_id=candidate.id,
        dedupe_key=candidate.dedupe_key,
        confidence=candidate.confidence,
    )
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    candidate.review_status = "confirmed"
    candidate.confirmed_transaction_id = transaction.id
    session.add(candidate)
    session.commit()
    return transaction


def auto_confirm_candidates(session: Session, min_confidence: float = 0.90) -> int:
    candidates = session.exec(select(CandidateTransaction).where(CandidateTransaction.review_status == "pending")).all()
    count = 0
    for candidate in candidates:
        if candidate_can_auto_confirm(candidate, min_confidence):
            confirm_candidate(session, candidate.id)
            count += 1
        else:
            candidate.review_status = "needs_review"
            session.add(candidate)
    session.commit()
    return count
```

- [ ] **Step 4: Run ledger tests**

Run:

```powershell
pytest tests/test_ledger.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add assetflow/ledger.py tests/test_ledger.py
git commit -m "feat: confirm recognized transactions"
```

### Task 7: Reconciliation

**Files:**
- Create: `assetflow/reconciliation.py`
- Create: `tests/test_reconciliation.py`

- [ ] **Step 1: Write failing reconciliation tests**

Create `tests/test_reconciliation.py`:

```python
from datetime import datetime
from decimal import Decimal

from sqlmodel import select

from assetflow.models import PositionSnapshot, ReconciliationIssue, Transaction
from assetflow.reconciliation import reconcile_positions


def test_reconcile_matching_position_creates_no_issue(session) -> None:
    session.add(Transaction(
        broker="htsc_global",
        market="HK",
        symbol="00700",
        security_name="腾讯控股",
        trade_type="buy",
        trade_date=datetime(2026, 5, 1).date(),
        quantity=Decimal("100"),
        price=Decimal("350"),
        net_amount=Decimal("-35000"),
        currency="HKD",
        source_upload_id=1,
        source_ocr_result_id=1,
        source_candidate_id=1,
        dedupe_key="match",
        confidence=0.99,
    ))
    session.add(PositionSnapshot(
        upload_id=1,
        ocr_result_id=1,
        broker="htsc_global",
        market="HK",
        symbol="00700",
        quantity=Decimal("100"),
        currency="HKD",
        snapshot_at=datetime(2026, 5, 1, 16),
        confidence=0.95,
    ))
    session.commit()

    count = reconcile_positions(session, broker="htsc_global")

    assert count == 0
    assert session.exec(select(ReconciliationIssue)).all() == []


def test_reconcile_mismatch_creates_issue(session) -> None:
    session.add(Transaction(
        broker="htsc_global",
        market="HK",
        symbol="00700",
        security_name="腾讯控股",
        trade_type="buy",
        trade_date=datetime(2026, 5, 1).date(),
        quantity=Decimal("100"),
        price=Decimal("350"),
        net_amount=Decimal("-35000"),
        currency="HKD",
        source_upload_id=1,
        source_ocr_result_id=1,
        source_candidate_id=1,
        dedupe_key="mismatch",
        confidence=0.99,
    ))
    session.add(PositionSnapshot(
        upload_id=1,
        ocr_result_id=1,
        broker="htsc_global",
        market="HK",
        symbol="00700",
        quantity=Decimal("80"),
        currency="HKD",
        snapshot_at=datetime(2026, 5, 1, 16),
        confidence=0.95,
    ))
    session.commit()

    count = reconcile_positions(session, broker="htsc_global")

    issue = session.exec(select(ReconciliationIssue)).one()
    assert count == 1
    assert issue.expected_value == Decimal("100.000000")
    assert issue.observed_value == Decimal("80.000000")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
pytest tests/test_reconciliation.py -v
```

Expected: FAIL because `assetflow.reconciliation` does not exist.

- [ ] **Step 3: Implement position reconciliation**

Create `assetflow/reconciliation.py`:

```python
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
```

- [ ] **Step 4: Run reconciliation tests**

Run:

```powershell
pytest tests/test_reconciliation.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add assetflow/reconciliation.py tests/test_reconciliation.py
git commit -m "feat: reconcile positions against snapshots"
```

### Task 8: XLSX Template Export

**Files:**
- Create: `assetflow/exporters/__init__.py`
- Create: `assetflow/exporters/xlsx_template.py`
- Create: `tests/test_xlsx_export.py`

- [ ] **Step 1: Write failing xlsx export tests**

Create `tests/test_xlsx_export.py`:

```python
from datetime import date, time
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook, load_workbook

from assetflow.exporters.xlsx_template import EXPECTED_HEADERS, export_transactions_to_template
from assetflow.models import Transaction


def _make_template(path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(EXPECTED_HEADERS)
    ws.append(["20230512", "10:10:10（非必填项）", "000811", "示例股票", "买入", 10000, 14.82, -148244.46, "10000（非必填项）", "0.0000（非必填项）", "44.4600（非必填项）", "请删除示例行"])
    wb.save(path)
    return path


def test_export_writes_transactions_from_row_two(tmp_path: Path) -> None:
    template = _make_template(tmp_path / "导入模板.xlsx")
    output = tmp_path / "output.xlsx"
    tx = Transaction(
        broker="htsc_global",
        market="HK",
        symbol="00700",
        security_name="腾讯控股",
        trade_type="buy",
        trade_date=date(2026, 5, 1),
        trade_time=time(10, 10, 10),
        quantity=Decimal("100"),
        price=Decimal("350.1200"),
        net_amount=Decimal("-35035.0000"),
        commission=Decimal("15.0000"),
        fees=Decimal("8.0000"),
        currency="HKD",
        position_balance_after=Decimal("100"),
        source_upload_id=1,
        source_ocr_result_id=1,
        source_candidate_id=1,
        dedupe_key="xlsx",
        confidence=0.99,
    )

    result = export_transactions_to_template(template, output, [tx])

    wb = load_workbook(output)
    ws = wb["Sheet1"]
    assert result.row_count == 1
    assert [cell.value for cell in ws[1][:12]] == EXPECTED_HEADERS
    assert ws["A2"].value == "20260501"
    assert ws["C2"].value == "00700"
    assert ws["E2"].value == "买入"
    assert ws["H2"].value == -35035
    assert ws["L2"].value is None
    assert ws.max_row == 2
```

- [ ] **Step 2: Run export test to verify failure**

Run:

```powershell
pytest tests/test_xlsx_export.py -v
```

Expected: FAIL because exporter package does not exist.

- [ ] **Step 3: Implement xlsx exporter**

Create `assetflow/exporters/__init__.py`:

```python
__all__ = []
```

Create `assetflow/exporters/xlsx_template.py`:

```python
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from assetflow.domain import TEMPLATE_TRADE_TYPES
from assetflow.models import Transaction


EXPECTED_HEADERS = [
    "成交日期",
    "成交时间",
    "证券代码",
    "证券名称",
    "交易类别",
    "成交数量",
    "成交价格",
    "发生金额",
    "证券余额",
    "佣金",
    "费用",
    "重要提醒",
]


@dataclass(frozen=True)
class ExportResult:
    output_path: Path
    row_count: int
    skipped_ids: list[int]


def _to_excel_number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _validate_headers(ws) -> None:
    headers = [cell.value for cell in ws[1][: len(EXPECTED_HEADERS)]]
    if headers != EXPECTED_HEADERS:
        raise ValueError(f"Template header mismatch. Expected: {EXPECTED_HEADERS}. Actual: {headers}")


def _transaction_row(tx: Transaction) -> list[object]:
    return [
        tx.trade_date.strftime("%Y%m%d"),
        tx.trade_time.strftime("%H:%M:%S") if tx.trade_time else None,
        tx.symbol,
        tx.security_name,
        TEMPLATE_TRADE_TYPES[tx.trade_type],
        _to_excel_number(tx.quantity),
        _to_excel_number(tx.price),
        _to_excel_number(tx.net_amount),
        _to_excel_number(tx.position_balance_after),
        _to_excel_number(tx.commission),
        _to_excel_number(tx.fees),
        None,
    ]


def _is_exportable(tx: Transaction) -> bool:
    return all([
        tx.trade_date,
        tx.symbol,
        tx.security_name,
        tx.trade_type in TEMPLATE_TRADE_TYPES,
        tx.quantity is not None,
        tx.price is not None,
        tx.net_amount is not None,
    ])


def export_transactions_to_template(template_path: Path, output_path: Path, transactions: list[Transaction]) -> ExportResult:
    if not template_path.exists():
        raise FileNotFoundError(template_path)
    wb = load_workbook(template_path)
    ws = wb.active
    _validate_headers(ws)

    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)

    skipped_ids: list[int] = []
    row_count = 0
    for tx in transactions:
        if not _is_exportable(tx):
            skipped_ids.append(tx.id or -1)
            continue
        ws.append(_transaction_row(tx))
        row_count += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return ExportResult(output_path=output_path, row_count=row_count, skipped_ids=skipped_ids)
```

- [ ] **Step 4: Run xlsx export tests**

Run:

```powershell
pytest tests/test_xlsx_export.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add assetflow/exporters tests/test_xlsx_export.py
git commit -m "feat: export transactions with xlsx template"
```

### Task 9: FastAPI Upload, Review, Reconcile, And Export Endpoints

**Files:**
- Create: `assetflow/api.py`
- Create: `assetflow/main.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_api.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import select

from assetflow.api import create_app
from assetflow.models import Transaction


def test_upload_requires_token(settings, session) -> None:
    app = create_app(settings=settings, session=session)
    client = TestClient(app)

    response = client.post("/api/uploads/ios-shortcut", files={"file": ("a.png", b"\x89PNG\r\n\x1a\nabc", "image/png")})

    assert response.status_code == 401


def test_upload_processes_fixture_and_auto_confirms(settings, session) -> None:
    app = create_app(settings=settings, session=session)
    client = TestClient(app)

    response = client.post(
        "/api/uploads/ios-shortcut",
        headers={"X-AssetFlow-Token": "secret-token"},
        data={"broker": "htsc_global"},
        files={"file": ("trade.png", b"\x89PNG\r\n\x1a\nabc", "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["upload"]["status"] == "recognized"
    assert body["auto_confirmed"] == 1
    assert session.exec(select(Transaction)).one().symbol == "00700"
```

- [ ] **Step 2: Run API tests to verify failure**

Run:

```powershell
pytest tests/test_api.py -v
```

Expected: FAIL because `assetflow.api` does not exist.

- [ ] **Step 3: Implement API app**

Create `assetflow/api.py`:

```python
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from sqlmodel import Session, select

from assetflow.config import Settings
from assetflow.db import create_db_and_tables, make_engine
from assetflow.exporters.xlsx_template import export_transactions_to_template
from assetflow.ledger import auto_confirm_candidates, confirm_candidate
from assetflow.models import CandidateTransaction, Transaction
from assetflow.recognition.providers import FixtureVisionProvider, make_provider
from assetflow.recognition.service import process_recognition_result
from assetflow.reconciliation import reconcile_positions
from assetflow.uploads import InvalidUploadError, store_upload


def create_app(settings: Settings | None = None, session: Session | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.ensure_directories()
    engine = None if session is not None else make_engine(settings.database_url)
    if engine is not None:
        create_db_and_tables(engine)

    app = FastAPI(title="AssetFlow")

    def get_session():
        if session is not None:
            yield session
            return
        with Session(engine) as db:
            yield db

    def require_token(x_assetflow_token: Annotated[str | None, Header()] = None) -> None:
        if x_assetflow_token != settings.assetflow_upload_token:
            raise HTTPException(status_code=401, detail="Invalid upload token")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/uploads/ios-shortcut")
    async def upload_ios_shortcut(
        _: Annotated[None, Depends(require_token)],
        db: Annotated[Session, Depends(get_session)],
        broker: Annotated[str, Form()] = "htsc_global",
        account_alias: Annotated[str | None, Form()] = None,
        file: UploadFile = File(),
    ) -> dict[str, object]:
        data = await file.read()
        try:
            upload = store_upload(
                session=db,
                settings=settings,
                broker=broker,
                source="ios_shortcut",
                filename=file.filename or "screenshot.png",
                content_type=file.content_type or "application/octet-stream",
                data=data,
                account_alias=account_alias,
            )
        except InvalidUploadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        auto_confirmed = 0
        if upload.status != "duplicate":
            provider = make_provider(settings)
            result = provider.recognize(Path(upload.image_path), broker)
            process_recognition_result(db, upload, provider, result)
            auto_confirmed = auto_confirm_candidates(db)
            reconcile_positions(db, broker=broker, account_alias=account_alias)
            db.refresh(upload)

        return {
            "upload": {"id": upload.id, "status": upload.status, "duplicate_of_upload_id": upload.duplicate_of_upload_id},
            "auto_confirmed": auto_confirmed,
        }

    @app.get("/api/review/candidates")
    def list_candidates(db: Annotated[Session, Depends(get_session)]) -> list[CandidateTransaction]:
        return db.exec(select(CandidateTransaction).where(CandidateTransaction.review_status != "confirmed")).all()

    @app.post("/api/review/candidates/{candidate_id}/confirm")
    def confirm(candidate_id: int, db: Annotated[Session, Depends(get_session)]) -> dict[str, int]:
        tx = confirm_candidate(db, candidate_id)
        return {"transaction_id": tx.id}

    @app.post("/api/reconcile")
    def reconcile(broker: str = "htsc_global", db: Session = Depends(get_session)) -> dict[str, int]:
        return {"created": reconcile_positions(db, broker=broker)}

    @app.post("/api/exports/xlsx")
    def export_xlsx(
        template_path: str,
        output_path: str,
        currency: str,
        db: Session = Depends(get_session),
    ) -> dict[str, object]:
        transactions = db.exec(select(Transaction).where(Transaction.currency == currency)).all()
        result = export_transactions_to_template(Path(template_path), Path(output_path), transactions)
        return {"output_path": str(result.output_path), "row_count": result.row_count, "skipped_ids": result.skipped_ids}

    return app
```

Create `assetflow/main.py`:

```python
from assetflow.api import create_app

app = create_app()
```

- [ ] **Step 4: Run API tests**

Run:

```powershell
pytest tests/test_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add assetflow/api.py assetflow/main.py tests/test_api.py
git commit -m "feat: expose local assetflow api"
```

### Task 10: iPhone Shortcut Documentation And Final Verification

**Files:**
- Create: `docs/ios-shortcut.md`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-05-02-screenshot-investment-ledger-design.md`

- [ ] **Step 1: Add iOS Shortcut setup document**

Create `docs/ios-shortcut.md`:

```markdown
# iPhone Shortcut Setup

## Prerequisites

- iPhone and AssetFlow computer are on the same Wi-Fi.
- AssetFlow is running with `uvicorn assetflow.main:app --host 0.0.0.0 --port 8787`.
- `.env` contains a strong `ASSETFLOW_UPLOAD_TOKEN`.

## Shortcut Actions

1. Create a new Shortcut named `Upload to AssetFlow`.
2. Enable "Show in Share Sheet".
3. Accept images as input.
4. Add "Get Contents of URL".
5. URL: `http://电脑局域网IP:8787/api/uploads/ios-shortcut`.
6. Method: `POST`.
7. Headers:
   - `X-AssetFlow-Token`: value from `.env`
8. Request Body: Form.
9. Form fields:
   - `broker`: Text, `htsc_global`
   - `file`: File, Shortcut Input
10. Save the Shortcut.

## Usage

1. Open 华泰涨乐全球通.
2. Take a screenshot of 成交记录, 持仓, or 资金 page.
3. Open the screenshot in Photos.
4. Share to `Upload to AssetFlow`.
5. Check AssetFlow review queue if the record is not auto-confirmed.
```

- [ ] **Step 2: Update README with commands**

Replace the `README.md` local run section with:

```markdown
## Local Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn assetflow.main:app --host 0.0.0.0 --port 8787
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/health
```

Upload endpoint:

```text
POST http://电脑局域网IP:8787/api/uploads/ios-shortcut
Header: X-AssetFlow-Token
Form fields: broker=htsc_global, file=<screenshot>
```

iPhone setup is documented in `docs/ios-shortcut.md`.
```

- [ ] **Step 3: Link implementation plan from the design spec**

Append this line to `docs/superpowers/specs/2026-05-02-screenshot-investment-ledger-design.md`:

```markdown

## 实施计划

- `docs/superpowers/plans/2026-05-02-screenshot-investment-ledger.md`
```

- [ ] **Step 4: Run full test suite**

Run:

```powershell
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 5: Run application smoke test**

Run:

```powershell
uvicorn assetflow.main:app --host 127.0.0.1 --port 8787
```

In another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/health
```

Expected response:

```json
{"status":"ok"}
```

Stop Uvicorn after the smoke test.

- [ ] **Step 6: Check git status**

Run:

```powershell
git status --short
```

Expected: only intended files are modified before final commit.

- [ ] **Step 7: Commit docs and final verification**

```powershell
git add README.md docs/ios-shortcut.md docs/superpowers/specs/2026-05-02-screenshot-investment-ledger-design.md
git commit -m "docs: add iphone shortcut instructions"
```

## Final Acceptance Checklist

- [ ] `pytest -v` passes.
- [ ] `POST /api/uploads/ios-shortcut` rejects missing token.
- [ ] Fixture upload creates one upload, one OCR result, one candidate, and one confirmed transaction.
- [ ] Duplicate screenshot upload does not create a second confirmed transaction.
- [ ] Reconciliation creates an issue when position quantity differs.
- [ ] xlsx export preserves template headers and writes data from row 2.
- [ ] README explains local run command and upload endpoint.
- [ ] `docs/ios-shortcut.md` describes iPhone sharing setup.
- [ ] No broker password or broker login automation exists in the codebase.
- [ ] `OPENAI_API_KEY` is read only from environment or `.env`, and is not logged.
