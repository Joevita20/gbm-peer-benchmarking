"""
Illustrative scenario forecast of next fiscal year's trading revenue (FICC + Equities).

THIS IS A PLANNING MODEL, NOT A PREDICTION. It answers: "if volatility next year
looks like X, and each bank otherwise keeps its recent run-rate, what would
trading revenue look like?"

Method, per bank:
    run_rate_q     = average quarterly trading revenue over the trailing 4 quarters
    trailing_vix   = average VIX over those same 4 quarters
    scenario_vix   = BASE_VIX (default: trailing_vix) + scenario shift
    quarterly_fcst = run_rate_q + beta * (scenario_vix - trailing_vix)
    FY forecast    = 4 * quarterly_fcst

beta comes from the bank fixed-effects regression in regression.py and is the
same for all banks (a $mm-per-VIX-point sensitivity).
"""
import pandas as pd

# ---------------------------------------------------------------------------
# EDITABLE SCENARIO ASSUMPTIONS
# ---------------------------------------------------------------------------
BASE_VIX = None            # None = use the trailing 4-quarter average VIX; or set a number, e.g. 18.0
SCENARIO_VIX_SHIFT = {     # points added to the base VIX in each scenario
    "Base": 0.0,
    "Upside": +5.0,        # higher volatility -> more client hedging / repositioning
    "Downside": -5.0,      # calmer markets -> lower trading activity
}
RUN_RATE_QUARTERS = 4      # quarters used for the run-rate and trailing VIX
QUARTERS_PER_YEAR = 4
# ---------------------------------------------------------------------------


def build_forecast(trading: pd.DataFrame, vix_q: pd.DataFrame, beta: float,
                   base_vix: float | None = BASE_VIX,
                   shifts: dict[str, float] | None = None,
                   run_rate_quarters: int = RUN_RATE_QUARTERS) -> pd.DataFrame:
    """Return one row per bank x scenario with the FY trading revenue forecast."""
    shifts = shifts or SCENARIO_VIX_SHIFT
    quarters = sorted(trading["quarter"].unique())
    window = quarters[-run_rate_quarters:]
    fiscal_year = pd.Period(quarters[-1], freq="Q").year + 1

    trailing_vix = vix_q.loc[vix_q["quarter"].isin(window), "avg_vix"].mean()
    base = trailing_vix if base_vix is None else base_vix

    recent = trading[trading["quarter"].isin(window)]
    run_rate = recent.groupby("bank")["trading_revenue_usd_mm"].mean()
    trailing_total = recent.groupby("bank")["trading_revenue_usd_mm"].sum()

    rows = []
    for bank in run_rate.index:
        for scenario, shift in shifts.items():
            scenario_vix = base + shift
            quarterly = run_rate[bank] + beta * (scenario_vix - trailing_vix)
            annual = QUARTERS_PER_YEAR * quarterly
            rows.append({
                "bank": bank,
                "scenario": scenario,
                "forecast_fiscal_year": f"FY{fiscal_year}",
                "scenario_vix": scenario_vix,
                "trailing_avg_vix": trailing_vix,
                "vix_beta_usd_mm": beta,
                "run_rate_quarterly_usd_mm": run_rate[bank],
                "trailing_4q_actual_usd_mm": trailing_total[bank],
                "forecast_fy_trading_revenue_usd_mm": annual,
                "change_vs_trailing_4q": annual / trailing_total[bank] - 1,
            })
    order = {s: i for i, s in enumerate(shifts)}
    out = pd.DataFrame(rows)
    return out.sort_values(["bank", "scenario"], key=lambda c: c.map(order) if c.name == "scenario" else c) \
              .reset_index(drop=True)


def assumptions_table(forecast: pd.DataFrame, quarters: list[str]) -> pd.DataFrame:
    """Human-readable list of every assumption, for the Excel 'Assumptions' sheet."""
    window = quarters[-RUN_RATE_QUARTERS:]
    trailing_vix = forecast["trailing_avg_vix"].iloc[0]
    beta = forecast["vix_beta_usd_mm"].iloc[0]
    rows = [
        ("Model type", "Illustrative planning model - NOT a prediction"),
        ("Forecast period", forecast["forecast_fiscal_year"].iloc[0] + " (next full fiscal year; all 5 banks use a calendar fiscal year)"),
        ("Trading revenue definition", "FICC + Equities net revenue as reported by each bank ($mm)"),
        ("Run-rate window", f"{window[0]}-{window[-1]} ({RUN_RATE_QUARTERS} quarters, simple average)"),
        ("Trailing average VIX", f"{trailing_vix:.2f}"),
        ("Base VIX", "Trailing average VIX" if BASE_VIX is None else f"{BASE_VIX:.2f} (user override)"),
        *[(f"{s} scenario VIX shift", f"{v:+.1f} points") for s, v in SCENARIO_VIX_SHIFT.items()],
        ("VIX sensitivity (beta)", f"${beta:,.1f}mm per VIX point per bank-quarter (bank fixed-effects OLS)"),
        ("Formula", "FY = 4 x [run-rate + beta x (scenario VIX - trailing VIX)]"),
        ("Not modelled", "Market share shifts, rates/FX volatility, financing balances, strategic changes, FX translation"),
        ("Peer-set share", "Market share is share of the 5-bank peer set only, not of the total industry wallet"),
    ]
    return pd.DataFrame(rows, columns=["assumption", "value"])
