"""Tests for peer-set market share, YoY growth and revenue mix (FAKE TEST DATA only)."""
import pandas as pd
import pytest

from benchmarking import compute_benchmarking, trading_revenue


def test_peer_set_share_sums_to_100pct(fake_revenue):
    bench = compute_benchmarking(fake_revenue)
    totals = bench.groupby(["quarter", "business_line"])["peer_set_share"].sum()
    assert totals.round(10).eq(1.0).all()


def test_revenue_mix_sums_to_100pct(fake_revenue):
    bench = compute_benchmarking(fake_revenue)
    totals = bench.groupby(["bank", "quarter"])["revenue_mix"].sum()
    assert totals.round(10).eq(1.0).all()


def _two_bank_example():
    # FAKE TEST DATA: hand-checkable numbers
    return pd.DataFrame({
        "bank": ["A", "B", "A", "B"],
        "quarter": ["2024Q1", "2024Q1", "2025Q1", "2025Q1"],
        "business_line": ["FICC"] * 4,
        "revenue_usd_mm": [200.0, 200.0, 300.0, 100.0],
    })


def test_share_yoy_growth_and_bps_by_hand():
    bench = compute_benchmarking(_two_bank_example()).set_index(["bank", "quarter"])
    a = bench.loc[("A", "2025Q1")]
    assert a["peer_set_share"] == pytest.approx(0.75)                # 300 / 400
    assert a["peer_set_share_prior_year"] == pytest.approx(0.50)     # 200 / 400
    assert a["peer_set_share_change_bps"] == pytest.approx(2500)     # +25 pts = 2,500 bps
    assert a["yoy_growth"] == pytest.approx(0.50)                    # 300 / 200 - 1
    b = bench.loc[("B", "2025Q1")]
    assert b["yoy_growth"] == pytest.approx(-0.50)
    assert b["peer_set_share_change_bps"] == pytest.approx(-2500)


def test_yoy_is_blank_not_filled_without_prior_year():
    bench = compute_benchmarking(_two_bank_example())
    first_year = bench[bench["quarter"] == "2024Q1"]
    assert first_year["yoy_growth"].isna().all()
    assert first_year["peer_set_share_change_bps"].isna().all()


def test_yoy_matches_same_quarter_even_with_gaps():
    # 2024Q2-2024Q4 missing: 2025Q1 must still compare against 2024Q1, not the previous row
    df = pd.DataFrame({
        "bank": ["A"] * 3, "business_line": ["FICC"] * 3,
        "quarter": ["2024Q1", "2025Q1", "2025Q2"],
        "revenue_usd_mm": [100.0, 120.0, 130.0],
    })
    bench = compute_benchmarking(df).set_index("quarter")
    assert bench.loc["2025Q1", "yoy_growth"] == pytest.approx(0.20)
    assert pd.isna(bench.loc["2025Q2", "yoy_growth"])  # no 2024Q2 -> blank


def test_trading_revenue_is_ficc_plus_equities(fake_revenue):
    t = trading_revenue(fake_revenue).set_index(["bank", "quarter"])
    raw = fake_revenue.set_index(["bank", "quarter", "business_line"])["revenue_usd_mm"]
    q = fake_revenue["quarter"].iloc[0]
    expected = raw[("FAKE_A", q, "FICC")] + raw[("FAKE_A", q, "Equities")]
    assert t.loc[("FAKE_A", q), "trading_revenue_usd_mm"] == pytest.approx(expected)
