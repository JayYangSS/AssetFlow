from datetime import date, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
from sqlmodel import select

from assetflow.cash_movements import create_cash_movement
from assetflow.config import Settings
from assetflow.dashboard import dashboard_summary, latest_cash, latest_positions, list_transactions, recent_uploads
from assetflow.domain import SUPPORTED_CURRENCIES, TEMPLATE_TRADE_TYPES, build_dedupe_key
from assetflow.exporters.xlsx_template import export_transactions_to_template
from assetflow.export_paths import resolve_export_output_path
from assetflow.ledger import ACTIONABLE_REVIEW_STATUSES, confirm_candidate, ignore_candidate
from assetflow.models import CandidateTransaction, PositionSnapshot, Transaction
from assetflow.position_snapshots import complete_position_value_triplet
from assetflow.transaction_costs import estimate_transaction_costs
from assetflow.upload_pipeline import process_uploaded_image
from assetflow.uploads import InvalidUploadError


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
_resolve_export_output_path = resolve_export_output_path


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _parse_optional_decimal(value: str | None, label: str) -> Decimal | None:
    text = _clean_optional_text(value)
    if text is None:
        return None
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{label}格式不正确") from exc
    if not parsed.is_finite():
        raise ValueError(f"{label}格式不正确")
    return parsed


def _parse_optional_date(value: str | None, label: str) -> date | None:
    text = _clean_optional_text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{label}格式不正确，应为 YYYY-MM-DD") from exc


def _parse_optional_time(value: str | None, label: str) -> time | None:
    text = _clean_optional_text(value)
    if text is None:
        return None
    try:
        return time.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{label}格式不正确，应为 HH:MM 或 HH:MM:SS") from exc


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

    def render_candidate_edit_response(
        request: Request,
        candidate: CandidateTransaction,
        error: str | None = None,
    ):
        return templates.TemplateResponse(
            request,
            "edit_candidate.html",
            {
                "settings": settings,
                "active": "review",
                "candidate": candidate,
                "error": error,
                "trade_types": TEMPLATE_TRADE_TYPES,
                "currencies": sorted(SUPPORTED_CURRENCIES),
            },
        )

    def render_position_edit_response(
        request: Request,
        snapshot: PositionSnapshot,
        error: str | None = None,
    ):
        return templates.TemplateResponse(
            request,
            "edit_position.html",
            {
                "settings": settings,
                "active": "positions",
                "position": snapshot,
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

    @router.get("/ui/review/{candidate_id}/edit")
    def edit_candidate_page(candidate_id: int, request: Request, db: Session = Depends(get_session)):
        candidate = db.get(CandidateTransaction, candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        return render_candidate_edit_response(request, candidate)

    @router.post("/ui/review/{candidate_id}/edit")
    def edit_candidate_form(
        candidate_id: int,
        request: Request,
        db: Session = Depends(get_session),
        market: str | None = Form(None),
        symbol: str | None = Form(None),
        security_name: str | None = Form(None),
        trade_type: str | None = Form(None),
        trade_date: str | None = Form(None),
        trade_time: str | None = Form(None),
        quantity: str | None = Form(None),
        price: str | None = Form(None),
        gross_amount: str | None = Form(None),
        net_amount: str | None = Form(None),
        commission: str | None = Form(None),
        fees: str | None = Form(None),
        currency: str | None = Form(None),
        position_balance_after: str | None = Form(None),
    ):
        candidate = db.get(CandidateTransaction, candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        if candidate.review_status not in ACTIONABLE_REVIEW_STATUSES:
            return render_candidate_edit_response(request, candidate, error=f"当前状态不能编辑：{candidate.review_status}")

        try:
            parsed_market = (_clean_optional_text(market) or "").upper() or None
            parsed_symbol = _clean_optional_text(symbol)
            parsed_security_name = _clean_optional_text(security_name)
            parsed_trade_type = (_clean_optional_text(trade_type) or "").lower() or None
            parsed_trade_date = _parse_optional_date(trade_date, "交易日期")
            parsed_trade_time = _parse_optional_time(trade_time, "交易时间")
            parsed_quantity = _parse_optional_decimal(quantity, "数量")
            parsed_price = _parse_optional_decimal(price, "价格")
            parsed_gross_amount = _parse_optional_decimal(gross_amount, "成交金额")
            parsed_net_amount = _parse_optional_decimal(net_amount, "现金变动")
            parsed_commission = _parse_optional_decimal(commission, "佣金")
            parsed_fees = _parse_optional_decimal(fees, "费用")
            parsed_currency = (_clean_optional_text(currency) or "").upper() or None
            parsed_position_balance_after = _parse_optional_decimal(position_balance_after, "成交后持仓")
            costs = estimate_transaction_costs(
                broker=candidate.broker,
                market=parsed_market,
                trade_type=parsed_trade_type,
                quantity=parsed_quantity,
                price=parsed_price,
                gross_amount=parsed_gross_amount,
                net_amount=parsed_net_amount,
                commission=parsed_commission,
                fees=parsed_fees,
            )
        except ValueError as exc:
            return render_candidate_edit_response(request, candidate, error=str(exc))

        candidate.market = parsed_market
        candidate.symbol = parsed_symbol
        candidate.security_name = parsed_security_name
        candidate.trade_type = parsed_trade_type
        candidate.trade_date = parsed_trade_date
        candidate.trade_time = parsed_trade_time
        candidate.quantity = parsed_quantity
        candidate.price = parsed_price
        candidate.gross_amount = costs.gross_amount
        candidate.net_amount = costs.net_amount
        candidate.commission = costs.commission
        candidate.fees = costs.fees
        candidate.currency = parsed_currency
        candidate.position_balance_after = parsed_position_balance_after
        candidate.review_status = "needs_review"
        candidate.review_notes = None
        candidate.dedupe_key = build_dedupe_key(
            broker=candidate.broker,
            account_alias=candidate.account_alias,
            trade_date=candidate.trade_date,
            trade_time=candidate.trade_time,
            symbol=candidate.symbol,
            trade_type=candidate.trade_type,
            quantity=candidate.quantity,
            price=candidate.price,
            net_amount=candidate.net_amount,
            currency=candidate.currency,
        )
        db.add(candidate)
        db.commit()
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

    @router.get("/ui/positions/{snapshot_id}/edit")
    def edit_position_page(snapshot_id: int, request: Request, db: Session = Depends(get_session)):
        snapshot = db.get(PositionSnapshot, snapshot_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Position snapshot not found")
        return render_position_edit_response(request, snapshot)

    @router.post("/ui/positions/{snapshot_id}/edit")
    def edit_position_form(
        snapshot_id: int,
        request: Request,
        db: Session = Depends(get_session),
        quantity: str | None = Form(None),
        available_quantity: str | None = Form(None),
        cost_price: str | None = Form(None),
        market_price: str | None = Form(None),
        market_value: str | None = Form(None),
        daily_pnl: str | None = Form(None),
        unrealized_pnl: str | None = Form(None),
    ):
        snapshot = db.get(PositionSnapshot, snapshot_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Position snapshot not found")
        try:
            parsed_quantity = _parse_optional_decimal(quantity, "数量")
            parsed_available_quantity = _parse_optional_decimal(available_quantity, "可用")
            parsed_cost_price = _parse_optional_decimal(cost_price, "成本价")
            parsed_market_price = _parse_optional_decimal(market_price, "市价")
            parsed_market_value = _parse_optional_decimal(market_value, "市值")
            parsed_daily_pnl = _parse_optional_decimal(daily_pnl, "今日盈亏")
            parsed_unrealized_pnl = _parse_optional_decimal(unrealized_pnl, "持仓盈亏")
            parsed_quantity, parsed_market_price, parsed_market_value = complete_position_value_triplet(
                quantity=parsed_quantity,
                market_price=parsed_market_price,
                market_value=parsed_market_value,
            )
        except ValueError as exc:
            return render_position_edit_response(request, snapshot, error=str(exc))

        snapshot.quantity = parsed_quantity
        snapshot.available_quantity = parsed_available_quantity
        snapshot.cost_price = parsed_cost_price
        snapshot.market_price = parsed_market_price
        snapshot.market_value = parsed_market_value
        snapshot.daily_pnl = parsed_daily_pnl
        snapshot.unrealized_pnl = parsed_unrealized_pnl
        db.add(snapshot)
        db.commit()
        return RedirectResponse("/ui/positions", status_code=303)

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
