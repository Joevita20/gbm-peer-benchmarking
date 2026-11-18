"""Tests for the validation checks (FAKE TEST DATA only)."""
import pytest

from conftest import FAKE_BANKS, FAKE_QUARTERS
from validate import DataMissingError, load_csv, validate_pnl, validate_revenue


def _rev(df):
    return validate_revenue(df, banks=FAKE_BANKS, quarters=FAKE_QUARTERS)


def _pnl(df, **kw):
    return validate_pnl(df, banks=FAKE_BANKS, quarters=FAKE_QUARTERS, **kw)


def test_clean_fake_data_passes(fake_revenue, fake_pnl):
    assert _rev(fake_revenue)[0].passed
    assert _pnl(fake_pnl)[0].passed


def test_missing_value_is_critical_and_not_filled(fake_revenue):
    fake_revenue.loc[3, "revenue_usd_mm"] = None
    report, clean = _rev(fake_revenue)
    assert not report.passed
    assert any("Missing value in revenue_usd_mm" in m for m in report.critical)
    assert clean["revenue_usd_mm"].isna().sum() == 1  # still missing - nothing imputed


def test_duplicate_row_is_critical(fake_revenue):
    import pandas as pd
    dup = pd.concat([fake_revenue, fake_revenue.iloc[[0]]], ignore_index=True)
    report, _ = _rev(dup)
    assert any("Duplicate rows" in m for m in report.critical)


def test_negative_revenue_is_critical(fake_revenue):
    fake_revenue.loc[0, "revenue_usd_mm"] = -5
    report, _ = _rev(fake_revenue)
    assert any("Negative revenue" in m for m in report.critical)


def test_missing_source_url_is_critical(fake_pnl):
    fake_pnl.loc[0, "source_url"] = None
    report, _ = _pnl(fake_pnl)
    assert any("Missing source_url" in m for m in report.critical)


def test_absent_row_and_non_numeric_are_critical(fake_revenue):
    fake_revenue = fake_revenue.drop(index=0).reset_index(drop=True)
    fake_revenue["revenue_usd_mm"] = fake_revenue["revenue_usd_mm"].astype(object)
    fake_revenue.loc[0, "revenue_usd_mm"] = "n/a"
    report, _ = _rev(fake_revenue)
    assert any("Expected row not present" in m for m in report.critical)
    assert any("Non-numeric" in m for m in report.critical)


def test_pretax_mismatch_is_review_not_critical(fake_pnl):
    fake_pnl.loc[0, "pretax_income_usd_mm"] = 0.0  # far from revenue - expenses
    report, _ = _pnl(fake_pnl)
    assert report.passed
    assert any("Pre-tax income differs" in m for m in report.review)


def test_large_qoq_change_flagged_for_manual_review(fake_revenue):
    idx = fake_revenue[(fake_revenue["bank"] == "FAKE_A") & (fake_revenue["business_line"] == "IB_Fees")].index[4]
    fake_revenue.loc[idx, "revenue_usd_mm"] *= 2  # +100% QoQ
    report, _ = _rev(fake_revenue)
    assert report.passed
    assert any("QoQ" in m and "FAKE_A" in m for m in report.review)


def test_missing_input_file_fails_clearly(tmp_path):
    with pytest.raises(DataMissingError, match="Copy the template"):
        load_csv(tmp_path / "peer_revenue.csv", tmp_path / "peer_revenue_template.csv")
