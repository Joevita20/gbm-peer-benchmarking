"""
Generate the blank data-entry templates in data/raw/.

The templates are pre-filled with one row per bank / quarter / business line
(or segment) and the label each bank uses in its own reporting. ALL numeric
columns are left EMPTY on purpose: every figure is entered by hand from the
bank's earnings release or financial supplement, with its source URL.

Usage:
    python src/make_templates.py            # writes the two *_template.csv files
Then copy each template to peer_revenue.csv / segment_pnl.csv and fill it in.

Labels were verified against each bank's filings (see README section 3). Re-check
them whenever a bank reorganises its segments.
"""
import pandas as pd

import config

# How each bank labels the three business lines in its earnings materials.
# (label, needs_verification)
REPORTED_LABELS = {
    "GS": {
        "FICC": ("FICC", False),
        "Equities": ("Equities", False),
        "IB_Fees": ("Investment banking fees", False),
    },
    "MS": {
        # MS lists "Fixed income"/"Equity" twice: use the sales & trading lines, not underwriting.
        "FICC": ("Fixed income", False),
        "Equities": ("Equity", False),
        # MS reports Investment banking *revenue* (advisory + underwriting), not a "fees" line.
        "IB_Fees": ("Investment banking", False),
    },
    "JPM": {
        "FICC": ("Fixed Income Markets", False),
        "Equities": ("Equity Markets", False),
        # CIB income-statement line (gross), not the "Investment Banking" revenue-by-business line.
        "IB_Fees": ("Investment banking fees", False),
    },
    "BAC": {
        # Reported basis incl. net DVA (BAC also shows an ex-DVA, non-GAAP figure).
        "FICC": ("FICC (Fixed income, currencies and commodities)", False),
        "Equities": ("Equities", False),
        # Total Corporation IB fees including self-led deals (gross); split across two segments.
        "IB_Fees": ("Total Corporation investment banking fees", False),
    },
    "C": {
        "FICC": ("Fixed Income Markets", False),
        "Equities": ("Equity Markets", False),
        # Banking segment fee line; not the broader "Investment banking revenues" used from 2Q26.
        "IB_Fees": ("Investment banking fees", False),
    },
}

# The reporting segment(s) that hold each bank's markets + banking businesses.
# BAC and C report these as two separate segments; the pipeline sums them.
# (segment_name, needs_verification)
SEGMENTS = {
    "GS": [("Global Banking & Markets", False)],
    "MS": [("Institutional Securities", False)],
    "JPM": [("Commercial & Investment Bank", False)],
    "BAC": [("Global Banking", False), ("Global Markets", False)],
    "C": [("Banking", False), ("Markets", False)],
}

REVENUE_COLUMNS = [
    "bank", "quarter", "business_line", "reported_label",
    "revenue_usd_mm", "source_url", "notes",
]
PNL_COLUMNS = [
    "bank", "quarter", "segment_name",
    "net_revenue_usd_mm", "operating_expenses_usd_mm", "pretax_income_usd_mm",
    "reported_roe_pct", "source_url", "notes",
]


def verify_note(needs_check: bool) -> str:
    return "VERIFY label against source" if needs_check else ""


def build_revenue_template() -> pd.DataFrame:
    rows = []
    for bank in config.BANKS:
        for quarter in config.QUARTERS:
            for line in config.BUSINESS_LINES:
                label, check = REPORTED_LABELS[bank][line]
                rows.append({
                    "bank": bank, "quarter": quarter, "business_line": line,
                    "reported_label": label, "revenue_usd_mm": None,
                    "source_url": None, "notes": verify_note(check),
                })
    return pd.DataFrame(rows, columns=REVENUE_COLUMNS)


def build_pnl_template() -> pd.DataFrame:
    rows = []
    for bank in config.BANKS:
        for quarter in config.QUARTERS:
            for segment, check in SEGMENTS[bank]:
                rows.append({
                    "bank": bank, "quarter": quarter, "segment_name": segment,
                    "net_revenue_usd_mm": None, "operating_expenses_usd_mm": None,
                    "pretax_income_usd_mm": None, "reported_roe_pct": None,
                    "source_url": None, "notes": verify_note(check),
                })
    return pd.DataFrame(rows, columns=PNL_COLUMNS)


def main() -> None:
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    revenue = build_revenue_template()
    pnl = build_pnl_template()
    revenue.to_csv(config.REVENUE_TEMPLATE, index=False)
    pnl.to_csv(config.PNL_TEMPLATE, index=False)
    print(f"Wrote {len(revenue)} rows -> {config.REVENUE_TEMPLATE.relative_to(config.PROJECT_ROOT)}")
    print(f"Wrote {len(pnl)} rows -> {config.PNL_TEMPLATE.relative_to(config.PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
