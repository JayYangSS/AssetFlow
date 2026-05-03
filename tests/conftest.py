from collections.abc import Generator
from pathlib import Path

import pytest
from sqlmodel import Session

from assetflow.config import Settings
from assetflow.db import create_db_and_tables, make_engine


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    value = Settings(
        assetflow_data_dir=tmp_path / "data",
        assetflow_upload_token="secret-token",
        assetflow_recognition_provider="fixture",
    )
    value.ensure_directories()
    return value


@pytest.fixture
def session(settings: Settings) -> Generator[Session, None, None]:
    engine = make_engine(settings.database_url)
    create_db_and_tables(engine)
    with Session(engine) as db:
        yield db
