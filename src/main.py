"""
Run the full pipeline with one command:

    python src/main.py

Steps: validate -> revenue benchmarking -> segment P&L & scorecard -> VIX regression
-> scenario forecast -> Tableau CSVs -> Excel report -> charts.

If an input file is missing or a critical validation check fails, the pipeline
stops with a clear message and a non-zero exit code. Nothing is ever filled in.
"""
import sys
from pathlib import Path

import config
from benchmarking import compute_benchmarking, trading_revenue
from charts import make_all_charts
from export_excel import build_workbook
from forecast import assumptions_table, build_forecast
from regression import load_vix_quarterly, plain_english_summary, run_regression
from segment_pnl import build_scorecard, compute_segment_kpis
from validate import DataMissingError, ValidationError, run_validation


def save_tableau_extracts(outputs: dict, processed_dir: Path) -> None:
    """Tidy long-format CSVs (one row per observation) for the Tableau dashboard."""
    processed_dir.mkdir(parents=True, exist_ok=True)
    for name, df in outputs.items():
        path = processed_dir / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"  wrote {path.name} ({len(df)} rows)")


def run(revenue_path=None, pnl_path=None, vix_path=None, processed_dir=None,
        excel_path=None, charts_dir=None, banks=None, quarters=None) -> dict:
    """Run every step. Paths / banks / quarters can be overridden (used by the end-to-end test)."""
    banks = banks or config.BANKS
    quarters = quarters or config.QUARTERS

    print("[1/7] Validating input data ...")
    revenue, pnl = run_validation(revenue_path, pnl_path, banks=banks, quarters=quarters)

    print("\n[2/7] Revenue benchmarking (peer-set share, YoY growth, mix) ...")
    bench = compute_benchmarking(revenue)

    print("[3/7] Segment P&L KPIs and scorecard ...")
    kpis = compute_segment_kpis(pnl)
    scorecard = build_scorecard(kpis, quarters)

    print("[4/7] VIX regression ...")
    vix_q = load_vix_quarterly(Path(vix_path) if vix_path else None, quarters)
    trading = trading_revenue(revenue)
    reg = run_regression(trading, vix_q)
    print(plain_english_summary(reg))

    print("\n[5/7] Scenario forecast (illustrative) ...")
    forecast = build_forecast(trading, vix_q, reg.beta)
    assumptions = assumptions_table(forecast, quarters)

    print("[6/7] Writing Tableau extracts and Excel report ...")
    save_tableau_extracts({
        "revenue_benchmarking": bench,
        "segment_kpis": kpis,
        "kpi_scorecard": scorecard,
        "forecast_scenarios": forecast,
        "vix_quarterly": vix_q,
    }, Path(processed_dir or config.PROCESSED_DIR))
    excel_path = Path(excel_path or config.EXCEL_REPORT)
    build_workbook(revenue, pnl, bench, kpis, scorecard, reg, forecast, assumptions, excel_path)
    print(f"  wrote {excel_path.name}")

    print("[7/7] Charts ...")
    for p in make_all_charts(bench, kpis, forecast, Path(charts_dir or config.CHARTS_DIR), banks):
        print(f"  wrote {p.name}")

    print("\nDone.")
    return {"bench": bench, "kpis": kpis, "scorecard": scorecard, "regression": reg, "forecast": forecast}


def main() -> int:
    try:
        run()
    except (DataMissingError, ValidationError) as e:
        print(f"\nPIPELINE STOPPED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
