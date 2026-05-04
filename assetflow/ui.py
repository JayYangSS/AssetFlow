from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from assetflow.config import Settings
from assetflow.dashboard import dashboard_summary


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

    return router


def mount_static(app) -> None:
    static_dir = BASE_DIR / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
