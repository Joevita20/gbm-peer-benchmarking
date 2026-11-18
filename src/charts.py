"""
Static PNG charts for the README / slides, saved to outputs/charts/.

Design rules followed:
  * one fixed colour per bank in every chart (colour = identity, never rank)
  * thin 2px lines, visible markers, faint grid, no dual axes
  * a legend whenever there is more than one series; stacked bars carry % labels
"""
import matplotlib

matplotlib.use("Agg")  # render to files, no display needed
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter, PercentFormatter

import config

# Fixed categorical order (validated colour-blind-safe palette, slots 1-5)
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6", "#008300", "#e34948"]
LINE_COLORS = {"FICC": "#2a78d6", "Equities": "#eb6834", "IB_Fees": "#1baf7a"}
SCENARIO_COLORS = {"Downside": "#a9c9f0", "Base": "#2a78d6", "Upside": "#174a8c"}  # one hue, light -> dark
TEXT, TEXT_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def bank_colors(banks) -> dict:
    return {b: SERIES_COLORS[i % len(SERIES_COLORS)] for i, b in enumerate(banks)}


def _style(ax, title: str, ylabel: str | None = None) -> None:
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=TEXT)
    if ylabel:
        ax.set_ylabel(ylabel, color=TEXT_2)
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=TEXT_2, length=0)


def _save(fig, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def market_share_chart(bench: pd.DataFrame, path, banks) -> None:
    """Small multiples: one panel per business line, peer-set share over time per bank."""
    colors = bank_colors(banks)
    lines = [l for l in config.BUSINESS_LINES if l in bench["business_line"].unique()]
    fig, axes = plt.subplots(1, len(lines), figsize=(5 * len(lines), 4.2), sharey=True, facecolor=SURFACE)
    for ax, line in zip(axes, lines):
        d = bench[bench["business_line"] == line]
        for bank in banks:
            s = d[d["bank"] == bank].sort_values("quarter")
            ax.plot(s["quarter"], s["peer_set_share"], color=colors[bank], linewidth=2,
                    marker="o", markersize=5, label=bank)
        _style(ax, line.replace("_", " "))
        ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        ax.tick_params(axis="x", rotation=45)
    axes[0].set_ylabel("Peer-set share", color=TEXT_2)
    axes[-1].legend(frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    fig.suptitle("Peer-set market share by business line (share of 5-bank peer set, not industry)",
                 x=0.01, ha="left", fontsize=13, fontweight="bold", color=TEXT)
    fig.tight_layout()
    _save(fig, path)


def revenue_mix_chart(bench: pd.DataFrame, path, banks) -> None:
    """100% stacked bar of each bank's revenue mix in the latest quarter."""
    latest = bench["quarter"].max()
    d = bench[bench["quarter"] == latest].pivot(index="bank", columns="business_line", values="revenue_mix")
    d = d.reindex(banks)
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor=SURFACE)
    bottom = pd.Series(0.0, index=d.index)
    for line in [l for l in config.BUSINESS_LINES if l in d.columns]:
        bars = ax.bar(d.index, d[line], bottom=bottom, color=LINE_COLORS[line], width=0.6,
                      edgecolor=SURFACE, linewidth=2, label=line.replace("_", " "))
        for rect, value in zip(bars, d[line]):
            if pd.notna(value) and value >= 0.08:  # label only segments big enough to read
                ax.text(rect.get_x() + rect.get_width() / 2, rect.get_y() + rect.get_height() / 2,
                        f"{value:.0%}", ha="center", va="center", fontsize=9, color=TEXT)
        bottom = bottom + d[line].fillna(0)
    _style(ax, f"Revenue mix, {latest} (FICC + Equities + IB fees = 100%)")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    _save(fig, path)


def efficiency_chart(kpis: pd.DataFrame, path, banks) -> None:
    """Efficiency ratio (opex / net revenue) over time - lower is better."""
    colors = bank_colors(banks)
    fig, ax = plt.subplots(figsize=(9, 4.5), facecolor=SURFACE)
    for bank in banks:
        s = kpis[kpis["bank"] == bank].sort_values("quarter")
        ax.plot(s["quarter"], s["efficiency_ratio"], color=colors[bank], linewidth=2,
                marker="o", markersize=5, label=bank)
    _style(ax, "Segment efficiency ratio (operating expenses / net revenue; lower is better)")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    _save(fig, path)


def forecast_chart(forecast: pd.DataFrame, path, banks) -> None:
    """Grouped bars: FY trading revenue by bank under each scenario ($bn)."""
    fy = forecast["forecast_fiscal_year"].iloc[0]
    scenarios = [s for s in ["Downside", "Base", "Upside"] if s in forecast["scenario"].unique()]
    width = 0.8 / len(scenarios)
    fig, ax = plt.subplots(figsize=(9, 4.5), facecolor=SURFACE)
    x = range(len(banks))
    for i, scen in enumerate(scenarios):
        d = forecast[forecast["scenario"] == scen].set_index("bank").reindex(banks)
        ax.bar([p + (i - (len(scenarios) - 1) / 2) * width for p in x],
               d["forecast_fy_trading_revenue_usd_mm"] / 1000, width=width,
               color=SCENARIO_COLORS.get(scen, TEXT_2), edgecolor=SURFACE, linewidth=2, label=scen)
    ax.set_xticks(list(x), banks)
    _style(ax, f"ILLUSTRATIVE {fy} trading revenue (FICC + Equities) by VIX scenario")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}bn"))
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    _save(fig, path)


def make_all_charts(bench, kpis, forecast, charts_dir=None, banks=None) -> list:
    charts_dir = charts_dir or config.CHARTS_DIR
    banks = banks or config.BANKS
    paths = {
        "peer_set_market_share.png": lambda p: market_share_chart(bench, p, banks),
        "revenue_mix_latest_quarter.png": lambda p: revenue_mix_chart(bench, p, banks),
        "efficiency_ratio.png": lambda p: efficiency_chart(kpis, p, banks),
        "forecast_scenarios.png": lambda p: forecast_chart(forecast, p, banks),
    }
    written = []
    for name, draw in paths.items():
        draw(charts_dir / name)
        written.append(charts_dir / name)
    return written
