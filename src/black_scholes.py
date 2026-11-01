"""Black-Scholes pricing and bounded numerical implied-volatility inversion.

Per AI_CONTEXT/MAJOR_DECISIONS.md ADR-002 and AI_CONTEXT/SECURITY.md 2.2: the IV
solver is bracketed on a finite interval and degrades to np.nan rather than
raising on malformed or arbitrage-violating input.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

SIGMA_MIN = 1e-4
SIGMA_MAX = 4.0

_CALL = "CE"
_PUT = "PE"
_VALID_TYPES = (_CALL, _PUT)


def _normalize_option_type(option_type: str) -> str:
    normalized = str(option_type).strip().upper()
    if normalized not in _VALID_TYPES:
        raise ValueError(f"option_type must be one of {_VALID_TYPES}, got {option_type!r}")
    return normalized


def bs_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = _CALL,
) -> float:
    """Undiscounted-dividend European option price under Black-Scholes."""
    opt = _normalize_option_type(option_type)
    S, K, T, r, sigma = float(S), float(K), float(T), float(r), float(sigma)

    if not all(np.isfinite([S, K, T, r, sigma])) or S <= 0.0 or K <= 0.0:
        return np.nan

    discounted_strike = K * np.exp(-r * T) if T > 0.0 else K

    # At or past expiry, and in the zero-vol limit, the price collapses to its
    # deterministic lower bound; both avoid the sigma*sqrt(T) division below.
    if T <= 0.0:
        return max(S - K, 0.0) if opt == _CALL else max(K - S, 0.0)
    if sigma <= 0.0:
        return (
            max(S - discounted_strike, 0.0)
            if opt == _CALL
            else max(discounted_strike - S, 0.0)
        )

    vol_sqrt_t = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t

    if opt == _CALL:
        return S * norm.cdf(d1) - discounted_strike * norm.cdf(d2)
    return discounted_strike * norm.cdf(-d2) - S * norm.cdf(-d1)


def bs_vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """First derivative of option price with respect to volatility."""
    S, K, T, r, sigma = float(S), float(K), float(T), float(r), float(sigma)

    if not all(np.isfinite([S, K, T, r, sigma])) or S <= 0.0 or K <= 0.0:
        return np.nan
    if T <= 0.0 or sigma <= 0.0:
        return 0.0

    vol_sqrt_t = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / vol_sqrt_t
    return S * np.sqrt(T) * norm.pdf(d1)


def implied_volatility(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float = 0.07,
    option_type: str = _CALL,
) -> float:
    """Invert bs_price for sigma on [SIGMA_MIN, SIGMA_MAX], or np.nan on failure."""
    opt = _normalize_option_type(option_type)
    market_price, S, K, T, r = (
        float(market_price),
        float(S),
        float(K),
        float(T),
        float(r),
    )

    if not all(np.isfinite([market_price, S, K, T, r])):
        return np.nan
    if T <= 0.0 or S <= 0.0 or K <= 0.0 or market_price <= 0.0:
        return np.nan

    discounted_strike = K * np.exp(-r * T)

    # No-arbitrage bracket: a price at or below intrinsic, or at or above the
    # asymptotic upper bound, has no sigma in [SIGMA_MIN, SIGMA_MAX] that solves it.
    if opt == _CALL:
        intrinsic, upper_bound = max(S - discounted_strike, 0.0), S
    else:
        intrinsic, upper_bound = max(discounted_strike - S, 0.0), discounted_strike

    if market_price <= intrinsic or market_price >= upper_bound:
        return np.nan

    def objective(sigma: float) -> float:
        return bs_price(S, K, T, r, sigma, opt) - market_price

    try:
        f_lo, f_hi = objective(SIGMA_MIN), objective(SIGMA_MAX)
        if not np.isfinite(f_lo) or not np.isfinite(f_hi) or f_lo * f_hi > 0.0:
            return np.nan
        return float(brentq(objective, SIGMA_MIN, SIGMA_MAX))
    except (ValueError, RuntimeError, FloatingPointError):
        return np.nan
