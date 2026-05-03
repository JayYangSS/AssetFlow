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
