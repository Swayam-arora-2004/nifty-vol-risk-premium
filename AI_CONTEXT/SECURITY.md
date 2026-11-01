# Security & Data Integrity Protocol — `nifty-vol-risk-premium`

This document defines the mandatory security, secret-handling, and anti-hallucination/anti-defect protocols for all code contributed to this repository, whether written by a human or an AI coding assistant.

---

## 1. Zero-Secret Ingestion Guardrails

### 1.1 Credential Isolation
- All configuration values that could vary by environment or that are sensitive (API base URLs, optional auth tokens, local data directory overrides) **must** be loaded via `python-dotenv` from a local `.env` file.
- `.env.example` in the repository root documents every expected variable name with a placeholder value. It must never contain a real secret.
- Application code must read configuration exclusively through environment variables (`os.environ` / `os.getenv`), never hardcoded literals.

### 1.2 Pre-Commit Exclusion (`.gitignore`)
The following patterns **must** be present in `.gitignore` and are never to be removed without explicit security review:
```
.env
*.duckdb
*.parquet
data/raw/
data/processed/
credentials*
*.key
*.pem
```
Rationale: `.duckdb` and `.parquet` files can contain full market datasets that are large, environment-specific, and should be regenerated from source rather than versioned; `.env` and credential files must never reach version control under any circumstance.

### 1.3 Pre-Push Review
Before any `git add` of a broad pattern (`git add .`, `git add -A`), run `git status` and visually inspect the file list. If a file with an innocuous name is staged that could plausibly contain environment-specific paths, tokens, or dataset dumps, its contents must be checked before committing.

---

## 2. Defenses Against AI-Generated Code Vulnerabilities & Flaws

### 2.1 Elimination of Look-Ahead Bias (Temporal Leakage)
This is the single most critical correctness guarantee in a financial backtesting system, and AI-assisted code generation is particularly prone to violating it silently.

- **Rule:** Every rolling metric, volatility scaler, GARCH fit, or feature computed for use at timestamp `t` must be computed using **only** data where `date <= t`.
- **Banned pattern:** Global feature scalers or statistics computed once over the entire dataset and reused across all backtest steps — e.g., `df['vol'].mean()` or `df['vol'].std()` computed globally and then applied to every row of the backtest — are **strictly banned**. Any normalization, standardization, or scaling step must be recomputed at each walk-forward step using only the trailing window of data available as of that step.
- **Enforcement:** Code review must explicitly check every `.rolling()`, `.expanding()`, GARCH `.fit()`, and ADF test call site to confirm the window boundary respects `date <= t`. Unit tests in `tests/test_backtest.py` must include at least one explicit test that perturbs future data and asserts the backtest output at time `t` is unchanged (a "future-blindness" test).

### 2.2 Numerical Boundary Safety
- All options-pricing and volatility formulas must guard against zero-division (e.g., `T → 0` as expiry approaches) and negative arguments to `sqrt()` or `log()`.
- The Black-Scholes IV solver (`src/black_scholes.py`) must define a **finite, bounded search interval** (`σ ∈ [1e-4, 4.0]`, per [[ADR-002]]) and must **never raise an unhandled exception** on a malformed or intrinsic-value-violating market price — it must catch the solver failure and return `np.nan`.
- No solver, estimator, or statistical test in `src/` may terminate the process on a single bad data point; all must degrade gracefully to `np.nan` and allow downstream aggregation to skip/report missing values.

### 2.3 DuckDB Injection Prevention
- **Mandatory:** All DuckDB queries that incorporate any externally-derived or user-influenced value must use parameterized binding: `conn.execute(sql, [params])`.
- **Preferred alternative:** Where possible, register a Pandas/Arrow DataFrame directly as a virtual table via `conn.register("table_name", df)` and reference it in SQL, avoiding string interpolation entirely.
- **Banned pattern:** Python f-string or `.format()` interpolation of any variable value directly into a SQL string (e.g., `f"SELECT * FROM t WHERE date = '{date_var}'"`) is strictly prohibited, even for values that appear to be internally generated, since this pattern is how injection vulnerabilities and subtle quoting bugs are introduced.

### 2.4 Dependency Pinning
- All PyPI dependencies declared in `requirements.txt` and `pyproject.toml` must be **pinned to exact, verified versions** (`==x.y.z`), not floating ranges (`>=`, `^`, `~=`).
- Rationale: floating version ranges create a supply-chain attack surface where a compromised or malicious package release could be silently pulled into CI or a contributor's environment. Version bumps must be a deliberate, reviewed change, not an automatic side effect of a fresh `pip install`.
- Dependency updates must be reviewed individually in a dedicated PR, not bundled silently into feature changes.
