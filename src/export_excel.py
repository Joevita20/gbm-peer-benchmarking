"""
Build the formatted Excel report: outputs/gbm_peer_benchmarking.xlsx

Sheets: Executive Summary, Market Share, YoY Growth, Revenue Mix, Segment P&L,
KPI Scorecard, Forecast Scenarios, Assumptions, Data Sources.

Number formats are chosen from the (friendly) column name, so every sheet is
formatted consistently: "($mm)" -> #,##0 ; share / growth / ratio -> 0.0% ;
"(bps)" -> +0 bps ; "ROE (%)" -> 0.0 ; rank -> 0.
"""
import math

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import config
from benchmarking import pivot_metric

FMT_USD = "#,##0"
FMT_PCT = "0.0%"
FMT_BPS = '+#,##0" bps";-#,##0" bps";0" bps"'
FMT_NUM1 = "0.0"
FMT_NUM2 = "0.00"
FMT_INT = "0"

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14)
NOTE_FONT = Font(italic=True, color="595959")

# Raw column name -> label shown in Excel (units in brackets drive the number format)
FRIENDLY = {
    "bank": "Bank", "bank_name": "Bank name", "quarter": "Quarter", "business_line": "Business line",
    "segments": "Segment(s)", "period": "Period", "scenario": "Scenario",
    "revenue_usd_mm": "Revenue ($mm)", "revenue_usd_mm_prior_year": "Revenue prior year ($mm)",
    "yoy_growth": "YoY growth (%)", "peer_set_total_usd_mm": "Peer-set total ($mm)",
    "peer_set_share": "Peer-set share (%)", "peer_set_share_prior_year": "Peer-set share prior year (%)",
    "peer_set_share_change_bps": "Peer-set share change YoY (bps)",
    "bank_total_usd_mm": "Bank total, 3 lines ($mm)", "revenue_mix": "Revenue mix (%)",
    "net_revenue_usd_mm": "Net revenue ($mm)", "operating_expenses_usd_mm": "Operating expenses ($mm)",
    "pretax_income_usd_mm": "Pre-tax income ($mm)", "efficiency_ratio": "Efficiency ratio (%)",
    "pretax_margin": "Pre-tax margin (%)", "revenue_yoy_growth": "Revenue YoY growth (%)",
    "expense_yoy_growth": "Expense YoY growth (%)", "operating_leverage": "Operating leverage (% pts)",
    "reported_roe_pct": "Reported ROE (%)", "average_rank": "Average rank", "overall_rank": "Overall rank",
    "rank_efficiency_ratio": "Rank: efficiency", "rank_pretax_margin": "Rank: pre-tax margin",
    "rank_operating_leverage": "Rank: operating leverage", "rank_revenue_yoy_growth": "Rank: revenue growth",
    "rank_reported_roe_pct": "Rank: ROE",
    "forecast_fiscal_year": "Fiscal year", "scenario_vix": "Scenario VIX", "trailing_avg_vix": "Trailing avg VIX",
    "vix_beta_usd_mm": "VIX beta ($mm per pt)", "run_rate_quarterly_usd_mm": "Quarterly run-rate ($mm)",
    "trailing_4q_actual_usd_mm": "Trailing 4Q actual ($mm)",
    "forecast_fy_trading_revenue_usd_mm": "FY trading revenue forecast ($mm)",
    "change_vs_trailing_4q": "Change vs trailing 4Q (%)",
}


def format_for(header: str) -> str | None:
    """Pick a number format from a friendly column header."""
    h = str(header)
    if "(bps)" in h:
        return FMT_BPS
    if "ROE (%)" in h:
        return FMT_NUM1           # ROE is entered as a percent number, e.g. 14.2
    if "($mm" in h:
        return FMT_USD
    if "(%" in h:
        return FMT_PCT
    if "VIX" in h:
        return FMT_NUM2
    if "rank" in h.lower():
        return FMT_NUM1 if "Average" in h else FMT_INT
    return None


def _clean(value):
    """openpyxl can't write NaN; leave missing values as blank cells (never filled)."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, pd.Period):
        return str(value)
    return value


def write_table(ws, df: pd.DataFrame, start_row: int, default_fmt: str | None = None) -> int:
    """Write df with a styled header at start_row. Returns the next free row."""
    df = df.rename(columns=FRIENDLY)
    for j, col in enumerate(df.columns, start=1):
        c = ws.cell(row=start_row, column=j, value=str(col))
        c.font, c.fill = HEADER_FONT, HEADER_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for i, row in enumerate(df.itertuples(index=False), start=start_row + 1):
        for j, (col, value) in enumerate(zip(df.columns, row), start=1):
            cell = ws.cell(row=i, column=j, value=_clean(value))
            fmt = format_for(col) or (default_fmt if isinstance(cell.value, (int, float)) else None)
            if fmt:
                cell.number_format = fmt
    return start_row + len(df) + 2


def add_title(ws, title: str, note: str | None = None) -> int:
    ws.cell(row=1, column=1, value=title).font = TITLE_FONT
    if note:
        ws.cell(row=2, column=1, value=note).font = NOTE_FONT
    return 4  # tables start on row 4


def add_subtitle(ws, row: int, text: str) -> int:
    ws.cell(row=row, column=1, value=text).font = Font(bold=True, size=12)
    return row + 1


def finish_sheet(ws, freeze: str | None = "B5") -> None:
    """Set column widths from content and freeze the header row / first column."""
    for col_cells in ws.columns:
        letter = get_column_letter(col_cells[0].column)
        lengths = [len(str(c.value)) for c in col_cells[3:] if c.value is not None]  # skip title rows
        ws.column_dimensions[letter].width = min(max([10, *lengths]) + 2, 45)
    if freeze:
        ws.freeze_panes = freeze


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------
def executive_summary(bench, kpis, scorecard, reg, forecast) -> pd.DataFrame:
    latest = bench["quarter"].max()
    b = bench[bench["quarter"] == latest]
    share = b.pivot(index="bank", columns="business_line", values="peer_set_share")
    share = share[[l for l in config.BUSINESS_LINES if l in share.columns]]  # FICC, Equities, IB fees
    share.columns = [f"{c.replace('_', ' ')} peer-set share (%)" for c in share.columns]

    trading = (b[b["business_line"].isin(config.TRADING_LINES)]
               .groupby("bank")[["revenue_usd_mm", "revenue_usd_mm_prior_year"]].sum(min_count=1))
    share["Trading revenue, FICC + Equities ($mm)"] = trading["revenue_usd_mm"]
    share["Trading revenue YoY (%)"] = trading["revenue_usd_mm"] / trading["revenue_usd_mm_prior_year"] - 1

    k = kpis[kpis["quarter"] == latest].set_index("bank")
    share["Efficiency ratio (%)"] = k["efficiency_ratio"]
    share["Pre-tax margin (%)"] = k["pretax_margin"]
    share["Reported ROE (%)"] = k["reported_roe_pct"]
    lq = scorecard[scorecard["period"].str.startswith("Latest")].set_index("bank")
    share["KPI overall rank (latest Q)"] = lq["overall_rank"]
    base = forecast[forecast["scenario"] == "Base"].set_index("bank")
    share[f"Base-case {base['forecast_fiscal_year'].iloc[0]} trading forecast ($mm)"] = \
        base["forecast_fy_trading_revenue_usd_mm"]
    return share.reset_index().sort_values("KPI overall rank (latest Q)")


def data_sources(revenue, pnl) -> pd.DataFrame:
    rev = revenue.assign(dataset="Peer revenue", item=revenue["business_line"])
    seg = pnl.assign(dataset="Segment P&L", item=pnl["segment_name"])
    cols = ["dataset", "bank", "quarter", "item", "source_url", "notes"]
    out = pd.concat([rev.reindex(columns=cols), seg.reindex(columns=cols)], ignore_index=True)
    fred = pd.DataFrame([{"dataset": "Market data", "bank": "-", "quarter": "all", "item": "VIX (VIXCLS, daily close)",
                          "source_url": "https://fred.stlouisfed.org/series/VIXCLS",
                          "notes": "Averaged to calendar quarters"}])
    return pd.concat([out, fred], ignore_index=True).rename(columns=str.title)


def build_workbook(revenue, pnl, bench, kpis, scorecard, reg, forecast, assumptions, path=None) -> None:
    path = path or config.EXCEL_REPORT
    latest = bench["quarter"].max()
    wb = Workbook()

    # 1. Executive Summary
    ws = wb.active
    ws.title = "Executive Summary"
    r = add_title(ws, f"GBM Peer Benchmarking - Executive Summary ({latest})",
                  "Peer set: GS, MS, JPM, BAC, C. Share = share of this 5-bank peer set, not total industry. "
                  "Segments are not perfectly comparable across banks (see README).")
    r = write_table(ws, executive_summary(bench, kpis, scorecard, reg, forecast), r)
    r = add_subtitle(ws, r, "Volatility sensitivity (illustrative, small sample)")
    ws.cell(row=r, column=1, value=(
        f"A 1-pt higher average VIX is associated with ${reg.beta:,.0f}mm change in quarterly trading revenue per bank "
        f"(p = {reg.p_value:.3f}, n = {reg.n_obs}, {reg.n_quarters} distinct VIX quarters)."))
    finish_sheet(ws, freeze="B5")

    # 2. Market Share (+ bps change)
    ws = wb.create_sheet("Market Share")
    r = add_title(ws, "Peer-set market share by business line", "Bank revenue / sum of 5 peers' revenue for that quarter and line")
    r = write_table(ws, pivot_metric(bench, "peer_set_share"), r, default_fmt=FMT_PCT)
    r = add_subtitle(ws, r, "Change in peer-set share vs. same quarter last year (bps)")
    write_table(ws, pivot_metric(bench, "peer_set_share_change_bps"), r, default_fmt=FMT_BPS)
    finish_sheet(ws, freeze="C5")

    # 3. YoY Growth
    ws = wb.create_sheet("YoY Growth")
    r = add_title(ws, "Revenue growth vs. same quarter last year", "Blank = no prior-year quarter in the dataset")
    write_table(ws, pivot_metric(bench, "yoy_growth"), r, default_fmt=FMT_PCT)
    finish_sheet(ws, freeze="C5")

    # 4. Revenue Mix (+ underlying $mm)
    ws = wb.create_sheet("Revenue Mix")
    r = add_title(ws, "Revenue mix: share of each bank's FICC + Equities + IB fees", None)
    r = write_table(ws, pivot_metric(bench, "revenue_mix"), r, default_fmt=FMT_PCT)
    r = add_subtitle(ws, r, "Reported revenue ($mm)")
    write_table(ws, pivot_metric(bench, "revenue_usd_mm"), r, default_fmt=FMT_USD)
    finish_sheet(ws, freeze="C5")

    # 5. Segment P&L
    ws = wb.create_sheet("Segment P&L")
    r = add_title(ws, "Markets / banking segment P&L and KPIs",
                  "BAC and C sum two reported segments; their ROE is blank because segment ROEs cannot be added.")
    write_table(ws, kpis, r)
    finish_sheet(ws, freeze="D5")

    # 6. KPI Scorecard
    ws = wb.create_sheet("KPI Scorecard")
    r = add_title(ws, "KPI scorecard (1 = best)",
                  "Lower efficiency ratio is better; higher margin, operating leverage, growth and ROE are better. "
                  "Overall = average of available ranks.")
    write_table(ws, scorecard, r)
    finish_sheet(ws, freeze="C5")

    # 7. Forecast Scenarios
    ws = wb.create_sheet("Forecast Scenarios")
    r = add_title(ws, f"ILLUSTRATIVE planning model: {forecast['forecast_fiscal_year'].iloc[0]} trading revenue (FICC + Equities)",
                  "Not a prediction. Run-rate + VIX sensitivity only - see Assumptions sheet.")
    wide = forecast.pivot(index="bank", columns="scenario", values="forecast_fy_trading_revenue_usd_mm")
    wide = wide[[s for s in ["Downside", "Base", "Upside"] if s in wide.columns]]
    wide.columns = [f"{c} ($mm)" for c in wide.columns]
    r = write_table(ws, wide.reset_index(), r)
    r = add_subtitle(ws, r, "Detail")
    write_table(ws, forecast, r)
    finish_sheet(ws, freeze="B5")

    # 8. Assumptions (+ regression statistics)
    ws = wb.create_sheet("Assumptions")
    r = add_title(ws, "Forecast assumptions and regression statistics", None)
    r = write_table(ws, assumptions.rename(columns=str.title), r)
    r = add_subtitle(ws, r, "Regression: trading revenue ~ avg VIX + bank fixed effects (OLS, HC1 robust SE)")
    reg_table = reg.to_frame().rename(columns=str.title)
    end = write_table(ws, reg_table, r)
    for row in ws.iter_rows(min_row=r + 1, max_row=end - 2, min_col=2, max_col=2):
        if isinstance(row[0].value, float):
            row[0].number_format = "#,##0.000"
    finish_sheet(ws, freeze=None)

    # 9. Data Sources
    ws = wb.create_sheet("Data Sources")
    r = add_title(ws, "Data sources (every figure entered manually from official bank materials)", None)
    write_table(ws, data_sources(revenue, pnl), r)
    finish_sheet(ws, freeze="A5")

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
