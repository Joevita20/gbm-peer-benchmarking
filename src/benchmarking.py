"""
Revenue benchmarking across FICC, Equities and Investment Banking fees.

For every bank / quarter / business line we compute:
  * peer_set_share            bank revenue / sum of the 5 peers' revenue
  * peer_set_share_change_bps change in peer-set share vs. the same quarter last year, in basis points
  * yoy_growth                revenue growth vs. the same quarter last year
  * revenue_mix               business line revenue / bank's total of the 3 lines that quarter

IMPORTANT: "share" here is PEER-SET share - the bank's slice of these five banks
only - not share of the total industry wallet (which would need Coalition /
Dealogic style data including European and boutique competitors).
"""
import pandas as pd

import config


def add_prior_year(df: pd.DataFrame, keys: list[str], value_cols: list[str]) -> pd.DataFrame:
    """
    Attach the same-quarter-last-year value of each column in value_cols as `<col>_prior_year`.
    Uses a merge on (quarter - 4) instead of shift(4), so a missing quarter can
    never cause the wrong periods to be compared.
    """
    d = df.copy()
    d["_period"] = pd.PeriodIndex(d["quarter"].astype(str), freq="Q")
    prior = d[keys + ["_period"] + value_cols].copy()
    prior["_period"] = prior["_period"] + 4  # last year's row lines up with this year's quarter
    prior = prior.rename(columns={c: f"{c}_prior_year" for c in value_cols})
    return d.merge(prior, on=keys + ["_period"], how="left").drop(columns="_period")


def growth(current: pd.Series, prior: pd.Series) -> pd.Series:
    """Simple % growth; NaN where there is no prior value (never filled)."""
    return current / prior - 1


def compute_benchmarking(revenue: pd.DataFrame) -> pd.DataFrame:
    """Return the tidy long-format revenue benchmarking table."""
    d = revenue[["bank", "quarter", "business_line", "revenue_usd_mm"]].copy()

    # Peer-set market share: each bank's slice of the 5-bank total per quarter and line
    d["peer_set_total_usd_mm"] = d.groupby(["quarter", "business_line"])["revenue_usd_mm"].transform("sum")
    d["peer_set_share"] = d["revenue_usd_mm"] / d["peer_set_total_usd_mm"]

    # Revenue mix: what portion of the bank's FICC + Equities + IB fees comes from this line
    d["bank_total_usd_mm"] = d.groupby(["bank", "quarter"])["revenue_usd_mm"].transform("sum")
    d["revenue_mix"] = d["revenue_usd_mm"] / d["bank_total_usd_mm"]

    # Year-over-year comparisons
    d = add_prior_year(d, ["bank", "business_line"], ["revenue_usd_mm", "peer_set_share"])
    d["yoy_growth"] = growth(d["revenue_usd_mm"], d["revenue_usd_mm_prior_year"])
    d["peer_set_share_change_bps"] = (d["peer_set_share"] - d["peer_set_share_prior_year"]) * 10_000

    d["bank_name"] = d["bank"].map(config.BANK_NAMES)
    cols = [
        "bank", "bank_name", "quarter", "business_line",
        "revenue_usd_mm", "revenue_usd_mm_prior_year", "yoy_growth",
        "peer_set_total_usd_mm", "peer_set_share", "peer_set_share_prior_year",
        "peer_set_share_change_bps", "bank_total_usd_mm", "revenue_mix",
    ]
    return d[cols].sort_values(["business_line", "quarter", "bank"]).reset_index(drop=True)


def trading_revenue(revenue: pd.DataFrame) -> pd.DataFrame:
    """Combined FICC + Equities revenue per bank and quarter (used by regression & forecast)."""
    t = revenue[revenue["business_line"].isin(config.TRADING_LINES)]
    out = t.groupby(["bank", "quarter"], as_index=False)["revenue_usd_mm"].sum()
    return out.rename(columns={"revenue_usd_mm": "trading_revenue_usd_mm"})


def pivot_metric(bench: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Wide view for Excel: rows = business line x bank, columns = quarters."""
    return (bench.pivot_table(index=["business_line", "bank"], columns="quarter",
                              values=metric, aggfunc="first")
            .reset_index())
