import datetime as dt

import duckdb
import pandas as pd
import pytest

from src import database
from src.database import get_db_connection, init_db, query_df


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point the module-level DB_PATH at a throwaway file and initialize it."""
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test_nifty_vol.duckdb")
    init_db()
    return tmp_path / "test_nifty_vol.duckdb"


def _insert_option_row(symbol, strike, option_type="CE", trade_date="2024-01-01"):
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO options_eod (
                trade_date, expiry_date, symbol, strike, option_type,
                close, volume, open_interest, underlying_close
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [trade_date, "2024-01-25", symbol, strike, option_type,
             125.5, 1200, 45000, 21500.0],
        )


def test_init_db_creates_both_tables(isolated_db):
    assert isolated_db.exists()
    tables = query_df(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
        ["main"],
    )
    assert set(tables["table_name"]) == {"index_eod", "options_eod"}


def test_init_db_is_idempotent(isolated_db):
    init_db()
    init_db()
    tables = query_df("SELECT table_name FROM information_schema.tables")
    assert sorted(tables["table_name"]) == ["index_eod", "options_eod"]


def test_options_eod_has_symbol_column(isolated_db):
    cols = query_df(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
        ["options_eod"],
    )
    assert "symbol" in set(cols["column_name"])
    symbol_type = cols.loc[cols["column_name"] == "symbol", "data_type"].iloc[0]
    assert symbol_type.upper().startswith("VARCHAR")


def test_symbol_participates_in_primary_key(isolated_db):
    _insert_option_row("NIFTY", 21500.0)
    _insert_option_row("BANKNIFTY", 21500.0)

    rows = query_df(
        "SELECT symbol FROM options_eod WHERE strike = ? ORDER BY symbol", [21500.0]
    )
    assert rows["symbol"].tolist() == ["BANKNIFTY", "NIFTY"]

    with pytest.raises(duckdb.ConstraintException):
        _insert_option_row("NIFTY", 21500.0)


def test_query_df_parameterized_filter(isolated_db):
    _insert_option_row("NIFTY", 21000.0)
    _insert_option_row("NIFTY", 21500.0)
    _insert_option_row("NIFTY", 22000.0)

    result = query_df(
        "SELECT strike, close FROM options_eod "
        "WHERE symbol = ? AND strike BETWEEN ? AND ? ORDER BY strike",
        ["NIFTY", 21000.0, 21500.0],
    )
    assert result["strike"].tolist() == [21000.0, 21500.0]


def test_query_df_returns_dataframe_with_native_dtypes(isolated_db):
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO index_eod (symbol, trade_date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["NIFTY", "2024-01-01", 21000.0, 21600.0, 20950.0, 21500.0, 250000],
        )

    df = query_df("SELECT * FROM index_eod WHERE symbol = ?", ["NIFTY"])

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["symbol"] == "NIFTY"
    assert pd.to_datetime(df["trade_date"]).iloc[0] == pd.Timestamp("2024-01-01")
    assert row["close"] == pytest.approx(21500.0)
    assert int(row["volume"]) == 250000
    assert pd.api.types.is_float_dtype(df["close"])
    assert pd.api.types.is_integer_dtype(df["volume"])


def test_query_df_handles_empty_result_set(isolated_db):
    df = query_df("SELECT * FROM options_eod WHERE symbol = ?", ["DOES_NOT_EXIST"])
    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert "implied_vol" in df.columns


def test_query_df_without_params(isolated_db):
    df = query_df("SELECT COUNT(*) AS n FROM options_eod")
    assert df["n"].iloc[0] == 0


def test_index_eod_rejects_duplicate_primary_key(isolated_db):
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO index_eod (symbol, trade_date, close) VALUES (?, ?, ?)",
            ["NIFTY", dt.date(2024, 1, 1), 21500.0],
        )
        with pytest.raises(duckdb.ConstraintException):
            conn.execute(
                "INSERT INTO index_eod (symbol, trade_date, close) VALUES (?, ?, ?)",
                ["NIFTY", dt.date(2024, 1, 1), 21600.0],
            )
