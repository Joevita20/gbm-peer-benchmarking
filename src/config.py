"""
Central configuration for the investment banking & trading peer benchmarking project.

Everything that is a "choice" (which banks, which quarters, file locations,
validation thresholds) lives here, so the analysis modules contain only logic.
"""
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
CHARTS_DIR = OUTPUTS_DIR / "charts"

# Blank templates (committed, never edited) and the filled-in files the pipeline reads.
REVENUE_TEMPLATE = RAW_DIR / "peer_revenue_template.csv"
PNL_TEMPLATE = RAW_DIR / "segment_pnl_template.csv"
REVENUE_FILE = RAW_DIR / "peer_revenue.csv"
PNL_FILE = RAW_DIR / "segment_pnl.csv"
VIX_FILE = RAW_DIR / "vix.csv"  # FRED series VIXCLS, daily

EXCEL_REPORT = OUTPUTS_DIR / "ib_trading_peer_benchmarking.xlsx"

# ---------------------------------------------------------------------------
# Peer set and time window
# ---------------------------------------------------------------------------
BANKS = ["GS", "MS", "JPM", "BAC", "C"]

BANK_NAMES = {
    "GS": "Goldman Sachs",
    "MS": "Morgan Stanley",
    "JPM": "JPMorgan Chase",
    "BAC": "Bank of America",
    "C": "Citigroup",
}

BUSINESS_LINES = ["FICC", "Equities", "IB_Fees"]
TRADING_LINES = ["FICC", "Equities"]  # "trading revenue" = FICC + Equities

# Latest quarter all five banks have reported. Update this each earnings season.
LATEST_QUARTER = "2026Q3"
N_QUARTERS = 8


def quarter_list(latest: str = LATEST_QUARTER, n: int = N_QUARTERS) -> list[str]:
    """Return the last `n` quarters ending at `latest`, oldest first, e.g. ['2024Q4', ..., '2026Q3']."""
    end = pd.Period(latest, freq="Q")
    return [str(end - i) for i in range(n - 1, -1, -1)]


QUARTERS = quarter_list()

# ---------------------------------------------------------------------------
# Validation thresholds
# ---------------------------------------------------------------------------
# Pre-tax income should be close to net revenue - operating expenses. Banks also
# deduct provisions for credit losses (and sometimes other items), so we allow a
# gap of up to this share of net revenue before flagging it for review.
PRETAX_TOLERANCE_PCT_OF_REVENUE = 0.05

# Quarter-over-quarter moves bigger than this are flagged "review manually"
# (likely a typo or a reporting change, but could be genuine).
QOQ_REVIEW_THRESHOLD = 0.40
