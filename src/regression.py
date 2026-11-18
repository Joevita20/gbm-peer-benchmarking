"""
Does market volatility explain trading revenue?

Model (OLS with bank fixed effects):
    trading_revenue[bank, q] = alpha[bank] + beta * avg_VIX[q] + error

  * trading_revenue = FICC + Equities, $mm, per bank per quarter
  * alpha[bank]     = a separate intercept per bank (absorbs the fact that JPM is
                      structurally bigger than C, etc.), so beta is estimated from
                      how each bank's revenue moves *over time* with VIX
  * beta            = $mm change in a bank's quarterly trading revenue per
                      1-point change in average quarterly VIX

Standard errors are heteroskedasticity-robust (HC1) because residual noise is
naturally larger for bigger banks.

Data: FRED series VIXCLS (daily close), downloaded by the user to data/raw/vix.csv.
"""
from dataclasses import dataclass

import pandas as pd
import statsmodels.formula.api as smf

import config
from validate import DataMissingError, ValidationError

MIN_DAYS_PER_QUARTER = 55  # ~63 trading days in a quarter; fewer suggests a partial download


def load_vix_quarterly(path=None, quarters=None) -> pd.DataFrame:
    """Read FRED VIXCLS daily data and average it by calendar quarter."""
    path = path or config.VIX_FILE
    quarters = quarters or config.QUARTERS
    if not path.exists():
        raise DataMissingError(
            f"Missing {path}\n  -> Download series VIXCLS from https://fred.stlouisfed.org/series/VIXCLS "
            f"(Download > CSV) covering {quarters[0]}-{quarters[-1]} and save it as data/raw/vix.csv."
        )
    raw = pd.read_csv(path)
    date_col = raw.columns[0]  # FRED uses 'observation_date' (newer) or 'DATE' (older)
    if "VIXCLS" not in raw.columns:
        raise ValidationError(f"{path.name} must contain a VIXCLS column (found {list(raw.columns)})")

    d = pd.DataFrame({
        "date": pd.to_datetime(raw[date_col]),
        "vix": pd.to_numeric(raw["VIXCLS"], errors="coerce"),  # FRED marks holidays as '.' or blank
    }).dropna(subset=["vix"])  # dropping market holidays, not filling them
    d["quarter"] = d["date"].dt.to_period("Q").astype(str)

    q = d.groupby("quarter").agg(avg_vix=("vix", "mean"), trading_days=("vix", "count")).reset_index()
    q = q[q["quarter"].isin(quarters)]

    missing = sorted(set(quarters) - set(q["quarter"]))
    if missing:
        raise ValidationError(f"VIX data missing for quarters: {missing}. Re-download a longer date range.")
    partial = q[q["trading_days"] < MIN_DAYS_PER_QUARTER]
    for _, r in partial.iterrows():
        print(f"  [REVIEW MANUALLY] VIX {r['quarter']} has only {r['trading_days']} trading days - partial quarter?")
    return q.reset_index(drop=True)


@dataclass
class RegressionResult:
    beta: float            # $mm per VIX point, per bank per quarter
    std_error: float
    p_value: float
    ci_low: float
    ci_high: float
    r_squared: float
    n_obs: int
    n_quarters: int
    model: object          # full statsmodels result, for anyone who wants .summary()

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([
            ("VIX coefficient ($mm per VIX point, per bank-quarter)", self.beta),
            ("Robust std. error (HC1)", self.std_error),
            ("p-value", self.p_value),
            ("95% CI low", self.ci_low),
            ("95% CI high", self.ci_high),
            ("R-squared (incl. bank fixed effects)", self.r_squared),
            ("Observations (bank-quarters)", self.n_obs),
            ("Distinct quarters (distinct VIX values)", self.n_quarters),
        ], columns=["statistic", "value"])


def run_regression(trading: pd.DataFrame, vix_q: pd.DataFrame) -> RegressionResult:
    """Fit trading revenue on average VIX with bank fixed effects."""
    data = trading.merge(vix_q[["quarter", "avg_vix"]], on="quarter", how="inner")
    model = smf.ols("trading_revenue_usd_mm ~ avg_vix + C(bank)", data=data).fit(cov_type="HC1")
    ci = model.conf_int().loc["avg_vix"]
    return RegressionResult(
        beta=model.params["avg_vix"],
        std_error=model.bse["avg_vix"],
        p_value=model.pvalues["avg_vix"],
        ci_low=ci[0], ci_high=ci[1],
        r_squared=model.rsquared,
        n_obs=int(model.nobs),
        n_quarters=data["quarter"].nunique(),
        model=model,
    )


def plain_english_summary(r: RegressionResult) -> str:
    direction = "higher" if r.beta > 0 else "lower"
    significance = (
        "statistically significant at the 5% level" if r.p_value < 0.05
        else "NOT statistically significant at the 5% level"
    )
    return "\n".join([
        "\n=== Regression: trading revenue (FICC + Equities) vs. average quarterly VIX ===",
        f"  A 1-point higher average VIX is associated with ${abs(r.beta):,.0f}mm {direction} quarterly",
        f"  trading revenue per bank (95% CI: ${r.ci_low:,.0f}mm to ${r.ci_high:,.0f}mm), after controlling",
        f"  for each bank's typical revenue level (bank fixed effects).",
        f"  The relationship is {significance} (p = {r.p_value:.3f}).",
        f"  R-squared = {r.r_squared:.2f}, but most of that comes from the bank fixed effects (bank size).",
        "",
        f"  CAUTION - ILLUSTRATIVE ONLY: the sample is small ({r.n_obs} bank-quarters) and VIX takes only",
        f"  {r.n_quarters} distinct values (one per quarter, shared by all banks). Trading revenue also depends",
        "  on rates/FX volatility, client activity, financing balances and market share, which this",
        "  one-variable model ignores. Treat the coefficient as a directional sensitivity, not a forecast.",
    ])


if __name__ == "__main__":
    from benchmarking import trading_revenue
    from validate import run_validation

    revenue, _ = run_validation()
    result = run_regression(trading_revenue(revenue), load_vix_quarterly())
    print(plain_english_summary(result))
