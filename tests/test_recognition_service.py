from pathlib import Path

from assetflow.recognition.providers import FixtureVisionProvider


def test_fixture_provider_loads_normalized_trade_response() -> None:
    provider = FixtureVisionProvider(Path("tests/fixtures/recognition/trade_history.json"))

    result = provider.recognize(image_path=Path("unused.png"), broker="htsc_global")

    assert result.screenshot_type == "trade_history"
    assert result.transactions[0].symbol == "00700"
    assert result.transactions[0].currency == "HKD"
