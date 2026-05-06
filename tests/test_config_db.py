from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from assetflow.config import Settings
from assetflow.db import create_db_and_tables, make_engine
from assetflow.models import Upload


def create_legacy_transaction_table(engine: Engine) -> None:
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


def insert_legacy_transaction_row(engine: Engine, *, row_id: int = 1, dedupe_key: str = "legacy-key") -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            INSERT INTO "transaction" (
                id,
                broker,
                symbol,
                security_name,
                trade_type,
                trade_date,
                quantity,
                price,
                net_amount,
                currency,
                source_upload_id,
                source_ocr_result_id,
                source_candidate_id,
                dedupe_key,
                confidence,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                "htsc_global",
                "00700",
                "Tencent",
                "buy",
                "2026-05-04",
                "100",
                "10",
                "-1000",
                "HKD",
                10,
                20,
                30,
                dedupe_key,
                0.95,
                "confirmed",
                "2026-05-04 01:02:03",
                "2026-05-04 01:02:03",
            ),
        )


def create_legacy_position_snapshot_table_without_daily_pnl(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE positionsnapshot (
                id INTEGER PRIMARY KEY,
                upload_id INTEGER NOT NULL,
                ocr_result_id INTEGER NOT NULL,
                broker VARCHAR NOT NULL,
                account_alias VARCHAR,
                market VARCHAR,
                symbol VARCHAR NOT NULL,
                security_name VARCHAR,
                quantity NUMERIC(20, 6) NOT NULL,
                available_quantity NUMERIC(20, 6),
                cost_price NUMERIC(20, 6),
                market_price NUMERIC(20, 6),
                market_value NUMERIC(20, 6),
                unrealized_pnl NUMERIC(20, 6),
                currency VARCHAR NOT NULL,
                snapshot_at DATETIME NOT NULL,
                confidence FLOAT NOT NULL,
                created_at DATETIME NOT NULL
            )
            """
        )


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
    create_legacy_transaction_table(engine)
    insert_legacy_transaction_row(engine)

    create_db_and_tables(engine)

    with engine.connect() as connection:
        rows = connection.exec_driver_sql('PRAGMA table_info("transaction")').all()
        indexes = connection.exec_driver_sql('PRAGMA index_list("transaction")').all()
        saved = connection.exec_driver_sql('SELECT id, dedupe_key FROM "transaction"').all()
    not_null_by_name = {row[1]: row[3] for row in rows}
    index_names = {row[1] for row in indexes}
    assert not_null_by_name["source_upload_id"] == 0
    assert not_null_by_name["source_ocr_result_id"] == 0
    assert not_null_by_name["source_candidate_id"] == 0
    assert "ix_transaction_dedupe_key" in index_names
    assert saved == [(1, "legacy-key")]


def test_create_db_and_tables_adds_position_daily_pnl_column(tmp_path: Path) -> None:
    settings = Settings(
        assetflow_data_dir=tmp_path / "data",
        assetflow_upload_token="secret-token",
        assetflow_recognition_provider="fixture",
    )
    settings.ensure_directories()
    engine = make_engine(settings.database_url)
    create_legacy_position_snapshot_table_without_daily_pnl(engine)

    create_db_and_tables(engine)

    with engine.connect() as connection:
        rows = connection.exec_driver_sql('PRAGMA table_info("positionsnapshot")').all()
    column_names = {row[1] for row in rows}
    assert "daily_pnl" in column_names


def test_create_db_and_tables_relaxes_position_quantity_column(tmp_path: Path) -> None:
    settings = Settings(
        assetflow_data_dir=tmp_path / "data",
        assetflow_upload_token="secret-token",
        assetflow_recognition_provider="fixture",
    )
    settings.ensure_directories()
    engine = make_engine(settings.database_url)
    create_legacy_position_snapshot_table_without_daily_pnl(engine)

    create_db_and_tables(engine)

    with engine.connect() as connection:
        rows = connection.exec_driver_sql('PRAGMA table_info("positionsnapshot")').all()
    not_null_by_name = {row[1]: row[3] for row in rows}
    assert not_null_by_name["quantity"] == 0


def test_sqlite_engine_uses_wal_and_busy_timeout(tmp_path: Path) -> None:
    settings = Settings(
        assetflow_data_dir=tmp_path / "data",
        assetflow_upload_token="secret-token",
        assetflow_recognition_provider="fixture",
    )
    settings.ensure_directories()
    engine = make_engine(settings.database_url)

    with engine.connect() as connection:
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
        busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar()

    assert journal_mode == "wal"
    assert busy_timeout >= 30000


def test_create_db_and_tables_preserves_existing_legacy_named_table(tmp_path: Path) -> None:
    settings = Settings(
        assetflow_data_dir=tmp_path / "data",
        assetflow_upload_token="secret-token",
        assetflow_recognition_provider="fixture",
    )
    settings.ensure_directories()
    engine = make_engine(settings.database_url)
    create_legacy_transaction_table(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE "transaction__legacy_source_nullable" (id INTEGER PRIMARY KEY, marker VARCHAR)')
        connection.exec_driver_sql(
            'INSERT INTO "transaction__legacy_source_nullable" (id, marker) VALUES (1, "do-not-delete")'
        )

    create_db_and_tables(engine)

    with engine.connect() as connection:
        saved = connection.exec_driver_sql(
            'SELECT id, marker FROM "transaction__legacy_source_nullable"'
        ).all()
    assert saved == [(1, "do-not-delete")]
