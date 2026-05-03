from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from sqlmodel import Session, select

from assetflow.config import Settings
from assetflow.db import create_db_and_tables, make_engine
from assetflow.exporters.xlsx_template import export_transactions_to_template
from assetflow.ledger import auto_confirm_candidates, confirm_candidate
from assetflow.models import CandidateTransaction, Transaction
from assetflow.recognition.providers import make_provider
from assetflow.recognition.service import process_recognition_result
from assetflow.reconciliation import reconcile_positions
from assetflow.uploads import InvalidUploadError, store_upload


def create_app(settings: Settings | None = None, session: Session | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.ensure_directories()
    engine = None if session is not None else make_engine(settings.database_url)
    if engine is not None:
        create_db_and_tables(engine)

    app = FastAPI(title="AssetFlow")

    def get_session():
        if session is not None:
            yield session
            return
        with Session(engine) as db:
            yield db

    def require_token(x_assetflow_token: Annotated[str | None, Header()] = None) -> None:
        if x_assetflow_token != settings.assetflow_upload_token:
            raise HTTPException(status_code=401, detail="Invalid upload token")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/uploads/ios-shortcut")
    async def upload_ios_shortcut(
        _: Annotated[None, Depends(require_token)],
        db: Annotated[Session, Depends(get_session)],
        broker: Annotated[str, Form()] = "htsc_global",
        account_alias: Annotated[str | None, Form()] = None,
        file: UploadFile = File(),
    ) -> dict[str, object]:
        data = await file.read()
        try:
            upload = store_upload(
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

        auto_confirmed = 0
        if upload.status != "duplicate":
            provider = make_provider(settings)
            result = provider.recognize(Path(upload.image_path), broker)
            process_recognition_result(db, upload, provider, result)
            auto_confirmed = auto_confirm_candidates(db)
            reconcile_positions(db, broker=broker, account_alias=account_alias)
            db.refresh(upload)

        return {
            "upload": {"id": upload.id, "status": upload.status, "duplicate_of_upload_id": upload.duplicate_of_upload_id},
            "auto_confirmed": auto_confirmed,
        }

    @app.get("/api/review/candidates")
    def list_candidates(db: Annotated[Session, Depends(get_session)]) -> list[CandidateTransaction]:
        return db.exec(select(CandidateTransaction).where(CandidateTransaction.review_status != "confirmed")).all()

    @app.post("/api/review/candidates/{candidate_id}/confirm")
    def confirm(candidate_id: int, db: Annotated[Session, Depends(get_session)]) -> dict[str, int | None]:
        tx = confirm_candidate(db, candidate_id)
        return {"transaction_id": tx.id}

    @app.post("/api/reconcile")
    def reconcile(broker: str = "htsc_global", db: Session = Depends(get_session)) -> dict[str, int]:
        return {"created": reconcile_positions(db, broker=broker)}

    @app.post("/api/exports/xlsx")
    def export_xlsx(
        template_path: str,
        output_path: str,
        currency: str,
        db: Session = Depends(get_session),
    ) -> dict[str, object]:
        transactions = db.exec(select(Transaction).where(Transaction.currency == currency)).all()
        result = export_transactions_to_template(Path(template_path), Path(output_path), transactions)
        return {"output_path": str(result.output_path), "row_count": result.row_count, "skipped_ids": result.skipped_ids}

    return app
