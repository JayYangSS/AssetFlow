from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from assetflow.api import create_app
from assetflow.models import CandidateTransaction, Upload


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
