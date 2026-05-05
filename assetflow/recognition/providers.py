import base64
import json
from pathlib import Path
from typing import Protocol

from openai import OpenAI

from assetflow.config import Settings
from assetflow.recognition.paddleocr_provider import PaddleOCRVisionProvider
from assetflow.recognition.schemas import RecognizedScreenshot


class VisionProvider(Protocol):
    provider_name: str
    model_name: str

    def recognize(self, image_path: Path, broker: str) -> RecognizedScreenshot:
        ...


class FixtureVisionProvider:
    provider_name = "fixture"
    model_name = "fixture-json"

    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path

    def recognize(self, image_path: Path, broker: str) -> RecognizedScreenshot:
        data = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        return RecognizedScreenshot.model_validate(data)


class OpenAIVisionProvider:
    provider_name = "openai"

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when ASSETFLOW_RECOGNITION_PROVIDER=openai")
        self.model_name = settings.assetflow_openai_model
        self.client = OpenAI(api_key=settings.openai_api_key)

    def recognize(self, image_path: Path, broker: str) -> RecognizedScreenshot:
        image_bytes = image_path.read_bytes()
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        prompt = (
            "你是投资交易截图结构化助手。只输出符合 schema 的字段。"
            f"券商标识是 {broker}。"
            "识别截图类型为 trade_history、positions、cash 或 unknown。"
            "金额、数量、价格必须保留原始精度；无法确定的字段用 null；不要编造。"
        )
        response = self.client.responses.parse(
            model=self.model_name,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": f"data:image/png;base64,{image_b64}"},
                    ],
                }
            ],
            text_format=RecognizedScreenshot,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ValueError("OpenAI response did not include parsed recognition output")
        return parsed


def make_provider(settings: Settings) -> VisionProvider:
    if settings.assetflow_recognition_provider == "fixture":
        return FixtureVisionProvider(Path("tests/fixtures/recognition/trade_history.json"))
    if settings.assetflow_recognition_provider == "openai":
        return OpenAIVisionProvider(settings)
    if settings.assetflow_recognition_provider == "paddleocr":
        return PaddleOCRVisionProvider()
    raise ValueError(f"Unsupported recognition provider: {settings.assetflow_recognition_provider}")
