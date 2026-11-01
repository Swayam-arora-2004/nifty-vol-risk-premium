# Software Requirements Specification (SRS) — `nifty-vol-risk-premium`

*Formatted per IEEE 830 conventions.*

---

## 1. Introduction

### 1.1 Purpose
This document specifies the functional and non-functional requirements for `nifty-vol-risk-premium`, a quantitative research system that ingests historical NIFTY 50 index options data, computes implied and realized volatility measures, models the Variance Risk Premium (VRP), and backtests a volatility-selling strategy net of statutory Indian exchange transaction costs.

### 1.2 System Scope
The system covers the complete pipeline from raw NSE market data ingestion through econometric modeling to a walk-forward backtest and an interactive Streamlit dashboard. It excludes live order execution, broker connectivity, and real-time (intraday) data processing — the system operates exclusively on end-of-day (EOD) historical data.

### 1.3 Product Perspective
The system is a standalone, self-contained analytical research tool. It depends on no external server-side infrastructure: all storage (DuckDB, Parquet) and compute occurs in-process or within a CI runner / Streamlit Cloud container. It is designed to be reproducible and auditable from source.

### 1.4 User Characteristics
The intended users are:
- **Quantitative researchers** evaluating volatility risk premium strategies on Indian index options, who require transparent, auditable cost modeling and econometric rigor.
- **Hiring panels / technical reviewers** assessing the system as a demonstration of production-grade quantitative engineering practice, who require the codebase and documentation to be legible, correct, and professionally structured without requiring the reviewer to run the system.

---

## 2. Functional Requirements

### FR-01: Data Ingestion & Schema Normalization
The system shall automatically stream and ingest NSE F&O daily bhavcopy archives from January 2021 to the present, along with NIFTY 50 and India VIX EOD closing histories over the same period.
- The ingestion module shall auto-detect the bhavcopy schema family per file and map both:
  - **Legacy headers:** `STRIKE_PR`, `OPTION_TYP`, `EXPIRY_DT`
  - **UDiFF headers:** `StrkPric`, `OptnTp`, `XpryDt`
  into a single normalized internal schema (see [[ARCHITECTURE.md]] §3 Data Contracts).
- Ingestion shall occur via HTTP streaming with in-memory ZIP extraction — no persistent raw archive need be retained on disk as an intermediate step beyond the configured `data/raw/` cache.

### FR-02: Data Cleaning & Liquidity Filtering
The system shall apply the following exclusion filters to all ingested option contracts prior to any downstream calculation:
- `Volume < 500` → excluded
- `Open Interest < 1,000` → excluded
- `Settlement Price <= ₹1.00` → excluded
- `Moneyness` outside `0.90 <= K/S <= 1.10` → excluded

### FR-03: Mathematical Inversion (Implied Volatility Engine)
The system shall compute implied volatility for every retained option contract via numerical Black-Scholes inversion.
- Time to expiry shall be annualized as `T = DTE / 365.0`.
- Inversion shall use Brent's method (`scipy.optimize.brentq`), bounded on the interval `σ ∈ [σ_min = 1e-4, σ_max = 4.0]` (see [[MAJOR_DECISIONS.md]] ADR-002).
- If the option's market price violates the no-arbitrage intrinsic-value boundary condition (i.e., no sign change exists within the bounded bracket), the system shall return `np.nan` for that contract rather than raising an exception.

### FR-04: Realized Volatility Estimation
The system shall compute 30-day forward-looking rolling realized volatility using three estimators, executed via DuckDB SQL window CTEs:
- Close-to-Close standard deviation of log returns (diagnostic baseline)
- Parkinson High-Low range estimator
- Garman-Klass OHLC range estimator
(see [[MAJOR_DECISIONS.md]] ADR-003 for estimator selection rationale.)

### FR-05: Econometric Spread Modeling
The system shall compute, for each trading day `t`:
- **Variance Risk Premium:** `VRP_t = IV_{t, ATM} − RV_{t → t+30}`
- **Augmented Dickey-Fuller (ADF) test** for stationarity of the VRP series
- **GARCH(1,1)** forward conditional volatility forecast, fit via the `arch` library

### FR-06: Walk-Forward Backtesting with Indian Friction
The system shall simulate a walk-forward, delta-neutral short straddle/strangle rebalancing strategy driven by the VRP signal, applying the full Indian statutory transaction cost schedule at every rebalance event:
- STT: 0.0625% on option sale turnover; 0.125% on settlement of exercised intrinsic value
- NSE turnover fee: 0.05%
- SEBI turnover charges: ₹10 per crore
- Flat brokerage: ₹20 per executed leg
- Half-tick slippage buffer per leg
The backtest shall report Sharpe ratio, Sortino ratio, and Maximum Drawdown over the full simulation period.

---

## 3. Non-Functional Requirements

### NFR-01: Performance
DuckDB aggregation queries across the full historical dataset (approximately 1.5 million option records spanning 5 years) shall execute in under 250 milliseconds per query.

### NFR-02: Determinism
The automated test suite (`pytest tests/`) shall execute with 100% deterministic results — no test outcome may depend on wall-clock time, random seed state left unfixed, or network availability at test time.

### NFR-03: Data Integrity
The system shall strictly prohibit forward-looking data leakage at every rebalancing step of the backtest (see [[SECURITY.md]] §2.1 for the enforced technical control).

### NFR-04: Portability
The system shall execute identically across Linux, macOS, and Windows, with zero dependency on an external background daemon or network-resident database server (see [[MAJOR_DECISIONS.md]] ADR-001).
