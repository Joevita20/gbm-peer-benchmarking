"""
Data validation for the hand-entered bank figures.

Two levels of finding:
  CRITICAL -> the pipeline stops (missing / duplicate / negative / unsourced data).
  REVIEW   -> printed for a human to check, but the pipeline continues
              (pre-tax mismatch vs. revenue - expenses, QoQ swings > 40%).

Nothing here ever fills or fixes a value - it only reports.
"""
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

import config

REVENUE_KEYS = ["bank", "quarter", "business_line"]
PNL_KEYS = ["bank", "quarter", "segment_name"]
PNL_REQUIRED_NUMBERS = ["net_revenue_usd_mm", "operating_expenses_usd_mm", "pretax_income_usd_mm"]

MAX_ROWS_SHOWN = 8  # keep the printed report readable when many rows fail


class DataMissingError(Exception):
    """Raised when an input file does not exist yet."""


class ValidationError(Exception):
    """Raised when critical validation checks fail."""


@dataclass
class ValidationReport:
    name: str
    critical: list[str] = field(default_factory=list)
    review: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.critical

    def add_rows(self, bucket: list[str], title: str, rows: pd.DataFrame, cols: list[str]) -> None:
        """Add one finding that lists the offending rows (truncated)."""
        if rows.empty:
            return
        lines = [f"{title} ({len(rows)} rows)"]
        for _, r in rows.head(MAX_ROWS_SHOWN).iterrows():
            lines.append("      - " + ", ".join(f"{c}={r[c]}" for c in cols))
        if len(rows) > MAX_ROWS_SHOWN:
            lines.append(f"      ... and {len(rows) - MAX_ROWS_SHOWN} more")
        bucket.append("\n".join(lines))

    def print(self) -> None:
        status = "PASSED" if self.passed else "FAILED"
        print(f"\n=== Validation: {self.name} -> {status} "
              f"({len(self.critical)} critical, {len(self.review)} review) ===")
        for msg in self.critical:
            print(f"  [CRITICAL] {msg}")
        for msg in self.review:
            print(f"  [REVIEW MANUALLY] {msg}")
        for msg in self.info:
            print(f"  [INFO] {msg}")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_csv(path: Path, template: Path) -> pd.DataFrame:
    """Read an input CSV, or fail with instructions if the user hasn't created it yet."""
    if not Path(path).exists():
        raise DataMissingError(
            f"Missing input file: {path}\n"
            f"  -> Copy the template ({Path(template).name}) to {Path(path).name} "
            f"and enter figures from the bank's earnings materials."
        )
    return pd.read_csv(path)


def to_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Convert numeric columns (tolerating '1,234' style thousands separators)."""
    out = df.copy()
    for c in cols:
        out[c] = pd.to_numeric(out[c].astype(str).str.replace(",", "").str.strip()
                               .replace({"": None, "nan": None}), errors="coerce")
    return out


# ---------------------------------------------------------------------------
# Shared checks
# ---------------------------------------------------------------------------
def _check_columns(df, required, report) -> bool:
    missing = [c for c in required if c not in df.columns]
    if missing:
        report.critical.append(f"Missing columns: {missing}")
    return not missing


def _check_keys(df, keys, banks, quarters, report) -> None:
    bad_bank = df[~df["bank"].isin(banks)]
    report.add_rows(report.critical, f"Unknown bank (expected one of {banks})", bad_bank, keys)

    bad_q = df[~df["quarter"].astype(str).isin(quarters)]
    report.add_rows(report.critical, "Quarter outside expected window / wrong format (use e.g. 2025Q3)",
                    bad_q, keys)

    dups = df[df.duplicated(subset=keys, keep=False)]
    report.add_rows(report.critical, "Duplicate rows", dups, keys)


def _check_non_numeric(raw, clean, cols, keys, report) -> None:
    for c in cols:
        bad = raw[raw[c].notna() & clean[c].isna()]
        report.add_rows(report.critical, f"Non-numeric value in {c}", bad, keys + [c])


def _check_missing(clean, cols, keys, report) -> None:
    for c in cols:
        report.add_rows(report.critical, f"Missing value in {c}", clean[clean[c].isna()], keys)


def _check_source(df, keys, report) -> None:
    no_src = df[df["source_url"].isna() | (df["source_url"].astype(str).str.strip() == "")]
    report.add_rows(report.critical, "Missing source_url", no_src, keys)


def qoq_changes(df: pd.DataFrame, group_cols: list[str], value_col: str) -> pd.DataFrame:
    """Quarter-over-quarter % change of value_col within each group (sorted by quarter)."""
    d = df.copy()
    d["_period"] = pd.PeriodIndex(d["quarter"].astype(str), freq="Q")
    d = d.sort_values(group_cols + ["_period"])
    d["prev_value"] = d.groupby(group_cols)[value_col].shift(1)
    d["prev_period"] = d.groupby(group_cols)["_period"].shift(1)
    # only compare truly consecutive quarters
    consecutive = d["prev_period"] == d["_period"] - 1
    d["qoq_change"] = (d[value_col] / d["prev_value"] - 1).where(consecutive)
    return d.drop(columns=["_period", "prev_period"])


def _check_qoq(clean, group_cols, value_col, threshold, report) -> None:
    d = qoq_changes(clean, group_cols, value_col)
    big = d[d["qoq_change"].abs() > threshold].copy()
    big["qoq_change"] = big["qoq_change"].map(lambda x: f"{x:+.0%}")
    report.add_rows(report.review, f"{value_col} moved more than {threshold:.0%} QoQ",
                    big, group_cols + ["quarter", "prev_value", value_col, "qoq_change"])


# ---------------------------------------------------------------------------
# Dataset-specific validation
# ---------------------------------------------------------------------------
def validate_revenue(raw: pd.DataFrame, banks=None, quarters=None, business_lines=None,
                     qoq_threshold=None) -> tuple[ValidationReport, pd.DataFrame]:
    """Validate peer_revenue data. Returns (report, cleaned dataframe)."""
    banks = banks or config.BANKS
    quarters = quarters or config.QUARTERS
    business_lines = business_lines or config.BUSINESS_LINES
    qoq_threshold = qoq_threshold or config.QOQ_REVIEW_THRESHOLD
    report = ValidationReport("peer revenue")

    required = REVENUE_KEYS + ["revenue_usd_mm", "source_url"]
    if not _check_columns(raw, required, report):
        return report, raw

    raw = raw.copy()
    raw["quarter"] = raw["quarter"].astype(str).str.strip().str.upper()
    clean = to_numeric(raw, ["revenue_usd_mm"])

    _check_keys(clean, REVENUE_KEYS, banks, quarters, report)
    report.add_rows(report.critical, f"Unknown business_line (expected {business_lines})",
                    clean[~clean["business_line"].isin(business_lines)], REVENUE_KEYS)

    # completeness: every bank x quarter x business line must have a row
    expected = pd.MultiIndex.from_product([banks, quarters, business_lines], names=REVENUE_KEYS)
    present = pd.MultiIndex.from_frame(clean[REVENUE_KEYS])
    absent = expected.difference(present).to_frame(index=False)
    report.add_rows(report.critical, "Expected row not present", absent, REVENUE_KEYS)

    _check_non_numeric(raw, clean, ["revenue_usd_mm"], REVENUE_KEYS, report)
    _check_missing(clean, ["revenue_usd_mm"], REVENUE_KEYS, report)
    report.add_rows(report.critical, "Negative revenue", clean[clean["revenue_usd_mm"] < 0],
                    REVENUE_KEYS + ["revenue_usd_mm"])
    _check_source(clean, REVENUE_KEYS, report)

    if report.passed:  # swings only make sense once the numbers are complete
        _check_qoq(clean, ["bank", "business_line"], "revenue_usd_mm", qoq_threshold, report)
    return report, clean


def validate_pnl(raw: pd.DataFrame, banks=None, quarters=None, tolerance=None,
                 qoq_threshold=None) -> tuple[ValidationReport, pd.DataFrame]:
    """Validate segment_pnl data. Returns (report, cleaned dataframe)."""
    banks = banks or config.BANKS
    quarters = quarters or config.QUARTERS
    tolerance = config.PRETAX_TOLERANCE_PCT_OF_REVENUE if tolerance is None else tolerance
    qoq_threshold = qoq_threshold or config.QOQ_REVIEW_THRESHOLD
    report = ValidationReport("segment P&L")

    required = PNL_KEYS + PNL_REQUIRED_NUMBERS + ["source_url"]
    if not _check_columns(raw, required, report):
        return report, raw

    raw = raw.copy()
    raw["quarter"] = raw["quarter"].astype(str).str.strip().str.upper()
    if "reported_roe_pct" not in raw.columns:
        raw["reported_roe_pct"] = None
    numeric = PNL_REQUIRED_NUMBERS + ["reported_roe_pct"]
    clean = to_numeric(raw, numeric)

    _check_keys(clean, PNL_KEYS, banks, quarters, report)

    # completeness: every bank x quarter needs at least one segment row
    expected = pd.MultiIndex.from_product([banks, quarters], names=["bank", "quarter"])
    present = pd.MultiIndex.from_frame(clean[["bank", "quarter"]].drop_duplicates())
    absent = expected.difference(present).to_frame(index=False)
    report.add_rows(report.critical, "No segment row for bank/quarter", absent, ["bank", "quarter"])

    _check_non_numeric(raw, clean, numeric, PNL_KEYS, report)
    _check_missing(clean, PNL_REQUIRED_NUMBERS, PNL_KEYS, report)
    report.add_rows(report.critical, "Negative net revenue",
                    clean[clean["net_revenue_usd_mm"] < 0], PNL_KEYS + ["net_revenue_usd_mm"])
    report.add_rows(report.critical, "Negative operating expenses",
                    clean[clean["operating_expenses_usd_mm"] < 0], PNL_KEYS + ["operating_expenses_usd_mm"])
    _check_source(clean, PNL_KEYS, report)

    # Pre-tax income ~= net revenue - operating expenses. The gap is usually the
    # provision for credit losses, so it is a REVIEW flag, not critical.
    implied = clean["net_revenue_usd_mm"] - clean["operating_expenses_usd_mm"]
    gap = clean["pretax_income_usd_mm"] - implied
    mismatch = clean[(gap.abs() > tolerance * clean["net_revenue_usd_mm"].abs()) & gap.notna()].copy()
    mismatch["implied_pretax"] = implied[mismatch.index].round(1)
    mismatch["gap"] = gap[mismatch.index].round(1)
    report.add_rows(report.review,
                    f"Pre-tax income differs from revenue - expenses by > {tolerance:.0%} of revenue "
                    "(check provisions / other items)",
                    mismatch, PNL_KEYS + ["pretax_income_usd_mm", "implied_pretax", "gap"])

    roe_missing = clean["reported_roe_pct"].isna().sum()
    if roe_missing:
        report.info.append(f"reported_roe_pct blank for {roe_missing} rows (optional - not all banks report segment ROE)")

    if report.passed:
        for col in ["net_revenue_usd_mm", "operating_expenses_usd_mm"]:
            _check_qoq(clean, ["bank", "segment_name"], col, qoq_threshold, report)
    return report, clean


def run_validation(revenue_path=None, pnl_path=None, banks=None, quarters=None):
    """Load both inputs, print the reports, and raise if any critical check failed."""
    revenue_raw = load_csv(revenue_path or config.REVENUE_FILE, config.REVENUE_TEMPLATE)
    pnl_raw = load_csv(pnl_path or config.PNL_FILE, config.PNL_TEMPLATE)

    rev_report, revenue = validate_revenue(revenue_raw, banks=banks, quarters=quarters)
    pnl_report, pnl = validate_pnl(pnl_raw, banks=banks, quarters=quarters)
    rev_report.print()
    pnl_report.print()

    if not (rev_report.passed and pnl_report.passed):
        raise ValidationError("Critical validation checks failed - fix the input data and re-run.")
    return revenue, pnl


if __name__ == "__main__":
    run_validation()
