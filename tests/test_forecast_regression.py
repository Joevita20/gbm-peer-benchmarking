"""Tests for the VIX loader, regression and scenario forecast math (FAKE TEST DATA only)."""
import pandas as pd
import pytest

from benchmarking import trading_revenue
from conftest import FAKE_QUARTERS, FAKE_TRUE_BETA, FAKE_VIX
from forecast import build_forecast
from regression import load_vix_quarterly, run_regression


def test_forecast_math_by_hand():
    # FAKE TEST DATA: run-rate 1,000/qtr, trailing VIX 20, beta 100 $mm per VIX point
    trading = pd.DataFrame({"bank": ["A"] * 4, "quarter": ["2025Q1", "2025Q2", "2025Q3", "2025Q4"],
                            "trading_revenue_usd_mm": [900.0, 1100.0, 950.0, 1050.0]})
    vix = pd.DataFrame({"quarter": trading["quarter"], "avg_vix": [18.0, 22.0, 19.0, 21.0]})
    f = build_forecast(trading, vix, beta=100.0, base_vix=None,
                       shifts={"Base": 0.0, "Upside": 5.0, "Downside": -5.0}).set_index("scenario")
    assert f.loc["Base", "forecast_fy_trading_revenue_usd_mm"] == pytest.approx(4000)      # 4 x 1,000
    assert f.loc["Upside", "forecast_fy_trading_revenue_usd_mm"] == pytest.approx(6000)    # 4 x (1,000 + 100x5)
    assert f.loc["Downside", "forecast_fy_trading_revenue_usd_mm"] == pytest.approx(2000)  # 4 x (1,000 - 100x5)
    assert f.loc["Base", "change_vs_trailing_4q"] == pytest.approx(0.0)
    assert f.loc["Base", "forecast_fiscal_year"] == "FY2026"


def test_forecast_respects_base_vix_override():
    trading = pd.DataFrame({"bank": ["A"] * 4, "quarter": ["2025Q1", "2025Q2", "2025Q3", "2025Q4"],
                            "trading_revenue_usd_mm": [1000.0] * 4})
    vix = pd.DataFrame({"quarter": trading["quarter"], "avg_vix": [20.0] * 4})
    f = build_forecast(trading, vix, beta=10.0, base_vix=25.0, shifts={"Base": 0.0}).iloc[0]
    assert f["forecast_fy_trading_revenue_usd_mm"] == pytest.approx(4 * (1000 + 10 * 5))


def test_vix_loader_averages_by_quarter_and_drops_fred_missing_marker(fake_vix_csv):
    q = load_vix_quarterly(fake_vix_csv, FAKE_QUARTERS).set_index("quarter")
    for quarter, value in FAKE_VIX.items():
        assert q.loc[quarter, "avg_vix"] == pytest.approx(value)


def test_regression_recovers_known_fake_beta(fake_revenue, fake_vix_csv):
    vix_q = load_vix_quarterly(fake_vix_csv, FAKE_QUARTERS)
    result = run_regression(trading_revenue(fake_revenue), vix_q)
    assert result.n_obs == 3 * 8
    assert result.n_quarters == 8
    # the fake data were generated with a known VIX effect plus a time trend, so beta
    # should land in the right neighbourhood (trend is partly absorbed - hence loose bounds)
    assert result.beta == pytest.approx(FAKE_TRUE_BETA, rel=0.5)
