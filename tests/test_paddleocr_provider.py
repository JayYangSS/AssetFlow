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
    assert result.transactions[0].gross_amount == Decimal("48900.000")
    assert result.transactions[0].net_amount is None
    assert result.transactions[0].market == "HK"
    assert result.transactions[0].currency == "HKD"
    assert result.transactions[1].trade_type == "sell"
    assert result.transactions[1].gross_amount == Decimal("9000.000")
    assert result.transactions[1].net_amount is None


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


def test_parse_htsc_compact_filled_order_list_accepts_noisy_market_tokens() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "订单",
            "已成交",
            "时间",
            "名称代码",
            "买卖方向",
            "数量丨价格",
            "2025-07-15阿里巴巴-W",
            "200",
            "卖出",
            "14:18",
            "HK]",
            "09988",
            "112.200",
            "2025-06-12阿里巴巴-W",
            "200",
            "买入",
            "15:40",
            "HK",
            "09988",
            "114.500",
            "2025-06-05阿里巴巴-W",
            "200",
            "卖出",
            "09:31",
            "HK]",
            "09988",
            "118.000",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "trade_history"
    assert len(result.transactions) == 3
    assert [(item.trade_date.isoformat(), item.trade_type) for item in result.transactions] == [
        ("2025-07-15", "sell"),
        ("2025-06-12", "buy"),
        ("2025-06-05", "sell"),
    ]
    assert result.transactions[0].market == "HK"
    assert result.transactions[0].symbol == "09988"
    assert result.transactions[0].price == Decimal("112.200")
    assert result.transactions[2].price == Decimal("118.000")


def test_parse_htsc_security_detail_transactions_treats_lottery_allocation_as_buy() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "HK",
            "曦智科技-P(01879)",
            "累计盈亏T-1日盈亏收益",
            "盈亏金额",
            "交易明细",
            "流水明细",
            "日期",
            "类型",
            "实现金额",
            "数量丨均价",
            "04-28",
            "2026",
            "卖出",
            "11,698.00",
            "15.00",
            "781.000",
            "04-27",
            "2026",
            "中签",
            "-2,874.71",
            "15.00",
            "183.200",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "trade_history"
    assert result.confidence == 0.75
    assert len(result.transactions) == 2
    sell, allocation = result.transactions
    assert sell.market == "HK"
    assert sell.symbol == "01879"
    assert sell.security_name == "曦智科技-P"
    assert sell.trade_type == "sell"
    assert sell.trade_date == date(2026, 4, 28)
    assert sell.trade_time is None
    assert sell.quantity == Decimal("15.00")
    assert sell.price == Decimal("781.000")
    assert sell.net_amount == Decimal("11698.00")
    assert sell.gross_amount == Decimal("11715.00000")
    assert sell.currency == "HKD"
    assert allocation.trade_type == "buy"
    assert allocation.trade_date == date(2026, 4, 27)
    assert allocation.quantity == Decimal("15.00")
    assert allocation.price == Decimal("183.200")
    assert allocation.net_amount == Decimal("-2874.71")
    assert allocation.gross_amount == Decimal("2748.00000")


def test_parse_htsc_security_detail_transactions_accepts_real_ocr_line_order() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "12:26 ≥",
            "44",
            "曦智科技-P（01879）",
            "HK",
            "累计盈亏为T-1日盈亏收益",
            "盈亏金额",
            "页=市值变动+进账金额－出账金额",
            "盈亏金额（HKD）",
            "建仓以来",
            "+8.823.29",
            "盈亏比例！",
            "市值变动",
            "0.00",
            "进账金额",
            "出账金额",
            "11,698.00",
            "2,874.71",
            "卖出金额",
            "11,698.00",
            "买入金额",
            "0.00",
            "中签金额",
            "2,874.71",
            "交易明细",
            "流水明细",
            "全部",
            "日期",
            "类型",
            "实现金额",
            "数量|均价",
            "04-28",
            "15.00",
            "卖出",
            "11,698.00",
            "2026",
            "781.000",
            "04-27",
            "15.00",
            "中签",
            "-2,874.71",
            "2026",
            "183.200",
            "我是有底线的~",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "trade_history"
    assert result.confidence == 0.75
    assert len(result.transactions) == 2
    sell, allocation = result.transactions
    assert sell.market == "HK"
    assert sell.symbol == "01879"
    assert sell.security_name == "曦智科技-P"
    assert sell.trade_type == "sell"
    assert sell.trade_date == date(2026, 4, 28)
    assert sell.quantity == Decimal("15.00")
    assert sell.price == Decimal("781.000")
    assert sell.net_amount == Decimal("11698.00")
    assert sell.gross_amount == Decimal("11715.00000")
    assert sell.currency == "HKD"
    assert allocation.trade_type == "buy"
    assert allocation.trade_date == date(2026, 4, 27)
    assert allocation.quantity == Decimal("15.00")
    assert allocation.price == Decimal("183.200")
    assert allocation.net_amount == Decimal("-2874.71")
    assert allocation.gross_amount == Decimal("2748.00000")


def test_parse_htsc_trade_history_does_not_emit_empty_fallback_transaction() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "交易明细",
            "日期",
            "类型",
            "实现金额",
            "数量|均价",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "trade_history"
    assert result.transactions == []


def test_parse_htsc_cash_transfer_history_creates_cash_movement_transactions() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "21:26 ≥",
            "入金记录",
            "出金记录",
            "HKD",
            "+7,000.00",
            "转入成功",
            "其他入金",
            "04-0909:35:06",
            "2020-12",
            "HKD",
            "+7,299.03",
            "转入成功",
            "其他入金",
            "12-3110:55:43",
            "2020-11",
            "HKD",
            "+1,300.00",
            "转入成功",
            "其他入金",
            "11-2714:25:14",
            "2020-08",
            "HKD",
            "+40,000.00",
            "转入成功",
            "其他入金",
            "08-2510:02:13",
            "HKD",
            "+10,000.00",
            "转入成功",
            "其他入金",
            "08-1914:51:30",
            "HKD",
            "+10,135.00",
            "转入成功",
            "其他入金",
            "08-1911:13:47",
            "HKD",
            "+20,000.00",
            "转入成功",
            "其他入金",
            "08-0419:45:59",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "cash"
    assert result.confidence == 0.75
    assert len(result.transactions) == 7
    first = result.transactions[0]
    assert first.symbol == "CASH"
    assert first.security_name == "Cash"
    assert first.trade_type == "cash_in"
    assert first.trade_date == date(2021, 4, 9)
    assert first.trade_time.isoformat() == "09:35:06"
    assert first.quantity == Decimal("0")
    assert first.price == Decimal("0")
    assert first.net_amount == Decimal("7000.00")
    assert first.currency == "HKD"
    assert result.transactions[1].trade_date == date(2020, 12, 31)
    assert result.transactions[1].net_amount == Decimal("7299.03")
    assert result.transactions[-1].trade_date == date(2020, 8, 4)
    assert result.transactions[-1].trade_time.isoformat() == "19:45:59"
    assert result.transactions[-1].net_amount == Decimal("20000.00")


def test_parse_htsc_cash_transfer_history_accepts_dot_between_date_and_time() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "入金记录",
            "出金记录",
            "HKD",
            "+1,174.60",
            "转入成功",
            "付款账户（9276）1银证转账",
            "08-2612:47:14",
            "2022-03",
            "HKD",
            "+10,000.02",
            "转入成功",
            "付款账户（9276）1银证转账",
            "03-1509:16:41",
            "2022-01",
            "HKD",
            "+24,567.24",
            "转入成功",
            "付款账户（9276）1银证转账",
            "01-0612:43:19",
            "2021-11",
            "HKD",
            "+40,000.00",
            "转入成功",
            "付款账户（9276）1银证转账",
            "11-30.14:54:24",
            "2021-10",
            "HKD",
            "+36,177.08",
            "转入成功",
            "付款账户（9276）1银证转账",
            "10-0710:03:53",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "cash"
    assert len(result.transactions) == 5
    highlighted = result.transactions[3]
    assert highlighted.trade_date == date(2021, 11, 30)
    assert highlighted.trade_time.isoformat() == "14:54:24"
    assert highlighted.net_amount == Decimal("40000.00")


def test_parse_htsc_cash_out_history_with_chinese_currency_and_processed_status() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "入金记录",
            "出金记录",
            "全部",
            "共计10笔",
            "港元",
            "2025-09-05 19:03:28",
            "4,347.63",
            "已处理",
            "港元",
            "2025-09-05 14:26:48",
            "60,000.00",
            "已处理",
            "港元",
            "2025-06-1009:30:02",
            "672.35",
            "已处理",
            "美元",
            "2025-04-11 14:44:02",
            "1,164.68",
            "已处理",
            "美元",
            "2025-02-26 13:16:20",
            "444.56",
            "已处理",
            "港元",
            "2024-01-0309:55:13",
            "61,092.13",
            "已处理",
            "港元",
            "2023-12-29 12:19:12",
            "15.807.32",
            "已处理",
            "港元",
            "2023-12-2809:52:36",
            "40.741.38",
            "已处理",
            "港元",
            "2023-12-2713:46:16",
            "200.00",
            "已处理",
            "港元",
            "2023-09-1021:18:26",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "cash"
    assert result.confidence == 0.75
    assert len(result.transactions) == 9
    first = result.transactions[0]
    assert first.trade_type == "cash_out"
    assert first.trade_date == date(2025, 9, 5)
    assert first.trade_time.isoformat() == "14:26:48"
    assert first.net_amount == Decimal("-4347.63")
    assert first.currency == "HKD"
    assert result.transactions[2].trade_date == date(2025, 4, 11)
    assert result.transactions[2].currency == "USD"
    assert result.transactions[6].net_amount == Decimal("-15807.32")
    assert result.transactions[7].net_amount == Decimal("-40741.38")
    assert result.transactions[-1].trade_date == date(2023, 9, 10)
    assert result.transactions[-1].trade_time.isoformat() == "21:18:26"
    assert result.transactions[-1].net_amount == Decimal("-200.00")


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


def test_parse_htsc_positions_watchlist_screenshot() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "自选",
            "持仓",
            "订单",
            "港股",
            "393,680.00 HKD",
            "名称代码",
            "市值|数量",
            "今日盈亏",
            "腾讯控股",
            "47,220.00",
            "-80.00",
            "HK",
            "00700",
            "M",
            "100",
            "-0.16%",
            "天星医疗",
            "0.00",
            "16,239.68",
            "HK",
            "01609",
            "0.00",
            "理想汽车-W",
            "13,930.00",
            "-100.00",
            "HK",
            "02015",
            "200",
            "-0.71%",
            "美团-W",
            "33,420.00",
            "-360.00",
            "HK",
            "03690",
            "M",
            "400",
            "-1.06%",
            "地平线机器人-W",
            "207,270.00",
            "-9,702.00",
            "HK",
            "09660",
            "29,400",
            "-4.47%",
            "阿里巴巴-W",
            "91,840.00",
            "-350.00",
            "HK",
            "09988",
            "M",
            "700",
            "-0.37%",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "positions"
    assert result.confidence == 0.75
    assert len(result.positions) == 6
    assert result.positions[0].security_name == "腾讯控股"
    assert result.positions[0].market == "HK"
    assert result.positions[0].symbol == "00700"
    assert result.positions[0].market_value == Decimal("47220.00")
    assert result.positions[0].quantity == Decimal("100")
    assert result.positions[0].currency == "HKD"
    assert result.positions[0].daily_pnl == Decimal("-80.00")
    assert result.positions[0].unrealized_pnl is None
    assert result.positions[2].security_name == "理想汽车-W"
    assert result.positions[2].symbol == "02015"
    assert result.positions[2].quantity == Decimal("200")
    assert result.positions[4].security_name == "地平线机器人-W"
    assert result.positions[4].quantity == Decimal("29400")
    assert result.positions[5].symbol == "09988"


def test_parse_htsc_positions_current_cost_screenshot_keeps_columns_aligned() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "自选",
            "持仓",
            "订单",
            "港股",
            "名称代码",
            "现价|成本",
            "持仓盈亏",
            "腾讯控股",
            "472.200",
            "-1,735.20",
            "HK",
            "00700",
            "M",
            "489.552",
            "-3.54%",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "positions"
    assert len(result.positions) == 1
    position = result.positions[0]
    assert position.security_name == "腾讯控股"
    assert position.market == "HK"
    assert position.symbol == "00700"
    assert position.market_price == Decimal("472.200")
    assert position.cost_price == Decimal("489.552")
    assert position.unrealized_pnl == Decimal("-1735.20")
    assert position.quantity is None
    assert position.market_value is None
    assert position.daily_pnl is None


def test_parse_htsc_positions_market_value_screenshot_can_use_holding_pnl() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "持仓",
            "名称代码",
            "市值|数量",
            "持仓盈亏",
            "腾讯控股",
            "47,220.00",
            "-1,735.20",
            "HK",
            "00700",
            "M",
            "100",
            "-3.54%",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "positions"
    assert len(result.positions) == 1
    position = result.positions[0]
    assert position.market_value == Decimal("47220.00")
    assert position.quantity == Decimal("100")
    assert position.unrealized_pnl == Decimal("-1735.20")
    assert position.daily_pnl is None
    assert position.market_price is None
    assert position.cost_price is None


def test_parse_htsc_us_positions_with_letter_tickers() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "自选",
            "持仓",
            "订单",
            "港股",
            "美股",
            "名称代码",
            "市值|数量",
            "今日盈亏",
            "美国超微公司",
            "3,552.60",
            "137.20",
            "US",
            "AMD",
            "10",
            "+4.01%",
            "谷歌-A",
            "3,495.87",
            "46.62",
            "US",
            "GOOGL",
            "9",
            "+1.35%",
            "美光科技",
            "3,841.20",
            "382.50",
            "US",
            "MU",
            "6",
            "+11.05%",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "positions"
    assert result.confidence == 0.75
    assert len(result.positions) == 3
    first = result.positions[0]
    assert first.security_name == "美国超微公司"
    assert first.market == "US"
    assert first.symbol == "AMD"
    assert first.currency == "USD"
    assert first.market_value == Decimal("3552.60")
    assert first.quantity == Decimal("10")
    assert first.daily_pnl == Decimal("137.20")
    assert first.unrealized_pnl is None
    assert result.positions[1].symbol == "GOOGL"
    assert result.positions[1].quantity == Decimal("9")
    assert result.positions[2].symbol == "MU"
    assert result.positions[2].daily_pnl == Decimal("382.50")


def test_parse_htsc_us_positions_when_ocr_misses_quantity_lines() -> None:
    result = parse_htsc_global_ocr_lines(
        [
            "持仓",
            "美股",
            "名称代码",
            "市值|数量",
            "今日盈亏",
            "美国超微公司",
            "3,552.60",
            "137.20",
            "US",
            "AMD",
            "10",
            "+4.01%",
            "谷歌-A",
            "3,495.87",
            "46.62",
            "US",
            "GOOGL",
            "+1.35%",
            "美光科技",
            "异动?",
            "3,841.20",
            "382.50",
            "US",
            "MU",
            "+11.05%",
        ],
        broker="htsc_global",
    )

    assert result.screenshot_type == "positions"
    assert result.confidence == 0.75
    assert len(result.positions) == 3
    assert result.positions[0].symbol == "AMD"
    assert result.positions[0].quantity == Decimal("10")
    assert result.positions[0].daily_pnl == Decimal("137.20")
    assert result.positions[1].security_name == "谷歌-A"
    assert result.positions[1].symbol == "GOOGL"
    assert result.positions[1].market_value == Decimal("3495.87")
    assert result.positions[1].quantity is None
    assert result.positions[1].daily_pnl == Decimal("46.62")
    assert result.positions[2].security_name == "美光科技"
    assert result.positions[2].symbol == "MU"
    assert result.positions[2].market_value == Decimal("3841.20")
    assert result.positions[2].quantity is None
    assert result.positions[2].daily_pnl == Decimal("382.50")


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
