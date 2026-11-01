import numpy as np
import pytest

from src.black_scholes import (
    SIGMA_MAX,
    SIGMA_MIN,
    bs_price,
    bs_vega,
    implied_volatility,
)

R = 0.07
S0 = 20000.0
T0 = 30.0 / 365.0

MONEYNESS_STRIKES = [
    pytest.param(18000.0, id="itm_call_otm_put"),
    pytest.param(20000.0, id="atm"),
    pytest.param(22000.0, id="otm_call_itm_put"),
]


@pytest.mark.parametrize("K", MONEYNESS_STRIKES)
@pytest.mark.parametrize("sigma", [0.10, 0.18, 0.45])
def test_put_call_parity(K, sigma):
    call = bs_price(S0, K, T0, R, sigma, "CE")
    put = bs_price(S0, K, T0, R, sigma, "PE")
    assert call - put == pytest.approx(S0 - K * np.exp(-R * T0), rel=1e-9, abs=1e-9)


@pytest.mark.parametrize("K", MONEYNESS_STRIKES)
@pytest.mark.parametrize("sigma", [0.08, 0.15, 0.22, 0.60, 1.20])
@pytest.mark.parametrize("option_type", ["CE", "PE"])
def test_iv_inversion_recovers_known_sigma(K, sigma, option_type):
    synthetic_price = bs_price(S0, K, T0, R, sigma, option_type)
    recovered = implied_volatility(synthetic_price, S0, K, T0, R, option_type)
    assert recovered == pytest.approx(sigma, rel=1e-6)


@pytest.mark.parametrize("option_type", ["CE", "PE"])
def test_iv_inversion_round_trips_across_tenors(option_type):
    for dte in (1.0, 7.0, 45.0, 180.0):
        T = dte / 365.0
        price = bs_price(S0, S0, T, R, 0.20, option_type)
        assert implied_volatility(price, S0, S0, T, R, option_type) == pytest.approx(
            0.20, rel=1e-6
        )


def test_vega_is_positive_and_peaks_near_the_money():
    atm_vega = bs_vega(S0, S0, T0, R, 0.20)
    wing_vega = bs_vega(S0, S0 * 1.4, T0, R, 0.20)
    assert atm_vega > 0.0
    assert atm_vega > wing_vega


def test_vega_collapses_at_expiry_and_zero_vol():
    assert bs_vega(S0, S0, 0.0, R, 0.20) == 0.0
    assert bs_vega(S0, S0, -0.01, R, 0.20) == 0.0
    assert bs_vega(S0, S0, T0, R, 0.0) == 0.0


@pytest.mark.parametrize("option_type", ["CE", "PE"])
def test_price_at_expiry_is_intrinsic(option_type):
    expected = 500.0 if option_type == "CE" else 0.0
    assert bs_price(S0, S0 - 500.0, 0.0, R, 0.20, option_type) == pytest.approx(expected)


def test_iv_returns_nan_below_intrinsic():
    K = 18000.0
    intrinsic = S0 - K * np.exp(-R * T0)
    assert np.isnan(implied_volatility(intrinsic * 0.5, S0, K, T0, R, "CE"))
    assert np.isnan(implied_volatility(intrinsic, S0, K, T0, R, "CE"))


def test_iv_returns_nan_above_upper_bound():
    assert np.isnan(implied_volatility(S0 * 1.01, S0, S0, T0, R, "CE"))
    discounted_strike = S0 * np.exp(-R * T0)
    assert np.isnan(
        implied_volatility(discounted_strike * 1.01, S0, S0, T0, R, "PE")
    )


@pytest.mark.parametrize("T", [0.0, -0.01, -1.0])
@pytest.mark.parametrize("option_type", ["CE", "PE"])
def test_iv_returns_nan_for_non_positive_expiry(T, option_type):
    assert np.isnan(implied_volatility(250.0, S0, S0, T, R, option_type))


@pytest.mark.parametrize("market_price", [0.0, -1.0, np.nan, np.inf])
def test_iv_returns_nan_for_degenerate_prices(market_price):
    assert np.isnan(implied_volatility(market_price, S0, S0, T0, R, "CE"))


@pytest.mark.parametrize(
    ("S", "K"),
    [(0.0, S0), (-S0, S0), (S0, 0.0), (S0, -S0)],
)
def test_iv_returns_nan_for_degenerate_spot_or_strike(S, K):
    assert np.isnan(implied_volatility(250.0, S, K, T0, R, "CE"))


def test_iv_outside_solver_bracket_returns_nan_not_exception():
    below = bs_price(S0, S0, T0, R, SIGMA_MIN / 2.0, "CE")
    above = bs_price(S0, S0, T0, R, SIGMA_MAX * 2.0, "CE")
    assert np.isnan(implied_volatility(below, S0, S0, T0, R, "CE"))
    assert np.isnan(implied_volatility(above, S0, S0, T0, R, "CE"))


def test_invalid_option_type_is_rejected():
    with pytest.raises(ValueError):
        bs_price(S0, S0, T0, R, 0.20, "CALL")
    with pytest.raises(ValueError):
        implied_volatility(250.0, S0, S0, T0, R, "X")


def test_option_type_is_case_and_whitespace_tolerant():
    assert bs_price(S0, S0, T0, R, 0.20, " ce ") == pytest.approx(
        bs_price(S0, S0, T0, R, 0.20, "CE")
    )
