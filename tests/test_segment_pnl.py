"""Tests for segment KPIs and the scorecard (FAKE TEST DATA only)."""
import pandas as pd
import pytest

from conftest import FAKE_QUARTERS
from segment_pnl import build_scorecard, compute_segment_kpis


def _pnl(rows):
    cols = ["bank", "quarter", "segment_name", "net_revenue_usd_mm", "operating_expenses_usd_mm",
            "pretax_income_usd_mm", "reported_roe_pct"]
    return pd.DataFrame(rows, columns=cols)


def test_efficiency_ratio_margin_and_operating_leverage_by_hand():
    # FAKE TEST DATA
    kpis = compute_segment_kpis(_pnl([
        ("A", "2024Q1", "Seg", 800.0, 500.0, 300.0, 10.0),
        ("A", "2025Q1", "Seg", 1000.0, 600.0, 380.0, 12.0),
    ])).set_index("quarter")
    k = kpis.loc["2025Q1"]
    assert k["efficiency_ratio"] == pytest.approx(0.60)        # 600 / 1000
    assert k["pretax_margin"] == pytest.approx(0.38)           # 380 / 1000
    assert k["revenue_yoy_growth"] == pytest.approx(0.25)      # 1000 / 800 - 1
    assert k["expense_yoy_growth"] == pytest.approx(0.20)      # 600 / 500 - 1
    assert k["operating_leverage"] == pytest.approx(0.05)      # 25% - 20% = +5 pts
    assert k["reported_roe_pct"] == pytest.approx(12.0)        # passed through, not computed


def test_multi_segment_banks_are_summed_and_roe_left_blank():
    kpis = compute_segment_kpis(_pnl([
        ("B", "2025Q1", "Banking", 400.0, 200.0, 190.0, 15.0),
        ("B", "2025Q1", "Markets", 600.0, 400.0, 195.0, 11.0),
    ]))
    k = kpis.iloc[0]
    assert k["net_revenue_usd_mm"] == 1000.0
    assert k["efficiency_ratio"] == pytest.approx(0.60)
    assert pd.isna(k["reported_roe_pct"])  # two ROEs can't be added -> blank, never averaged
    assert k["segments"] == "Banking + Markets"


def test_scorecard_ranks_lower_efficiency_first(fake_pnl):
    kpis = compute_segment_kpis(fake_pnl)
    card = build_scorecard(kpis, FAKE_QUARTERS)
    latest = card[card["period"].str.startswith("Latest")].set_index("bank")
    # FAKE_A has the lowest cost ratio (60% vs 65%) -> rank 1
    assert latest.loc["FAKE_A", "rank_efficiency_ratio"] == 1
    assert set(card["period"].str.split(" ").str[0]) == {"Latest", "Trailing"}


def test_trailing_4q_uses_sums_not_average_of_ratios(fake_pnl):
    kpis = compute_segment_kpis(fake_pnl)
    card = build_scorecard(kpis, FAKE_QUARTERS)
    t4 = card[card["period"].str.startswith("Trailing")].set_index("bank")
    last4 = kpis[kpis["quarter"].isin(FAKE_QUARTERS[-4:]) & (kpis["bank"] == "FAKE_B")]
    expected = last4["operating_expenses_usd_mm"].sum() / last4["net_revenue_usd_mm"].sum()
    assert t4.loc["FAKE_B", "efficiency_ratio"] == pytest.approx(expected)
