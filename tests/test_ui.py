from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import select

from assetflow.api import create_app
from assetflow.models import CandidateTransaction, Transaction, Upload


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
