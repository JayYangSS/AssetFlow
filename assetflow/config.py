from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    assetflow_data_dir: Path = Field(default=Path("data"))
    assetflow_upload_token: str = Field(min_length=8)
    assetflow_host: str = "0.0.0.0"
    assetflow_port: int = 8787
    assetflow_recognition_provider: str = "fixture"
    assetflow_openai_model: str = "gpt-4.1-mini"
    openai_api_key: str | None = None

    @property
    def upload_dir(self) -> Path:
        return self.assetflow_data_dir / "uploads"

    @property
    def export_dir(self) -> Path:
        return self.assetflow_data_dir / "exports"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.assetflow_data_dir / 'assetflow.db'}"

    def ensure_directories(self) -> None:
        self.assetflow_data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)
