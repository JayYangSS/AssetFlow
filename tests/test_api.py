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
