from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from assetflow.cash_movements import create_cash_movement
from assetflow.config import Settings
from assetflow.dashboard import dashboard_summary, latest_cash, latest_positions, list_transactions, recent_uploads
from assetflow.db import create_db_and_tables, make_engine
from assetflow.exporters.xlsx_template import export_transactions_to_template
from assetflow.ledger import confirm_candidate
from assetflow.models import CandidateTransaction, Transaction
from assetflow.reconciliation import reconcile_positions
from assetflow.upload_pipeline import process_uploaded_image
from assetflow.uploads import InvalidUploadError


class CashMovementRequest(BaseModel):
    broker: str = "htsc_global"
    account_alias: str | None = None
    trade_type: str
    trade_date: date
    currency: str
    amount: Decimal


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
            result = process_uploaded_image(
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

        upload = result.upload
        return {
            "upload": {"id": upload.id, "status": upload.status, "duplicate_of_upload_id": upload.duplicate_of_upload_id},
            "auto_confirmed": result.auto_confirmed,
        }

    @app.get("/api/review/candidates")
    def list_candidates(db: Annotated[Session, Depends(get_session)]) -> list[CandidateTransaction]:
        return db.exec(
            select(CandidateTransaction).where(CandidateTransaction.review_status.in_(("pending", "needs_review")))
        ).all()

    @app.post("/api/review/candidates/{candidate_id}/confirm")
    def confirm(candidate_id: int, db: Annotated[Session, Depends(get_session)]) -> dict[str, int | None]:
        tx = confirm_candidate(db, candidate_id)
        return {"transaction_id": tx.id}

    @app.post("/api/review/candidates/{candidate_id}/ignore")
    def ignore_candidate(candidate_id: int, db: Annotated[Session, Depends(get_session)]) -> dict[str, int]:
        candidate = db.get(CandidateTransaction, candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_id}")
        candidate.review_status = "ignored"
        db.add(candidate)
        db.commit()
        return {"candidate_id": candidate_id}

    @app.post("/api/cash/movements")
    def cash_movement(request: CashMovementRequest, db: Annotated[Session, Depends(get_session)]) -> dict[str, int | None]:
        try:
            tx = create_cash_movement(
                db,
                broker=request.broker,
                account_alias=request.account_alias,
                trade_type=request.trade_type,
                trade_date=request.trade_date,
                currency=request.currency,
                amount=request.amount,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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

    @app.get("/api/dashboard/summary")
    def dashboard(db: Annotated[Session, Depends(get_session)]) -> dict[str, object]:
        return dashboard_summary(db)

    @app.get("/api/transactions")
    def transactions(
        db: Annotated[Session, Depends(get_session)],
        currency: str | None = None,
        symbol: str | None = None,
        trade_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 100,
    ) -> list[Transaction]:
        return list_transactions(
            db,
            currency=currency,
            symbol=symbol,
            trade_type=trade_type,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )

    @app.get("/api/positions/latest")
    def positions_latest(db: Annotated[Session, Depends(get_session)]):
        return latest_positions(db)

    @app.get("/api/cash/latest")
    def cash_latest(db: Annotated[Session, Depends(get_session)]):
        return latest_cash(db)

    @app.get("/api/uploads")
    def uploads(db: Annotated[Session, Depends(get_session)]):
        return recent_uploads(db)

    return app
