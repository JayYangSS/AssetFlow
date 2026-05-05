from decimal import Decimal
from datetime import date
from pathlib import Path
import sys
from types import SimpleNamespace

from assetflow.config import Settings
from assetflow.recognition.providers import PaddleOCRVisionProvider, make_provider
from assetflow.recognition.paddleocr_provider import parse_htsc_global_ocr_lines


def test_parse_htsc_trade_history_lines() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "成交记录",
            "成交日期 2026-05-01",
            "成交时间 10:10:10",
            "证券代码 00700",
            "证券名称 腾讯控股",
            "交易类别 买入",
            "成交数量 100",
            "成交价格 350.1200",
            "发生金额 -35035.0000",
            "佣金 15.0000",
            "费用 8.0000",
            "币种 HKD",
            "证券余额 100",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "trade_history"
    assert result.confidence == 0.70
    assert result.transactions[0].symbol == "00700"
    assert result.transactions[0].security_name == "腾讯控股"
    assert result.transactions[0].trade_type == "buy"
    assert result.transactions[0].trade_date.isoformat() == "2026-05-01"
    assert result.transactions[0].trade_time.isoformat() == "10:10:10"
    assert result.transactions[0].quantity == 100
    assert result.transactions[0].price == Decimal("350.1200")
    assert result.transactions[0].net_amount == Decimal("-35035.0000")
    assert result.transactions[0].currency == "HKD"


def test_parse_htsc_compact_filled_order_list() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "持仓",
            "已成交",
            "待成交",
            "时间",
            "名称代码",
            "买卖方向",
            "数量|价格",
            "04-27",
            "腾讯控股",
            "100",
            "买入",
            "09:30",
            "HK",
            "00700",
            "489.000",
            "04-24",
            "华勤技术",
            "100",
            "卖出",
            "11:26",
            "HK",
            "03296",
            "90.000",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "trade_history"
    assert result.confidence == 0.75
    assert len(result.transactions) == 2
    assert result.transactions[0].symbol == "00700"
    assert result.transactions[0].security_name == "腾讯控股"
    assert result.transactions[0].trade_type == "buy"
    assert result.transactions[0].trade_date == date(date.today().year, 4, 27)
    assert result.transactions[0].trade_time.isoformat() == "09:30:00"
    assert result.transactions[0].quantity == Decimal("100")
    assert result.transactions[0].price == Decimal("489.000")
    assert result.transactions[0].market == "HK"
    assert result.transactions[0].currency == "HKD"
    assert result.transactions[1].trade_type == "sell"


def test_parse_htsc_compact_filled_order_list_accepts_full_dates() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "持仓",
            "已成交",
            "时间",
            "名称代码",
            "买卖方向",
            "数量|价格",
            "04-24",
            "Li Auto-W",
            "100",
            "买入",
            "09:42",
            "HK",
            "02015",
            "71.000",
            "2025-10-02Li Auto-W",
            "100",
            "买入",
            "15:41",
            "HK",
            "02015",
            "102.300",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "trade_history"
    assert len(result.transactions) == 2
    assert result.transactions[0].trade_date == date(date.today().year, 4, 24)
    assert result.transactions[0].trade_time.isoformat() == "09:42:00"
    assert result.transactions[0].symbol == "02015"
    assert result.transactions[0].price == Decimal("71.000")
    assert result.transactions[1].trade_date == date(2025, 10, 2)
    assert result.transactions[1].trade_time.isoformat() == "15:41:00"
    assert result.transactions[1].symbol == "02015"
    assert result.transactions[1].price == Decimal("102.300")


def test_parse_htsc_compact_filled_order_list_accepts_row_ordered_ocr_lines() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "持仓",
            "已成交",
            "时间",
            "名称代码",
            "买卖方向",
            "数量|价格",
            "04-24",
            "理想汽车-W",
            "买入",
            "100",
            "09:42",
            "HK 02015",
            "71.000",
            "2025-10-02理想汽车-W",
            "买入",
            "100",
            "15:41",
            "HK 02015",
            "102.300",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "trade_history"
    assert len(result.transactions) == 2
    assert result.transactions[0].trade_date == date(date.today().year, 4, 24)
    assert result.transactions[0].trade_time.isoformat() == "09:42:00"
    assert result.transactions[0].symbol == "02015"
    assert result.transactions[0].price == Decimal("71.000")
    assert result.transactions[1].trade_date == date(2025, 10, 2)
    assert result.transactions[1].trade_time.isoformat() == "15:41:00"
    assert result.transactions[1].symbol == "02015"
    assert result.transactions[1].price == Decimal("102.300")


def test_parse_htsc_compact_filled_order_list_ignores_invalid_month_day() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "已成交",
            "名称代码",
            "买卖方向",
            "数量|价格",
            "23-14",
            "噪声",
            "100",
            "买入",
            "09:30",
            "HK",
            "00700",
            "489.000",
            "04-27",
            "腾讯控股",
            "100",
            "买入",
            "09:30",
            "HK",
            "00700",
            "489.000",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "trade_history"
    assert len(result.transactions) == 1
    assert result.transactions[0].symbol == "00700"


def test_make_provider_creates_paddleocr_provider() -> None:
    settings = Settings(
        assetflow_upload_token="secret-token",
        assetflow_recognition_provider="paddleocr",
    )

    provider = make_provider(settings)

    assert isinstance(provider, PaddleOCRVisionProvider)


def test_paddleocr_engine_uses_windows_safe_cpu_defaults(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakePaddleOCR:
        def __init__(self, **kwargs: object) -> None:
            calls.append(kwargs)

    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=FakePaddleOCR))

    provider = PaddleOCRVisionProvider()
    provider._get_engine()

    assert calls[0]["ocr_version"] == "PP-OCRv4"
    assert calls[0]["device"] == "cpu"
    assert calls[0]["engine"] == "paddle_static"
    assert calls[0]["enable_mkldnn"] is False


def test_paddleocr_provider_accepts_injected_engine(tmp_path: Path) -> None:
    class FakeEngine:
        def ocr(self, image_path: str, cls: bool = True):
            assert image_path == str(tmp_path / "trade.png")
            assert cls is True
            return [
                [
                    [None, ("成交记录", 0.99)],
                    [None, ("证券代码 00700", 0.98)],
                    [None, ("证券名称 腾讯控股", 0.98)],
                    [None, ("交易类别 买入", 0.98)],
                    [None, ("成交日期 2026-05-01", 0.98)],
                    [None, ("成交数量 100", 0.98)],
                    [None, ("成交价格 350.1200", 0.98)],
                    [None, ("发生金额 -35035.0000", 0.98)],
                    [None, ("币种 HKD", 0.98)],
                ]
            ]

    provider = PaddleOCRVisionProvider(engine=FakeEngine())

    result = provider.recognize(tmp_path / "trade.png", "htsc_global")

    assert result.screenshot_type == "trade_history"
    assert result.transactions[0].symbol == "00700"


def test_paddleocr_provider_accepts_v3_predict_results(tmp_path: Path) -> None:
    class FakeResult:
        json = {
            "res": {
                "rec_texts": [
                    "成交记录",
                    "证券代码 00700",
                    "证券名称 腾讯控股",
                    "交易类别 买入",
                    "成交日期 2026-05-01",
                    "成交数量 100",
                    "成交价格 350.1200",
                    "发生金额 -35035.0000",
                    "币种 HKD",
                ]
            }
        }

    class FakeEngine:
        def predict(self, image_path: str):
            assert image_path == str(tmp_path / "trade.png")
            return [FakeResult()]

        def ocr(self, image_path: str, cls: bool = True):
            raise AssertionError("PaddleOCR 3.x engines should use predict()")

    provider = PaddleOCRVisionProvider(engine=FakeEngine())

    result = provider.recognize(tmp_path / "trade.png", "htsc_global")

    assert result.screenshot_type == "trade_history"
    assert result.transactions[0].symbol == "00700"
