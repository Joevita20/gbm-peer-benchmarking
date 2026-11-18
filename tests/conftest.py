"""
Shared FAKE TEST DATA for the test suite.

!!! Every number in this file is synthetic and exists only to test the math. !!!
Bank names are FAKE_A / FAKE_B / FAKE_C so they can never be mistaken for real
bank figures, and source URLs point to example.com.
"""
import numpy as np
import pandas as pd
import pytest

import config

FAKE_BANKS = ["FAKE_A", "FAKE_B", "FAKE_C"]
FAKE_QUARTERS = config.quarter_list("2026Q3", 8)
FAKE_SOURCE = "https://example.com/FAKE-TEST-DATA"
FAKE_VIX = dict(zip(FAKE_QUARTERS, [15.0, 22.0, 18.0, 16.0, 25.0, 19.0, 17.0, 21.0]))

# Fake base revenue ($mm) per bank and business line
_BASE = {
    "FAKE_A": {"FICC": 3000, "Equities": 2500, "IB_Fees": 1500},
    "FAKE_B": {"FICC": 2000, "Equities": 2000, "IB_Fees": 1000},
    "FAKE_C": {"FICC": 1500, "Equities": 1000, "IB_Fees": 800},
}
FAKE_TRUE_BETA = 40.0  # $mm of combined trading revenue per VIX point (split across FICC/Equities)


def make_fake_revenue() -> pd.DataFrame:
    """Steady growth + a VIX effect on trading lines + small noise. FAKE TEST DATA."""
    rng = np.random.default_rng(0)
    rows = []
    for bank in FAKE_BANKS:
        for i, q in enumerate(FAKE_QUARTERS):
            for line, base in _BASE[bank].items():
                value = base * (1 + 0.02 * i)
                if line in config.TRADING_LINES:
                    value += (FAKE_TRUE_BETA / 2) * FAKE_VIX[q] + rng.normal(0, 10)
                rows.append({"bank": bank, "quarter": q, "business_line": line,
                             "reported_label": "FAKE", "revenue_usd_mm": round(value, 1),
                             "source_url": FAKE_SOURCE, "notes": "FAKE TEST DATA"})
    return pd.DataFrame(rows)


def make_fake_pnl() -> pd.DataFrame:
    """FAKE_C reports two segments to exercise the summing logic. FAKE TEST DATA."""
    rows = []
    for bank in FAKE_BANKS:
        segments = ["Seg X", "Seg Y"] if bank == "FAKE_C" else ["Seg X"]
        for i, q in enumerate(FAKE_QUARTERS):
            for seg in segments:
                rev = 5000 + 100 * i + (500 if bank == "FAKE_A" else 0)
                opex = rev * (0.60 if bank == "FAKE_A" else 0.65)
                pretax = rev - opex - 50  # small provision, within tolerance
                rows.append({"bank": bank, "quarter": q, "segment_name": seg,
                             "net_revenue_usd_mm": rev, "operating_expenses_usd_mm": round(opex, 1),
                             "pretax_income_usd_mm": round(pretax, 1),
                             "reported_roe_pct": 12.0 + i * 0.1 if bank != "FAKE_C" else None,
                             "source_url": FAKE_SOURCE, "notes": "FAKE TEST DATA"})
    return pd.DataFrame(rows)


def make_fake_vix_daily() -> pd.DataFrame:
    """Daily FRED-style VIXCLS file with a constant value per quarter and '.' on a holiday."""
    frames = []
    for q, v in FAKE_VIX.items():
        p = pd.Period(q, freq="Q")
        days = pd.bdate_range(p.start_time, p.end_time)
        frames.append(pd.DataFrame({"observation_date": days.strftime("%Y-%m-%d"), "VIXCLS": v}))
    d = pd.concat(frames, ignore_index=True).astype({"VIXCLS": object})
    d.loc[0, "VIXCLS"] = "."  # FRED's missing-value marker must be dropped, not filled
    return d


@pytest.fixture
def fake_revenue():
    return make_fake_revenue()


@pytest.fixture
def fake_pnl():
    return make_fake_pnl()


@pytest.fixture
def fake_vix_csv(tmp_path):
    path = tmp_path / "vix.csv"
    make_fake_vix_daily().to_csv(path, index=False)
    return path
