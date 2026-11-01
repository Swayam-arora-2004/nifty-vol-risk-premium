# Architectural Decision Records — `nifty-vol-risk-premium`

> **Scope Note:** This log records only foundational architectural pivots — decisions that constrain future design, change a core dependency, or alter the system's structural shape. Minor incremental code changes (refactors, bug fixes, small feature additions, parameter tuning) are **strictly excluded** and belong in commit history / PR descriptions, not here.

---

## ADR-001: Columnar In-Process OLAP Engine (DuckDB) over Client-Server RDBMS

**Status:** Accepted

**Context:**
The system must execute fast analytical aggregations (GROUP BY date/strike/expiry, rolling window functions, joins across ~1.5M option records spanning 5 years) in a research/backtesting context that must also run inside Streamlit Cloud (resource-constrained, ephemeral containers) and GitHub Actions CI (no persistent infrastructure). Traditional client-server RDBMS options (PostgreSQL) assume a long-lived server process and network socket; row-store engines (SQLite) are not optimized for analytical scan patterns.

**Decision:**
Adopt **DuckDB** as the sole analytical database engine, with the on-disk file at `data/processed/nifty_vol.duckdb`, and partitioned Parquet files as a secondary columnar cache.

**Structural Justification:**
- **Vectorized SIMD execution** — DuckDB scans only the columns referenced in a query (columnar storage), unlike row-store engines that must read full rows even for a two-column aggregation.
- **Zero-copy Arrow memory buffers** — DuckDB integrates natively with Pandas/Arrow, allowing `conn.register()` to expose DataFrames as virtual tables without serialization overhead.
- **Zero background daemon / zero connection socket overhead** — DuckDB runs embedded in-process; there is no server to provision, authenticate against, or keep alive, which is a hard requirement for stateless CI runners and Streamlit Cloud's container lifecycle.
- **Portability** — a single `.duckdb` file (or in-memory `:memory:` instance) requires no installation step beyond `pip install duckdb`, making local dev, CI, and cloud deployment environments identical.

**Alternatives Evaluated:**

- **PostgreSQL** — Rejected. Requires a running server process, connection pooling, and credential management; incompatible with ephemeral CI/Streamlit Cloud deployment and adds operational overhead disproportionate to a single-user analytical workload.

- **SQLite** — Rejected. Row-store architecture forces full-row scans for column-selective analytical queries; no native vectorized execution; weaker window-function performance at the ~1.5M row scale this system operates at.

---

## ADR-002: SciPy Brent's Method (`brentq`) over Newton-Raphson for Implied Volatility Inversion

**Status:** Accepted

**Context:**
Implied volatility has no closed-form solution under Black-Scholes and must be solved numerically by inverting the pricing function against observed option premiums. The solver must be robust across the full NIFTY options chain, including deep OTM strikes and near-expiry contracts where Vega approaches zero.

**Decision:**
Use `scipy.optimize.brentq` bounded on `σ ∈ [1e-4, 4.0]` as the implied volatility solver in `src/black_scholes.py`.

**Structural Justification:**
- **Guaranteed convergence on a bounded interval** — Brent's method combines bisection, secant, and inverse quadratic interpolation and is guaranteed to converge within `[σ_min, σ_max]` provided the function changes sign across the interval, with no risk of diverging outside a sane volatility range.
- **Immune to zero-Vega wing divergence** — Newton-Raphson's update step divides by Vega (`∂C/∂σ`), which approaches zero for deep OTM options or contracts near expiry, causing step-size explosion or outright division-by-zero. Brent's method requires no derivative at all.
- **No catastrophic failure mode** — a failed Brent inversion (no sign change in bracket) can be caught deterministically and mapped to `np.nan`, whereas Newton-Raphson can silently diverge to nonsensical volatility values.

**Alternatives Evaluated:**

- **Newton-Raphson** — Rejected. Fast when it converges, but unstable (div-by-zero / divergence) near zero-Vega regions — common at deep OTM strikes and short-dated contracts, which are exactly the regions this system must handle robustly across a full exchange-wide chain.

- **Precomputed lookup grids** — Rejected. Requires pre-generating a dense grid of (moneyness, T, σ) → price mappings and interpolating; introduces interpolation error, large storage overhead, and staleness risk as pricing conventions or rate assumptions change.

---

## ADR-003: Range-Based Realized Volatility (Parkinson & Garman-Klass) over Close-to-Close Sample Variance

**Status:** Accepted

**Context:**
Realized volatility (RV) is the counterpart to implied volatility (IV) in computing the Variance Risk Premium (`VRP = IV - RV`). The choice of RV estimator directly affects the statistical validity of the VRP signal.

**Decision:**
Compute RV using **Parkinson (High-Low)** and **Garman-Klass (OHLC)** range-based estimators, in `src/realized_vol.py`, as the primary RV measures, with close-to-close retained only as a diagnostic baseline.

**Structural Justification:**
- **Close-to-close discards all intraday path information** — it uses only two price points per day (today's close, yesterday's close), ignoring the full intraday trading range.
- **Parkinson estimator is ~5x more statistically efficient** — by using the daily high and low, it captures realized price dispersion the close-to-close estimator misses entirely, reducing estimator variance for the same sample size.
- **Garman-Klass estimator is up to 7.4x more efficient** — by incorporating open, high, low, and close, it further reduces estimation noise.
- **Prevents artificial VRP inflation** — a noisy, high-variance RV estimator (close-to-close) understates true realized volatility on average in trending/range-bound regimes, which would artificially inflate the measured VRP and bias backtest conclusions about the vol risk premium's profitability.

**Alternatives Evaluated:**

- **Close-to-close sample std. dev. of log returns** — Rejected. Statistically inefficient relative to range-based estimators; discards intraday high/low information that is already present for free in the EOD index data this system ingests.

---

## ADR-004: Direct Automated NSE Bhavcopy Ingestion over Third-Party Broker APIs

**Status:** Accepted

**Context:**
The system requires full-chain historical options data (all strikes, all expiries) across NIFTY 50 options from 2021 onward for backtesting. Broker APIs (e.g., Zerodha Kite Connect) are an alternative data source but are designed primarily for live trading, not bulk historical research.

**Decision:**
Ingest data directly from **NSE's published daily Bhavcopy ZIP archives** via HTTP streaming with in-memory unzip, rather than through a broker API.

**Structural Justification:**
- **Zero ongoing subscription overhead** — NSE Bhavcopy files are publicly published EOD archives with no API key, no rate-limited quota, and no recurring cost.
- **Full market options chain** — Bhavcopy files contain every traded strike and expiry for the full exchange session, whereas broker historical APIs are typically throttled, paginated, and sometimes restricted to a subset of liquid contracts.
- **Eliminates daily token authentication scripts** — broker APIs require OAuth-style daily token refresh flows (e.g., Kite Connect's daily login token), adding operational fragility to a batch research pipeline that should run unattended in CI.

**Alternatives Evaluated:**

- **Zerodha Kite Connect Historical API** — Rejected. Requires a paid API subscription, daily manual/scripted token re-authentication, and imposes rate limits and chain-completeness restrictions unsuitable for full-chain multi-year backtesting research.

---

## ADR-005: Custom Vectorized Walk-Forward Backtesting Engine over Off-the-Shelf Packages

**Status:** Accepted

**Context:**
The backtest must simulate delta-neutral short straddle/strangle rebalancing under the exact, non-linear Indian statutory cost schedule (STT, NSE turnover fee, SEBI charges, GST, stamp duty, tick slippage), while strictly guaranteeing no look-ahead bias during walk-forward rebalancing. Off-the-shelf backtesting frameworks are designed primarily around US equities/futures event loops.

**Decision:**
Build a **custom vectorized walk-forward backtesting engine** in `src/backtest.py` rather than adopting an existing backtesting package.

**Structural Justification:**
- **Full auditable control over cost application** — Indian options have non-linear, asymmetric statutory costs (e.g., STT differs for sale vs. exercise; SEBI charges are per-crore-of-turnover) that generic frameworks do not model natively; a custom engine can apply these exactly and transparently at every rebalance event.
- **No look-ahead bias by construction** — a hand-rolled walk-forward loop enforces, at each step, that only information available as of `date <= t` is used, which is easier to verify by direct code inspection than to audit inside a third-party event-loop abstraction.
- **Avoids unnecessary complexity** — Backtrader and Zipline are built around tick/bar event loops optimized for long-only equity/futures strategies and have poor native support for options chain rolling, multi-leg delta-neutral rebalancing, or Indian market microstructure.

**Alternatives Evaluated:**

- **Backtrader** — Rejected. Event-loop architecture is bloated for vectorized options research; poor native support for options rolling and Indian-market-specific fee schedules.

- **VectorBT** — Rejected. Strong vectorized primitives for equities but lacks native multi-leg options/delta-neutral position modeling and Indian derivatives cost conventions out of the box.

- **Zipline** — Rejected. Designed for US equities with a fixed calendar/commission model; retrofitting Indian options statutory costs and NSE expiry conventions would require extensive forking of internals.

---

## ADR-006: Hermetic Python 3.11 Virtual Environment and PyArrow Supply-Chain Pinning

**Status:** Accepted

**Context:**
The test suite failed during stop-hook execution because bare `pytest` resolved to an unpinned system Python interpreter lacking runtime dependencies (`duckdb`, `pyarrow`). Additionally, DuckDB's zero-copy Arrow memory bridge (`query_df()`) requires an explicit Arrow engine.

**Decision:**
Enforce a strict Python 3.11 virtual environment (`.venv`) for all testing, stop hooks, and CI execution. Pin `pyarrow==19.0.1` and `duckdb==1.2.0` with exact `==` specifiers per [[SECURITY.md]] §2.4.

**Structural Justification:**
- **Eliminates host-interpreter pollution** — the interpreter and every dependency version are resolved from `.venv`, not from whichever Python happens to be first on `PATH`, so test outcomes do not depend on machine-local state (see [[SRS.md]] NFR-02 Determinism, NFR-04 Portability).
- **Ensures C-extension wheel compatibility** — pinning to Python 3.11 avoids source compilation on newer, unverified runtimes for which `duckdb`, `pyarrow`, `numpy`, and `scipy` may not yet publish binary wheels.
- **Guarantees zero-copy buffer transfers** — `pyarrow` is a hard runtime requirement of `query_df()`, which calls `.arrow()`; without it the Arrow→Pandas path raises at import rather than degrading, so it belongs in `requirements.txt` as a first-class pin, not an implicit transitive dependency.

**Alternatives Evaluated:**

- **System Python execution** — Rejected. Flaky and breaks across development environments; the interpreter and its installed package set vary per machine, which is precisely the failure that motivated this ADR.

- **Open range dependencies (`>=`)** — Rejected. Violates the dependency-pinning contract in [[SECURITY.md]] §2.4 and introduces silent breaking changes across minor releases, since a fresh `pip install` can resolve to an unreviewed version.
