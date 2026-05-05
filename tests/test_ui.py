from datetime import date, time
from decimal import Decimal
from pathlib import Path, PurePosixPath

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlmodel import select

import assetflow.export_paths as export_paths_module
from assetflow.api import create_app
from assetflow.exporters.xlsx_template import EXPECTED_HEADERS
from assetflow.models import CandidateTransaction, Transaction, Upload


def _make_export_template(path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.append(EXPECTED_HEADERS)
    wb.save(path)
    return path


class _PosixOnlyPath:
    def __init__(self, *parts: object) -> None:
        self._path = PurePosixPath(*(str(part) for part in parts))

    @property
    def drive(self) -> str:
        return self._path.drive

    @property
    def parts(self) -> tuple[str, ...]:
        return self._path.parts

    def is_absolute(self) -> bool:
        return self._path.is_absolute()

    def resolve(self) -> "_PosixOnlyPath":
        return self

    def relative_to(self, other: object) -> "_PosixOnlyPath":
        return _PosixOnlyPath(self._path.relative_to(str(other)))

    def __truediv__(self, other: object) -> "_PosixOnlyPath":
        return _PosixOnlyPath(self._path, other)

    def __str__(self) -> str:
        return str(self._path)


def test_ui_dashboard_page_returns_html(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.get("/ui")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AssetFlow" in response.text
    assert "总览" in response.text
    assert 'href="http://testserver/static/app.css"' in response.text


def test_ui_navigation_links_core_pages(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.get("/ui")

    assert 'href="/ui/upload"' in response.text
    assert 'href="/ui/review"' in response.text
    assert 'href="/ui/transactions"' in response.text
    assert 'href="/ui/positions"' in response.text
    assert 'href="/ui/cash"' in response.text
    assert 'href="/ui/export"' in response.text


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


def test_ui_positions_page_labels_daily_and_holding_pnl(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.get("/ui/positions")

    assert response.status_code == 200
    assert "今日盈亏" in response.text
    assert "持仓盈亏" in response.text


def test_upload_page_contains_file_form(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.get("/ui/upload")

    assert 'enctype="multipart/form-data"' in response.text
    assert 'name="file"' in response.text
    assert 'name="broker"' in response.text


def test_cash_page_contains_cash_movement_form(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.get("/ui/cash")

    assert 'action="/ui/cash/movements"' in response.text
    assert 'name="trade_type"' in response.text
    assert 'name="trade_date"' in response.text
    assert 'name="amount"' in response.text


def test_ui_serves_static_css(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.get("/static/app.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert ".topbar" in response.text


def test_ui_dashboard_renders_pending_review_count(settings, session) -> None:
    upload = Upload(
        broker="htsc_global",
        source="web",
        original_filename="trade.png",
        content_hash="ui-summary",
        image_path=str(settings.upload_dir / "trade.png"),
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
            symbol="00700",
            security_name="Tencent",
            trade_type="buy",
            trade_date=date(2026, 5, 4),
            quantity=Decimal("100"),
            price=Decimal("400"),
            currency="HKD",
            dedupe_key="ui-summary-candidate",
            confidence=0.9,
            review_status="needs_review",
        )
    )
    session.commit()
    client = TestClient(create_app(settings=settings, session=session))

    response = client.get("/ui")

    assert response.status_code == 200
    assert "<span>待审核</span><strong>1</strong>" in response.text


def test_ui_transaction_tables_label_net_amount_as_cash_change(settings, session) -> None:
    tx = Transaction(
        broker="htsc_global",
        market="HK",
        symbol="00700",
        security_name="Tencent",
        trade_type="buy",
        trade_date=date(2026, 5, 4),
        quantity=Decimal("100"),
        price=Decimal("400"),
        net_amount=Decimal("-40000"),
        currency="HKD",
        dedupe_key="ui-cash-change-label",
        confidence=0.95,
    )
    session.add(tx)
    session.commit()
    client = TestClient(create_app(settings=settings, session=session))

    dashboard_response = client.get("/ui")
    transactions_response = client.get("/ui/transactions")

    assert dashboard_response.status_code == 200
    assert transactions_response.status_code == 200
    assert "现金变动" in dashboard_response.text
    assert "现金变动" in transactions_response.text


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


def test_ui_ignore_candidate_form_marks_actionable_candidate_ignored(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))
    client.post(
        "/ui/upload",
        data={"broker": "htsc_global", "account_alias": ""},
        files={"file": ("trade.png", b"\x89PNG\r\n\x1a\nabc", "image/png")},
    )
    candidate = session.exec(select(CandidateTransaction)).one()
    for tx in session.exec(select(Transaction)).all():
        session.delete(tx)
    candidate.review_status = "needs_review"
    candidate.confirmed_transaction_id = None
    session.add(candidate)
    session.commit()

    ignore_response = client.post(f"/ui/review/{candidate.id}/ignore", follow_redirects=False)

    assert ignore_response.status_code == 303
    session.refresh(candidate)
    assert candidate.review_status == "ignored"


def test_ui_confirm_form_is_safe_for_already_confirmed_candidate(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))
    client.post(
        "/ui/upload",
        data={"broker": "htsc_global", "account_alias": ""},
        files={"file": ("trade.png", b"\x89PNG\r\n\x1a\nabc", "image/png")},
    )
    candidate = session.exec(select(CandidateTransaction)).one()

    first_response = client.post(f"/ui/review/{candidate.id}/confirm", follow_redirects=False)
    second_response = client.post(f"/ui/review/{candidate.id}/confirm", follow_redirects=False)

    assert first_response.status_code == 303
    assert second_response.status_code == 303
    session.refresh(candidate)
    assert candidate.review_status == "confirmed"
    assert len(session.exec(select(Transaction)).all()) == 1


def test_ui_confirm_form_renders_error_for_incomplete_candidate(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))
    candidate = CandidateTransaction(
        upload_id=1,
        ocr_result_id=1,
        broker="htsc_global",
        market="HK",
        symbol="00700",
        security_name="Tencent",
        trade_type="buy",
        trade_date=date(2026, 5, 4),
        quantity=Decimal("100"),
        price=Decimal("400"),
        currency="HKD",
        dedupe_key="ui-incomplete-candidate",
        confidence=0.75,
        review_status="needs_review",
    )
    session.add(candidate)
    session.commit()
    session.refresh(candidate)

    response = client.post(f"/ui/review/{candidate.id}/confirm")

    assert response.status_code == 200
    assert "确认失败" in response.text
    session.refresh(candidate)
    assert candidate.review_status == "needs_review"
    assert session.exec(select(Transaction)).all() == []


def test_ui_review_page_links_to_candidate_edit_form(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))
    candidate = CandidateTransaction(
        upload_id=1,
        ocr_result_id=1,
        broker="htsc_global",
        market="HK",
        symbol="00700",
        security_name="Tencent",
        trade_type="buy",
        trade_date=date(2026, 5, 4),
        quantity=Decimal("100"),
        price=Decimal("400"),
        currency="HKD",
        dedupe_key="ui-review-edit-link",
        confidence=0.75,
        review_status="needs_review",
    )
    session.add(candidate)
    session.commit()
    session.refresh(candidate)

    response = client.get("/ui/review")

    assert response.status_code == 200
    assert f'href="/ui/review/{candidate.id}/edit"' in response.text
    assert "编辑" in response.text
    assert "现金变动" in response.text


def test_ui_edit_candidate_form_updates_and_confirms_candidate(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))
    candidate = CandidateTransaction(
        upload_id=1,
        ocr_result_id=1,
        broker="htsc_global",
        market="HK",
        symbol=None,
        security_name="Tencent",
        trade_type="buy",
        trade_date=date(2026, 5, 4),
        quantity=Decimal("100"),
        price=Decimal("400"),
        currency="HKD",
        dedupe_key="ui-edit-candidate",
        confidence=0.75,
        review_status="needs_review",
    )
    session.add(candidate)
    session.commit()
    session.refresh(candidate)

    edit_response = client.get(f"/ui/review/{candidate.id}/edit")

    assert edit_response.status_code == 200
    assert "编辑候选交易" in edit_response.text
    assert "现金变动" in edit_response.text
    assert 'name="net_amount"' in edit_response.text

    save_response = client.post(
        f"/ui/review/{candidate.id}/edit",
        data={
            "market": "HK",
            "symbol": "00700",
            "security_name": "Tencent",
            "trade_type": "buy",
            "trade_date": "2026-05-04",
            "trade_time": "09:42:00",
            "quantity": "100",
            "price": "400",
            "gross_amount": "40000",
            "net_amount": "-40000",
            "commission": "",
            "fees": "",
            "currency": "HKD",
            "position_balance_after": "100",
        },
        follow_redirects=False,
    )

    assert save_response.status_code == 303
    session.refresh(candidate)
    assert candidate.symbol == "00700"
    assert candidate.net_amount == Decimal("-40000.000000")
    assert candidate.trade_time == time(9, 42)

    confirm_response = client.post(f"/ui/review/{candidate.id}/confirm", follow_redirects=False)

    assert confirm_response.status_code == 303
    transaction = session.exec(select(Transaction)).one()
    assert transaction.symbol == "00700"
    assert transaction.net_amount == Decimal("-40000.000000")


def test_ui_edit_candidate_form_defaults_htsc_hk_costs_when_blank(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))
    candidate = CandidateTransaction(
        upload_id=1,
        ocr_result_id=1,
        broker="htsc_global",
        market="HK",
        symbol="02015",
        security_name="Li Auto-W",
        trade_type="buy",
        trade_date=date(2026, 4, 24),
        quantity=Decimal("100"),
        price=Decimal("71"),
        currency="HKD",
        dedupe_key="ui-edit-default-costs",
        confidence=0.75,
        review_status="needs_review",
    )
    session.add(candidate)
    session.commit()
    session.refresh(candidate)

    response = client.post(
        f"/ui/review/{candidate.id}/edit",
        data={
            "market": "HK",
            "symbol": "02015",
            "security_name": "Li Auto-W",
            "trade_type": "buy",
            "trade_date": "2026-04-24",
            "trade_time": "09:42:00",
            "quantity": "100",
            "price": "71",
            "gross_amount": "",
            "net_amount": "",
            "commission": "",
            "fees": "",
            "currency": "HKD",
            "position_balance_after": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    session.refresh(candidate)
    assert candidate.gross_amount == Decimal("7100.000000")
    assert candidate.commission == Decimal("0.000000")
    assert candidate.fees == Decimal("8.900000")
    assert candidate.net_amount == Decimal("-7108.900000")


def test_ui_ignore_form_does_not_mutate_confirmed_candidate(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))
    client.post(
        "/ui/upload",
        data={"broker": "htsc_global", "account_alias": ""},
        files={"file": ("trade.png", b"\x89PNG\r\n\x1a\nabc", "image/png")},
    )
    candidate = session.exec(select(CandidateTransaction)).one()

    confirm_response = client.post(f"/ui/review/{candidate.id}/confirm", follow_redirects=False)
    ignore_response = client.post(f"/ui/review/{candidate.id}/ignore", follow_redirects=False)

    assert confirm_response.status_code == 303
    assert ignore_response.status_code == 303
    session.refresh(candidate)
    assert candidate.review_status == "confirmed"


def test_ui_cash_movement_form_creates_transaction(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.post(
        "/ui/cash/movements",
        data={"trade_type": "cash_in", "trade_date": "2026-05-04", "currency": "HKD", "amount": "1000"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    tx = session.exec(select(Transaction)).one()
    assert tx.trade_type == "cash_in"
    assert tx.net_amount == Decimal("1000.000000")


def test_ui_cash_movement_form_renders_error_for_invalid_amount(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    for amount in ["", "not-a-number"]:
        response = client.post(
            "/ui/cash/movements",
            data={"trade_type": "cash_in", "trade_date": "2026-05-04", "currency": "HKD", "amount": amount},
        )

        assert response.status_code == 200
        assert "记录失败" in response.text
    assert session.exec(select(Transaction)).all() == []


def test_ui_cash_movement_form_renders_error_for_invalid_date(settings, session) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.post(
        "/ui/cash/movements",
        data={"trade_type": "cash_in", "trade_date": "not-a-date", "currency": "HKD", "amount": "1000"},
    )

    assert response.status_code == 200
    assert "记录失败" in response.text
    assert session.exec(select(Transaction)).all() == []


def test_ui_export_form_rejects_unsafe_output_paths(settings, session, tmp_path) -> None:
    client = TestClient(create_app(settings=settings, session=session))
    template_path = _make_export_template(tmp_path / "template.xlsx")
    unsafe_outputs = [
        (str(tmp_path / "outside.xlsx"), tmp_path / "outside.xlsx"),
        ("../outside.xlsx", settings.export_dir.parent / "outside.xlsx"),
    ]

    for output_path, outside_output in unsafe_outputs:
        response = client.post(
            "/ui/export",
            data={
                "template_path": str(template_path),
                "output_path": output_path,
                "currency": "HKD",
            },
        )

        assert response.status_code == 200
        assert "导出失败" in response.text
        assert not outside_output.exists()


def test_resolve_export_output_path_rejects_windows_style_paths_on_posix(monkeypatch) -> None:
    monkeypatch.setattr(export_paths_module, "Path", _PosixOnlyPath)

    class SettingsStub:
        export_dir = _PosixOnlyPath("/exports")

    unsafe_outputs = [
        r"C:\temp\outside.xlsx",
        r"C:outside.xlsx",
        r"\\server\share\outside.xlsx",
        r"..\outside.xlsx",
    ]

    for output_path in unsafe_outputs:
        with pytest.raises(ValueError):
            export_paths_module.resolve_export_output_path(SettingsStub(), output_path)


def test_ui_export_form_writes_relative_output_under_export_dir(settings, session, tmp_path) -> None:
    client = TestClient(create_app(settings=settings, session=session))
    template_path = _make_export_template(tmp_path / "template.xlsx")

    response = client.post(
        "/ui/export",
        data={
            "template_path": str(template_path),
            "output_path": "reports/output.xlsx",
            "currency": "HKD",
        },
    )

    assert response.status_code == 200
    assert (settings.export_dir / "reports" / "output.xlsx").exists()


def test_ui_export_form_reports_missing_template(settings, session, tmp_path) -> None:
    client = TestClient(create_app(settings=settings, session=session))

    response = client.post(
        "/ui/export",
        data={
            "template_path": str(tmp_path / "missing.xlsx"),
            "output_path": "output.xlsx",
            "currency": "HKD",
        },
    )

    assert response.status_code == 200
    assert "导出失败" in response.text
