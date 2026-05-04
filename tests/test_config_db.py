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


def test_create_db_and_tables_relaxes_manual_transaction_source_columns(tmp_path: Path) -> None:
    settings = Settings(
        assetflow_data_dir=tmp_path / "data",
        assetflow_upload_token="secret-token",
        assetflow_recognition_provider="fixture",
    )
    settings.ensure_directories()
    engine = make_engine(settings.database_url)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE "transaction" (
                id INTEGER PRIMARY KEY,
                broker VARCHAR NOT NULL,
                account_alias VARCHAR,
                market VARCHAR,
                symbol VARCHAR NOT NULL,
                security_name VARCHAR NOT NULL,
                trade_type VARCHAR NOT NULL,
                trade_date DATE NOT NULL,
                trade_time TIME,
                quantity NUMERIC(20, 6) NOT NULL,
                price NUMERIC(20, 6) NOT NULL,
                gross_amount NUMERIC(20, 6),
                net_amount NUMERIC(20, 6) NOT NULL,
                commission NUMERIC(20, 6),
                fees NUMERIC(20, 6),
                currency VARCHAR NOT NULL,
                position_balance_after NUMERIC(20, 6),
                source_upload_id INTEGER NOT NULL,
                source_ocr_result_id INTEGER NOT NULL,
                source_candidate_id INTEGER NOT NULL,
                dedupe_key VARCHAR NOT NULL,
                confidence FLOAT NOT NULL,
                status VARCHAR NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        connection.exec_driver_sql('CREATE UNIQUE INDEX ix_transaction_dedupe_key ON "transaction" (dedupe_key)')

    create_db_and_tables(engine)

    with engine.connect() as connection:
        rows = connection.exec_driver_sql('PRAGMA table_info("transaction")').all()
        indexes = connection.exec_driver_sql('PRAGMA index_list("transaction")').all()
    not_null_by_name = {row[1]: row[3] for row in rows}
    index_names = {row[1] for row in indexes}
    assert not_null_by_name["source_upload_id"] == 0
    assert not_null_by_name["source_ocr_result_id"] == 0
    assert not_null_by_name["source_candidate_id"] == 0
    assert "ix_transaction_dedupe_key" in index_names
