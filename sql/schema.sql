-- Canonical DDL for the DuckDB analytical store (data/processed/nifty_vol.duckdb).
-- Executed idempotently by src.database.init_db().

CREATE TABLE IF NOT EXISTS index_eod (
    symbol           VARCHAR  NOT NULL,
    trade_date       DATE     NOT NULL,
    open             DOUBLE,
    high             DOUBLE,
    low              DOUBLE,
    close            DOUBLE,
    volume           BIGINT,
    PRIMARY KEY (symbol, trade_date)
);

CREATE TABLE IF NOT EXISTS options_eod (
    trade_date       DATE        NOT NULL,
    expiry_date      DATE        NOT NULL,
    symbol           VARCHAR     NOT NULL,
    strike           DOUBLE      NOT NULL,
    option_type      VARCHAR(2)  NOT NULL,
    open             DOUBLE,
    high             DOUBLE,
    low              DOUBLE,
    close            DOUBLE,
    settle_price     DOUBLE,
    volume           BIGINT,
    open_interest    BIGINT,
    underlying_close DOUBLE,
    implied_vol      DOUBLE,
    PRIMARY KEY (trade_date, expiry_date, symbol, strike, option_type)
);
