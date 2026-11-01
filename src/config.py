"""Filesystem paths and environment-derived configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.getenv("DATA_DIR") or BASE_DIR / "data").resolve()
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

DB_PATH = Path(os.getenv("DB_PATH") or PROCESSED_DIR / "nifty_vol.duckdb").resolve()

SQL_DIR = BASE_DIR / "sql"
SCHEMA_PATH = SQL_DIR / "schema.sql"

for _directory in (RAW_DIR, PROCESSED_DIR, DB_PATH.parent):
    _directory.mkdir(parents=True, exist_ok=True)
