from pathlib import Path

from sqlmodel import Session, select

from assetflow.config import Settings
from assetflow.db import create_db_and_tables, make_engine
from assetflow.models import Upload


def test_settings_builds_data_directories(tmp_path: Path) -> None:
    settings = Settings(
        assetflow_data_dir=tmp_path / "data",
        assetflow_upload_token="secret-token",
        assetflow_recognition_provider="fixture",
    )

    assert settings.upload_dir == tmp_path / "data" / "uploads"
    assert settings.export_dir == tmp_path / "data" / "exports"
    assert settings.database_url == f"sqlite:///{tmp_path / 'data' / 'assetflow.db'}"


def test_env_example_contains_startable_settings() -> None:
    settings = Settings(_env_file=Path(".env.example"))

    assert len(settings.assetflow_upload_token) >= 8
    assert settings.assetflow_recognition_provider == "fixture"


def test_create_db_and_tables_allows_upload_insert(tmp_path: Path) -> None:
    settings = Settings(
        assetflow_data_dir=tmp_path / "data",
        assetflow_upload_token="secret-token",
        assetflow_recognition_provider="fixture",
    )
    settings.ensure_directories()
    engine = make_engine(settings.database_url)
    create_db_and_tables(engine)

    with Session(engine) as session:
        upload = Upload(
            broker="htsc_global",
            source="ios_shortcut",
            original_filename="sample.png",
            content_hash="abc123",
            image_path=str(tmp_path / "data" / "uploads" / "sample.png"),
            mime_type="image/png",
            file_size_bytes=12,
            status="stored",
        )
        session.add(upload)
        session.commit()

        saved = session.exec(select(Upload)).one()

    assert saved.content_hash == "abc123"
