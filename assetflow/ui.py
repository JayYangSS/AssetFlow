from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
from sqlmodel import select

from assetflow.cash_movements import create_cash_movement
from assetflow.config import Settings
from assetflow.dashboard import dashboard_summary, latest_cash, latest_positions, list_transactions, recent_uploads
from assetflow.exporters.xlsx_template import export_transactions_to_template
from assetflow.export_paths import resolve_export_output_path
from assetflow.ledger import ACTIONABLE_REVIEW_STATUSES, confirm_candidate, ignore_candidate
from assetflow.models import CandidateTransaction, Transaction
from assetflow.upload_pipeline import process_uploaded_image
from assetflow.uploads import InvalidUploadError


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
_resolve_export_output_path = resolve_export_output_path


def create_ui_router(settings: Settings, get_session: Callable):
    router = APIRouter()

    def render_review_response(request: Request, db: Session, status: str | None = None, error: str | None = None):
        query = select(CandidateTransaction)
        if status:
            statuses = [status]
            query = query.where(CandidateTransaction.review_status == status)
        else:
            statuses = ["pending", "needs_review"]
            query = query.where(CandidateTransaction.review_status.in_(statuses))
        candidates = db.exec(query.order_by(CandidateTransaction.created_at.desc())).all()
        return templates.TemplateResponse(
            request,
            "review.html",
            {
                "settings": settings,
                "active": "review",
                "candidates": candidates,
                "status": status,
                "statuses": statuses,
                "error": error,
            },
        )

    @router.get("/ui")
    def dashboard_page(request: Request, db: Session = Depends(get_session)):
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {"settings": settings, "summary": dashboard_summary(db), "active": "dashboard"},
        )

    @router.get("/ui/upload")
    def upload_page(request: Request, db: Session = Depends(get_session)):
        return templates.TemplateResponse(
            request,
            "upload.html",
            {
                "settings": settings,
                "active": "upload",
                "result": None,
                "error": None,
                "uploads": recent_uploads(db),
            },
        )

    @router.post("/ui/upload")
    async def upload_form(
        request: Request,
        db: Session = Depends(get_session),
        broker: str = Form("htsc_global"),
        account_alias: str | None = Form(None),
        file: UploadFile = File(),
    ):
        data = await file.read()
        if account_alias is not None:
            account_alias = account_alias.strip() or None
        try:
            result = process_uploaded_image(
                session=db,
                settings=settings,
                broker=broker,
                source="web",
                filename=file.filename or "screenshot.png",
                content_type=file.content_type or "application/octet-stream",
                data=data,
                account_alias=account_alias,
            )
        except InvalidUploadError as exc:
            return templates.TemplateResponse(
                request,
                "upload.html",
                {
                    "settings": settings,
                    "active": "upload",
                    "result": None,
                    "error": str(exc),
                    "uploads": recent_uploads(db),
                },
            )

        return templates.TemplateResponse(
            request,
            "upload.html",
            {
                "settings": settings,
                "active": "upload",
                "result": f"{result.upload.status}; auto_confirmed={result.auto_confirmed}",
                "error": None,
                "uploads": recent_uploads(db),
            },
        )

    @router.get("/ui/review")
    def review_page(request: Request, status: str | None = None, db: Session = Depends(get_session)):
        return render_review_response(request, db, status=status)

    @router.post("/ui/review/{candidate_id}/confirm")
    def confirm_candidate_form(candidate_id: int, request: Request, db: Session = Depends(get_session)):
        candidate = db.get(CandidateTransaction, candidate_id)
        if candidate is not None and candidate.review_status in ACTIONABLE_REVIEW_STATUSES:
            try:
                confirm_candidate(db, candidate_id)
            except ValueError as exc:
                return render_review_response(request, db, error=f"确认失败：{exc}")
        return RedirectResponse("/ui/review", status_code=303)

    @router.post("/ui/review/{candidate_id}/ignore")
    def ignore_candidate_form(candidate_id: int, db: Session = Depends(get_session)):
        candidate = db.get(CandidateTransaction, candidate_id)
        if candidate is not None and candidate.review_status in ACTIONABLE_REVIEW_STATUSES:
            try:
                ignore_candidate(db, candidate_id)
            except ValueError:
                pass
        return RedirectResponse("/ui/review", status_code=303)

    @router.get("/ui/transactions")
    def transactions_page(
        request: Request,
        currency: str | None = None,
        symbol: str | None = None,
        db: Session = Depends(get_session),
    ):
        return templates.TemplateResponse(
            request,
            "transactions.html",
            {
                "settings": settings,
                "active": "transactions",
                "transactions": list_transactions(db, currency=currency, symbol=symbol),
                "currency": currency or "",
                "symbol": symbol or "",
            },
        )

    @router.get("/ui/positions")
    def positions_page(request: Request, db: Session = Depends(get_session)):
        return templates.TemplateResponse(
            request,
            "positions.html",
            {"settings": settings, "active": "positions", "positions": latest_positions(db)},
        )

    @router.get("/ui/cash")
    def cash_page(request: Request, db: Session = Depends(get_session)):
        return templates.TemplateResponse(
            request,
            "cash.html",
            {"settings": settings, "active": "cash", "cash_items": latest_cash(db), "result": None, "error": None},
        )

    @router.post("/ui/cash/movements")
    def cash_movement_form(
        request: Request,
        db: Session = Depends(get_session),
        trade_type: str = Form(),
        trade_date: str = Form(""),
        currency: str = Form(),
        amount: str = Form(""),
    ):
        try:
            parsed_trade_date = date.fromisoformat(trade_date)
            parsed_amount = Decimal(amount)
            create_cash_movement(
                db,
                broker="htsc_global",
                account_alias=None,
                trade_type=trade_type,
                trade_date=parsed_trade_date,
                currency=currency,
                amount=parsed_amount,
            )
        except (ValueError, ArithmeticError) as exc:
            return templates.TemplateResponse(
                request,
                "cash.html",
                {
                    "settings": settings,
                    "active": "cash",
                    "cash_items": latest_cash(db),
                    "result": None,
                    "error": str(exc),
                },
            )
        return RedirectResponse("/ui/cash", status_code=303)

    @router.get("/ui/export")
    def export_page(request: Request):
        return templates.TemplateResponse(
            request,
            "export.html",
            {"settings": settings, "active": "export", "result": None, "error": None},
        )

    @router.post("/ui/export")
    def export_form(
        request: Request,
        db: Session = Depends(get_session),
        template_path: str = Form(),
        output_path: str = Form(),
        currency: str = Form(),
    ):
        transactions = db.exec(select(Transaction).where(Transaction.currency == currency)).all()
        try:
            resolved_output_path = _resolve_export_output_path(settings, output_path)
            export_result = export_transactions_to_template(Path(template_path), resolved_output_path, transactions)
            result = f"导出 {export_result.row_count} 行到 {export_result.output_path}，跳过 {len(export_result.skipped_ids)} 条"
        except Exception as exc:
            return templates.TemplateResponse(
                request,
                "export.html",
                {"settings": settings, "active": "export", "result": None, "error": str(exc)},
            )

        return templates.TemplateResponse(
            request,
            "export.html",
            {"settings": settings, "active": "export", "result": result, "error": None},
        )

    return router


def mount_static(app) -> None:
    static_dir = BASE_DIR / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
