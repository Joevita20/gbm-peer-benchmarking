"""
Segment P&L analysis and KPI scorecard.

Per bank and quarter:
  * efficiency_ratio     operating expenses / net revenue        (lower is better)
  * pretax_margin        pre-tax income / net revenue            (higher is better)
  * revenue_yoy_growth / expense_yoy_growth  vs. same quarter last year
  * operating_leverage   revenue growth - expense growth         (positive = "jaws" opening)
  * reported_roe_pct     as reported by the bank, never calculated or estimated

BAC (Global Banking + Global Markets) and C (Banking + Markets) report two
segments, so their rows are summed first. Their ROE is left blank because two
segment ROEs cannot be added together.
"""
import pandas as pd

import config
from benchmarking import add_prior_year, growth


def aggregate_segments(pnl: pd.DataFrame) -> pd.DataFrame:
    """One row per bank and quarter, summing banks that report more than one segment."""
    g = pnl.groupby(["bank", "quarter"])
    agg = g.agg(
        segments=("segment_name", lambda s: " + ".join(sorted(s))),
        segment_count=("segment_name", "count"),
        net_revenue_usd_mm=("net_revenue_usd_mm", "sum"),
        operating_expenses_usd_mm=("operating_expenses_usd_mm", "sum"),
        pretax_income_usd_mm=("pretax_income_usd_mm", "sum"),
        reported_roe_pct=("reported_roe_pct", "first"),
    ).reset_index()
    # ROE only meaningful when a single segment was reported
    agg.loc[agg["segment_count"] > 1, "reported_roe_pct"] = float("nan")
    return agg


def compute_segment_kpis(pnl: pd.DataFrame) -> pd.DataFrame:
    """Tidy bank x quarter KPI table."""
    d = aggregate_segments(pnl)
    d["efficiency_ratio"] = d["operating_expenses_usd_mm"] / d["net_revenue_usd_mm"]
    d["pretax_margin"] = d["pretax_income_usd_mm"] / d["net_revenue_usd_mm"]

    d = add_prior_year(d, ["bank"], ["net_revenue_usd_mm", "operating_expenses_usd_mm"])
    d["revenue_yoy_growth"] = growth(d["net_revenue_usd_mm"], d["net_revenue_usd_mm_prior_year"])
    d["expense_yoy_growth"] = growth(d["operating_expenses_usd_mm"], d["operating_expenses_usd_mm_prior_year"])
    d["operating_leverage"] = d["revenue_yoy_growth"] - d["expense_yoy_growth"]

    d["bank_name"] = d["bank"].map(config.BANK_NAMES)
    cols = [
        "bank", "bank_name", "quarter", "segments",
        "net_revenue_usd_mm", "operating_expenses_usd_mm", "pretax_income_usd_mm",
        "efficiency_ratio", "pretax_margin",
        "revenue_yoy_growth", "expense_yoy_growth", "operating_leverage", "reported_roe_pct",
    ]
    return d[cols].sort_values(["bank", "quarter"]).reset_index(drop=True)


def _trailing_4q(kpis: pd.DataFrame, quarters: list[str]) -> pd.DataFrame:
    """Sum the last 4 quarters (and the 4 before that, for growth) per bank."""
    last4, prior4 = quarters[-4:], quarters[-8:-4]
    sums = ["net_revenue_usd_mm", "operating_expenses_usd_mm", "pretax_income_usd_mm"]

    cur = kpis[kpis["quarter"].isin(last4)].groupby("bank")
    out = cur[sums].sum(min_count=4)  # NaN unless all 4 quarters are present
    # Average ROE only if the bank reported it in all 4 quarters - never partially filled
    out["reported_roe_pct"] = cur["reported_roe_pct"].apply(lambda s: s.mean() if s.notna().sum() == 4 else float("nan"))

    prev = kpis[kpis["quarter"].isin(prior4)].groupby("bank")[sums[:2]].sum(min_count=4) if len(prior4) == 4 else None
    out["efficiency_ratio"] = out["operating_expenses_usd_mm"] / out["net_revenue_usd_mm"]
    out["pretax_margin"] = out["pretax_income_usd_mm"] / out["net_revenue_usd_mm"]
    if prev is not None:
        out["revenue_yoy_growth"] = growth(out["net_revenue_usd_mm"], prev["net_revenue_usd_mm"])
        out["expense_yoy_growth"] = growth(out["operating_expenses_usd_mm"], prev["operating_expenses_usd_mm"])
    else:
        out["revenue_yoy_growth"] = out["expense_yoy_growth"] = float("nan")
    out["operating_leverage"] = out["revenue_yoy_growth"] - out["expense_yoy_growth"]
    return out.reset_index()


# metric -> True if higher is better
RANKED_METRICS = {
    "efficiency_ratio": False,
    "pretax_margin": True,
    "operating_leverage": True,
    "revenue_yoy_growth": True,
    "reported_roe_pct": True,
}


def rank_banks(df: pd.DataFrame) -> pd.DataFrame:
    """Add rank_<metric> columns (1 = best) and an overall rank = average of available ranks."""
    d = df.copy()
    for metric, higher_better in RANKED_METRICS.items():
        d[f"rank_{metric}"] = d[metric].rank(ascending=not higher_better, method="min")
    rank_cols = [f"rank_{m}" for m in RANKED_METRICS]
    d["average_rank"] = d[rank_cols].mean(axis=1, skipna=True)  # ROE rank skipped where not reported
    d["overall_rank"] = d["average_rank"].rank(method="min")
    return d.sort_values("overall_rank")


def build_scorecard(kpis: pd.DataFrame, quarters: list[str] | None = None) -> pd.DataFrame:
    """KPI scorecard for the latest quarter and trailing 4 quarters, stacked in one table."""
    quarters = quarters or sorted(kpis["quarter"].unique())
    latest = quarters[-1]

    lq = kpis[kpis["quarter"] == latest].copy()
    lq = rank_banks(lq)
    lq.insert(0, "period", f"Latest quarter ({latest})")

    t4 = rank_banks(_trailing_4q(kpis, quarters))
    t4.insert(0, "period", f"Trailing 4Q ({quarters[-4]}-{latest})")

    cols = ["period", "bank", "net_revenue_usd_mm", "operating_expenses_usd_mm", "pretax_income_usd_mm",
            *RANKED_METRICS.keys(), *[f"rank_{m}" for m in RANKED_METRICS], "average_rank", "overall_rank"]
    return pd.concat([lq[cols], t4[cols]], ignore_index=True)
