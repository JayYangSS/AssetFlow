# AssetFlow Portfolio and Upload View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add portfolio totals, investment return summaries, recent transaction names, and safe original-upload image viewing to the local AssetFlow UI.

**Architecture:** Keep calculations in pure Python helpers so they can be tested without FastAPI. `assetflow.dashboard` remains the query/aggregation boundary, while `assetflow.ui` owns web routes and file-serving safety checks. Jinja templates only render already-prepared values.

**Tech Stack:** FastAPI, SQLModel, Jinja2, pytest, Python `Decimal`, Starlette `FileResponse`.

---

## Execution Notes

- Do implementation in a feature worktree, not directly on `main`.
- Use the conda environment requested for this project:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && pytest -q --basetemp .pytest-tmp"
```

- Keep commits small, one commit per task after the task's verification command passes.
- Use `apply_patch` for manual source edits.
- Do not expose `Upload.image_path` or `Upload.content_hash` in API payloads.

## File Structure

- Create `assetflow/returns.py`
  - Pure FIFO return-summary calculation.
  - No database session dependency.
  - Input: iterable of `Transaction`.
  - Output: list of serializable `ReturnSummary` objects.
- Create `tests/test_returns.py`
  - Unit tests for FIFO matching, dividends, standalone fees, and unmatched sells.
- Modify `assetflow/dashboard.py`
  - Add asset totals to `dashboard_summary`.
  - Add `transaction_profit_summary`.
  - Keep `list_transactions` focused on trade table rows.
- Modify `tests/test_dashboard_api.py`
  - Cover asset totals and API-safe upload payloads.
- Modify `assetflow/ui.py`
  - Add safe upload image path resolver.
  - Add `GET /ui/uploads/{upload_id}/image`.
  - Pass return summaries into `/ui/transactions`.
- Modify `tests/test_ui.py`
  - Cover return summary rendering, upload image links, image serving, and path traversal rejection.
- Modify `assetflow/templates/dashboard.html`
  - Render asset totals.
  - Render recent transaction security names.
  - Add upload image links.
- Modify `assetflow/templates/upload.html`
  - Add upload image links.
- Modify `assetflow/templates/transactions.html`
  - Render investment return summary above the transaction table.
- Modify `assetflow/static/app.css`
  - Add inline action link styling.

---

### Task 1: Pure FIFO Return Summary

**Files:**
- Create: `assetflow/returns.py`
- Create: `tests/test_returns.py`

- [ ] **Step 1: Write failing tests for FIFO, dividends, fees, and unmatched sells**

Create `tests/test_returns.py`:

```python
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
    net_amount: str,
    symbol: str = "00700",
    security_name: str = "Tencent",
    currency: str = "HKD",
    trade_time: time | None = None,
    commission: str | None = None,
    fees: str | None = None,
) -> Transaction:
    return Transaction(
        broker="htsc_global",
        account_alias=None,
        market="HK",
        symbol=symbol,
        security_name=security_name,
        trade_type=trade_type,
        trade_date=trade_date,
        trade_time=trade_time,
        quantity=Decimal(quantity),
        price=Decimal(price),
        net_amount=Decimal(net_amount),
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
    assert summary.realized_pnl == Decimal("200.0")
    assert summary.matched_cost == Decimal("250.0")
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
```

- [ ] **Step 2: Run the new tests and verify they fail because `assetflow.returns` does not exist**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && pytest tests/test_returns.py -q"
```

Expected: FAIL with `ModuleNotFoundError: No module named 'assetflow.returns'`.

- [ ] **Step 3: Implement the return-summary module**

Create `assetflow/returns.py`:

```python
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import time
from decimal import Decimal

from assetflow.models import Transaction


ZERO = Decimal("0")
RETURN_TRADE_TYPES = ("buy", "sell", "dividend", "fee")


@dataclass
class ReturnSummary:
    currency: str
    realized_pnl: Decimal = ZERO
    dividends: Decimal = ZERO
    extra_fees: Decimal = ZERO
    sell_proceeds: Decimal = ZERO
    matched_cost: Decimal = ZERO
    sell_quantity: Decimal = ZERO
    unmatched_quantity: Decimal = ZERO
    transaction_count: int = 0
    incomplete_count: int = 0

    @property
    def total_return(self) -> Decimal:
        return self.realized_pnl + self.dividends - self.extra_fees

    def as_dict(self) -> dict[str, object]:
        return {
            "currency": self.currency,
            "total_return": self.total_return,
            "realized_pnl": self.realized_pnl,
            "dividends": self.dividends,
            "extra_fees": self.extra_fees,
            "sell_proceeds": self.sell_proceeds,
            "matched_cost": self.matched_cost,
            "sell_quantity": self.sell_quantity,
            "unmatched_quantity": self.unmatched_quantity,
            "transaction_count": self.transaction_count,
            "incomplete_count": self.incomplete_count,
        }


@dataclass
class _Lot:
    quantity: Decimal
    total_cost: Decimal


def _stock_key(transaction: Transaction) -> tuple[str, str | None, str | None, str, str]:
    return (
        transaction.broker,
        transaction.account_alias,
        transaction.market,
        transaction.symbol,
        transaction.currency,
    )


def _sort_key(transaction: Transaction) -> tuple[object, ...]:
    return (
        transaction.trade_date,
        transaction.trade_time or time.min,
        transaction.created_at,
        transaction.id or 0,
    )


def _value_or_zero(value: Decimal | None) -> Decimal:
    return value if value is not None else ZERO


def _buy_cost(transaction: Transaction) -> Decimal | None:
    if transaction.net_amount is not None:
        return abs(transaction.net_amount)
    if transaction.gross_amount is not None:
        return transaction.gross_amount + _value_or_zero(transaction.commission) + _value_or_zero(transaction.fees)
    if transaction.quantity is not None and transaction.price is not None:
        return transaction.quantity * transaction.price + _value_or_zero(transaction.commission) + _value_or_zero(transaction.fees)
    return None


def _sell_proceeds(transaction: Transaction) -> Decimal | None:
    if transaction.net_amount is not None:
        return transaction.net_amount
    if transaction.gross_amount is not None:
        return transaction.gross_amount - _value_or_zero(transaction.commission) - _value_or_zero(transaction.fees)
    if transaction.quantity is not None and transaction.price is not None:
        return transaction.quantity * transaction.price - _value_or_zero(transaction.commission) - _value_or_zero(transaction.fees)
    return None


def summarize_returns(transactions: Iterable[Transaction]) -> list[ReturnSummary]:
    summaries: dict[str, ReturnSummary] = {}
    lots_by_stock: dict[tuple[str, str | None, str | None, str, str], deque[_Lot]] = defaultdict(deque)

    for transaction in sorted(transactions, key=_sort_key):
        if transaction.trade_type not in RETURN_TRADE_TYPES:
            continue

        summary = summaries.setdefault(transaction.currency, ReturnSummary(currency=transaction.currency))
        summary.transaction_count += 1

        if transaction.trade_type == "buy":
            cost = _buy_cost(transaction)
            if cost is None or transaction.quantity is None or transaction.quantity <= ZERO:
                summary.incomplete_count += 1
                continue
            lots_by_stock[_stock_key(transaction)].append(_Lot(quantity=transaction.quantity, total_cost=cost))
        elif transaction.trade_type == "sell":
            proceeds = _sell_proceeds(transaction)
            if proceeds is None or transaction.quantity is None or transaction.quantity <= ZERO:
                summary.incomplete_count += 1
                continue
            _match_sell(transaction, proceeds, summary, lots_by_stock[_stock_key(transaction)])
        elif transaction.trade_type == "dividend":
            if transaction.net_amount is None:
                summary.incomplete_count += 1
                continue
            summary.dividends += transaction.net_amount
        elif transaction.trade_type == "fee":
            if transaction.net_amount is None:
                summary.incomplete_count += 1
                continue
            summary.extra_fees += abs(transaction.net_amount)

    return [summaries[currency] for currency in sorted(summaries)]


def _match_sell(transaction: Transaction, proceeds: Decimal, summary: ReturnSummary, lots: deque[_Lot]) -> None:
    sell_quantity = transaction.quantity
    summary.sell_quantity += sell_quantity
    summary.sell_proceeds += proceeds

    remaining = sell_quantity
    while remaining > ZERO and lots:
        lot = lots[0]
        matched_quantity = min(remaining, lot.quantity)
        proceeds_part = proceeds * matched_quantity / sell_quantity
        cost_part = lot.total_cost * matched_quantity / lot.quantity

        summary.realized_pnl += proceeds_part - cost_part
        summary.matched_cost += cost_part

        remaining -= matched_quantity
        lot.quantity -= matched_quantity
        lot.total_cost -= cost_part
        if lot.quantity == ZERO:
            lots.popleft()

    if remaining > ZERO:
        summary.unmatched_quantity += remaining
```

- [ ] **Step 4: Run the new tests and verify they pass**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && pytest tests/test_returns.py -q"
```

Expected: PASS, `4 passed`.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add assetflow/returns.py tests/test_returns.py
git commit -m "feat: calculate investment return summaries"
```

---

### Task 2: Dashboard Asset Totals and Return Summary Query

**Files:**
- Modify: `assetflow/dashboard.py`
- Modify: `tests/test_dashboard_api.py`

- [ ] **Step 1: Write failing dashboard API tests**

Append these tests to `tests/test_dashboard_api.py`:

```python
def test_dashboard_summary_includes_asset_totals_by_currency(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="assets.png",
        content_hash="asset-totals",
        image_path=str(settings.upload_dir / "assets.png"),
        mime_type="image/png",
        file_size_bytes=10,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    session.add(
        PositionSnapshot(
            upload_id=upload.id,
            ocr_result_id=1,
            broker="htsc_global",
            market="HK",
            symbol="00700",
            security_name="Tencent",
            quantity=Decimal("100"),
            market_value=Decimal("8000"),
            currency="HKD",
            snapshot_at=datetime(2026, 5, 7, 10, 0),
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
            snapshot_at=datetime(2026, 5, 7, 10, 0),
            confidence=0.9,
        )
    )
    session.add(
        CashSnapshot(
            upload_id=upload.id,
            ocr_result_id=1,
            broker="htsc_global",
            currency="USD",
            cash_balance=Decimal("300"),
            snapshot_at=datetime(2026, 5, 7, 10, 0),
            confidence=0.9,
        )
    )
    session.commit()

    client = TestClient(create_app(settings=settings, session=session))
    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    assert response.json()["asset_totals"] == [
        {
            "currency": "HKD",
            "position_value": "8000.000000",
            "cash_balance": "1200.000000",
            "total_assets": "9200.000000",
        },
        {
            "currency": "USD",
            "position_value": "0",
            "cash_balance": "300.000000",
            "total_assets": "300.000000",
        },
    ]


def test_transaction_profit_summary_returns_dividends_fees_and_fifo_pnl(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="returns.png",
        content_hash="return-summary",
        image_path=str(settings.upload_dir / "returns.png"),
        mime_type="image/png",
        file_size_bytes=10,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    for tx in [
        Transaction(
            broker="htsc_global",
            market="HK",
            symbol="00700",
            security_name="Tencent",
            trade_type="buy",
            trade_date=date(2026, 1, 2),
            quantity=Decimal("100"),
            price=Decimal("10"),
            net_amount=Decimal("-1008"),
            fees=Decimal("8"),
            currency="HKD",
            dedupe_key="summary-buy",
            confidence=0.95,
        ),
        Transaction(
            broker="htsc_global",
            market="HK",
            symbol="00700",
            security_name="Tencent",
            trade_type="sell",
            trade_date=date(2026, 2, 3),
            quantity=Decimal("40"),
            price=Decimal("12"),
            net_amount=Decimal("480"),
            fees=Decimal("5"),
            currency="HKD",
            dedupe_key="summary-sell",
            confidence=0.95,
        ),
        Transaction(
            broker="htsc_global",
            market="HK",
            symbol="00700",
            security_name="Tencent",
            trade_type="dividend",
            trade_date=date(2026, 3, 4),
            quantity=Decimal("0"),
            price=Decimal("0"),
            net_amount=Decimal("12"),
            currency="HKD",
            dedupe_key="summary-dividend",
            confidence=0.95,
        ),
        Transaction(
            broker="htsc_global",
            symbol="CASH",
            security_name="Cash",
            trade_type="fee",
            trade_date=date(2026, 3, 5),
            quantity=Decimal("0"),
            price=Decimal("0"),
            net_amount=Decimal("-3"),
            currency="HKD",
            dedupe_key="summary-fee",
            confidence=0.95,
        ),
    ]:
        session.add(tx)
    session.commit()

    from assetflow.dashboard import transaction_profit_summary

    summaries = transaction_profit_summary(session)

    assert summaries == [
        {
            "currency": "HKD",
            "total_return": "85.800000",
            "realized_pnl": "76.800000",
            "dividends": "12.000000",
            "extra_fees": "3.000000",
            "sell_proceeds": "480.000000",
            "matched_cost": "403.200000",
            "sell_quantity": "40.000000",
            "unmatched_quantity": "0",
            "transaction_count": 4,
            "incomplete_count": 0,
        }
    ]
```

- [ ] **Step 2: Run the targeted tests and verify failure**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && pytest tests/test_dashboard_api.py::test_dashboard_summary_includes_asset_totals_by_currency tests/test_dashboard_api.py::test_transaction_profit_summary_returns_dividends_fees_and_fifo_pnl -q"
```

Expected: FAIL because `asset_totals` and `transaction_profit_summary` are missing.

- [ ] **Step 3: Implement asset totals and return summary in `assetflow/dashboard.py`**

Patch `assetflow/dashboard.py`:

```python
from assetflow.returns import RETURN_TRADE_TYPES, summarize_returns
```

Add these helpers near `_decimal_map_to_strings`:

```python
def _decimal_to_string(value: Decimal) -> str:
    return str(value)


def _return_decimal_to_string(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.000001")))


def _asset_totals_payload(
    cash_by_currency: dict[str, Decimal],
    position_value_by_currency: dict[str, Decimal],
) -> list[dict[str, str]]:
    payload = []
    for currency in sorted(set(cash_by_currency) | set(position_value_by_currency)):
        cash_balance = cash_by_currency.get(currency, Decimal("0"))
        position_value = position_value_by_currency.get(currency, Decimal("0"))
        payload.append(
            {
                "currency": currency,
                "position_value": _decimal_to_string(position_value),
                "cash_balance": _decimal_to_string(cash_balance),
                "total_assets": _decimal_to_string(position_value + cash_balance),
            }
        )
    return payload
```

Add `"asset_totals"` to `dashboard_summary`:

```python
    return {
        "pending_review_count": pending_review_count,
        "cash_by_currency": _decimal_map_to_strings(cash_by_currency),
        "position_value_by_currency": _decimal_map_to_strings(position_value_by_currency),
        "asset_totals": _asset_totals_payload(cash_by_currency, position_value_by_currency),
        "recent_transactions": recent_transactions,
        "recent_uploads": recent_uploads,
    }
```

Add this public function after `list_transactions`:

```python
def transaction_profit_summary(
    session: Session,
    *,
    currency: str | None = None,
    symbol: str | None = None,
) -> list[dict[str, object]]:
    query = select(Transaction).where(Transaction.trade_type.in_(RETURN_TRADE_TYPES))
    if currency:
        query = query.where(Transaction.currency == currency)
    if symbol:
        query = query.where(Transaction.symbol == symbol)
    transactions = session.exec(
        query.order_by(Transaction.trade_date, Transaction.trade_time, Transaction.created_at, Transaction.id)
    ).all()
    return [_return_summary_payload(summary) for summary in summarize_returns(transactions)]
```

Add this helper below it:

```python
def _return_summary_payload(summary) -> dict[str, object]:
    values = summary.as_dict()
    return {
        "currency": values["currency"],
        "total_return": _return_decimal_to_string(values["total_return"]),
        "realized_pnl": _return_decimal_to_string(values["realized_pnl"]),
        "dividends": _return_decimal_to_string(values["dividends"]),
        "extra_fees": _return_decimal_to_string(values["extra_fees"]),
        "sell_proceeds": _return_decimal_to_string(values["sell_proceeds"]),
        "matched_cost": _return_decimal_to_string(values["matched_cost"]),
        "sell_quantity": _return_decimal_to_string(values["sell_quantity"]),
        "unmatched_quantity": _decimal_to_string(values["unmatched_quantity"]),
        "transaction_count": values["transaction_count"],
        "incomplete_count": values["incomplete_count"],
    }
```

- [ ] **Step 4: Run targeted tests and verify they pass**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && pytest tests/test_dashboard_api.py::test_dashboard_summary_includes_asset_totals_by_currency tests/test_dashboard_api.py::test_transaction_profit_summary_returns_dividends_fees_and_fifo_pnl -q"
```

Expected: PASS, `2 passed`.

- [ ] **Step 5: Run dashboard API tests**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && pytest tests/test_dashboard_api.py -q"
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add assetflow/dashboard.py tests/test_dashboard_api.py
git commit -m "feat: add portfolio and return summaries"
```

---

### Task 3: Safe Upload Image Endpoint

**Files:**
- Modify: `assetflow/ui.py`
- Modify: `tests/test_ui.py`

- [ ] **Step 1: Write failing UI endpoint tests**

Append these tests to `tests/test_ui.py`:

```python
def test_ui_upload_image_endpoint_serves_original_upload(settings, session) -> None:
    image_path = settings.upload_dir / "sample.png"
    image_bytes = b"\x89PNG\r\n\x1a\nsample"
    image_path.write_bytes(image_bytes)
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="sample.png",
        content_hash="ui-image-serve",
        image_path=str(image_path),
        mime_type="image/png",
        file_size_bytes=len(image_bytes),
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    client = TestClient(create_app(settings=settings, session=session))

    response = client.get(f"/ui/uploads/{upload.id}/image")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == image_bytes


def test_ui_upload_image_endpoint_returns_404_for_missing_upload(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.get("/ui/uploads/999/image")

    assert response.status_code == 404


def test_ui_upload_image_endpoint_rejects_paths_outside_upload_dir(settings, session, tmp_path) -> None:
    outside_path = tmp_path / "outside.png"
    outside_path.write_bytes(b"outside")
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="outside.png",
        content_hash="ui-image-outside",
        image_path=str(outside_path),
        mime_type="image/png",
        file_size_bytes=7,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    client = TestClient(create_app(settings=settings, session=session))

    response = client.get(f"/ui/uploads/{upload.id}/image")

    assert response.status_code == 404
```

- [ ] **Step 2: Run endpoint tests and verify failure**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && pytest tests/test_ui.py::test_ui_upload_image_endpoint_serves_original_upload tests/test_ui.py::test_ui_upload_image_endpoint_returns_404_for_missing_upload tests/test_ui.py::test_ui_upload_image_endpoint_rejects_paths_outside_upload_dir -q"
```

Expected: FAIL with 404 for the serving test because the route is not registered.

- [ ] **Step 3: Implement safe upload image serving**

Patch imports in `assetflow/ui.py`:

```python
from fastapi.responses import FileResponse, RedirectResponse
```

Patch model imports:

```python
from assetflow.models import CandidateTransaction, PositionSnapshot, Transaction, Upload
```

Add this helper inside `create_ui_router`, before route definitions:

```python
    def resolve_upload_image_path(upload: Upload) -> Path:
        upload_dir = settings.upload_dir.resolve()
        image_path = Path(upload.image_path).resolve()
        try:
            image_path.relative_to(upload_dir)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Upload image not found") from exc
        if not image_path.is_file():
            raise HTTPException(status_code=404, detail="Upload image not found")
        return image_path
```

Add this route after `/ui/upload` routes:

```python
    @router.get("/ui/uploads/{upload_id}/image")
    def upload_image(upload_id: int, db: Session = Depends(get_session)):
        upload = db.get(Upload, upload_id)
        if upload is None:
            raise HTTPException(status_code=404, detail="Upload not found")
        return FileResponse(
            resolve_upload_image_path(upload),
            media_type=upload.mime_type,
            filename=upload.original_filename,
        )
```

- [ ] **Step 4: Run endpoint tests and verify they pass**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && pytest tests/test_ui.py::test_ui_upload_image_endpoint_serves_original_upload tests/test_ui.py::test_ui_upload_image_endpoint_returns_404_for_missing_upload tests/test_ui.py::test_ui_upload_image_endpoint_rejects_paths_outside_upload_dir -q"
```

Expected: PASS, `3 passed`.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add assetflow/ui.py tests/test_ui.py
git commit -m "feat: serve uploaded screenshots safely"
```

---

### Task 4: UI Rendering for Asset Totals, Return Summary, Names, and Image Links

**Files:**
- Modify: `assetflow/ui.py`
- Modify: `assetflow/templates/dashboard.html`
- Modify: `assetflow/templates/upload.html`
- Modify: `assetflow/templates/transactions.html`
- Modify: `assetflow/static/app.css`
- Modify: `tests/test_ui.py`

- [ ] **Step 1: Write failing UI rendering tests**

Append these tests to `tests/test_ui.py`:

```python
def test_ui_dashboard_renders_asset_totals_and_recent_transaction_name(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="dashboard.png",
        content_hash="ui-dashboard-assets",
        image_path=str(settings.upload_dir / "dashboard.png"),
        mime_type="image/png",
        file_size_bytes=10,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    session.add(
        PositionSnapshot(
            upload_id=upload.id,
            ocr_result_id=1,
            broker="htsc_global",
            market="HK",
            symbol="00700",
            security_name="Tencent",
            quantity=Decimal("100"),
            market_value=Decimal("8000"),
            currency="HKD",
            snapshot_at=datetime(2026, 5, 7, 10, 0),
            confidence=0.9,
        )
    )
    session.add(
        Transaction(
            broker="htsc_global",
            market="HK",
            symbol="00700",
            security_name="Tencent",
            trade_type="buy",
            trade_date=date(2026, 5, 7),
            quantity=Decimal("100"),
            price=Decimal("80"),
            net_amount=Decimal("-8000"),
            currency="HKD",
            dedupe_key="ui-dashboard-name",
            confidence=0.95,
        )
    )
    session.commit()
    client = TestClient(create_app(settings=settings, session=session))

    response = client.get("/ui")

    assert response.status_code == 200
    assert "资产汇总" in response.text
    assert "持仓市值" in response.text
    assert "合计资产" in response.text
    assert "8000.000000" in response.text
    assert "Tencent" in response.text


def test_ui_transactions_page_renders_investment_return_summary(settings, session) -> None:
    for tx in [
        Transaction(
            broker="htsc_global",
            market="HK",
            symbol="00700",
            security_name="Tencent",
            trade_type="buy",
            trade_date=date(2026, 1, 2),
            quantity=Decimal("100"),
            price=Decimal("10"),
            net_amount=Decimal("-1008"),
            fees=Decimal("8"),
            currency="HKD",
            dedupe_key="ui-return-buy",
            confidence=0.95,
        ),
        Transaction(
            broker="htsc_global",
            market="HK",
            symbol="00700",
            security_name="Tencent",
            trade_type="sell",
            trade_date=date(2026, 2, 3),
            quantity=Decimal("40"),
            price=Decimal("12"),
            net_amount=Decimal("480"),
            fees=Decimal("5"),
            currency="HKD",
            dedupe_key="ui-return-sell",
            confidence=0.95,
        ),
        Transaction(
            broker="htsc_global",
            market="HK",
            symbol="00700",
            security_name="Tencent",
            trade_type="dividend",
            trade_date=date(2026, 3, 4),
            quantity=Decimal("0"),
            price=Decimal("0"),
            net_amount=Decimal("12"),
            currency="HKD",
            dedupe_key="ui-return-dividend",
            confidence=0.95,
        ),
        Transaction(
            broker="htsc_global",
            symbol="CASH",
            security_name="Cash",
            trade_type="fee",
            trade_date=date(2026, 3, 5),
            quantity=Decimal("0"),
            price=Decimal("0"),
            net_amount=Decimal("-3"),
            currency="HKD",
            dedupe_key="ui-return-fee",
            confidence=0.95,
        ),
    ]:
        session.add(tx)
    session.commit()
    client = TestClient(create_app(settings=settings, session=session))

    response = client.get("/ui/transactions")

    assert response.status_code == 200
    assert "投资收益" in response.text
    assert "总收益" in response.text
    assert "买卖已实现盈亏" in response.text
    assert "分红收入" in response.text
    assert "额外费用" in response.text
    assert "85.800000" in response.text
    assert "76.800000" in response.text
    assert "12.000000" in response.text
    assert "3.000000" in response.text
    assert "cash_in" not in response.text


def test_ui_dashboard_and_upload_pages_link_to_uploaded_images(settings, session) -> None:
    image_path = settings.upload_dir / "linked.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nlinked")
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="linked.png",
        content_hash="ui-linked-image",
        image_path=str(image_path),
        mime_type="image/png",
        file_size_bytes=16,
        status="recognized",
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    client = TestClient(create_app(settings=settings, session=session))

    dashboard_response = client.get("/ui")
    upload_response = client.get("/ui/upload")
    expected_href = f'href="/ui/uploads/{upload.id}/image"'

    assert dashboard_response.status_code == 200
    assert upload_response.status_code == 200
    assert expected_href in dashboard_response.text
    assert expected_href in upload_response.text
    assert "查看" in dashboard_response.text
    assert "查看" in upload_response.text
```

- [ ] **Step 2: Run rendering tests and verify failure**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && pytest tests/test_ui.py::test_ui_dashboard_renders_asset_totals_and_recent_transaction_name tests/test_ui.py::test_ui_transactions_page_renders_investment_return_summary tests/test_ui.py::test_ui_dashboard_and_upload_pages_link_to_uploaded_images -q"
```

Expected: FAIL because templates and route context do not render the new values.

- [ ] **Step 3: Pass return summary into transactions route**

Patch imports in `assetflow/ui.py`:

```python
from assetflow.dashboard import (
    dashboard_summary,
    latest_cash,
    latest_positions,
    list_cash_movements,
    list_transactions,
    recent_uploads,
    transaction_profit_summary,
)
```

Patch the `/ui/transactions` route context:

```python
                "transactions": list_transactions(db, currency=currency, symbol=symbol),
                "return_summaries": transaction_profit_summary(db, currency=currency, symbol=symbol),
                "currency": currency or "",
                "symbol": symbol or "",
```

- [ ] **Step 4: Update `dashboard.html`**

Replace the body content after the cards with:

```html
<section class="panel">
  <h2>资产汇总</h2>
  <div class="table-wrap">
    <table>
      <thead><tr><th>币种</th><th>持仓市值</th><th>现金余额</th><th>合计资产</th></tr></thead>
      <tbody>
      {% for item in summary.asset_totals %}
        <tr><td>{{ item.currency }}</td><td>{{ item.position_value }}</td><td>{{ item.cash_balance }}</td><td>{{ item.total_assets }}</td></tr>
      {% else %}
        <tr><td colspan="4">暂无资产数据。</td></tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
</section>
<section class="grid-two">
  <article class="panel">
    <h2>最近上传</h2>
    <div class="table-wrap">
      <table>
        <thead><tr><th>ID</th><th>券商</th><th>文件</th><th>状态</th><th>时间</th><th>操作</th></tr></thead>
        <tbody>
        {% for item in summary.recent_uploads %}
          <tr>
            <td>{{ item.id }}</td>
            <td>{{ item.broker }}</td>
            <td>{{ item.original_filename }}</td>
            <td>{{ item.status }}</td>
            <td>{{ item.created_at }}</td>
            <td><a class="inline-link" href="/ui/uploads/{{ item.id }}/image" target="_blank" rel="noopener">查看</a></td>
          </tr>
        {% else %}
          <tr><td colspan="6">暂无上传。</td></tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </article>
  <article class="panel">
    <h2>最近交易</h2>
    <div class="table-wrap">
      <table>
        <thead><tr><th>日期</th><th>代码</th><th>名称</th><th>类型</th><th>数量</th><th>现金变动</th></tr></thead>
        <tbody>
        {% for item in summary.recent_transactions %}
          <tr><td>{{ item.trade_date }}</td><td>{{ item.symbol }}</td><td>{{ item.security_name }}</td><td>{{ item.trade_type }}</td><td>{{ item.quantity }}</td><td>{{ item.net_amount }} {{ item.currency }}</td></tr>
        {% else %}
          <tr><td colspan="6">暂无交易。</td></tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </article>
</section>
```

- [ ] **Step 5: Update `upload.html`**

Change the upload table header and rows:

```html
<thead><tr><th>ID</th><th>券商</th><th>账户</th><th>文件</th><th>类型</th><th>大小</th><th>状态</th><th>操作</th></tr></thead>
```

```html
<tr>
  <td>{{ item.id }}</td>
  <td>{{ item.broker }}</td>
  <td>{{ item.account_alias or "" }}</td>
  <td>{{ item.original_filename }}</td>
  <td>{{ item.mime_type }}</td>
  <td>{{ item.file_size_bytes }}</td>
  <td>{{ item.status }}</td>
  <td><a class="inline-link" href="/ui/uploads/{{ item.id }}/image" target="_blank" rel="noopener">查看</a></td>
</tr>
```

Change the empty row colspan to 8:

```html
<tr><td colspan="8">暂无上传。</td></tr>
```

- [ ] **Step 6: Update `transactions.html`**

Insert this block after the filters form and before the transaction table:

```html
<section class="panel">
  <h2>投资收益</h2>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>币种</th>
          <th>总收益</th>
          <th>买卖已实现盈亏</th>
          <th>分红收入</th>
          <th>额外费用</th>
          <th>卖出收入</th>
          <th>匹配成本</th>
          <th>卖出数量</th>
          <th>未匹配数量</th>
          <th>不完整记录</th>
        </tr>
      </thead>
      <tbody>
      {% for item in return_summaries %}
        <tr>
          <td>{{ item.currency }}</td>
          <td>{{ item.total_return }}</td>
          <td>{{ item.realized_pnl }}</td>
          <td>{{ item.dividends }}</td>
          <td>{{ item.extra_fees }}</td>
          <td>{{ item.sell_proceeds }}</td>
          <td>{{ item.matched_cost }}</td>
          <td>{{ item.sell_quantity }}</td>
          <td>{{ item.unmatched_quantity }}</td>
          <td>{{ item.incomplete_count }}</td>
        </tr>
      {% else %}
        <tr><td colspan="10">暂无收益统计。</td></tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
</section>
```

- [ ] **Step 7: Add link styling**

Append to `assetflow/static/app.css`:

```css
.inline-link {
  color: var(--accent);
  font-weight: 700;
}

.inline-link:hover {
  text-decoration: underline;
}
```

- [ ] **Step 8: Run rendering tests and verify they pass**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && pytest tests/test_ui.py::test_ui_dashboard_renders_asset_totals_and_recent_transaction_name tests/test_ui.py::test_ui_transactions_page_renders_investment_return_summary tests/test_ui.py::test_ui_dashboard_and_upload_pages_link_to_uploaded_images -q"
```

Expected: PASS, `3 passed`.

- [ ] **Step 9: Run all UI tests**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && pytest tests/test_ui.py -q"
```

Expected: PASS.

- [ ] **Step 10: Commit Task 4**

Run:

```powershell
git add assetflow/ui.py assetflow/templates/dashboard.html assetflow/templates/upload.html assetflow/templates/transactions.html assetflow/static/app.css tests/test_ui.py
git commit -m "feat: show portfolio totals and upload previews"
```

---

### Task 5: Full Verification and Documentation Touch-Up

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Inspect README UI section**

Run:

```powershell
rg -n "/ui|收益|资产|截图|上传" README.md
```

Expected: existing UI startup and page descriptions are shown.

- [ ] **Step 2: Update README UI page descriptions**

Replace the existing `/ui`, `/ui/upload`, and `/ui/transactions` bullets with:

```markdown
- `/ui`：总览页，展示按币种汇总的持仓市值、现金余额和合计资产，并可查看最近上传截图。
- `/ui/upload`：浏览器上传截图，也可查看最近上传的原始图片。
- `/ui/transactions`：已确认交易流水，可按币种、股票代码过滤，并展示按 FIFO 计算的买卖已实现盈亏、分红收入、额外费用和总收益。
```

- [ ] **Step 3: Run focused tests**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && pytest tests/test_returns.py tests/test_dashboard_api.py tests/test_ui.py -q --basetemp .pytest-tmp"
```

Expected: PASS.

- [ ] **Step 4: Run full test suite**

Run:

```powershell
cmd /d /c "call C:\Users\jiyang\miniconda3\condabin\conda.bat activate assetflow-ocr && pytest -q --basetemp .pytest-tmp"
```

Expected: PASS.

- [ ] **Step 5: Remove `.pytest-tmp` safely**

Run:

```powershell
$workspace = (Resolve-Path .).Path
$tmp = Join-Path $workspace '.pytest-tmp'
if (Test-Path -LiteralPath $tmp) {
  $resolved = (Resolve-Path -LiteralPath $tmp).Path
  if (-not $resolved.StartsWith($workspace, [System.StringComparison]::OrdinalIgnoreCase)) { throw "Refusing to remove outside workspace: $resolved" }
  Remove-Item -LiteralPath $resolved -Recurse -Force
}
```

- [ ] **Step 6: Check diff whitespace**

Run:

```powershell
git diff --check
```

Expected: exit 0. LF/CRLF warnings are acceptable on this Windows repo.

- [ ] **Step 7: Commit README update**

Run:

```powershell
git add README.md
git commit -m "docs: update UI asset summary guide"
```

- [ ] **Step 8: Final status check**

Run:

```powershell
git status --short
git log -5 --oneline
```

Expected: clean working tree, with task commits visible.

---

## Self-Review Checklist

- Spec coverage:
  - FIFO buy/sell realized PnL: Task 1 and Task 2.
  - Dividends and fees in total return: Task 1, Task 2, Task 4.
  - Portfolio totals by currency: Task 2 and Task 4.
  - Recent transaction names: Task 4.
  - Safe original image view: Task 3 and Task 4.
  - API upload payload safety: preserved by not changing `_upload_payload`; existing `test_uploads_api_hides_local_storage_fields` remains.
- Type consistency:
  - `summarize_returns()` returns `list[ReturnSummary]`.
  - `transaction_profit_summary()` returns template/API-ready `list[dict[str, object]]`.
  - `dashboard_summary()` includes `asset_totals`.
- Verification:
  - Each production change has a failing test first.
  - Full suite runs at the end.
