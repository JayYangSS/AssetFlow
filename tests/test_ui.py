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
