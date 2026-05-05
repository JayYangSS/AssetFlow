from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlmodel import select

from assetflow.api import create_app
from assetflow.exporters.xlsx_template import EXPECTED_HEADERS
from assetflow.models import CandidateTransaction, OcrResult, Transaction, Upload


def _make_export_template(path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.append(EXPECTED_HEADERS)
    wb.save(path)
    return path


def _make_candidate_actionable(session, candidate: CandidateTransaction) -> None:
    for transaction in session.exec(select(Transaction)).all():
        session.delete(transaction)
    candidate.review_status = "needs_review"
    candidate.confirmed_transaction_id = None
    session.add(candidate)
    session.commit()


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
    _make_candidate_actionable(session, candidate)

    response = client.post(f"/api/review/candidates/{candidate.id}/ignore")

    assert response.status_code == 200
    assert response.json() == {"candidate_id": candidate.id}
    session.refresh(candidate)
    assert candidate.review_status == "ignored"


def test_ignored_candidate_is_excluded_from_default_review_queue(settings, session) -> None:
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
    _make_candidate_actionable(session, candidate)

    ignore_response = client.post(f"/api/review/candidates/{candidate.id}/ignore")
    queue_response = client.get("/api/review/candidates")

    assert ignore_response.status_code == 200
    assert queue_response.status_code == 200
    assert all(item["id"] != candidate.id for item in queue_response.json())


def test_ignore_candidate_returns_404_when_missing(settings, session) -> None:
    app = create_app(settings=settings, session=session)
    client = TestClient(app)

    response = client.post("/api/review/candidates/999/ignore")

    assert response.status_code == 404


def test_api_ignore_confirmed_candidate_returns_400_without_mutating(settings, session) -> None:
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
    transaction = session.exec(select(Transaction)).one()

    response = client.post(f"/api/review/candidates/{candidate.id}/ignore")

    assert response.status_code == 400
    session.refresh(candidate)
    session.refresh(transaction)
    assert candidate.review_status == "confirmed"
    assert candidate.confirmed_transaction_id == transaction.id
    assert len(session.exec(select(Transaction)).all()) == 1


def test_api_confirm_ignored_candidate_returns_400_without_creating_transaction(settings, session) -> None:
    app = create_app(settings=settings, session=session)
    client = TestClient(app)
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
        net_amount=Decimal("-40000"),
        currency="HKD",
        dedupe_key="api-ignored-candidate",
        confidence=0.9,
        review_status="ignored",
    )
    session.add(candidate)
    session.commit()
    session.refresh(candidate)

    response = client.post(f"/api/review/candidates/{candidate.id}/confirm")

    assert response.status_code == 400
    session.refresh(candidate)
    assert candidate.review_status == "ignored"
    assert session.exec(select(Transaction)).all() == []


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


def test_api_export_xlsx_rejects_unsafe_output_paths(settings, session, tmp_path) -> None:
    app = create_app(settings=settings, session=session)
    client = TestClient(app)
    template_path = _make_export_template(tmp_path / "template.xlsx")
    unsafe_outputs = [
        (str(tmp_path / "outside.xlsx"), tmp_path / "outside.xlsx"),
        ("../outside.xlsx", settings.export_dir.parent / "outside.xlsx"),
        (r"C:\temp\outside.xlsx", Path(r"C:\temp\outside.xlsx")),
        (r"\\server\share\outside.xlsx", Path(r"\\server\share\outside.xlsx")),
        (r"..\outside.xlsx", settings.export_dir.parent / "outside.xlsx"),
    ]

    for output_path, outside_output in unsafe_outputs:
        response = client.post(
            "/api/exports/xlsx",
            params={"template_path": str(template_path), "output_path": output_path, "currency": "HKD"},
        )

        assert response.status_code == 400
        assert not outside_output.exists()


def test_api_export_xlsx_writes_relative_output_under_export_dir(settings, session, tmp_path) -> None:
    app = create_app(settings=settings, session=session)
    client = TestClient(app)
    template_path = _make_export_template(tmp_path / "template.xlsx")

    response = client.post(
        "/api/exports/xlsx",
        params={"template_path": str(template_path), "output_path": "reports/output.xlsx", "currency": "HKD"},
    )

    assert response.status_code == 200
    output_path = settings.export_dir / "reports" / "output.xlsx"
    assert output_path.exists()
    assert response.json()["output_path"] == str(output_path.resolve())
