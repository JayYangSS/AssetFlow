# AssetFlow Dashboard UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local FastAPI/Jinja2 dashboard for AssetFlow so the user can upload screenshots, review candidate transactions, view transactions/positions/cash, enter cash movements, reconcile, and export XLSX without opening SQLite directly.

**Architecture:** Keep FastAPI as the single app. Extract reusable service/query helpers from the existing API, add JSON endpoints for dashboard data, and add server-rendered `/ui` pages backed by Jinja2 templates and a small CSS file. Reuse existing models and keep `Transaction` as the unified ledger for trades and cash movements.

**Tech Stack:** FastAPI, SQLModel, Jinja2, pytest, FastAPI TestClient, existing SQLite storage.

---

## File Structure

- Modify `pyproject.toml`: add `jinja2` dependency.
- Modify `assetflow/api.py`: include UI routes, add JSON endpoints, keep existing API behavior.
- Modify `assetflow/models.py`: allow manual ledger transactions to omit OCR/upload source ids.
- Modify `assetflow/db.py`: migrate existing SQLite `transaction` tables so manual transactions can store nullable source ids.
- Create `assetflow/upload_pipeline.py`: shared upload -> OCR -> candidate generation -> auto-confirm -> reconcile flow used by iOS and web upload.
- Create `assetflow/dashboard.py`: query helpers for summary, transactions, latest positions, latest cash, uploads.
- Create `assetflow/cash_movements.py`: create cash-in/out/dividend/fee/adjustment `Transaction` records.
- Create `assetflow/ui.py`: Jinja2 template setup and UI page/form routes.
- Create `assetflow/templates/base.html`: shared layout/navigation.
- Create `assetflow/templates/dashboard.html`: overview page.
- Create `assetflow/templates/upload.html`: web upload page.
- Create `assetflow/templates/review.html`: candidate review page.
- Create `assetflow/templates/transactions.html`: transaction list page.
- Create `assetflow/templates/positions.html`: latest positions page.
- Create `assetflow/templates/cash.html`: cash snapshots and cash movement form.
- Create `assetflow/templates/export.html`: XLSX export form.
- Create `assetflow/static/app.css`: restrained local dashboard styling.
- Create `tests/test_upload_pipeline.py`: shared upload pipeline tests.
- Create `tests/test_dashboard_api.py`: summary/list API tests.
- Create `tests/test_cash_movements.py`: cash movement creation tests.
- Create `tests/test_ui.py`: UI page and form route tests.
- Modify `README.md`: document `/ui` access and dashboard usage.

Implementation command convention in this repo:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest -q --basetemp .pytest-temp"
```

Use that environment for all verification.

---

### Task 1: Add Jinja2 Dependency And Shared Upload Pipeline

**Files:**
- Modify: `pyproject.toml`
- Create: `assetflow/upload_pipeline.py`
- Modify: `assetflow/api.py`
- Test: `tests/test_upload_pipeline.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing upload pipeline tests**

Create `tests/test_upload_pipeline.py`:

```python
from pathlib import Path

from sqlmodel import select

from assetflow.models import CandidateTransaction, OcrResult, Transaction, Upload
from assetflow.upload_pipeline import process_uploaded_image


PNG_BYTES = b"\x89PNG\r\n\x1a\nabc"


def test_upload_pipeline_processes_new_upload(settings, session) -> None:
    result = process_uploaded_image(
        session=session,
        settings=settings,
        broker="htsc_global",
        source="web",
        filename="trade.png",
        content_type="image/png",
        data=PNG_BYTES,
        account_alias=None,
    )

    assert result.upload.status == "recognized"
    assert result.auto_confirmed == 1
    assert result.reconciliation_created == 0
    assert session.exec(select(Upload)).one().source == "web"
    assert session.exec(select(OcrResult)).one().screenshot_type == "trade_history"
    assert session.exec(select(CandidateTransaction)).one().symbol == "00700"
    assert session.exec(select(Transaction)).one().symbol == "00700"


def test_upload_pipeline_skips_duplicate_upload(settings, session) -> None:
    first = process_uploaded_image(
        session=session,
        settings=settings,
        broker="htsc_global",
        source="web",
        filename="first.png",
        content_type="image/png",
        data=PNG_BYTES,
    )
    second = process_uploaded_image(
        session=session,
        settings=settings,
        broker="htsc_global",
        source="web",
        filename="second.png",
        content_type="image/png",
        data=PNG_BYTES,
    )

    assert first.upload.status == "recognized"
    assert second.upload.status == "duplicate"
    assert second.upload.duplicate_of_upload_id == first.upload.id
    assert second.auto_confirmed == 0
    assert len(session.exec(select(OcrResult)).all()) == 1
    assert len(session.exec(select(Transaction)).all()) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_upload_pipeline.py -q --basetemp .pytest-temp"
```

Expected: fail with `ModuleNotFoundError: No module named 'assetflow.upload_pipeline'`.

- [ ] **Step 3: Add Jinja2 dependency**

Modify `pyproject.toml` dependencies:

```toml
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.30.0",
  "sqlmodel>=0.0.22",
  "pydantic-settings>=2.4.0",
  "python-multipart>=0.0.9",
  "pillow>=10.4.0",
  "openpyxl>=3.1.5",
  "openai>=1.50.0",
  "jinja2>=3.1.0",
]
```

- [ ] **Step 4: Implement shared upload pipeline**

Create `assetflow/upload_pipeline.py`:

```python
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session

from assetflow.config import Settings
from assetflow.ledger import auto_confirm_candidates
from assetflow.models import Upload
from assetflow.recognition.providers import make_provider
from assetflow.recognition.service import process_recognition_result
from assetflow.reconciliation import reconcile_positions
from assetflow.uploads import store_upload


@dataclass(frozen=True)
class UploadPipelineResult:
    upload: Upload
    auto_confirmed: int
    reconciliation_created: int


def process_uploaded_image(
    *,
    session: Session,
    settings: Settings,
    broker: str,
    source: str,
    filename: str,
    content_type: str,
    data: bytes,
    account_alias: str | None = None,
) -> UploadPipelineResult:
    upload = store_upload(
        session=session,
        settings=settings,
        broker=broker,
        source=source,
        filename=filename,
        content_type=content_type,
        data=data,
        account_alias=account_alias,
    )
    auto_confirmed = 0
    reconciliation_created = 0
    if upload.status != "duplicate":
        provider = make_provider(settings)
        recognition = provider.recognize(Path(upload.image_path), broker)
        process_recognition_result(session, upload, provider, recognition)
        auto_confirmed = auto_confirm_candidates(session)
        reconciliation_created = reconcile_positions(session, broker=broker, account_alias=account_alias)
        session.refresh(upload)
    return UploadPipelineResult(
        upload=upload,
        auto_confirmed=auto_confirmed,
        reconciliation_created=reconciliation_created,
    )
```

- [ ] **Step 5: Refactor existing iOS upload endpoint to use pipeline**

Modify imports in `assetflow/api.py`:

```python
from assetflow.upload_pipeline import process_uploaded_image
```

Remove now-unused imports from `assetflow.api`:

```python
from pathlib import Path
from assetflow.ledger import auto_confirm_candidates
from assetflow.recognition.providers import make_provider
from assetflow.recognition.service import process_recognition_result
from assetflow.reconciliation import reconcile_positions
from assetflow.uploads import store_upload
```

Replace the body of `upload_ios_shortcut()` after `data = await file.read()` with:

```python
        try:
            result = process_uploaded_image(
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

        upload = result.upload
        return {
            "upload": {"id": upload.id, "status": upload.status, "duplicate_of_upload_id": upload.duplicate_of_upload_id},
            "auto_confirmed": result.auto_confirmed,
        }
```

- [ ] **Step 6: Run targeted tests**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_upload_pipeline.py tests/test_api.py -q --basetemp .pytest-temp"
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add pyproject.toml assetflow/upload_pipeline.py assetflow/api.py tests/test_upload_pipeline.py tests/test_api.py
git commit -m "feat: share upload processing pipeline"
```

---

### Task 2: Add Dashboard Query Helpers And Read APIs

**Files:**
- Create: `assetflow/dashboard.py`
- Modify: `assetflow/api.py`
- Test: `tests/test_dashboard_api.py`

- [ ] **Step 1: Write failing dashboard API tests**

Create `tests/test_dashboard_api.py`:

```python
from datetime import datetime, date, time
from decimal import Decimal

from fastapi.testclient import TestClient

from assetflow.api import create_app
from assetflow.models import CashSnapshot, CandidateTransaction, PositionSnapshot, Transaction, Upload


def test_dashboard_summary_returns_core_counts_and_latest_snapshots(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="positions.png",
        content_hash="positions",
        image_path=str(settings.upload_dir / "positions.png"),
        mime_type="image/png",
        file_size_bytes=10,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    session.add(
        CandidateTransaction(
            upload_id=upload.id,
            ocr_result_id=1,
            broker="htsc_global",
            market="HK",
            symbol="02015",
            security_name="Li Auto-W",
            trade_type="buy",
            trade_date=date(2026, 4, 24),
            trade_time=time(9, 42),
            quantity=Decimal("100"),
            price=Decimal("71"),
            currency="HKD",
            dedupe_key="candidate",
            confidence=0.75,
            review_status="needs_review",
        )
    )
    session.add(
        Transaction(
            broker="htsc_global",
            market="HK",
            symbol="02015",
            security_name="Li Auto-W",
            trade_type="buy",
            trade_date=date(2026, 4, 24),
            trade_time=time(9, 42),
            quantity=Decimal("100"),
            price=Decimal("71"),
            net_amount=Decimal("-7100"),
            currency="HKD",
            source_upload_id=upload.id,
            source_ocr_result_id=1,
            source_candidate_id=1,
            dedupe_key="tx",
            confidence=0.95,
        )
    )
    session.add(
        PositionSnapshot(
            upload_id=upload.id,
            ocr_result_id=1,
            broker="htsc_global",
            market="HK",
            symbol="02015",
            security_name="Li Auto-W",
            quantity=Decimal("100"),
            market_price=Decimal("80"),
            market_value=Decimal("8000"),
            unrealized_pnl=Decimal("900"),
            currency="HKD",
            snapshot_at=datetime(2026, 5, 4, 10, 0),
            confidence=0.9,
        )
    )
    session.add(
        CashSnapshot(
            upload_id=upload.id,
            ocr_result_id=1,
            broker="htsc_global",
            currency="HKD",
            cash_balance=Decimal("1200"),
            available_cash=Decimal("1200"),
            snapshot_at=datetime(2026, 5, 4, 10, 0),
            confidence=0.9,
        )
    )
    session.commit()

    client = TestClient(create_app(settings=settings, session=session))
    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["pending_review_count"] == 1
    assert body["cash_by_currency"]["HKD"] == "1200.000000"
    assert body["position_value_by_currency"]["HKD"] == "8000.000000"
    assert body["recent_transactions"][0]["symbol"] == "02015"
    assert body["recent_uploads"][0]["original_filename"] == "positions.png"


def test_transactions_api_filters_by_currency(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="trade.png",
        content_hash="trade",
        image_path=str(settings.upload_dir / "trade.png"),
        mime_type="image/png",
        file_size_bytes=10,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    for symbol, currency, key in [("02015", "HKD", "hkd"), ("AAPL", "USD", "usd")]:
        session.add(
            Transaction(
                broker="htsc_global",
                market="HK" if currency == "HKD" else "US",
                symbol=symbol,
                security_name=symbol,
                trade_type="buy",
                trade_date=date(2026, 5, 1),
                quantity=Decimal("1"),
                price=Decimal("10"),
                net_amount=Decimal("-10"),
                currency=currency,
                source_upload_id=upload.id,
                source_ocr_result_id=1,
                source_candidate_id=1,
                dedupe_key=key,
                confidence=0.9,
            )
        )
    session.commit()

    client = TestClient(create_app(settings=settings, session=session))
    response = client.get("/api/transactions", params={"currency": "HKD"})

    assert response.status_code == 200
    body = response.json()
    assert [item["symbol"] for item in body] == ["02015"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_dashboard_api.py -q --basetemp .pytest-temp"
```

Expected: fail with 404 for new endpoints.

- [ ] **Step 3: Implement dashboard query helpers**

Create `assetflow/dashboard.py`:

```python
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlmodel import Session, select

from assetflow.models import CashSnapshot, CandidateTransaction, PositionSnapshot, Transaction, Upload


def _decimal_map_to_strings(values: dict[str, Decimal]) -> dict[str, str]:
    return {key: str(value) for key, value in values.items()}


def _latest_positions(session: Session) -> list[PositionSnapshot]:
    snapshots = session.exec(select(PositionSnapshot)).all()
    latest: dict[tuple[str, str | None, str, str], PositionSnapshot] = {}
    for snapshot in snapshots:
        key = (snapshot.broker, snapshot.account_alias, snapshot.symbol, snapshot.currency)
        if key not in latest or snapshot.snapshot_at > latest[key].snapshot_at:
            latest[key] = snapshot
    return sorted(latest.values(), key=lambda item: (item.market or "", item.symbol))


def _latest_cash(session: Session) -> list[CashSnapshot]:
    snapshots = session.exec(select(CashSnapshot)).all()
    latest: dict[tuple[str, str | None, str], CashSnapshot] = {}
    for snapshot in snapshots:
        key = (snapshot.broker, snapshot.account_alias, snapshot.currency)
        if key not in latest or snapshot.snapshot_at > latest[key].snapshot_at:
            latest[key] = snapshot
    return sorted(latest.values(), key=lambda item: item.currency)


def dashboard_summary(session: Session) -> dict[str, object]:
    positions = _latest_positions(session)
    cash = _latest_cash(session)
    cash_by_currency: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in cash:
        cash_by_currency[item.currency] += item.cash_balance or Decimal("0")
    position_value_by_currency: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in positions:
        position_value_by_currency[item.currency] += item.market_value or Decimal("0")
    pending_review_count = len(
        session.exec(
            select(CandidateTransaction).where(CandidateTransaction.review_status.in_(["pending", "needs_review"]))
        ).all()
    )
    recent_transactions = session.exec(select(Transaction).order_by(Transaction.created_at.desc())).all()[:10]
    recent_uploads = session.exec(select(Upload).order_by(Upload.created_at.desc())).all()[:10]
    return {
        "pending_review_count": pending_review_count,
        "cash_by_currency": _decimal_map_to_strings(cash_by_currency),
        "position_value_by_currency": _decimal_map_to_strings(position_value_by_currency),
        "recent_transactions": recent_transactions,
        "recent_uploads": recent_uploads,
    }


def list_transactions(
    session: Session,
    *,
    currency: str | None = None,
    symbol: str | None = None,
    trade_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[Transaction]:
    query = select(Transaction)
    if currency:
        query = query.where(Transaction.currency == currency)
    if symbol:
        query = query.where(Transaction.symbol == symbol)
    if trade_type:
        query = query.where(Transaction.trade_type == trade_type)
    if date_from:
        query = query.where(Transaction.trade_date >= date_from)
    if date_to:
        query = query.where(Transaction.trade_date <= date_to)
    return session.exec(query.order_by(Transaction.trade_date.desc(), Transaction.created_at.desc())).all()


def latest_positions(session: Session) -> list[PositionSnapshot]:
    return _latest_positions(session)


def latest_cash(session: Session) -> list[CashSnapshot]:
    return _latest_cash(session)


def recent_uploads(session: Session) -> list[Upload]:
    return session.exec(select(Upload).order_by(Upload.created_at.desc())).all()[:50]
```

- [ ] **Step 4: Add JSON endpoints**

Modify imports in `assetflow/api.py`:

```python
from datetime import date

from assetflow.dashboard import dashboard_summary, latest_cash, latest_positions, list_transactions, recent_uploads
```

Add endpoints before `return app`:

```python
    @app.get("/api/dashboard/summary")
    def dashboard(db: Annotated[Session, Depends(get_session)]) -> dict[str, object]:
        return dashboard_summary(db)

    @app.get("/api/transactions")
    def transactions(
        db: Annotated[Session, Depends(get_session)],
        currency: str | None = None,
        symbol: str | None = None,
        trade_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Transaction]:
        return list_transactions(
            db,
            currency=currency,
            symbol=symbol,
            trade_type=trade_type,
            date_from=date_from,
            date_to=date_to,
        )

    @app.get("/api/positions/latest")
    def positions_latest(db: Annotated[Session, Depends(get_session)]):
        return latest_positions(db)

    @app.get("/api/cash/latest")
    def cash_latest(db: Annotated[Session, Depends(get_session)]):
        return latest_cash(db)

    @app.get("/api/uploads")
    def uploads(db: Annotated[Session, Depends(get_session)]):
        return recent_uploads(db)
```

- [ ] **Step 5: Run targeted tests**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_dashboard_api.py -q --basetemp .pytest-temp"
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add assetflow/dashboard.py assetflow/api.py tests/test_dashboard_api.py
git commit -m "feat: add dashboard read APIs"
```

---

### Task 3: Add Candidate Ignore And Cash Movement APIs

**Files:**
- Modify: `assetflow/models.py`
- Modify: `assetflow/db.py`
- Create: `assetflow/cash_movements.py`
- Modify: `assetflow/api.py`
- Test: `tests/test_cash_movements.py`
- Test: `tests/test_config_db.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Add to `tests/test_api.py`:

```python
def test_ignore_candidate_updates_review_status(settings, session) -> None:
    app = create_app(settings=settings, session=session)
    client = TestClient(app)
    upload_response = client.post(
        "/api/uploads/ios-shortcut",
        headers={"X-AssetFlow-Token": "secret-token"},
        data={"broker": "htsc_global"},
        files={"file": ("trade.png", b"\x89PNG\r\n\x1a\nabc", "image/png")},
    )
    assert upload_response.status_code == 200
    candidate = session.exec(select(CandidateTransaction)).one()

    response = client.post(f"/api/review/candidates/{candidate.id}/ignore")

    assert response.status_code == 200
    session.refresh(candidate)
    assert candidate.review_status == "ignored"
```

Create `tests/test_cash_movements.py`:

```python
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import select

from assetflow.api import create_app
from assetflow.models import Transaction


def test_create_cash_in_movement(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.post(
        "/api/cash/movements",
        json={
            "broker": "htsc_global",
            "trade_type": "cash_in",
            "trade_date": "2026-05-04",
            "currency": "HKD",
            "amount": "1000",
            "account_alias": None,
        },
    )

    assert response.status_code == 200
    body = response.json()
    tx = session.exec(select(Transaction)).one()
    assert body["transaction_id"] == tx.id
    assert tx.symbol == "CASH"
    assert tx.security_name == "Cash"
    assert tx.trade_type == "cash_in"
    assert tx.trade_date == date(2026, 5, 4)
    assert tx.quantity == Decimal("0")
    assert tx.price == Decimal("0")
    assert tx.net_amount == Decimal("1000.000000")
    assert tx.currency == "HKD"
    assert tx.source_upload_id is None
    assert tx.source_ocr_result_id is None
    assert tx.source_candidate_id is None


def test_create_cash_out_movement_requires_negative_net_amount(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.post(
        "/api/cash/movements",
        json={
            "broker": "htsc_global",
            "trade_type": "cash_out",
            "trade_date": "2026-05-04",
            "currency": "HKD",
            "amount": "1000",
        },
    )

    assert response.status_code == 200
    tx = session.exec(select(Transaction)).one()
    assert tx.trade_type == "cash_out"
    assert tx.net_amount == Decimal("-1000.000000")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_cash_movements.py tests/test_api.py::test_ignore_candidate_updates_review_status -q --basetemp .pytest-temp"
```

Expected: fail with 404 for both new endpoints.

- [ ] **Step 3: Write failing SQLite migration test**

Add to `tests/test_config_db.py`:

```python
def test_create_db_and_tables_relaxes_manual_transaction_source_columns(tmp_path: Path) -> None:
    settings = Settings(assetflow_data_dir=tmp_path / "data")
    settings.ensure_directories()
    engine = make_engine(settings.database_url)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE "transaction" (
                id INTEGER PRIMARY KEY,
                broker VARCHAR NOT NULL,
                account_alias VARCHAR,
                market VARCHAR,
                symbol VARCHAR NOT NULL,
                security_name VARCHAR NOT NULL,
                trade_type VARCHAR NOT NULL,
                trade_date DATE NOT NULL,
                trade_time TIME,
                quantity NUMERIC(20, 6) NOT NULL,
                price NUMERIC(20, 6) NOT NULL,
                gross_amount NUMERIC(20, 6),
                net_amount NUMERIC(20, 6) NOT NULL,
                commission NUMERIC(20, 6),
                fees NUMERIC(20, 6),
                currency VARCHAR NOT NULL,
                position_balance_after NUMERIC(20, 6),
                source_upload_id INTEGER NOT NULL,
                source_ocr_result_id INTEGER NOT NULL,
                source_candidate_id INTEGER NOT NULL,
                dedupe_key VARCHAR NOT NULL,
                confidence FLOAT NOT NULL,
                status VARCHAR NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        connection.exec_driver_sql('CREATE UNIQUE INDEX ix_transaction_dedupe_key ON "transaction" (dedupe_key)')

    create_db_and_tables(engine)

    with engine.connect() as connection:
        rows = connection.exec_driver_sql('PRAGMA table_info("transaction")').all()
    not_null_by_name = {row[1]: row[3] for row in rows}
    assert not_null_by_name["source_upload_id"] == 0
    assert not_null_by_name["source_ocr_result_id"] == 0
    assert not_null_by_name["source_candidate_id"] == 0
```

- [ ] **Step 4: Run migration test to verify it fails**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_config_db.py::test_create_db_and_tables_relaxes_manual_transaction_source_columns -q --basetemp .pytest-temp"
```

Expected: fail because the legacy columns are still `NOT NULL`.

- [ ] **Step 5: Make transaction source fields nullable**

Modify `assetflow/models.py`:

```python
    source_upload_id: int | None = Field(default=None, foreign_key="upload.id")
    source_ocr_result_id: int | None = Field(default=None, foreign_key="ocrresult.id")
    source_candidate_id: int | None = Field(default=None, foreign_key="candidatetransaction.id")
```

- [ ] **Step 6: Add lightweight SQLite migration for existing databases**

Modify `assetflow/db.py`:

```python
from collections.abc import Generator, Sequence

from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, SQLModel, create_engine


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_columns(connection: Connection, table_name: str) -> Sequence[tuple]:
    return connection.exec_driver_sql(f"PRAGMA table_info({_quote_identifier(table_name)})").all()


def _transaction_sources_need_nullable_migration(connection: Connection) -> bool:
    rows = _table_columns(connection, "transaction")
    if not rows:
        return False
    not_null_by_name = {row[1]: row[3] for row in rows}
    return any(
        not_null_by_name.get(column_name) == 1
        for column_name in ("source_upload_id", "source_ocr_result_id", "source_candidate_id")
    )


def _migrate_nullable_transaction_sources(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        if not _transaction_sources_need_nullable_migration(connection):
            return
        old_columns = [row[1] for row in _table_columns(connection, "transaction")]
        connection.exec_driver_sql("PRAGMA legacy_alter_table=ON")
        try:
            connection.exec_driver_sql('ALTER TABLE "transaction" RENAME TO "transaction_old"')
            for row in connection.exec_driver_sql('PRAGMA index_list("transaction_old")').all():
                index_name = row[1]
                if not index_name.startswith("sqlite_autoindex"):
                    connection.exec_driver_sql(f"DROP INDEX {_quote_identifier(index_name)}")
            SQLModel.metadata.tables["transaction"].create(bind=connection)
            column_sql = ", ".join(_quote_identifier(column) for column in old_columns)
            connection.exec_driver_sql(
                f'INSERT INTO "transaction" ({column_sql}) SELECT {column_sql} FROM "transaction_old"'
            )
            connection.exec_driver_sql('DROP TABLE "transaction_old"')
        finally:
            connection.exec_driver_sql("PRAGMA legacy_alter_table=OFF")
```

Update `create_db_and_tables()`:

```python
def create_db_and_tables(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    _migrate_nullable_transaction_sources(engine)
```

- [ ] **Step 7: Run migration test**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_config_db.py::test_create_db_and_tables_relaxes_manual_transaction_source_columns -q --basetemp .pytest-temp"
```

Expected: pass.

- [ ] **Step 8: Implement cash movement service**

Create `assetflow/cash_movements.py`:

```python
from datetime import date
from decimal import Decimal
from hashlib import sha256

from sqlmodel import Session, select

from assetflow.domain import SUPPORTED_BROKERS, SUPPORTED_CURRENCIES
from assetflow.models import Transaction


CASH_MOVEMENT_TYPES = {"cash_in", "cash_out", "dividend", "fee", "adjustment"}


def _signed_amount(trade_type: str, amount: Decimal) -> Decimal:
    absolute = abs(amount)
    if trade_type in {"cash_out", "fee"}:
        return -absolute
    return absolute


def _cash_dedupe_key(
    *,
    broker: str,
    account_alias: str | None,
    trade_type: str,
    trade_date: date,
    currency: str,
    amount: Decimal,
) -> str:
    raw = "|".join([broker, account_alias or "", trade_type, trade_date.isoformat(), currency, str(amount)])
    return sha256(raw.encode("utf-8")).hexdigest()


def create_cash_movement(
    session: Session,
    *,
    broker: str,
    trade_type: str,
    trade_date: date,
    currency: str,
    amount: Decimal,
    account_alias: str | None = None,
) -> Transaction:
    if broker not in SUPPORTED_BROKERS:
        raise ValueError(f"Unsupported broker: {broker}")
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported currency: {currency}")
    if trade_type not in CASH_MOVEMENT_TYPES:
        raise ValueError(f"Unsupported cash movement type: {trade_type}")
    net_amount = _signed_amount(trade_type, amount)
    dedupe_key = _cash_dedupe_key(
        broker=broker,
        account_alias=account_alias,
        trade_type=trade_type,
        trade_date=trade_date,
        currency=currency,
        amount=net_amount,
    )
    existing = session.exec(select(Transaction).where(Transaction.dedupe_key == dedupe_key)).first()
    if existing is not None:
        return existing
    transaction = Transaction(
        broker=broker,
        account_alias=account_alias,
        market=None,
        symbol="CASH",
        security_name="Cash",
        trade_type=trade_type,
        trade_date=trade_date,
        trade_time=None,
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_amount=None,
        net_amount=net_amount,
        commission=None,
        fees=None,
        currency=currency,
        position_balance_after=None,
        source_upload_id=None,
        source_ocr_result_id=None,
        source_candidate_id=None,
        dedupe_key=dedupe_key,
        confidence=1.0,
    )
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return transaction
```

- [ ] **Step 9: Add ignore and cash movement endpoints**

Modify imports in `assetflow/api.py`:

```python
from datetime import date
from decimal import Decimal
from pydantic import BaseModel

from assetflow.cash_movements import create_cash_movement
```

Add request model near `create_app`:

```python
class CashMovementRequest(BaseModel):
    broker: str = "htsc_global"
    account_alias: str | None = None
    trade_type: str
    trade_date: date
    currency: str
    amount: Decimal
```

Add endpoints before `return app`:

```python
    @app.post("/api/review/candidates/{candidate_id}/ignore")
    def ignore_candidate(candidate_id: int, db: Annotated[Session, Depends(get_session)]) -> dict[str, int]:
        candidate = db.get(CandidateTransaction, candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        candidate.review_status = "ignored"
        db.add(candidate)
        db.commit()
        return {"candidate_id": candidate_id}

    @app.post("/api/cash/movements")
    def cash_movement(payload: CashMovementRequest, db: Annotated[Session, Depends(get_session)]) -> dict[str, int | None]:
        try:
            tx = create_cash_movement(
                db,
                broker=payload.broker,
                account_alias=payload.account_alias,
                trade_type=payload.trade_type,
                trade_date=payload.trade_date,
                currency=payload.currency,
                amount=payload.amount,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"transaction_id": tx.id}
```

- [ ] **Step 10: Run targeted tests**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_cash_movements.py tests/test_config_db.py::test_create_db_and_tables_relaxes_manual_transaction_source_columns tests/test_api.py::test_ignore_candidate_updates_review_status -q --basetemp .pytest-temp"
```

Expected: pass.

- [ ] **Step 11: Commit**

```powershell
git add assetflow/models.py assetflow/db.py assetflow/cash_movements.py assetflow/api.py tests/test_cash_movements.py tests/test_config_db.py tests/test_api.py
git commit -m "feat: manage review ignores and cash movements"
```

---

### Task 4: Add UI Route Skeleton, Base Template, And Static CSS

**Files:**
- Create: `assetflow/ui.py`
- Modify: `assetflow/api.py`
- Create: `assetflow/templates/base.html`
- Create: `assetflow/static/app.css`
- Test: `tests/test_ui.py`

- [ ] **Step 1: Write failing UI skeleton tests**

Create `tests/test_ui.py`:

```python
from fastapi.testclient import TestClient

from assetflow.api import create_app


def test_ui_dashboard_page_returns_html(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.get("/ui")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AssetFlow" in response.text
    assert "总览" in response.text


def test_ui_navigation_links_core_pages(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.get("/ui")

    assert 'href="/ui/upload"' in response.text
    assert 'href="/ui/review"' in response.text
    assert 'href="/ui/transactions"' in response.text
    assert 'href="/ui/positions"' in response.text
    assert 'href="/ui/cash"' in response.text
    assert 'href="/ui/export"' in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_ui.py -q --basetemp .pytest-temp"
```

Expected: fail with 404 for `/ui`.

- [ ] **Step 3: Add UI route factory**

Create `assetflow/ui.py`:

```python
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from assetflow.config import Settings
from assetflow.dashboard import dashboard_summary


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_ui_router(settings: Settings, get_session: Callable):
    router = APIRouter()

    @router.get("/ui")
    def dashboard_page(request: Request, db: Session = Depends(get_session)):
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "settings": settings, "summary": dashboard_summary(db), "active": "dashboard"},
        )

    return router


def mount_static(app) -> None:
    static_dir = BASE_DIR / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
```

- [ ] **Step 4: Include UI router and static files**

Modify imports in `assetflow/api.py`:

```python
from assetflow.ui import create_ui_router, mount_static
```

Add after `app = FastAPI(title="AssetFlow")` and after `get_session` is defined. Because `get_session` is currently nested below `app`, place this after the `get_session` function:

```python
    mount_static(app)
    app.include_router(create_ui_router(settings, get_session))
```

- [ ] **Step 5: Add base template and dashboard placeholder**

Create `assetflow/templates/base.html`:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}AssetFlow{% endblock %}</title>
  <link rel="stylesheet" href="/static/app.css">
</head>
<body>
  <header class="topbar">
    <a class="brand" href="/ui">AssetFlow</a>
    <nav>
      <a href="/ui" class="{% if active == 'dashboard' %}active{% endif %}">总览</a>
      <a href="/ui/upload" class="{% if active == 'upload' %}active{% endif %}">上传</a>
      <a href="/ui/review" class="{% if active == 'review' %}active{% endif %}">审核</a>
      <a href="/ui/transactions" class="{% if active == 'transactions' %}active{% endif %}">交易流水</a>
      <a href="/ui/positions" class="{% if active == 'positions' %}active{% endif %}">持仓</a>
      <a href="/ui/cash" class="{% if active == 'cash' %}active{% endif %}">资金流水</a>
      <a href="/ui/export" class="{% if active == 'export' %}active{% endif %}">导出</a>
    </nav>
  </header>
  <main class="page">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

Create `assetflow/templates/dashboard.html`:

```html
{% extends "base.html" %}
{% block title %}总览 - AssetFlow{% endblock %}
{% block content %}
<section class="page-header">
  <h1>总览</h1>
</section>
<section class="cards">
  <article class="card"><span>待审核</span><strong>{{ summary.pending_review_count }}</strong></article>
  <article class="card"><span>现金币种</span><strong>{{ summary.cash_by_currency | length }}</strong></article>
  <article class="card"><span>持仓币种</span><strong>{{ summary.position_value_by_currency | length }}</strong></article>
  <article class="card"><span>最近交易</span><strong>{{ summary.recent_transactions | length }}</strong></article>
</section>
{% endblock %}
```

Create `assetflow/static/app.css`:

```css
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: #1f2933;
  background: #f6f7f9;
}
.topbar {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 12px 24px;
  background: #ffffff;
  border-bottom: 1px solid #d9dee7;
}
.brand {
  font-weight: 700;
  color: #111827;
  text-decoration: none;
}
nav {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
nav a {
  color: #52606d;
  text-decoration: none;
  font-size: 14px;
}
nav a.active {
  color: #0f766e;
  font-weight: 600;
}
.page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 24px;
}
.page-header h1 {
  margin: 0 0 6px;
  font-size: 24px;
}
.page-header p {
  margin: 0 0 18px;
  color: #667085;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}
.card {
  background: #ffffff;
  border: 1px solid #d9dee7;
  border-radius: 8px;
  padding: 16px;
}
.card span {
  display: block;
  color: #667085;
  margin-bottom: 8px;
}
.card strong {
  font-size: 24px;
}
```

- [ ] **Step 6: Run UI skeleton tests**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_ui.py -q --basetemp .pytest-temp"
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add assetflow/ui.py assetflow/api.py assetflow/templates/base.html assetflow/templates/dashboard.html assetflow/static/app.css tests/test_ui.py
git commit -m "feat: add dashboard UI shell"
```

---

### Task 5: Add Dashboard, Upload, Review, Transaction, Position, Cash, And Export Pages

**Files:**
- Modify: `assetflow/ui.py`
- Create: `assetflow/templates/upload.html`
- Create: `assetflow/templates/review.html`
- Create: `assetflow/templates/transactions.html`
- Create: `assetflow/templates/positions.html`
- Create: `assetflow/templates/cash.html`
- Create: `assetflow/templates/export.html`
- Modify: `assetflow/templates/dashboard.html`
- Test: `tests/test_ui.py`

- [ ] **Step 1: Write failing page tests**

Append to `tests/test_ui.py`:

```python
def test_ui_core_pages_return_200(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    for path, expected in [
        ("/ui/upload", "上传截图"),
        ("/ui/review", "候选交易"),
        ("/ui/transactions", "交易流水"),
        ("/ui/positions", "持仓"),
        ("/ui/cash", "资金流水"),
        ("/ui/export", "导出 XLSX"),
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert expected in response.text


def test_upload_page_contains_file_form(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.get("/ui/upload")

    assert 'enctype="multipart/form-data"' in response.text
    assert 'name="file"' in response.text
    assert 'name="broker"' in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_ui.py::test_ui_core_pages_return_200 tests/test_ui.py::test_upload_page_contains_file_form -q --basetemp .pytest-temp"
```

Expected: fail with 404 for `/ui/upload` and other pages.

- [ ] **Step 3: Add UI page routes**

Modify `assetflow/ui.py` imports:

```python
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from assetflow.dashboard import dashboard_summary, latest_cash, latest_positions, list_transactions, recent_uploads
from assetflow.models import CandidateTransaction
```

Add routes inside `create_ui_router()`:

```python
    @router.get("/ui/upload")
    def upload_page(request: Request):
        return templates.TemplateResponse("upload.html", {"request": request, "active": "upload", "result": None})

    @router.get("/ui/review")
    def review_page(request: Request, db: Session = Depends(get_session), status: str | None = None):
        query = select(CandidateTransaction)
        if status:
            query = query.where(CandidateTransaction.review_status == status)
        else:
            query = query.where(CandidateTransaction.review_status.in_(["pending", "needs_review"]))
        candidates = db.exec(query).all()
        return templates.TemplateResponse(
            "review.html",
            {"request": request, "active": "review", "candidates": candidates, "status": status or "open"},
        )

    @router.get("/ui/transactions")
    def transactions_page(request: Request, db: Session = Depends(get_session), currency: str | None = None, symbol: str | None = None):
        return templates.TemplateResponse(
            "transactions.html",
            {
                "request": request,
                "active": "transactions",
                "transactions": list_transactions(db, currency=currency, symbol=symbol),
                "currency": currency or "",
                "symbol": symbol or "",
            },
        )

    @router.get("/ui/positions")
    def positions_page(request: Request, db: Session = Depends(get_session)):
        return templates.TemplateResponse(
            "positions.html",
            {"request": request, "active": "positions", "positions": latest_positions(db)},
        )

    @router.get("/ui/cash")
    def cash_page(request: Request, db: Session = Depends(get_session)):
        return templates.TemplateResponse(
            "cash.html",
            {"request": request, "active": "cash", "cash_snapshots": latest_cash(db), "message": None},
        )

    @router.get("/ui/export")
    def export_page(request: Request):
        return templates.TemplateResponse(
            "export.html",
            {"request": request, "active": "export", "result": None, "error": None},
        )
```

Also add `select` import:

```python
from sqlmodel import Session, select
```

- [ ] **Step 4: Add templates**

Create `assetflow/templates/upload.html`:

```html
{% extends "base.html" %}
{% block title %}上传 - AssetFlow{% endblock %}
{% block content %}
<section class="page-header"><h1>上传截图</h1></section>
<form class="panel" method="post" action="/ui/upload" enctype="multipart/form-data">
  <label>券商 <input name="broker" value="htsc_global"></label>
  <label>账户别名 <input name="account_alias" placeholder="可选"></label>
  <label>截图 <input type="file" name="file" required></label>
  <button type="submit">上传并识别</button>
</form>
{% if result %}
<section class="panel"><h2>上传结果</h2><p>{{ result }}</p></section>
{% endif %}
{% endblock %}
```

Create `assetflow/templates/review.html`:

```html
{% extends "base.html" %}
{% block title %}审核 - AssetFlow{% endblock %}
{% block content %}
<section class="page-header"><h1>候选交易</h1></section>
<table>
  <thead><tr><th>ID</th><th>状态</th><th>日期</th><th>时间</th><th>代码</th><th>名称</th><th>类型</th><th>数量</th><th>价格</th><th>净额</th><th>操作</th></tr></thead>
  <tbody>
  {% for item in candidates %}
    <tr>
      <td>{{ item.id }}</td><td>{{ item.review_status }}</td><td>{{ item.trade_date }}</td><td>{{ item.trade_time }}</td>
      <td>{{ item.symbol }}</td><td>{{ item.security_name }}</td><td>{{ item.trade_type }}</td><td>{{ item.quantity }}</td><td>{{ item.price }}</td><td>{{ item.net_amount }}</td>
      <td>
        <form method="post" action="/ui/review/{{ item.id }}/confirm"><button>确认</button></form>
        <form method="post" action="/ui/review/{{ item.id }}/ignore"><button>忽略</button></form>
      </td>
    </tr>
  {% else %}
    <tr><td colspan="11">没有待处理候选。</td></tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
```

Create `assetflow/templates/transactions.html`:

```html
{% extends "base.html" %}
{% block title %}交易流水 - AssetFlow{% endblock %}
{% block content %}
<section class="page-header"><h1>交易流水</h1></section>
<form class="filters" method="get"><input name="currency" value="{{ currency }}" placeholder="币种"><input name="symbol" value="{{ symbol }}" placeholder="代码"><button>筛选</button></form>
<table>
  <thead><tr><th>ID</th><th>日期</th><th>代码</th><th>名称</th><th>类型</th><th>数量</th><th>价格</th><th>净额</th><th>币种</th></tr></thead>
  <tbody>
  {% for item in transactions %}
    <tr><td>{{ item.id }}</td><td>{{ item.trade_date }}</td><td>{{ item.symbol }}</td><td>{{ item.security_name }}</td><td>{{ item.trade_type }}</td><td>{{ item.quantity }}</td><td>{{ item.price }}</td><td>{{ item.net_amount }}</td><td>{{ item.currency }}</td></tr>
  {% else %}
    <tr><td colspan="9">暂无交易流水。</td></tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
```

Create `assetflow/templates/positions.html`:

```html
{% extends "base.html" %}
{% block title %}持仓 - AssetFlow{% endblock %}
{% block content %}
<section class="page-header"><h1>持仓</h1></section>
<table>
  <thead><tr><th>市场</th><th>代码</th><th>名称</th><th>数量</th><th>可用</th><th>成本</th><th>市价</th><th>市值</th><th>盈亏</th><th>币种</th><th>时间</th></tr></thead>
  <tbody>
  {% for item in positions %}
    <tr><td>{{ item.market }}</td><td>{{ item.symbol }}</td><td>{{ item.security_name }}</td><td>{{ item.quantity }}</td><td>{{ item.available_quantity }}</td><td>{{ item.cost_price }}</td><td>{{ item.market_price }}</td><td>{{ item.market_value }}</td><td>{{ item.unrealized_pnl }}</td><td>{{ item.currency }}</td><td>{{ item.snapshot_at }}</td></tr>
  {% else %}
    <tr><td colspan="11">暂无持仓快照。</td></tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
```

Create `assetflow/templates/cash.html`:

```html
{% extends "base.html" %}
{% block title %}资金流水 - AssetFlow{% endblock %}
{% block content %}
<section class="page-header"><h1>资金流水</h1></section>
<form class="panel" method="post" action="/ui/cash/movements">
  <label>类型 <select name="trade_type"><option value="cash_in">入金</option><option value="cash_out">出金</option><option value="dividend">分红</option><option value="fee">费用</option><option value="adjustment">调整</option></select></label>
  <label>日期 <input type="date" name="trade_date" required></label>
  <label>币种 <input name="currency" value="HKD"></label>
  <label>金额 <input name="amount" required></label>
  <button>新增资金流水</button>
</form>
<section class="panel"><h2>最新现金快照</h2>
{% for item in cash_snapshots %}<p>{{ item.currency }}: {{ item.cash_balance }} / {{ item.snapshot_at }}</p>{% else %}<p>暂无现金快照。</p>{% endfor %}
</section>
{% endblock %}
```

Create `assetflow/templates/export.html`:

```html
{% extends "base.html" %}
{% block title %}导出 - AssetFlow{% endblock %}
{% block content %}
<section class="page-header"><h1>导出 XLSX</h1></section>
<form class="panel" method="post" action="/ui/export">
  <label>模板路径 <input name="template_path" required></label>
  <label>输出路径 <input name="output_path" required></label>
  <label>币种 <input name="currency" value="HKD"></label>
  <button>导出</button>
</form>
{% if result %}<section class="panel"><h2>导出结果</h2><p>{{ result }}</p></section>{% endif %}
{% if error %}<section class="panel error"><h2>导出失败</h2><p>{{ error }}</p></section>{% endif %}
{% endblock %}
```

- [ ] **Step 5: Extend CSS for forms and tables**

Append to `assetflow/static/app.css`:

```css
.panel {
  background: #ffffff;
  border: 1px solid #d9dee7;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
label {
  display: block;
  margin-bottom: 12px;
  color: #344054;
}
input, select {
  display: block;
  width: 100%;
  max-width: 360px;
  padding: 8px 10px;
  margin-top: 4px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
}
button {
  border: 0;
  border-radius: 6px;
  background: #0f766e;
  color: #ffffff;
  padding: 8px 12px;
  cursor: pointer;
}
.filters {
  display: flex;
  gap: 8px;
  align-items: end;
  margin-bottom: 12px;
}
table {
  width: 100%;
  border-collapse: collapse;
  background: #ffffff;
  border: 1px solid #d9dee7;
}
th, td {
  padding: 8px 10px;
  border-bottom: 1px solid #edf0f4;
  text-align: left;
  font-size: 14px;
}
th {
  color: #52606d;
  background: #f8fafc;
}
td form {
  display: inline;
  margin-right: 6px;
}
.error {
  border-color: #fca5a5;
  background: #fff5f5;
}
```

- [ ] **Step 6: Run page tests**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_ui.py -q --basetemp .pytest-temp"
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add assetflow/ui.py assetflow/templates assetflow/static/app.css tests/test_ui.py
git commit -m "feat: add dashboard UI pages"
```

---

### Task 6: Wire UI Form Actions

**Files:**
- Modify: `assetflow/ui.py`
- Test: `tests/test_ui.py`

- [ ] **Step 1: Write failing UI form action tests**

Append to `tests/test_ui.py`:

```python
from decimal import Decimal

from sqlmodel import select

from assetflow.models import CandidateTransaction, Transaction, Upload


def test_ui_upload_form_processes_file(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.post(
        "/ui/upload",
        data={"broker": "htsc_global", "account_alias": ""},
        files={"file": ("trade.png", b"\x89PNG\r\n\x1a\nabc", "image/png")},
    )

    assert response.status_code == 200
    assert "recognized" in response.text
    assert session.exec(select(Upload)).one().source == "web"


def test_ui_confirm_and_ignore_candidate_forms(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))
    client.post(
        "/ui/upload",
        data={"broker": "htsc_global", "account_alias": ""},
        files={"file": ("trade.png", b"\x89PNG\r\n\x1a\nabc", "image/png")},
    )
    candidate = session.exec(select(CandidateTransaction)).one()

    ignore_response = client.post(f"/ui/review/{candidate.id}/ignore")

    assert ignore_response.status_code == 303
    session.refresh(candidate)
    assert candidate.review_status == "ignored"


def test_ui_cash_movement_form_creates_transaction(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.post(
        "/ui/cash/movements",
        data={"trade_type": "cash_in", "trade_date": "2026-05-04", "currency": "HKD", "amount": "1000"},
    )

    assert response.status_code == 303
    tx = session.exec(select(Transaction)).one()
    assert tx.trade_type == "cash_in"
    assert tx.net_amount == Decimal("1000.000000")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_ui.py::test_ui_upload_form_processes_file tests/test_ui.py::test_ui_confirm_and_ignore_candidate_forms tests/test_ui.py::test_ui_cash_movement_form_creates_transaction -q --basetemp .pytest-temp"
```

Expected: fail with 405 for missing POST routes.

- [ ] **Step 3: Add UI form action imports**

Modify `assetflow/ui.py` imports:

```python
from datetime import date
from decimal import Decimal

from assetflow.cash_movements import create_cash_movement
from assetflow.ledger import confirm_candidate
from assetflow.upload_pipeline import process_uploaded_image
from assetflow.uploads import InvalidUploadError
```

- [ ] **Step 4: Add upload POST route**

Inside `create_ui_router()` add:

```python
    @router.post("/ui/upload")
    async def upload_form(
        request: Request,
        db: Session = Depends(get_session),
        broker: str = Form("htsc_global"),
        account_alias: str | None = Form(None),
        file: UploadFile = File(),
    ):
        data = await file.read()
        try:
            result = process_uploaded_image(
                session=db,
                settings=settings,
                broker=broker,
                source="web",
                filename=file.filename or "screenshot.png",
                content_type=file.content_type or "application/octet-stream",
                data=data,
                account_alias=account_alias or None,
            )
            message = f"{result.upload.status}, auto_confirmed={result.auto_confirmed}"
            error = None
        except InvalidUploadError as exc:
            message = None
            error = str(exc)
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "active": "upload", "result": message, "error": error},
        )
```

Update `assetflow/templates/upload.html` to display `error`:

```html
{% if error %}
<section class="panel error"><h2>上传失败</h2><p>{{ error }}</p></section>
{% endif %}
```

- [ ] **Step 5: Add review confirm/ignore POST routes**

Inside `create_ui_router()` add:

```python
    @router.post("/ui/review/{candidate_id}/confirm")
    def confirm_candidate_form(candidate_id: int, db: Session = Depends(get_session)):
        try:
            confirm_candidate(db, candidate_id)
        except ValueError:
            pass
        return RedirectResponse("/ui/review", status_code=303)

    @router.post("/ui/review/{candidate_id}/ignore")
    def ignore_candidate_form(candidate_id: int, db: Session = Depends(get_session)):
        candidate = db.get(CandidateTransaction, candidate_id)
        if candidate is not None:
            candidate.review_status = "ignored"
            db.add(candidate)
            db.commit()
        return RedirectResponse("/ui/review", status_code=303)
```

- [ ] **Step 6: Add cash movement POST route**

Inside `create_ui_router()` add:

```python
    @router.post("/ui/cash/movements")
    def cash_movement_form(
        db: Session = Depends(get_session),
        trade_type: str = Form(),
        trade_date: date = Form(),
        currency: str = Form(),
        amount: Decimal = Form(),
    ):
        create_cash_movement(
            db,
            broker="htsc_global",
            trade_type=trade_type,
            trade_date=trade_date,
            currency=currency,
            amount=amount,
        )
        return RedirectResponse("/ui/cash", status_code=303)
```

- [ ] **Step 7: Run UI form tests**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_ui.py -q --basetemp .pytest-temp"
```

Expected: pass.

- [ ] **Step 8: Commit**

```powershell
git add assetflow/ui.py assetflow/templates/upload.html tests/test_ui.py
git commit -m "feat: wire dashboard UI actions"
```

---

### Task 7: Add UI Export Form Action And README Documentation

**Files:**
- Modify: `assetflow/ui.py`
- Modify: `README.md`
- Test: `tests/test_ui.py`

- [ ] **Step 1: Write failing export form test**

Append to `tests/test_ui.py`:

```python
def test_ui_export_form_reports_missing_template(settings, session, tmp_path) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.post(
        "/ui/export",
        data={
            "template_path": str(tmp_path / "missing.xlsx"),
            "output_path": str(tmp_path / "output.xlsx"),
            "currency": "HKD",
        },
    )

    assert response.status_code == 200
    assert "导出失败" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_ui.py::test_ui_export_form_reports_missing_template -q --basetemp .pytest-temp"
```

Expected: fail with 405 for missing POST route.

- [ ] **Step 3: Add export POST route**

Modify `assetflow/ui.py` imports:

```python
from assetflow.exporters.xlsx_template import export_transactions_to_template
from assetflow.models import Transaction
```

Inside `create_ui_router()` add:

```python
    @router.post("/ui/export")
    def export_form(
        request: Request,
        db: Session = Depends(get_session),
        template_path: str = Form(),
        output_path: str = Form(),
        currency: str = Form(),
    ):
        transactions = db.exec(select(Transaction).where(Transaction.currency == currency)).all()
        try:
            result = export_transactions_to_template(Path(template_path), Path(output_path), transactions)
            message = f"导出 {result.row_count} 行到 {result.output_path}，跳过 {len(result.skipped_ids)} 条"
            error = None
        except Exception as exc:
            message = None
            error = str(exc)
        return templates.TemplateResponse(
            "export.html",
            {"request": request, "active": "export", "result": message, "error": error},
        )
```

- [ ] **Step 4: Update README**

Add after health check in `README.md`:

````markdown
Dashboard UI:

```powershell
Start-Process http://127.0.0.1:8787/ui
```

The local dashboard supports web screenshot upload, candidate review, transaction and position views, cash movement entry, and XLSX export.
````

- [ ] **Step 5: Run targeted tests**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest tests/test_ui.py -q --basetemp .pytest-temp"
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add assetflow/ui.py README.md tests/test_ui.py
git commit -m "feat: add dashboard export action"
```

---

### Task 8: Full Verification And Manual Smoke Check

**Files:**
- Modify only if verification exposes a bug.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && python -m pytest -q --basetemp .pytest-temp"
```

Expected: all tests pass.

- [ ] **Step 2: Start local server**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && uvicorn assetflow.main:app --host 127.0.0.1 --port 8787"
```

Expected: Uvicorn starts without import errors.

- [ ] **Step 3: Manually open dashboard**

Open:

```text
http://127.0.0.1:8787/ui
```

Expected:

- Top navigation renders.
- 总览 page renders.
- 上传, 审核, 交易流水, 持仓, 资金流水, 导出 pages load.

- [ ] **Step 4: Stop server and clean temp directory**

Stop Uvicorn with `Ctrl+C`.

If `.pytest-temp` exists, remove it:

```powershell
Remove-Item -LiteralPath .pytest-temp -Recurse -Force
```

- [ ] **Step 5: Commit any final fixes**

Only if Step 1-3 required changes:

```powershell
git add <changed-files>
git commit -m "fix: polish dashboard UI verification"
```
