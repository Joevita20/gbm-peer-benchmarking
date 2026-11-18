"""End-to-end smoke test: the full pipeline runs on FAKE TEST DATA in a temp folder."""
import pytest
from openpyxl import load_workbook

import main
from conftest import FAKE_BANKS, FAKE_QUARTERS, make_fake_pnl, make_fake_revenue
from validate import ValidationError

EXPECTED_SHEETS = ["Executive Summary", "Market Share", "YoY Growth", "Revenue Mix", "Segment P&L",
                   "KPI Scorecard", "Forecast Scenarios", "Assumptions", "Data Sources"]


def _write_inputs(tmp_path, revenue=None):
    rev, pnl = tmp_path / "peer_revenue.csv", tmp_path / "segment_pnl.csv"
    (revenue if revenue is not None else make_fake_revenue()).to_csv(rev, index=False)
    make_fake_pnl().to_csv(pnl, index=False)
    return rev, pnl


def _run(tmp_path, rev, pnl, vix):
    return main.run(revenue_path=rev, pnl_path=pnl, vix_path=vix,
                    processed_dir=tmp_path / "processed", excel_path=tmp_path / "report.xlsx",
                    charts_dir=tmp_path / "charts", banks=FAKE_BANKS, quarters=FAKE_QUARTERS)


def test_full_pipeline_produces_all_outputs(tmp_path, fake_vix_csv):
    rev, pnl = _write_inputs(tmp_path)
    _run(tmp_path, rev, pnl, fake_vix_csv)

    assert load_workbook(tmp_path / "report.xlsx").sheetnames == EXPECTED_SHEETS
    for name in ["revenue_benchmarking", "segment_kpis", "kpi_scorecard", "forecast_scenarios", "vix_quarterly"]:
        assert (tmp_path / "processed" / f"{name}.csv").exists()
    assert len(list((tmp_path / "charts").glob("*.png"))) == 4


def test_pipeline_stops_on_missing_value(tmp_path, fake_vix_csv):
    revenue = make_fake_revenue()
    revenue.loc[0, "revenue_usd_mm"] = None
    rev, pnl = _write_inputs(tmp_path, revenue)
    with pytest.raises(ValidationError):
        _run(tmp_path, rev, pnl, fake_vix_csv)
    assert not (tmp_path / "report.xlsx").exists()  # nothing produced from incomplete data
