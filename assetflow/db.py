from collections.abc import Generator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine


def make_engine(database_url: str) -> Engine:
    is_sqlite = database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}
    engine = create_engine(database_url, connect_args=connect_args)
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def set_sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    return engine


def create_db_and_tables(engine: Engine) -> None:
    _relax_sqlite_transaction_source_columns(engine)
    _relax_sqlite_position_quantity_column(engine)
    _add_sqlite_column_if_missing(engine, "positionsnapshot", "daily_pnl", "NUMERIC(20, 6)")
    SQLModel.metadata.create_all(engine)


def session_scope(engine: Engine) -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def _relax_sqlite_transaction_source_columns(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    source_columns = {"source_upload_id", "source_ocr_result_id", "source_candidate_id"}
    with engine.begin() as connection:
        rows = connection.exec_driver_sql('PRAGMA table_info("transaction")').all()
        if not rows:
            return

        not_null_by_name = {row[1]: row[3] for row in rows}
        if not any(not_null_by_name.get(column_name) for column_name in source_columns):
            return

        legacy_table = _sqlite_unique_table_name(connection, "transaction__source_nullable_migration")
        indexes = connection.exec_driver_sql(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'index'
              AND tbl_name = 'transaction'
              AND sql IS NOT NULL
            """
        ).all()
        for index_name, _ in indexes:
            connection.exec_driver_sql(f'DROP INDEX IF EXISTS "{index_name}"')

        connection.exec_driver_sql(f'ALTER TABLE "transaction" RENAME TO "{legacy_table}"')
        SQLModel.metadata.tables["transaction"].create(connection)

        column_names = [row[1] for row in rows]
        quoted_columns = ", ".join(f'"{column_name}"' for column_name in column_names)
        connection.exec_driver_sql(
            f'INSERT INTO "transaction" ({quoted_columns}) SELECT {quoted_columns} FROM "{legacy_table}"'
        )

        current_indexes = connection.exec_driver_sql('PRAGMA index_list("transaction")').all()
        current_index_names = {row[1] for row in current_indexes}
        for index_name, index_sql in indexes:
            if index_name not in current_index_names:
                connection.exec_driver_sql(index_sql)

        connection.exec_driver_sql(f'DROP TABLE "{legacy_table}"')


def _add_sqlite_column_if_missing(engine: Engine, table_name: str, column_name: str, column_sql: str) -> None:
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        if not _sqlite_table_exists(connection, table_name):
            return
        rows = connection.exec_driver_sql(f'PRAGMA table_info("{table_name}")').all()
        column_names = {row[1] for row in rows}
        if column_name in column_names:
            return
        connection.exec_driver_sql(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_sql}')


def _relax_sqlite_position_quantity_column(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        rows = connection.exec_driver_sql('PRAGMA table_info("positionsnapshot")').all()
        if not rows:
            return

        not_null_by_name = {row[1]: row[3] for row in rows}
        if not not_null_by_name.get("quantity"):
            return

        legacy_table = _sqlite_unique_table_name(connection, "positionsnapshot__quantity_nullable_migration")
        indexes = connection.exec_driver_sql(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'index'
              AND tbl_name = 'positionsnapshot'
              AND sql IS NOT NULL
            """
        ).all()
        for index_name, _ in indexes:
            connection.exec_driver_sql(f'DROP INDEX IF EXISTS "{index_name}"')

        connection.exec_driver_sql(f'ALTER TABLE "positionsnapshot" RENAME TO "{legacy_table}"')
        SQLModel.metadata.tables["positionsnapshot"].create(connection)

        current_rows = connection.exec_driver_sql('PRAGMA table_info("positionsnapshot")').all()
        current_column_names = {row[1] for row in current_rows}
        column_names = [row[1] for row in rows if row[1] in current_column_names]
        quoted_columns = ", ".join(f'"{column_name}"' for column_name in column_names)
        connection.exec_driver_sql(
            f'INSERT INTO "positionsnapshot" ({quoted_columns}) SELECT {quoted_columns} FROM "{legacy_table}"'
        )

        current_indexes = connection.exec_driver_sql('PRAGMA index_list("positionsnapshot")').all()
        current_index_names = {row[1] for row in current_indexes}
        for index_name, index_sql in indexes:
            if index_name not in current_index_names:
                connection.exec_driver_sql(index_sql)

        connection.exec_driver_sql(f'DROP TABLE "{legacy_table}"')


def _sqlite_unique_table_name(connection, base_name: str) -> str:
    table_name = base_name
    suffix = 1
    while _sqlite_table_exists(connection, table_name):
        table_name = f"{base_name}_{suffix}"
        suffix += 1
    return table_name


def _sqlite_table_exists(connection, table_name: str) -> bool:
    return (
        connection.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).first()
        is not None
    )
