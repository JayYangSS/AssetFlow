import re
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from assetflow.recognition.schemas import RecognizedPosition, RecognizedScreenshot, RecognizedTransaction


FIELD_ALIASES = {
    "成交日期": "trade_date",
    "日期": "trade_date",
    "成交时间": "trade_time",
    "时间": "trade_time",
    "证券代码": "symbol",
    "代码": "symbol",
    "证券名称": "security_name",
    "名称": "security_name",
    "交易类别": "trade_type",
    "交易类型": "trade_type",
    "成交数量": "quantity",
    "数量": "quantity",
    "成交价格": "price",
    "价格": "price",
    "发生金额": "net_amount",
    "金额": "net_amount",
    "佣金": "commission",
    "费用": "fees",
    "币种": "currency",
    "货币": "currency",
    "证券余额": "position_balance_after",
    "余额": "position_balance_after",
}

TRADE_TYPES = {
    "买入": "buy",
    "买": "buy",
    "卖出": "sell",
    "卖": "sell",
}

TRADE_TYPES.update(
    {
        "买入": "buy",
        "买": "buy",
        "中签": "buy",
        "卖出": "sell",
        "卖": "sell",
    }
)


MARKET_CURRENCIES = {
    "HK": "HKD",
    "US": "USD",
    "SH": "CNY",
    "SZ": "CNY",
}


def flatten_paddleocr_result(raw_result: Any) -> list[str]:
    lines: list[str] = []

    def add_line(text: Any) -> None:
        if isinstance(text, str):
            line = text.strip()
            if line:
                lines.append(line)

    def walk(value: Any) -> None:
        json_payload = getattr(value, "json", None)
        if isinstance(json_payload, dict):
            walk(json_payload)
            return
        if callable(json_payload):
            walk(json_payload())
            return
        if isinstance(value, dict):
            rec_texts = value.get("rec_texts")
            if isinstance(rec_texts, list):
                for text in rec_texts:
                    add_line(text)
            for key in ("res", "result", "ocr_res", "prunedResult"):
                if key in value:
                    walk(value[key])
            return
        if isinstance(value, tuple) and len(value) >= 1 and isinstance(value[0], str):
            add_line(value[0])
            return
        if isinstance(value, list):
            for item in value:
                walk(item)

    walk(raw_result)
    return [line for line in lines if line]


def _extract_field_map(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        normalized = re.sub(r"\s+", " ", line.strip())
        for label, field_name in FIELD_ALIASES.items():
            if label not in normalized:
                continue
            value = normalized.split(label, 1)[1].strip(" :：\t")
            if value:
                values[field_name] = value
                break
    return values


def _parse_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    cleaned = value.replace(",", "").strip()
    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    match = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", value)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_month_day(value: str | None) -> date | None:
    if not value:
        return None
    match = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})", value.strip())
    if not match:
        return None
    month, day = (int(part) for part in match.groups())
    try:
        return date(date.today().year, month, day)
    except ValueError:
        return None


def _parse_compact_trade_date_line(value: str | None) -> tuple[date | None, str]:
    if not value:
        return None, ""
    stripped = value.strip()
    match = re.match(r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})(.*)", stripped)
    if match:
        return _parse_date(match.group(1)), match.group(2).strip()
    match = re.match(r"(\d{1,2}[-/.]\d{1,2})(.*)", stripped)
    if match:
        return _parse_month_day(match.group(1)), match.group(2).strip()
    return None, ""


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    match = re.search(r"(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?", value)
    if not match:
        return None
    hour, minute, second = match.groups()
    return time(int(hour), int(minute), int(second or 0))


def _parse_trade_type(value: str | None) -> str | None:
    if not value:
        return None
    for label, trade_type in TRADE_TYPES.items():
        if label in value:
            return trade_type
    return None


def _parse_market(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().upper()
    if normalized in MARKET_CURRENCIES:
        return normalized
    match = re.search(r"\b(HK|US|SH|SZ)\b", normalized)
    return match.group(1) if match else None


def _looks_like_symbol(value: str | None) -> bool:
    if not value:
        return False
    return bool(re.fullmatch(r"\d{4,6}", value.strip()))


def _looks_like_us_ticker(value: str | None) -> bool:
    if not value:
        return False
    return bool(re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", value.strip().upper()))


def _looks_like_position_symbol(value: str | None, market: str | None = None) -> bool:
    if market == "US":
        return _looks_like_us_ticker(value)
    return _looks_like_symbol(value)


def _extract_market_symbol(lines: list[str]) -> tuple[str | None, str | None, set[int]]:
    for index, line in enumerate(lines):
        match = re.search(r"\b(HK|US|SH|SZ)\s*(\d{4,6})\b", line.strip().upper())
        if match:
            market, symbol = match.groups()
            return market, symbol, {index}
    for index, line in enumerate(lines):
        market = _parse_market(line)
        if market is None:
            continue
        for symbol_index in (index + 1, index - 1):
            if 0 <= symbol_index < len(lines) and _looks_like_symbol(lines[symbol_index]):
                return market, lines[symbol_index].strip(), {index, symbol_index}
    return None, None, set()


def _looks_like_market_symbol(value: str) -> bool:
    stripped = value.strip().upper()
    compact = re.search(r"\b(HK|SH|SZ)\s*(\d{4,6})\b", stripped)
    if compact:
        return True
    return bool(re.search(r"\bUS\s*[A-Z][A-Z0-9.-]{0,9}\b", stripped))


def _looks_like_compact_number(value: str) -> bool:
    return bool(re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value.strip().replace(",", "")))


def _is_percentage(value: str) -> bool:
    return "%" in value


def _looks_like_position_name(value: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return False
    if normalized in {
        "自选",
        "持仓",
        "订单",
        "港股",
        "美股",
        "沪深",
        "新加坡",
        "名称代码",
        "市值|数量",
        "现价|成本",
        "今日盈亏",
        "持仓盈亏",
        "现价",
        "成本",
        "异动",
        "异动?",
        "M",
    }:
        return False
    if (
        _parse_market(normalized) is not None
        or _looks_like_symbol(normalized)
        or _looks_like_us_ticker(normalized)
        or _looks_like_market_symbol(normalized)
    ):
        return False
    if _parse_decimal(normalized) is not None and _looks_like_compact_number(normalized):
        return False
    if _is_percentage(normalized) or normalized == "--":
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", normalized))


def _extract_position_market_symbol(row_lines: list[str]) -> tuple[str | None, str | None, int, int]:
    for index, line in enumerate(row_lines):
        match = re.search(r"\b(HK|US|SH|SZ)\s*([A-Z0-9.-]{1,10})\b", line.strip().upper())
        if match:
            market, symbol = match.groups()
            if _looks_like_position_symbol(symbol, market):
                return market, symbol, index, index + 1

        market = _parse_market(line)
        if market is None:
            continue
        symbol_index = index + 1
        if symbol_index >= len(row_lines) or not _looks_like_position_symbol(row_lines[symbol_index], market):
            continue
        cursor = symbol_index + 1
        while cursor < len(row_lines) and row_lines[cursor].strip() in {"M"}:
            cursor += 1
        return market, row_lines[symbol_index].strip(), index, cursor
    return None, None, -1, -1


def _position_numbers(lines: list[str]) -> list[Decimal]:
    numbers: list[Decimal] = []
    for line in lines:
        stripped = line.strip()
        if stripped == "--" or _is_percentage(stripped):
            continue
        value = _parse_decimal(stripped)
        if value is not None and _looks_like_compact_number(stripped):
            numbers.append(value)
    return numbers


def _position_layout(lines: list[str]) -> str:
    joined = " ".join(lines)
    if any(keyword in joined for keyword in ("现价|成本", "现价", "成本")):
        return "current_cost"
    if "持仓盈亏" in joined:
        return "market_value_quantity_unrealized_pnl"
    return "market_value_quantity"


def _parse_compact_row(
    trade_date: date,
    inline_security_name: str,
    row_lines: list[str],
    broker: str,
) -> RecognizedTransaction | None:
    market, symbol, market_symbol_indexes = _extract_market_symbol(row_lines)
    security_name = inline_security_name
    trade_type = next((_parse_trade_type(line) for line in row_lines if _parse_trade_type(line) is not None), None)
    trade_time = next((_parse_time(line) for line in row_lines if _parse_time(line) is not None), None)
    numbers: list[Decimal] = []
    for index, line in enumerate(row_lines):
        if index in market_symbol_indexes:
            continue
        if _parse_trade_type(line) is not None or _parse_time(line) is not None:
            continue
        if _parse_market(line) is not None or _looks_like_symbol(line) or _looks_like_market_symbol(line):
            continue
        if not security_name and not _looks_like_compact_number(line):
            security_name = line.strip()
            continue
        number = _parse_decimal(line)
        if number is not None and _looks_like_compact_number(line):
            numbers.append(number)

    quantity = numbers[0] if numbers else None
    price = numbers[-1] if len(numbers) >= 2 else None
    if (
        not security_name
        or quantity is None
        or trade_type is None
        or trade_time is None
        or market is None
        or symbol is None
        or price is None
    ):
        return None
    gross_amount = quantity * price
    return RecognizedTransaction(
        broker=broker,
        market=market,
        symbol=symbol,
        security_name=security_name,
        trade_type=trade_type,
        trade_date=trade_date,
        trade_time=trade_time,
        quantity=quantity,
        price=price,
        gross_amount=gross_amount,
        currency=MARKET_CURRENCIES[market],
        confidence=0.75,
    )


def _extract_security_detail_identity(lines: list[str]) -> tuple[str | None, str | None, str | None]:
    for index, line in enumerate(lines):
        match = re.search(r"(?:(HK|US|SH|SZ)\s*)?(.+?)[(（]([^)）]+)[)）]", line.strip(), re.IGNORECASE)
        if not match:
            continue
        market, security_name, symbol = match.groups()
        symbol = symbol.strip().upper()
        if market is None:
            nearby_lines = lines[max(0, index - 2) : index] + lines[index + 1 : index + 3]
            for candidate in nearby_lines:
                market = _parse_market(candidate)
                if market is not None:
                    break
        if market is not None and not _looks_like_position_symbol(symbol, market):
            continue
        if market is None and not _looks_like_symbol(symbol):
            continue
        return market, symbol, security_name.strip()
    return None, None, None


def _is_year_line(value: str | None) -> bool:
    if not value:
        return False
    return bool(re.fullmatch(r"(?:19|20)\d{2}", value.strip()))


def _parse_year_month_day(month_day: str, year: str | None) -> date | None:
    if year is None:
        return _parse_month_day(month_day)
    match = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})", month_day.strip())
    if not match or not re.fullmatch(r"\d{4}", year.strip()):
        return None
    month, day = (int(part) for part in match.groups())
    try:
        return date(int(year), month, day)
    except ValueError:
        return None


def _parse_security_detail_amount_quantity_price(
    row_lines: list[str],
) -> tuple[Decimal, Decimal, Decimal] | None:
    number_entries: list[tuple[int, Decimal]] = []
    for index, line in enumerate(row_lines):
        if _parse_trade_type(line) is not None or _is_year_line(line):
            continue
        value = _parse_decimal(line)
        if value is not None and _looks_like_compact_number(line):
            number_entries.append((index, value))
    if len(number_entries) < 3:
        return None

    price = number_entries[-1][1]
    remaining = number_entries[:-1]
    best: tuple[Decimal, Decimal, Decimal] | None = None
    best_score: Decimal | None = None
    for quantity_index, quantity in remaining:
        for amount_index, net_amount in remaining:
            if amount_index == quantity_index:
                continue
            gross_amount = abs(quantity * price)
            if gross_amount == 0:
                continue
            score = abs(abs(net_amount) - gross_amount) / gross_amount
            if best_score is None or score < best_score:
                best_score = score
                best = (net_amount, quantity, price)
    return best


def _parse_security_detail_transaction_rows(lines: list[str], broker: str) -> list[RecognizedTransaction]:
    market, symbol, security_name = _extract_security_detail_identity(lines)
    if market is None or symbol is None or security_name is None:
        return []

    date_indexes = [
        index
        for index, line in enumerate(lines)
        if re.fullmatch(r"\d{1,2}[-/]\d{1,2}", line.strip())
    ]
    transactions: list[RecognizedTransaction] = []
    for position, index in enumerate(date_indexes):
        row_end = date_indexes[position + 1] if position + 1 < len(date_indexes) else len(lines)
        row_lines = lines[index + 1 : row_end]
        year_value = next((line for line in row_lines if _is_year_line(line)), None)
        year_index = index + 1 if index + 1 < len(lines) and _is_year_line(lines[index + 1]) else None
        trade_date = _parse_year_month_day(lines[index], lines[year_index] if year_index is not None else None)
        if trade_date is None and year_value is not None:
            trade_date = _parse_year_month_day(lines[index], year_value)
        if trade_date is None:
            continue

        row_start = (year_index + 1) if year_index is not None else index + 1
        row_lines = lines[row_start:row_end]
        trade_type = next((_parse_trade_type(line) for line in row_lines if _parse_trade_type(line) is not None), None)
        if trade_type is None:
            continue

        row_values = _parse_security_detail_amount_quantity_price(row_lines)
        if row_values is None:
            continue
        net_amount, quantity, price = row_values
        transactions.append(
            RecognizedTransaction(
                broker=broker,
                market=market,
                symbol=symbol,
                security_name=security_name,
                trade_type=trade_type,
                trade_date=trade_date,
                quantity=quantity,
                price=price,
                gross_amount=quantity * price,
                net_amount=net_amount,
                currency=MARKET_CURRENCIES[market],
                confidence=0.75,
            )
        )
    return transactions


def _guess_screenshot_type(lines: list[str]) -> str:
    joined = " ".join(lines)
    if any(keyword in joined for keyword in ("交易明细", "实现金额", "中签")):
        return "trade_history"
    if any(keyword in joined for keyword in ("成交记录", "成交日期", "交易类别", "成交价格")):
        return "trade_history"
    if any(keyword in joined for keyword in ("市值|数量", "今日盈亏", "可用数量")):
        return "positions"
    if "持仓" in joined and "名称代码" in joined and "买卖方向" not in joined:
        return "positions"
    if any(keyword in joined for keyword in ("已成交", "买卖方向", "数量|价格", "名称代码")):
        return "trade_history"
    if any(keyword in joined for keyword in ("持仓", "证券余额", "可用数量", "市值")):
        return "positions"
    if any(keyword in joined for keyword in ("资金", "可用资金", "现金", "总资产")):
        return "cash"
    return "unknown"


def _parse_compact_filled_order_rows(lines: list[str], broker: str) -> list[RecognizedTransaction]:
    transactions: list[RecognizedTransaction] = []
    date_lines: list[tuple[int, date, str]] = []
    for index, line in enumerate(lines):
        trade_date, inline_security_name = _parse_compact_trade_date_line(lines[index])
        if trade_date is not None:
            date_lines.append((index, trade_date, inline_security_name))
    for position, (index, trade_date, inline_security_name) in enumerate(date_lines):
        end = date_lines[position + 1][0] if position + 1 < len(date_lines) else len(lines)
        transaction = _parse_compact_row(trade_date, inline_security_name, lines[index + 1 : end], broker)
        if transaction is None:
            continue
        transactions.append(transaction)
    return transactions


def _parse_position_rows(lines: list[str], broker: str) -> list[RecognizedPosition]:
    positions: list[RecognizedPosition] = []
    index = 0
    snapshot_at = datetime.now(UTC)
    layout = _position_layout(lines)
    while index < len(lines):
        security_name = lines[index].strip()
        if not _looks_like_position_name(security_name):
            index += 1
            continue
        if index + 1 >= len(lines):
            break
        cursor = index + 1
        while cursor < len(lines) and not _looks_like_position_name(lines[cursor]):
            cursor += 1

        row_lines = lines[index + 1 : cursor]
        market, symbol, marker_start, marker_end = _extract_position_market_symbol(row_lines)
        if market is None or symbol is None:
            index = cursor
            continue

        values_before_marker = _position_numbers(row_lines[:marker_start])
        values_after_marker = _position_numbers(row_lines[marker_end:])
        values = values_before_marker + values_after_marker
        if layout == "current_cost":
            market_price = None
            cost_price = None
            unrealized_pnl = None
            if len(values_before_marker) >= 2 and values_after_marker:
                market_price = values_before_marker[0]
                unrealized_pnl = values_before_marker[1]
                cost_price = values_after_marker[0]
            elif values_before_marker and len(values_after_marker) >= 2:
                market_price = values_before_marker[0]
                cost_price = values_after_marker[0]
                unrealized_pnl = values_after_marker[1]
            elif len(values) >= 3:
                market_price = values[0]
                cost_price = values[1]
                unrealized_pnl = values[2]
            elif len(values) >= 2:
                market_price = values[0]
                cost_price = values[1]
            else:
                index = cursor
                continue

            positions.append(
                RecognizedPosition(
                    broker=broker,
                    market=market,
                    symbol=symbol,
                    security_name=security_name,
                    market_price=market_price,
                    cost_price=cost_price,
                    unrealized_pnl=unrealized_pnl,
                    currency=MARKET_CURRENCIES[market],
                    snapshot_at=snapshot_at,
                    confidence=0.75,
                )
            )
            index = cursor
            continue

        if len(values_before_marker) >= 2 and values_after_marker:
            market_value = values_before_marker[0]
            pnl_value = values_before_marker[1]
            quantity = values_after_marker[0]
        elif len(values_before_marker) >= 2:
            market_value = values_before_marker[0]
            pnl_value = values_before_marker[1]
            quantity = None
        elif len(values) >= 2:
            market_value = values[0]
            quantity = values[1]
            pnl_value = values[2] if len(values) >= 3 else None
        else:
            index = cursor
            continue
        daily_pnl = pnl_value if layout == "market_value_quantity" else None
        unrealized_pnl = pnl_value if layout == "market_value_quantity_unrealized_pnl" else None

        positions.append(
            RecognizedPosition(
                broker=broker,
                market=market,
                symbol=symbol,
                security_name=security_name,
                market_value=market_value,
                quantity=quantity,
                daily_pnl=daily_pnl,
                unrealized_pnl=unrealized_pnl,
                currency=MARKET_CURRENCIES[market],
                snapshot_at=snapshot_at,
                confidence=0.75,
            )
        )
        index = cursor
    return positions


def parse_htsc_global_ocr_lines(lines: list[str], broker: str) -> RecognizedScreenshot:
    screenshot_type = _guess_screenshot_type(lines)
    if screenshot_type == "positions":
        positions = _parse_position_rows(lines, broker)
        return RecognizedScreenshot(
            screenshot_type="positions",
            confidence=0.75 if positions else 0.40,
            positions=positions,
        )
    if screenshot_type != "trade_history":
        return RecognizedScreenshot(
            screenshot_type=screenshot_type,
            confidence=0.40 if screenshot_type != "unknown" else 0.0,
        )

    security_detail_transactions = _parse_security_detail_transaction_rows(lines, broker)
    if security_detail_transactions:
        return RecognizedScreenshot(
            screenshot_type="trade_history",
            confidence=0.75,
            transactions=security_detail_transactions,
        )

    compact_transactions = _parse_compact_filled_order_rows(lines, broker)
    if compact_transactions:
        return RecognizedScreenshot(
            screenshot_type="trade_history",
            confidence=0.75,
            transactions=compact_transactions,
        )

    values = _extract_field_map(lines)
    transaction = RecognizedTransaction(
        broker=broker,
        market="HK" if (values.get("currency") or "").upper() == "HKD" else None,
        symbol=values.get("symbol"),
        security_name=values.get("security_name"),
        trade_type=_parse_trade_type(values.get("trade_type")),
        trade_date=_parse_date(values.get("trade_date")),
        trade_time=_parse_time(values.get("trade_time")),
        quantity=_parse_decimal(values.get("quantity")),
        price=_parse_decimal(values.get("price")),
        net_amount=_parse_decimal(values.get("net_amount")),
        commission=_parse_decimal(values.get("commission")),
        fees=_parse_decimal(values.get("fees")),
        currency=(values.get("currency") or "").upper() or None,
        position_balance_after=_parse_decimal(values.get("position_balance_after")),
        confidence=0.70,
    )
    if not any(
        getattr(transaction, field_name) is not None
        for field_name in (
            "market",
            "symbol",
            "security_name",
            "trade_type",
            "trade_date",
            "trade_time",
            "quantity",
            "price",
            "net_amount",
            "commission",
            "fees",
            "currency",
            "position_balance_after",
        )
    ):
        return RecognizedScreenshot(
            screenshot_type="trade_history",
            confidence=0.40,
        )
    return RecognizedScreenshot(
        screenshot_type="trade_history",
        confidence=0.70,
        transactions=[transaction],
    )


class PaddleOCRVisionProvider:
    provider_name = "paddleocr"
    model_name = "paddleocr-local"

    def __init__(self, engine: Any | None = None) -> None:
        self.engine = engine

    def _get_engine(self) -> Any:
        if self.engine is not None:
            return self.engine
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR is not installed. Install it with: pip install -e \".[ocr]\""
            ) from exc
        try:
            self.engine = PaddleOCR(
                lang="ch",
                ocr_version="PP-OCRv4",
                device="cpu",
                engine="paddle_static",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                enable_mkldnn=False,
            )
        except TypeError:
            self.engine = PaddleOCR(use_angle_cls=True, lang="ch")
        return self.engine

    def recognize(self, image_path: Path, broker: str) -> RecognizedScreenshot:
        engine = self._get_engine()
        if hasattr(engine, "predict"):
            raw_result = engine.predict(str(image_path))
        elif hasattr(engine, "ocr"):
            raw_result = engine.ocr(str(image_path), cls=True)
        else:
            raise RuntimeError("PaddleOCR engine does not expose predict() or ocr()")
        lines = flatten_paddleocr_result(raw_result)
        if broker != "htsc_global":
            return RecognizedScreenshot(screenshot_type="unknown", confidence=0.0)
        return parse_htsc_global_ocr_lines(lines, broker=broker)
