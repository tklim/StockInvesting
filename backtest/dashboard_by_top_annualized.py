"""Build a fund dashboard ranked by TOP ANNUALIZED RETURN.

Companion to `dashboard_by_excess_annualized.py`, answering a different question.
The excess dashboard asks "where did the strategy beat the market most?". This one
asks "what is the best annualized return available on this ticker at all, however it
was achieved?" — so each run's score is:

    top_annualized = max(adaptive_annualized_return_pct, buy_hold_annualized_return_pct)

whichever is higher. A badge on every card states which of the two produced the
number, because a top return earned by buy & hold says nothing about the strategy.

Slice length is deliberately ignored: runs on `AAPL.csv`, `AAPL-3Y.csv` and
`AAPL-4Y.csv` all compete as one ticker, and the winning card names the slice and
config that won. Grouping uses `fund_group_from_label`, so it behaves the same
before and after the `fund_label` backfill.

Reads `outputs/tunings/backtest_run_history.csv` directly and ranks it here, so the
dashboard is always current with the history. No backtest is re-run; the chart each
winning run already produced is re-used.

Usage:
    python dashboard_by_top_annualized.py                       # all tickers
    python dashboard_by_top_annualized.py --top-funds 5
    python dashboard_by_top_annualized.py --basis strategy      # rank by strategy only
    python dashboard_by_top_annualized.py --basis buy-hold      # rank by buy & hold only
    python dashboard_by_top_annualized.py --basis buy-hold --derive-buyhold-horizons 20y 10y
    python dashboard_by_top_annualized.py --per-slice           # do not pool -NY slices
"""

import argparse
import html
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from common import TUNINGS_DIR, fund_group_from_label
from dashboard_render import (
    DashboardSpec,
    format_pct,
    render_html,
    render_pdf,
    source_provenance,
)

REPO_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = REPO_ROOT / "outputs" / "reports"
DEFAULT_HISTORY_FILE = TUNINGS_DIR / "backtest_run_history.csv"

ADAPTIVE_COLUMN = "adaptive_annualized_return_pct"
BUY_HOLD_COLUMN = "buy_hold_annualized_return_pct"
CHART_COLUMN = "chart_file"

STRATEGY_LABEL = "Strategy"
BUY_HOLD_LABEL = "Buy & hold"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Dashboard ranked by the best annualized return per ticker, "
                    "from either the strategy or buy & hold.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--history-file", default=None,
                        help=f"Run history CSV (default: {DEFAULT_HISTORY_FILE}).")
    parser.add_argument("--basis", choices=["best", "strategy", "buy-hold"], default="best",
                        help="Which annualized return to rank by: 'best' takes whichever of "
                             "the two is higher per run (default), or restrict to one.")
    parser.add_argument("--top-funds", type=int, default=0,
                        help="Number of top entries to show after ranking. 0 = all (default).")
    parser.add_argument("--per-slice", action="store_true",
                        help="Rank each -NY slice separately instead of pooling them per ticker.")
    parser.add_argument(
        "--derive-buyhold-horizons",
        "--derive-missing-horizons",
        dest="derive_buyhold_horizons",
        nargs="+",
        choices=("20y", "10y", "5y", "4y", "3y"),
        default=("10y",),
        metavar="HORIZON",
        help="Regenerate every eligible ticker in each selected buy-and-hold horizon "
             "from local price history. --derive-missing-horizons is a compatibility "
             "alias. Default: 10y. "
             "Only applies with --basis buy-hold.",
    )
    parser.add_argument("--output-name", default=None,
                        help="Base filename for the HTML/PDF (default derived from --basis).")
    return parser.parse_args()


def load_ranked_history(history_path, basis, top_funds, per_slice):
    """Best run per ticker by the chosen annualized-return basis.

    Returns (ranked_rows, runs_considered, tickers_seen).
    """
    df = pd.read_csv(history_path, low_memory=False)
    considered = len(df)

    missing = [c for c in (ADAPTIVE_COLUMN, BUY_HOLD_COLUMN, CHART_COLUMN) if c not in df.columns]
    if missing:
        raise ValueError(f"Run history is missing required column(s): {missing}")

    if "run_status" in df.columns:
        status = df["run_status"].fillna("completed").astype(str).str.lower()
        df = df[status.isin(["completed", "nan", ""])]

    df["_adaptive"] = pd.to_numeric(df[ADAPTIVE_COLUMN], errors="coerce")
    df["_buy_hold"] = pd.to_numeric(df[BUY_HOLD_COLUMN], errors="coerce")

    if basis == "strategy":
        df["_top"] = df["_adaptive"]
        df["_winner"] = STRATEGY_LABEL
    elif basis == "buy-hold":
        df["_top"] = df["_buy_hold"]
        df["_winner"] = BUY_HOLD_LABEL
    else:
        # Both must be present, otherwise "the higher of the two" is not defined.
        df = df.dropna(subset=["_adaptive", "_buy_hold"])
        df["_top"] = df[["_adaptive", "_buy_hold"]].max(axis=1)
        df["_winner"] = df["_adaptive"].ge(df["_buy_hold"]).map(
            {True: STRATEGY_LABEL, False: BUY_HOLD_LABEL}
        )

    df = df.dropna(subset=["_top"])
    df = df[df[CHART_COLUMN].notna()]
    df = df[df[CHART_COLUMN].map(lambda p: Path(str(p)).exists())].copy()
    if df.empty:
        return df, considered, 0

    # The label recorded on the row: post-backfill this is the group and the slice
    # lives in fund_slice_label; pre-backfill the slice is still in fund_label.
    df["_row_label"] = df.get("fund_slice_label")
    if "fund_slice_label" in df.columns:
        df["_row_label"] = df["fund_slice_label"].fillna("").astype(str).str.strip()
    else:
        df["_row_label"] = ""
    df.loc[df["_row_label"] == "", "_row_label"] = df["fund_label"].astype(str)

    df["_ticker"] = df["_row_label"].map(fund_group_from_label)
    group_key = "_row_label" if per_slice else "_ticker"

    if "run_started_at" in df.columns:
        df["_started"] = pd.to_datetime(df["run_started_at"], errors="coerce")
    else:
        df["_started"] = pd.NaT

    df = df.sort_values(["_top", "_started"], ascending=[False, False])
    best = df.groupby(group_key, sort=False, as_index=False).head(1)
    best = best.sort_values("_top", ascending=False)
    tickers = df[group_key].nunique()
    if top_funds and top_funds > 0:
        best = best.head(top_funds)
    return best.reset_index(drop=True), considered, tickers


BUY_HOLD_HORIZONS = (
    ("mixed", "Mixed highest", None),
    ("20y", "20 years", (19.0, 21.0)),
    ("10y", "10 years", (9.0, 11.0)),
    ("5y", "5 years", (4.75, 5.25)),
    ("4y", "4 years", (3.75, 4.25)),
    ("3y", "3 years", (2.75, 3.25)),
)


def build_data_derived_buy_hold_rows(data_dir=None, years=10):
    """Rank full local price histories by a trailing buy-and-hold window.

    This is deliberately separate from run-history rankings: it lets a horizon
    dashboard fill tickers that lack historical strategy runs without
    representing the derived results as strategy runs.
    """
    data_dir = Path(data_dir or REPO_ROOT / "data")
    rows = []
    for source in sorted(data_dir.glob("*.csv")):
        # Full ticker files are the source for a derived horizon window;
        # -3Y/-4Y/-5Y slices cannot provide an independent 10-year comparison.
        if "-" in source.stem:
            continue
        try:
            frame = pd.read_csv(source, low_memory=False)
        except (OSError, pd.errors.ParserError):
            continue
        if "Date" not in frame.columns:
            continue
        price_column = next(
            (column for column in ("Adj Close", "Close", "NAV") if column in frame.columns),
            None,
        )
        if price_column is None:
            continue
        values = pd.DataFrame(
            {
                "Date": pd.to_datetime(frame["Date"], errors="coerce"),
                "Price": pd.to_numeric(frame[price_column], errors="coerce"),
            }
        ).dropna()
        values = values[values["Price"] > 0].sort_values("Date")
        if len(values) < 2:
            continue
        end = values["Date"].iloc[-1]
        window = values[values["Date"] >= end - pd.DateOffset(years=years)]
        if len(window) < 2:
            continue
        start = window["Date"].iloc[0]
        elapsed_days = (end - start).days
        # Permit the first trading day after the exact calendar cutoff. Other
        # horizons remain strict; the 20-year group intentionally uses all
        # available history when a ticker has not traded for a full 20 years.
        if years != 20 and elapsed_days < years * 365.25 - 14:
            continue
        annualized = ((window["Price"].iloc[-1] / window["Price"].iloc[0]) ** (365.25 / elapsed_days) - 1) * 100
        ticker = source.stem
        rows.append(
            {
                "fund_label": ticker,
                "fund_slice_label": ticker,
                "data_file": str(source),
                "price_column": price_column,
                "data_start": start.strftime("%Y-%m-%d"),
                "data_end": end.strftime("%Y-%m-%d"),
                "backtest_start": start.strftime("%Y-%m-%d"),
                "backtest_end": end.strftime("%Y-%m-%d"),
                "_ticker": ticker,
                "_row_label": ticker,
                "_top": annualized,
                "_buy_hold": annualized,
                "_adaptive": np.nan,
                "_winner": BUY_HOLD_LABEL,
                "_source_years": elapsed_days / 365.25,
                "_data_derived": True,
            }
        )
    return pd.DataFrame(rows).sort_values(["_top", "_ticker"], ascending=[False, True]).reset_index(drop=True) if rows else pd.DataFrame()


def load_buy_hold_horizon_rankings(history_path, top_funds=0, derived_horizons=("10y",)):
    """Best buy-and-hold run per ticker for each source-data horizon."""
    df = pd.read_csv(history_path, low_memory=False)
    considered = len(df)
    required = (
        "fund_label",
        BUY_HOLD_COLUMN,
        CHART_COLUMN,
        "data_start",
        "data_end",
    )
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Run history is missing required column(s): {missing}")

    if "run_status" in df.columns:
        status = df["run_status"].fillna("completed").astype(str).str.lower()
        df = df[status.isin(["completed", "nan", ""])]

    df["_buy_hold"] = pd.to_numeric(df[BUY_HOLD_COLUMN], errors="coerce")
    df["_adaptive"] = pd.to_numeric(df.get(ADAPTIVE_COLUMN), errors="coerce")
    df["_source_start"] = pd.to_datetime(df["data_start"], errors="coerce")
    df["_source_end"] = pd.to_datetime(df["data_end"], errors="coerce")
    df["_source_years"] = (
        (df["_source_end"] - df["_source_start"]).dt.days / 365.25
    )
    df = df.dropna(subset=["_buy_hold"])
    df = df[df[CHART_COLUMN].notna()]
    df = df[df[CHART_COLUMN].map(lambda path: Path(str(path)).exists())].copy()

    if "fund_slice_label" in df.columns:
        df["_row_label"] = (
            df["fund_slice_label"].fillna("").astype(str).str.strip()
        )
    else:
        df["_row_label"] = ""
    df.loc[df["_row_label"] == "", "_row_label"] = df["fund_label"].astype(str)
    df["_ticker"] = df["_row_label"].map(fund_group_from_label)
    df["_top"] = df["_buy_hold"]
    df["_winner"] = BUY_HOLD_LABEL
    if "run_started_at" in df.columns:
        df["_started"] = pd.to_datetime(df["run_started_at"], errors="coerce")
    else:
        df["_started"] = pd.NaT

    # Historical rankings are built without applying --top-funds yet. Selected
    # horizons are replaced below, and the limit must apply to that final set.
    df["_data_derived"] = False
    rankings = {}
    for key, label, year_range in BUY_HOLD_HORIZONS:
        candidates = df
        if year_range is not None:
            candidates = candidates[
                candidates["_source_years"].between(*year_range)
            ]
        candidates = candidates.sort_values(
            ["_top", "_started"], ascending=[False, False]
        )
        ranked = candidates.groupby("_ticker", sort=False, as_index=False).head(1)
        ranked = ranked.sort_values("_top", ascending=False)
        rankings[key] = {
            "label": label,
            "rows": ranked.reset_index(drop=True),
            "candidate_count": len(candidates),
        }

    # A selected horizon is a consistent price-only comparison: every eligible
    # ticker is recalculated from the same trailing window, replacing historical
    # run rows whose scored windows may be shorter than the source-data span.
    for key in derived_horizons:
        if key not in rankings:
            continue
        years = int(key.removesuffix("y"))
        derived = build_data_derived_buy_hold_rows(years=years)
        if not derived.empty:
            derived = derived.drop_duplicates("_ticker", keep="first")
        else:
            # Retain the expected ranking columns so the selected tab renders
            # an empty state when no local file spans the requested horizon.
            derived = rankings[key]["rows"].iloc[0:0].copy()
        rankings[key]["rows"] = derived
        rankings[key]["fully_derived"] = True
        rankings[key]["local_source_count"] = len(derived)

    for group in rankings.values():
        rows = group["rows"].sort_values(
            ["_top", "_ticker"], ascending=[False, True]
        )
        if top_funds and top_funds > 0:
            rows = rows.head(top_funds)
        rows = rows.reset_index(drop=True)
        derived_mask = rows.get(
            "_data_derived", pd.Series(False, index=rows.index)
        ).fillna(False).astype(bool)
        group["rows"] = rows
        group["historical_count"] = int((~derived_mask).sum())
        group["derived_count"] = int(derived_mask.sum())
    return rankings, considered


def _resolve_price_source(row):
    for field in ("source_snapshot_file", "data_file"):
        value = str(row.get(field, "") or "").strip()
        if not value or value.lower() == "nan":
            continue
        path = Path(value)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if path.exists():
            return path
    return None


def simple_buy_hold_svg(row):
    """Render a lightweight normalized buy-and-hold price chart as inline SVG."""
    source = _resolve_price_source(row)
    if source is None:
        return None
    try:
        frame = pd.read_csv(source, low_memory=False)
    except (OSError, pd.errors.ParserError):
        return None
    if "Date" not in frame.columns:
        return None

    price_candidates = [
        str(row.get("price_column", "") or "").strip(),
        "NAV",
        "Adj Close",
        "Close",
    ]
    price_column = next(
        (column for column in price_candidates if column and column in frame.columns),
        None,
    )
    if price_column is None:
        return None

    raw_price_column = "Close" if "Close" in frame.columns else None
    values = pd.DataFrame(
        {
            "Date": pd.to_datetime(frame["Date"], errors="coerce"),
            "Price": pd.to_numeric(frame[price_column], errors="coerce"),
            "RawPrice": (
                pd.to_numeric(frame[raw_price_column], errors="coerce")
                if raw_price_column
                else np.nan
            ),
        }
    ).dropna(subset=["Date", "Price"])
    start = pd.to_datetime(row.get("backtest_start"), errors="coerce")
    end = pd.to_datetime(row.get("backtest_end") or row.get("data_end"), errors="coerce")
    if not pd.isna(start):
        values = values[values["Date"] >= start]
    if not pd.isna(end):
        values = values[values["Date"] <= end]
    values = values.sort_values("Date")
    if len(values) < 2 or values["Price"].iloc[0] <= 0:
        return None

    if len(values) > 180:
        indexes = np.linspace(0, len(values) - 1, 180, dtype=int)
        values = values.iloc[indexes]
    growth = 10000.0 * values["Price"] / values["Price"].iloc[0]
    low, high = float(growth.min()), float(growth.max())
    spread = high - low
    if spread <= 0:
        spread = 1.0
    xs = np.linspace(18, 782, len(growth))
    ys = 178 - ((growth.to_numpy() - low) / spread) * 152
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area_points = f"18,190 {points} 782,190"
    tone = "#12855b" if growth.iloc[-1] >= growth.iloc[0] else "#c9362c"
    start_label = values["Date"].iloc[0].strftime("%Y-%m-%d")
    end_label = values["Date"].iloc[-1].strftime("%Y-%m-%d")
    final_value = float(growth.iloc[-1])
    total_return = (final_value / 10000.0 - 1.0) * 100.0
    start_raw_price = values["RawPrice"].iloc[0]
    end_raw_price = values["RawPrice"].iloc[-1]
    start_raw_text = (
        f"${float(start_raw_price):,.2f}" if pd.notna(start_raw_price) else "n/a"
    )
    end_raw_text = (
        f"${float(end_raw_price):,.2f}" if pd.notna(end_raw_price) else "n/a"
    )
    return f"""
      <figure class="simple-chart">
        <svg viewBox="0 0 800 215" role="img" aria-label="Buy and hold growth from {start_label} through {end_label}">
          <line x1="18" y1="190" x2="782" y2="190" stroke="#dce2ea"/>
          <polygon points="{area_points}" fill="{tone}" opacity=".10"/>
          <polyline points="{points}" fill="none" stroke="{tone}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
          <circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="5" fill="{tone}"/>
        </svg>
        <figcaption class="chart-endpoints">
          <div class="endpoint endpoint-start">
            <span class="endpoint-date">{start_label}</span>
            <span><small>Investment</small><strong>$10,000 · 0.00%</strong></span>
            <span><small>Raw stock price</small><strong>{start_raw_text}</strong></span>
          </div>
          <div class="endpoint endpoint-end">
            <span class="endpoint-date">{end_label}</span>
            <span><small>Investment</small><strong>${final_value:,.0f} · {total_return:+.2f}%</strong></span>
            <span><small>Raw stock price</small><strong>{end_raw_text}</strong></span>
          </div>
        </figcaption>
      </figure>
    """


def _scored_years(row):
    start = pd.to_datetime(row.get("backtest_start"), errors="coerce")
    end = pd.to_datetime(row.get("backtest_end") or row.get("data_end"), errors="coerce")
    if pd.isna(start) or pd.isna(end) or end <= start:
        return "n/a"
    return f"{(end - start).days / 365.25:.1f}Y"


BUY_HOLD_GROUPED_STYLE = """
  :root{--ink:#172033;--muted:#667085;--line:#dce2ea;--surface:#fff;--accent:#176b5b;--accent-soft:#e8f4f1;--bg:#f3f5f7;--pos:#12855b;--neg:#c9362c}
  *{box-sizing:border-box} [hidden]{display:none!important}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}
  header{position:sticky;top:0;z-index:10;padding:17px clamp(16px,4vw,48px) 13px;background:rgba(243,245,247,.96);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
  .back-link{display:inline-flex;align-items:center;margin-bottom:7px;color:var(--accent);font-size:.78rem;font-weight:800;text-decoration:none}.back-link:hover{text-decoration:underline}
  h1{margin:0 0 4px;font-size:clamp(1.4rem,3vw,2.05rem)} header p{margin:0;color:var(--muted);font-size:.88rem}
  .source{margin-top:5px;font-size:.76rem}.source code{padding:1px 5px;border-radius:5px;background:var(--accent-soft);color:var(--accent)}
  .tabs{display:flex;gap:7px;overflow-x:auto;margin-top:12px;padding-bottom:2px}
  .tab{flex:0 0 auto;padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--ink);font:inherit;font-size:.8rem;font-weight:750;cursor:pointer}
  .tab[aria-selected="true"]{border-color:#8fc5b6;background:var(--accent-soft);color:var(--accent)}
  main{margin:0;padding:24px clamp(16px,4vw,48px) 56px}
  .group-note{margin:0 0 14px;color:var(--muted);font-size:.87rem}
  .ranking-grid{display:grid;gap:14px;grid-template-columns:repeat(2,minmax(0,1fr))}
  .rank-card{min-width:0;padding:15px;border:1px solid var(--line);border-radius:16px;background:var(--surface);box-shadow:0 7px 22px rgba(19,33,55,.05)}
  .card-head{display:flex;align-items:center;gap:10px}.rank{display:grid;place-items:center;min-width:36px;height:29px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-weight:850}
  h2{margin:0;font-size:1.12rem}.headline{margin-left:auto;text-align:right}.headline small{display:block;color:var(--muted);font-size:.66rem;text-transform:uppercase;letter-spacing:.05em}.headline strong{font-size:1.22rem;color:var(--pos)}
  .chips{display:flex;flex-wrap:wrap;gap:6px;margin:11px 0}.chips span{padding:6px 8px;border-radius:8px;background:#f7f8fa;color:var(--muted);font-size:.75rem}.chips b{color:var(--ink)}
  .simple-chart{margin:0;padding:7px 9px 8px;border-radius:11px;background:#f8faf9}.simple-chart svg{display:block;width:100%;height:auto;max-height:150px}
  .chart-endpoints{display:grid;grid-template-columns:1fr 1fr;gap:14px;color:var(--muted);font-size:.73rem}.endpoint{display:grid;gap:2px}.endpoint-end{text-align:right}.endpoint-date{font-weight:750;color:var(--ink)}.endpoint small{margin-right:4px;font-size:.66rem;text-transform:uppercase;letter-spacing:.035em}.endpoint strong{color:var(--ink)}
  .chart-missing,.empty{padding:34px 18px;border:1px dashed #bcc5cf;border-radius:14px;background:rgba(255,255,255,.55);color:var(--muted);text-align:center}
  @media(min-width:1500px){.ranking-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.rank-card{padding:12px}.chips{margin:8px 0;gap:5px}.chips span{padding:5px 7px;font-size:.72rem}.simple-chart svg{height:112px;max-height:112px}}
  @media(min-width:2100px){.ranking-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.simple-chart svg{height:96px;max-height:96px}}
  @media(max-width:760px){.ranking-grid{grid-template-columns:1fr}.chart-endpoints{grid-template-columns:1fr;gap:8px}.endpoint-end{text-align:left}}
"""


def render_buy_hold_horizon_dashboard(
    rankings, output_path, source_path, considered
):
    source_name, source_built_at, source_full = source_provenance(source_path)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tabs = []
    panels = []
    for index, (key, label, _) in enumerate(BUY_HOLD_HORIZONS):
        group = rankings[key]
        rows = group["rows"]
        selected = "true" if index == 0 else "false"
        tabs.append(
            f'<button class="tab" type="button" role="tab" id="tab-{key}" '
            f'data-group="{key}" aria-controls="panel-{key}" '
            f'aria-selected="{selected}">{html.escape(label)} ({len(rows)})</button>'
        )
        cards = []
        for rank, (_, row) in enumerate(rows.iterrows(), start=1):
            ticker = html.escape(str(row.get("_ticker", "Unknown")))
            descriptor = html.escape(slice_descriptor(row) or str(row.get("_row_label", "")))
            source_years = row.get("_source_years")
            source_years_text = (
                f"{float(source_years):.1f}Y"
                if source_years is not None and pd.notna(source_years)
                else "n/a"
            )
            simple_chart = simple_buy_hold_svg(row)
            chart_html = simple_chart or '<div class="chart-missing">Simple price chart unavailable for this run.</div>'
            data_derived = bool(row.get("_data_derived", False))
            provenance_chip = (
                '<span>Comparison <b>Derived from local price data</b></span>'
                if data_derived
                else f'<span>Winning run <b>{descriptor}</b></span>'
            )
            cards.append(
                f"""<article class="rank-card">
                  <div class="card-head"><span class="rank">#{rank}</span><h2>{ticker}</h2>
                    <div class="headline"><small>Buy &amp; hold annualized</small><strong>{format_pct(row.get('_top'))}</strong></div>
                  </div>
                  <div class="chips">
                    <span>Source years <b>{source_years_text}</b></span>
                    <span>Scored years <b>{_scored_years(row)}</b></span>
                    <span>Strategy ann. <b>{format_pct(row.get('_adaptive'))}</b></span>
                    <span>Through <b>{html.escape(str(row.get('data_end', 'n/a')))}</b></span>
                    {provenance_chip}
                  </div>{chart_html}
                </article>"""
            )
        content = (
            f'<div class="ranking-grid">{"".join(cards)}</div>'
            if cards
            else f'<div class="empty">No valid {html.escape(label)} source-data runs with usable ranking evidence are currently available.</div>'
        )
        note = (
            "Highest buy-and-hold annualized run per ticker, regardless of source-data horizon."
            if key == "mixed"
            else f"Highest buy-and-hold annualized run per ticker from source datasets spanning approximately {label.lower()}."
        )
        if group.get("fully_derived"):
            if key == "20y":
                note = (
                    "Buy-and-hold comparison regenerated from up to 20 years of local price history; "
                    "stocks with less history use their complete available record. Source years and "
                    "scored years use the same window."
                )
            else:
                note = (
                    f"Trailing {label.lower()} buy-and-hold comparison regenerated directly from local price histories. "
                    "Source years and scored years use the same consistent window."
                )
            evidence_note = f'{group.get("local_source_count", 0)} eligible local source file(s).'
        else:
            evidence_note = f'{group["candidate_count"]} candidate run(s).'
        panels.append(
            f'<section role="tabpanel" id="panel-{key}" aria-labelledby="tab-{key}" '
            f'{"hidden" if index else ""}><p class="group-note">{html.escape(note)} '
            f'{html.escape(evidence_note)}</p>{content}</section>'
        )

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fund Backtest Dashboard — Buy &amp; Hold Annualized by Source Years</title>
<style>{BUY_HOLD_GROUPED_STYLE}</style></head><body>
<header><a class="back-link" href="dashboard.html">← Master dashboard</a><h1>Buy &amp; Hold Annualized Ranking</h1>
  <p>Highest historical buy-and-hold outcome grouped by source-data horizon · generated {generated_at}</p>
  <p class="source">Source <code title="{html.escape(source_full, quote=True)}">{html.escape(source_name)}</code> last written {source_built_at} — {considered} run(s) considered.</p>
  <nav class="tabs" role="tablist" aria-label="Source-data horizon">{"".join(tabs)}</nav>
</header><main>{"".join(panels)}</main>
<script>
  const tabs=[...document.querySelectorAll('.tab')],panels=[...document.querySelectorAll('[role="tabpanel"]')];
  function selectGroup(key,focus=false){{
    tabs.forEach(tab=>{{const active=tab.dataset.group===key;tab.setAttribute('aria-selected',String(active));if(active&&focus)tab.focus()}});
    panels.forEach(panel=>panel.hidden=panel.id!==`panel-${{key}}`);
    if(history.replaceState)history.replaceState(null,'',`#${{key}}`);
  }}
  tabs.forEach(tab=>tab.addEventListener('click',()=>selectGroup(tab.dataset.group)));
  document.querySelector('.tabs').addEventListener('keydown',event=>{{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();const current=tabs.findIndex(tab=>tab.getAttribute('aria-selected')==='true');
    let next=event.key==='Home'?0:event.key==='End'?tabs.length-1:event.key==='ArrowRight'?(current+1)%tabs.length:(current-1+tabs.length)%tabs.length;
    selectGroup(tabs[next].dataset.group,true);
  }});
  const requested=location.hash.slice(1);if(tabs.some(tab=>tab.dataset.group===requested))selectGroup(requested);
</script></body></html>"""
    output_path.write_text(page, encoding="utf-8")
    return output_path


def slice_descriptor(row):
    """'AAPL-3Y · 2Y/12M generic' — which dataset and config won."""
    parts = []
    label = str(row.get("_row_label", "") or "").strip()
    ticker = str(row.get("_ticker", "") or "").strip()
    if label and label != ticker:
        parts.append(label)
    lookback, offset = row.get("lookback_years"), row.get("offset_months")
    if lookback is not None and not pd.isna(lookback) and offset is not None and not pd.isna(offset):
        try:
            parts.append(f"{float(lookback):g}Y/{int(float(offset))}M")
        except (TypeError, ValueError):
            pass
    profile = str(row.get("strategy_profile", "") or "").strip()
    if profile:
        parts.append(profile)
    return " · ".join(parts) if parts else None


def run_years(row):
    """Length of the scored backtest window, shown alongside annualized returns."""
    start = pd.to_datetime(row.get("backtest_start"), errors="coerce")
    end = pd.to_datetime(row.get("backtest_end") or row.get("data_end"), errors="coerce")
    if pd.isna(start) or pd.isna(end) or end <= start:
        return None
    return f"{(end - start).days / 365.25:.1f}Y"


def build_spec(basis, per_slice=False):
    def chips(row):
        items = [
            ("Strategy ann.", format_pct(row.get("_adaptive", float("nan")))),
            ("Buy & hold ann.", format_pct(row.get("_buy_hold", float("nan")))),
        ]
        excess = row.get("excess_annualized_return_pct")
        if excess is not None and not pd.isna(excess):
            items.append(("Excess ann.", format_pct(float(excess))))
        max_dd = row.get("max_dd_pct")
        if max_dd is not None and not pd.isna(max_dd):
            items.append(("Max drawdown", f"{float(max_dd):.2f}%"))
        duration = run_years(row)
        if duration:
            items.append(("Run years", duration))
        items.append(("Through", str(row.get("data_end", "n/a"))))
        descriptor = slice_descriptor(row)
        if descriptor:
            items.append(("Winning run", descriptor))
        return items

    headline_label = {
        "best": "Top annualized",
        "strategy": "Strategy annualized",
        "buy-hold": "Buy & hold annualized",
    }[basis]
    title_metric = {
        "best": "Top Annualized Return",
        "strategy": "Strategy Annualized Return",
        "buy-hold": "Buy & Hold Annualized Return",
    }[basis]

    return DashboardSpec(
        title=f"Fund Backtest Dashboard — {title_metric}",
        headline_label=headline_label,
        headline=lambda row: float(row["_top"]) if pd.notna(row["_top"]) else float("nan"),
        chart=lambda row: Path(str(row[CHART_COLUMN])),
        # Per-slice mode ranks each slice separately, so the slice must be the card
        # title - otherwise every AAPL slice renders as an indistinguishable "AAPL".
        name=lambda row: str(
            (row.get("_row_label") if per_slice else row.get("_ticker"))
            or row.get("_ticker") or row.get("_row_label") or "Unknown"
        ),
        chips=chips,
        # Only meaningful for --basis best; with a fixed basis the label is already
        # in the headline, so a badge would just repeat it.
        badge=(lambda row: row.get("_winner")) if basis == "best" else None,
    )


def main():
    args = parse_args()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    history_path = Path(args.history_file) if args.history_file else DEFAULT_HISTORY_FILE
    if not history_path.is_absolute():
        history_path = REPO_ROOT / history_path
    if not history_path.exists():
        raise FileNotFoundError(f"Run history not found: {history_path}")

    df, considered, tickers = load_ranked_history(
        history_path, args.basis, args.top_funds, args.per_slice
    )
    if df.empty:
        print(f"No usable rows with existing charts found in {history_path}. Nothing to render.")
        return 0

    spec = build_spec(args.basis, args.per_slice)
    grouping = "per -NY slice" if args.per_slice else "slices pooled per ticker"
    basis_text = {
        "best": "best of strategy or buy & hold, whichever is higher",
        "strategy": "strategy annualized return only",
        "buy-hold": "buy & hold annualized return only",
    }[args.basis]
    subtitle = f"ranked by {basis_text} · {grouping}"
    provenance_note = (
        f"ranking computed here from {considered} run(s) in this file, so it is current with it."
    )

    base = args.output_name or f"dashboard_top_annualized{'' if args.basis == 'best' else '_' + args.basis.replace('-', '')}"
    if args.per_slice:
        base += "_per_slice"

    if args.basis == "buy-hold" and not args.per_slice:
        horizon_rankings, horizon_considered = load_buy_hold_horizon_rankings(
            history_path, args.top_funds, args.derive_buyhold_horizons
        )
        html_path = render_buy_hold_horizon_dashboard(
            horizon_rankings,
            REPORTS_DIR / f"{base}.html",
            history_path,
            horizon_considered,
        )
    else:
        html_path = render_html(
            df,
            spec,
            REPORTS_DIR / f"{base}.html",
            history_path,
            subtitle,
            provenance_note,
            REPORTS_DIR,
        )
    pdf_path = render_pdf(df, spec, REPORTS_DIR / f"{base}.pdf", history_path, REPORTS_DIR)

    print(f"Source: {history_path}")
    print(f"Ranked {len(df)} of {tickers} entr{'y' if tickers == 1 else 'ies'} "
          f"from {considered} run(s) by {basis_text}:")
    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        winner = row.get("_winner", "")
        badge = f"  [{winner}]" if args.basis == "best" else ""
        descriptor = slice_descriptor(row)
        detail = f"   {descriptor}" if descriptor else ""
        name = str((row.get("_row_label") if args.per_slice else row.get("_ticker"))
                   or row.get("_ticker"))
        print(f"  #{rank:>2}  {name:<9} {format_pct(row['_top']):>9}{badge:<14}{detail}")

    if args.basis == "best":
        strategy_wins = int((df["_winner"] == STRATEGY_LABEL).sum())
        print(f"\nHeadline came from the strategy in {strategy_wins} of {len(df)} entries, "
              f"from buy & hold in {len(df) - strategy_wins}.")
    print(f"\nDashboard saved to: {html_path}")
    print(f"One-fund-per-page PDF saved to: {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
