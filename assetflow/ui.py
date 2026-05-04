from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
from sqlmodel import select

from assetflow.config import Settings
from assetflow.dashboard import dashboard_summary, latest_cash, latest_positions, list_transactions, recent_uploads
from assetflow.models import CandidateTransaction


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_ui_router(settings: Settings, get_session: Callable):
    router = APIRouter()

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

    @router.get("/ui/review")
    def review_page(request: Request, status: str | None = None, db: Session = Depends(get_session)):
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
            },
        )

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

    @router.get("/ui/export")
    def export_page(request: Request):
        return templates.TemplateResponse(
            request,
            "export.html",
            {"settings": settings, "active": "export", "result": None, "error": None},
        )

    return router


def mount_static(app) -> None:
    static_dir = BASE_DIR / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
