from pathlib import Path

from assetflow.config import Settings


def test_settings_builds_data_directories(tmp_path: Path) -> None:
    settings = Settings(
        assetflow_data_dir=tmp_path / "data",
        assetflow_upload_token="secret-token",
        assetflow_recognition_provider="fixture",
    )

    assert settings.upload_dir == tmp_path / "data" / "uploads"
    assert settings.export_dir == tmp_path / "data" / "exports"
    assert settings.database_url == f"sqlite:///{tmp_path / 'data' / 'assetflow.db'}"
