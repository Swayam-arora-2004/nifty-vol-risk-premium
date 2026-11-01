# Technical & Domain Specifications — `nifty-vol-risk-premium`

---

## 1. Technical Specifications (The Systems Layer)

| Category | Component | Version |
|---|---|---|
| Runtime Environment | Python | 3.11+ |
| Database / Analytical Engine | DuckDB | 0.10+ |
| Database / Analytical Engine | Apache Parquet | Snappy compression |
| Numerical & Statistical Computing | NumPy | 1.26+ |
| Numerical & Statistical Computing | Pandas | 2.2+ |
| Numerical & Statistical Computing | SciPy | 1.12+ |
| Numerical & Statistical Computing | statsmodels | 0.14+ |
| Numerical & Statistical Computing | arch | 6.3+ |
| Testing & Code Quality | pytest | 8.0+ |
| Testing & Code Quality | ruff (lint + format) | latest pinned |
| Testing & Code Quality | GitHub Actions CI | `.github/workflows/ci.yml` |
| Visualization & Dashboard | Streamlit | 1.32+ |
| Visualization & Dashboard | Plotly | 5.18+ |

All versions declared here are **minimums**; exact pinned versions are recorded in `requirements.txt` and `pyproject.toml` per [[SECURITY.md]] §2.4 (Dependency Pinning).

---

## 2. Non-Technical / Financial Domain Specifications

### 2.1 Asset Universe
NIFTY 50 Index Options, traded on the National Stock Exchange of India (NSE).

### 2.2 Time Horizon
January 2021 to present. This window deliberately captures:
- The post-COVID market recovery regime
- The 2022 global rate-hike cycle and its volatility transmission to Indian markets
- 2024 election-cycle and Union Budget volatility shocks

### 2.3 Moneyness Slicing
The primary analytical band for VRP signal construction is **Near-The-Money (NTM)**: `0.95 <= K/S <= 1.05`. (Note: this is narrower than the broader liquidity filter band of `0.90 <= K/S <= 1.10` defined in [[SRS.md]] FR-02, which governs data retention; the NTM band governs which retained contracts feed the ATM IV signal specifically.)

### 2.4 Indian Statutory Transaction Cost Schedule

| Cost Component | Rate / Amount | Applies To |
|---|---|---|
| Brokerage | Flat ₹20 | Per executed leg |
| Securities Transaction Tax (STT) | 0.0625% | Option turnover on sale |
| Securities Transaction Tax (STT) | 0.125% | Settlement value on exercised contracts |
| Exchange Turnover Charges (NSE) | 0.05% | Derivatives turnover |
| SEBI Turnover Charges | ₹10 per crore | Total turnover |
| Stamp Duty | 0.003% | Buy-side turnover |
| Slippage Buffer | Configurable 0.5 tick (₹0.05 – ₹0.25) | Per leg, per rebalance |

This schedule is implemented in `src/costs.py` and is the authoritative reference for all cost calculations in `src/backtest.py` (see [[MAJOR_DECISIONS.md]] ADR-005 and [[SRS.md]] FR-06).
