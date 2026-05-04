from fastapi.testclient import TestClient
from sqlmodel import select

from assetflow.api import create_app
from assetflow.models import CandidateTransaction, OcrResult, Transaction, Upload


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
    assert len(session.exec(select(Upload)).all()) == 1
    assert len(session.exec(select(OcrResult)).all()) == 1
    assert len(session.exec(select(CandidateTransaction)).all()) == 1
    assert session.exec(select(Transaction)).one().symbol == "00700"


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
    assert response.json() == {"candidate_id": candidate.id}
    session.refresh(candidate)
    assert candidate.review_status == "ignored"


def test_duplicate_upload_does_not_create_second_transaction(settings, session) -> None:
    app = create_app(settings=settings, session=session)
    client = TestClient(app)
    kwargs = {
        "headers": {"X-AssetFlow-Token": "secret-token"},
        "data": {"broker": "htsc_global"},
        "files": {"file": ("trade.png", b"\x89PNG\r\n\x1a\nabc", "image/png")},
    }

    first = client.post("/api/uploads/ios-shortcut", **kwargs)
    second = client.post("/api/uploads/ios-shortcut", **kwargs)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["upload"]["status"] == "duplicate"
    assert len(session.exec(select(Transaction)).all()) == 1
