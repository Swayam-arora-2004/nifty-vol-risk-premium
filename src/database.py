"""DuckDB connection management and parameterized query helpers."""

from __future__ import annotations

import duckdb
import pandas as pd

from src.config import DB_PATH, SCHEMA_PATH


def get_db_connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH))


def init_db() -> None:
    with get_db_connection() as conn:
        conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def query_df(query: str, params: list | None = None) -> pd.DataFrame:
    with get_db_connection() as conn:
        return conn.execute(query, params or []).arrow().to_pandas()
