"""Build a fund backtest dashboard ranked by EXCESS ANNUALIZED RETURN.

By default this reads `outputs/tunings/backtest_run_history.csv` directly and does
its own ranking: for each fund it picks the run with the highest excess annualized
return (strategy − buy & hold, annualized), then renders that run's own chart. The
dashboard is therefore always current with the run history and never inherits a
stale ranking from a snapshot.

`--source summary` keeps the older behaviour of reading a
`final_backtest_summary_*.csv` produced by `final_backtest_from_summary.py`. That
path exists because the summary's `latest_*` columns are a genuinely different
measurement — the winning parameters *re-run* over the full latest price window —
which cannot be derived from the run history. Use it when you want that view;
otherwise prefer the default.

Either way no backtest is re-run: charts already on disk are re-used.

Usage:
    python dashboard_by_excess_annualized.py                    # run history, own ranking (default)
    python dashboard_by_excess_annualized.py --top-funds 5      # only the 5 best funds
    python dashboard_by_excess_annualized.py --source summary   # newest summary, latest re-run window
    python dashboard_by_excess_annualized.py --source summary --window final
    python dashboard_by_excess_annualized.py --history-file outputs/tunings/backtest_run_history.csv
"""

import argparse
import html
import os
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from common import fund_group_from_label

SCRIPT_DIR = Path(__file__).resolve().parent
# Self-contained module: data/ and outputs/ live inside backtest/ (see common.py).
REPO_ROOT = SCRIPT_DIR
OUTPUTS_DIR = REPO_ROOT / "outputs"
TUNINGS_DIR = OUTPUTS_DIR / "tunings"
REPORTS_DIR = OUTPUTS_DIR / "reports"

# Column sets for the two windows the main run records. "latest" is the full/most
# recent price window; "final" is the historical backtest window of the winning run.
DEFAULT_HISTORY_FILE = TUNINGS_DIR / "backtest_run_history.csv"
ZERO_EXCESS_EPSILON = 1e-9

# Source data is deliberately classified separately from the scored backtest
# window.  A 20-year price file can, for example, contain a 3-year scored run.
SOURCE_HORIZONS = (
    ("mixed", "Mixed", None),
    ("20y", "20 years", (19.0, 21.0)),
    ("10y", "10 years", (9.0, 11.0)),
    ("5y", "5 years", (4.75, 5.25)),
    ("4y", "4 years", (3.75, 4.25)),
    ("3y", "3 years", (2.75, 3.25)),
    ("other", "Other", None),
)

# Run-history column mapping. Each row is one completed backtest, so the metrics are
# that run's own window and `chart_file` is the chart it generated.
HISTORY_COLUMNS = {
    "excess": "excess_annualized_return_pct",
    "adaptive_annualized": "adaptive_annualized_return_pct",
    "buy_hold_annualized": "buy_hold_annualized_return_pct",
    "adaptive_return": "adaptive_return_pct",
    "max_dd": "max_dd_pct",
    "through": "data_end",
    "chart": "chart_file",
}

WINDOW_COLUMNS = {
    "latest": {
        "excess": "latest_excess_annualized_return_pct",
        "adaptive_annualized": "latest_adaptive_annualized_return_pct",
        "buy_hold_annualized": "latest_buy_hold_annualized_return_pct",
        "adaptive_return": "latest_adaptive_return_pct",
        "max_dd": "latest_max_dd_pct",
        "through": "latest_data_end",
        "chart": "latest_chart_file",
    },
    "final": {
        "excess": "excess_annualized_return_pct",
        "adaptive_annualized": "adaptive_annualized_return_pct",
        "buy_hold_annualized": "buy_hold_annualized_return_pct",
        "adaptive_return": "adaptive_return_pct",
        "max_dd": "max_dd_pct",
        "through": "data_end",
        "chart": "simple_chart_file",
    },
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Rebuild the fund backtest dashboard ranked by excess annualized return."
    )
    parser.add_argument(
        "--source",
        choices=["history", "summary"],
        default="history",
        help="Where the ranking comes from: 'history' (default) reads the run history and "
        "ranks it here; 'summary' reads a final_backtest_summary_*.csv snapshot.",
    )
    parser.add_argument(
        "--history-file",
        default=None,
        help=f"Run history CSV for --source history (default: {DEFAULT_HISTORY_FILE}).",
    )
    parser.add_argument(
        "--summary-file",
        default=None,
        help="final_backtest_summary_*.csv to read (default: newest in outputs/tunings/). "
        "Implies --source summary.",
    )
    parser.add_argument(
        "--window",
        choices=sorted(WINDOW_COLUMNS.keys()),
        default="latest",
        help="--source summary only: which recorded window to rank/display, 'latest' full "
        "re-run window (default) or 'final' historical backtest window.",
    )
    parser.add_argument(
        "--top-funds",
        type=int,
        default=0,
        help="Number of top funds to show after ranking. 0 = all (default).",
    )
    return parser.parse_args()


def newest_summary_file():
    candidates = sorted(
        TUNINGS_DIR.glob("final_backtest_summary_*.csv"),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No final_backtest_summary_*.csv found in {TUNINGS_DIR}. "
            "Run final_backtest_from_summary.py first."
        )
    return candidates[-1]


def select_best_nonzero_per_ticker(df):
    """Select each ticker's highest non-zero excess run, falling back to zero."""
    selected = []
    for _, group in df.groupby("_ticker", sort=False):
        non_zero = group[group["_excess"].abs() > ZERO_EXCESS_EPSILON]
        selected.append((non_zero if not non_zero.empty else group).iloc[0])
    return pd.DataFrame(selected).reset_index(drop=True)


def load_ranked_history(history_path, cols, top_funds):
    """Rank the run history here: best run per fund by excess annualized return.

    This is the point of the default mode — the ordering is derived from the history
    on every render rather than inherited from a snapshot, so it cannot go stale.
    """
    df = pd.read_csv(history_path, low_memory=False)
    considered = len(df)

    if "run_status" in df.columns:
        status = df["run_status"].fillna("completed").astype(str).str.lower()
        df = df[status.isin(["completed", "nan", ""])]

    missing = [cols[key] for key in ("excess", "chart") if cols[key] not in df.columns]
    if missing:
        raise ValueError(f"Run history is missing required column(s): {missing}")

    df["_excess"] = pd.to_numeric(df[cols["excess"]], errors="coerce")
    df = df.dropna(subset=["_excess"])
    df = df[df[cols["chart"]].notna()]
    df = df[df[cols["chart"]].map(lambda p: Path(str(p)).exists())].copy()
    if df.empty:
        return df, considered

    # Newest run breaks ties so a re-run of an equally good config wins.
    if "run_started_at" in df.columns:
        df["_started"] = pd.to_datetime(df["run_started_at"], errors="coerce")
    else:
        df["_started"] = pd.NaT
    df = df.sort_values(["_excess", "_started"], ascending=[False, False])

    # Pool legacy slice labels such as AAPL-4Y under their base ticker so they
    # never appear as separate stocks in a fund-level ranking.
    if "fund_slice_label" in df.columns:
        row_labels = df["fund_slice_label"].fillna("").astype(str).str.strip()
        row_labels = row_labels.where(row_labels.ne(""), df["fund_label"].astype(str))
    else:
        row_labels = df["fund_label"].astype(str)
    df["_ticker"] = row_labels.map(fund_group_from_label)
    # A zero result is commonly an incomplete/no-trade run. Prefer the best
    # meaningful non-zero result even when it is negative; keep zero only when
    # every eligible run for that ticker is zero.
    best = select_best_nonzero_per_ticker(df)
    best["fund_label"] = best["_ticker"]
    best = best.sort_values("_excess", ascending=False)
    if top_funds and top_funds > 0:
        best = best.head(top_funds)
    return best.reset_index(drop=True), considered


def run_config_label(row):
    """Short 'which run won' descriptor, e.g. '3.0Y/12M generic'. History mode only."""
    lookback = row.get("lookback_years")
    offset = row.get("offset_months")
    if lookback is None or pd.isna(lookback) or offset is None or pd.isna(offset):
        return None
    try:
        window = f"{float(lookback):g}Y/{int(float(offset))}M"
    except (TypeError, ValueError):
        return None
    profile = str(row.get("strategy_profile", "") or "").strip()
    return f"{window} {profile}".strip()


def run_years(row):
    """Length of the scored backtest window, shown alongside annualized returns."""
    start = pd.to_datetime(row.get("backtest_start"), errors="coerce")
    end = pd.to_datetime(row.get("backtest_end") or row.get("data_end"), errors="coerce")
    if pd.isna(start) or pd.isna(end) or end <= start:
        return None
    return f"{(end - start).days / 365.25:.1f}Y"


def elapsed_years(row, start_key, end_key, fallback_end_key=None):
    """Return an elapsed duration in years, or NaN when the dates are unusable."""
    start = pd.to_datetime(row.get(start_key), errors="coerce")
    end_value = row.get(end_key)
    if (end_value is None or pd.isna(end_value)) and fallback_end_key:
        end_value = row.get(fallback_end_key)
    end = pd.to_datetime(end_value, errors="coerce")
    if pd.isna(start) or pd.isna(end) or end <= start:
        return np.nan
    return (end - start).days / 365.25


def source_horizon_key(years):
    """Classify an exact source span into the stable dashboard horizon tabs."""
    if not np.isfinite(years):
        return "other"
    for key, _, year_range in SOURCE_HORIZONS:
        if key in ("mixed", "other") or year_range is None:
            continue
        if year_range[0] <= years <= year_range[1]:
            return key
    return "other"


def run_year_bucket(years):
    """Use nearest whole scored year while retaining the exact duration on cards."""
    if not np.isfinite(years):
        return None
    whole_years = max(0, int(np.floor(years + 0.5)))
    return "lt1y" if whole_years == 0 else f"{whole_years}y"


def run_year_bucket_label(key):
    return "<1Y" if key == "lt1y" else f"{int(key.removesuffix('y'))}Y"


def run_year_bucket_sort_key(key):
    return 0 if key == "lt1y" else int(key.removesuffix("y"))


def prepare_history_candidates(history_path, cols):
    """Load completed chart-backed rows and calculate independent source/run windows."""
    df = pd.read_csv(history_path, low_memory=False)
    considered = len(df)
    if "run_status" in df.columns:
        status = df["run_status"].fillna("completed").astype(str).str.lower()
        df = df[status.isin(["completed", "nan", ""])]

    required = (cols["excess"], cols["chart"], "data_start", "data_end")
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Run history is missing required column(s): {missing}")

    df["_excess"] = pd.to_numeric(df[cols["excess"]], errors="coerce")
    df["_source_years"] = df.apply(
        lambda row: elapsed_years(row, "data_start", "data_end"), axis=1
    )
    df["_scored_years"] = df.apply(
        lambda row: elapsed_years(row, "backtest_start", "backtest_end", "data_end"), axis=1
    )
    df = df.dropna(subset=["_excess", "_source_years", "_scored_years"])
    df = df[df[cols["chart"]].notna()]
    df = df[df[cols["chart"]].map(lambda path: Path(str(path)).exists())].copy()
    if df.empty:
        return df, considered

    if "run_started_at" in df.columns:
        df["_started"] = pd.to_datetime(df["run_started_at"], errors="coerce")
    else:
        df["_started"] = pd.NaT
    if "fund_slice_label" in df.columns:
        row_labels = df["fund_slice_label"].fillna("").astype(str).str.strip()
        row_labels = row_labels.where(row_labels.ne(""), df["fund_label"].astype(str))
    else:
        row_labels = df["fund_label"].astype(str)
    df["_ticker"] = row_labels.map(fund_group_from_label)
    df["_source_horizon"] = df["_source_years"].map(source_horizon_key)
    df["_run_bucket"] = df["_scored_years"].map(run_year_bucket)
    return df.sort_values(["_excess", "_started"], ascending=[False, False]), considered


def ranked_excess_rows(candidates, top_funds=0):
    """Best meaningful candidate per ticker; newest run resolves exact ties."""
    if candidates.empty:
        return candidates.copy()
    candidates = candidates.sort_values(["_excess", "_started"], ascending=[False, False])
    ranked = select_best_nonzero_per_ticker(candidates).sort_values(
        ["_excess", "_started"], ascending=[False, False]
    )
    if top_funds and top_funds > 0:
        ranked = ranked.head(top_funds)
    return ranked.reset_index(drop=True)


def load_excess_horizon_rankings(history_path, cols=HISTORY_COLUMNS, top_funds=0):
    """Build Source years x Run years rankings for the live history dashboard."""
    candidates, considered = prepare_history_candidates(history_path, cols)
    rankings = {}
    for key, label, _ in SOURCE_HORIZONS:
        scoped = candidates if key == "mixed" else candidates[candidates["_source_horizon"] == key]
        run_buckets = sorted(
            scoped["_run_bucket"].dropna().unique().tolist(), key=run_year_bucket_sort_key
        ) if not scoped.empty else []
        views = {"all": ranked_excess_rows(scoped, top_funds)}
        for bucket in run_buckets:
            views[bucket] = ranked_excess_rows(
                scoped[scoped["_run_bucket"] == bucket], top_funds
            )
        rankings[key] = {
            "label": label,
            "candidate_count": len(scoped),
            "run_buckets": run_buckets,
            "views": views,
        }
    return rankings, considered


def safe_float(row, key, default=np.nan):
    value = row.get(key, default)
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_ranked_results(summary_path, cols, top_funds):
    df = pd.read_csv(summary_path)
    if "status" in df.columns:
        df = df[df["status"].astype(str).str.lower() == "completed"]

    missing = [key for key in ("excess", "chart") if cols[key] not in df.columns]
    if missing:
        raise ValueError(
            f"Summary file is missing required column(s) for the '{cols}' window: "
            f"{[cols[key] for key in missing]}"
        )

    df = df[df[cols["chart"]].notna()].copy()
    df = df[df[cols["chart"]].map(lambda p: Path(str(p)).exists())]
    df["_excess"] = pd.to_numeric(df[cols["excess"]], errors="coerce")
    df = df.dropna(subset=["_excess"])
    df = df.sort_values("_excess", ascending=False)
    if top_funds and top_funds > 0:
        df = df.head(top_funds)
    return df.reset_index(drop=True)


def pct(row, key):
    value = row.get(key)
    return "n/a" if value is None or pd.isna(value) else f"{float(value):+.2f}%"


def build_cards(df, cols):
    cards = []
    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        chart_path = Path(str(row[cols["chart"]]))
        chart_src = os.path.relpath(chart_path, REPORTS_DIR).replace(os.sep, "/")
        fund_label = html.escape(str(row.get("fund_label", "Unknown fund")))
        chart_alt = html.escape(f"Strategy chart for {row.get('fund_label', 'fund')}")
        excess_value = safe_float(row, cols["excess"])
        excess_class = "pos" if np.isfinite(excess_value) and excess_value >= 0 else "neg"
        config = run_config_label(row)
        config_span = (
            f"<span>Winning run <b>{html.escape(config)}</b></span>" if config else ""
        )
        duration = run_years(row)
        duration_span = f"<span>Run years <b>{duration}</b></span>" if duration else ""
        cards.append(
            f"""
            <article class="fund-card">
              <div class="card-heading">
                <div><span class="rank">#{rank}</span><h2>{fund_label}</h2></div>
                <div class="headline {excess_class}"><span>Excess annualized</span><strong>{pct(row, cols['excess'])}</strong></div>
              </div>
              <div class="metrics">
                <span>Strategy ann. <b>{pct(row, cols['adaptive_annualized'])}</b></span>
                <span>Buy &amp; hold ann. <b>{pct(row, cols['buy_hold_annualized'])}</b></span>
                <span>Strategy total <b>{pct(row, cols['adaptive_return'])}</b></span>
                <span>Max drawdown <b>{pct(row, cols['max_dd'])}</b></span>
                {duration_span}
                <span>Through <b>{html.escape(str(row.get(cols['through'], 'n/a')))}</b></span>
                {config_span}
              </div>
              <button class="chart-button" type="button" data-src="{html.escape(chart_src, quote=True)}" data-title="{fund_label}" aria-label="Open zoomable chart for {fund_label}">
                <img src="{html.escape(chart_src, quote=True)}" alt="{chart_alt}" loading="lazy">
                <span class="zoom-hint">Click to zoom</span>
              </button>
            </article>
            """
        )
    return cards


def source_provenance(source_path):
    """Describe the file the dashboard was built from, with its last-modified time.

    In history mode this is the live run history and the ranking is computed here, so
    the timestamp is just the data's age. In summary mode it is a point-in-time
    snapshot whose ranking can lag the history, which is exactly what this line makes
    visible instead of something to go digging for.
    """
    source_path = Path(source_path)
    try:
        built_at = datetime.fromtimestamp(source_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        built_at = "unknown"
    return source_path.name, built_at, str(source_path)


GROUPED_EXCESS_STYLE = """
  :root{--ink:#172033;--muted:#667085;--line:#dce2ea;--surface:#fff;--accent:#176b5b;--accent-soft:#e8f4f1;--bg:#f3f5f7;--pos:#12855b;--neg:#c9362c}
  *{box-sizing:border-box} [hidden]{display:none!important}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}
  header{position:sticky;top:0;z-index:10;padding:17px clamp(16px,4vw,48px) 13px;background:rgba(243,245,247,.96);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
  h1{margin:0 0 4px;font-size:clamp(1.4rem,3vw,2.05rem)} header p{margin:0;color:var(--muted);font-size:.88rem}
  .master-link{display:inline-block;margin-bottom:8px;color:var(--accent);font-size:.83rem;font-weight:800;text-decoration:none}.master-link:hover,.master-link:focus-visible{text-decoration:underline}
  .source{margin-top:5px;font-size:.76rem}.source code{padding:1px 5px;border-radius:5px;background:var(--accent-soft);color:var(--accent)}
  .tabs,.run-tabs{display:flex;gap:7px;overflow-x:auto;padding-bottom:2px}.tabs{margin-top:12px}.run-tabs{margin:0 0 14px}
  .tab,.run-tab{flex:0 0 auto;padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--ink);font:inherit;font-size:.8rem;font-weight:750;cursor:pointer}
  .tab[aria-selected=true],.run-tab[aria-selected=true]{border-color:#8fc5b6;background:var(--accent-soft);color:var(--accent)}
  main{margin:0;padding:24px clamp(16px,4vw,48px) 56px}.group-note{margin:0 0 14px;color:var(--muted);font-size:.87rem}
  .ranking-grid{display:grid;gap:14px;grid-template-columns:repeat(2,minmax(0,1fr))}
  .rank-card{min-width:0;padding:15px;border:1px solid var(--line);border-radius:16px;background:var(--surface);box-shadow:0 7px 22px rgba(19,33,55,.05)}
  .card-head{display:flex;align-items:center;gap:10px}.rank{display:grid;place-items:center;min-width:36px;height:29px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-weight:850}
  h2{margin:0;font-size:1.12rem;overflow-wrap:anywhere}.headline{margin-left:auto;text-align:right}.headline small{display:block;color:var(--muted);font-size:.66rem;text-transform:uppercase;letter-spacing:.05em}.headline strong{font-size:1.22rem}.headline.pos strong{color:var(--pos)}.headline.neg strong{color:var(--neg)}
  .chips{display:flex;flex-wrap:wrap;gap:6px;margin:11px 0}.chips span{padding:6px 8px;border-radius:8px;background:#f7f8fa;color:var(--muted);font-size:.75rem}.chips b{color:var(--ink)}
  .chart-button{display:block;position:relative;width:100%;padding:0;border:0;border-radius:11px;overflow:hidden;background:#e8ebef;cursor:zoom-in}.chart-button img{display:block;width:100%;height:auto}.zoom-hint{position:absolute;right:9px;bottom:9px;padding:5px 8px;border-radius:7px;background:rgba(16,24,40,.78);color:#fff;font-size:.72rem;opacity:0;transition:opacity .18s}.chart-button:hover .zoom-hint,.chart-button:focus-visible .zoom-hint{opacity:1}
  .empty{padding:34px 18px;border:1px dashed #bcc5cf;border-radius:14px;background:rgba(255,255,255,.55);color:var(--muted);text-align:center}
  dialog{width:calc(100vw - 24px);height:calc(100vh - 24px);max-width:none;max-height:none;padding:0;border:0;border-radius:16px;background:#111827;overflow:hidden}dialog::backdrop{background:rgba(3,8,18,.82)}.viewer-bar{position:absolute;inset:0 0 auto 0;z-index:3;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 14px;background:rgba(17,24,39,.9);color:#fff}.viewer-bar strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.controls{display:flex;gap:7px}.controls button{border:1px solid #667085;background:#263246;color:#fff;border-radius:8px;padding:7px 11px;cursor:pointer}.viewport{width:100%;height:100%;overflow:hidden;cursor:grab;touch-action:none}.viewport.dragging{cursor:grabbing}#viewerImage{position:absolute;left:50%;top:50%;max-width:none;transform-origin:center;user-select:none;pointer-events:none}
  @media(min-width:1500px){.ranking-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.rank-card{padding:12px}.chips{margin:8px 0;gap:5px}.chips span{padding:5px 7px;font-size:.72rem}}@media(min-width:2100px){.ranking-grid{grid-template-columns:repeat(4,minmax(0,1fr))}}@media(max-width:760px){.ranking-grid{grid-template-columns:1fr}}
"""


def build_grouped_excess_cards(rows, cols):
    cards = []
    for rank, (_, row) in enumerate(rows.iterrows(), start=1):
        chart_path = Path(str(row[cols["chart"]]))
        chart_src = os.path.relpath(chart_path, REPORTS_DIR).replace(os.sep, "/")
        ticker = html.escape(str(row.get("_ticker") or row.get("fund_label", "Unknown fund")))
        excess_value = safe_float(row, cols["excess"])
        excess_class = "pos" if np.isfinite(excess_value) and excess_value >= 0 else "neg"
        config = run_config_label(row)
        config_chip = f"<span>Winning run <b>{html.escape(config)}</b></span>" if config else ""
        cards.append(
            f'''<article class="rank-card">
              <div class="card-head"><span class="rank">#{rank}</span><h2>{ticker}</h2>
                <div class="headline {excess_class}"><small>Excess annualized</small><strong>{pct(row, cols['excess'])}</strong></div>
              </div>
              <div class="chips">
                <span>Source years <b>{safe_float(row, '_source_years'):.1f}Y</b></span>
                <span>Run years <b>{run_years(row) or 'n/a'}</b></span>
                <span>Strategy ann. <b>{pct(row, cols['adaptive_annualized'])}</b></span>
                <span>Buy &amp; hold ann. <b>{pct(row, cols['buy_hold_annualized'])}</b></span>
                <span>Through <b>{html.escape(str(row.get(cols['through'], 'n/a')))}</b></span>
                {config_chip}
              </div>
              <button class="chart-button" type="button" data-src="{html.escape(chart_src, quote=True)}" data-title="{ticker}" aria-label="Open zoomable chart for {ticker}">
                <img src="{html.escape(chart_src, quote=True)}" alt="Strategy chart for {ticker}" loading="lazy"><span class="zoom-hint">Click to zoom</span>
              </button>
            </article>'''
        )
    return "".join(cards)


def render_excess_horizon_dashboard(rankings, output_path, source_path, considered, cols=HISTORY_COLUMNS):
    """Render the run-history dashboard with independent Source and Run year controls."""
    source_name, source_built_at, source_full = source_provenance(source_path)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tabs, panels = [], []
    for index, (key, label, _) in enumerate(SOURCE_HORIZONS):
        group = rankings[key]
        selected = "true" if index == 0 else "false"
        all_rows = group["views"]["all"]
        tabs.append(
            f'<button class="tab" type="button" role="tab" id="source-tab-{key}" data-source="{key}" aria-controls="source-panel-{key}" aria-selected="{selected}">{html.escape(label)} ({len(all_rows)})</button>'
        )
        run_tabs, run_panels = [], []
        for run_index, bucket in enumerate(["all", *group["run_buckets"]]):
            run_label = "All run years" if bucket == "all" else run_year_bucket_label(bucket)
            run_selected = "true" if run_index == 0 else "false"
            run_tabs.append(
                f'<button class="run-tab" type="button" role="tab" data-source="{key}" data-run="{bucket}" aria-controls="run-panel-{key}-{bucket}" aria-selected="{run_selected}">{run_label}</button>'
            )
            rows = group["views"][bucket]
            content = f'<div class="ranking-grid">{build_grouped_excess_cards(rows, cols)}</div>' if not rows.empty else '<div class="empty">No valid completed runs match this Source years and Run years comparison.</div>'
            run_panels.append(
                f'<div role="tabpanel" class="run-panel" id="run-panel-{key}-{bucket}" data-run-panel="{bucket}" {"" if run_index == 0 else "hidden"}>{content}</div>'
            )
        note = "Best non-zero excess-annualized run per ticker regardless of source or scored duration." if key == "mixed" else f"Best non-zero excess-annualized run per ticker from approximately {label.lower()} source data."
        panels.append(
            f'<section role="tabpanel" class="source-panel" id="source-panel-{key}" data-source-panel="{key}" aria-labelledby="source-tab-{key}" {"" if index == 0 else "hidden"}><p class="group-note">{html.escape(note)} {group["candidate_count"]} eligible run(s); choose a scored duration to narrow the comparison.</p><div class="run-tabs" role="tablist" aria-label="Run years for {html.escape(label)}">{"".join(run_tabs)}</div>{"".join(run_panels)}</section>'
        )

    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fund Backtest Dashboard — Excess Annualized by Source Years</title><style>{GROUPED_EXCESS_STYLE}</style></head><body>
<header><a class="master-link" href="dashboard.html">← Master dashboard</a><h1>Excess Annualized Ranking</h1><p>Best strategy excess over buy &amp; hold, grouped by source-data horizon and scored run duration · generated {generated_at}</p><p class="source">Source <code title="{html.escape(source_full, quote=True)}">{html.escape(source_name)}</code> last written {source_built_at} — ranking computed from {considered} run(s) with existing charts.</p><nav class="tabs" role="tablist" aria-label="Source years">{"".join(tabs)}</nav></header><main>{"".join(panels)}</main>
<dialog id="viewer"><div class="viewer-bar"><strong id="viewerTitle">Chart</strong><div class="controls"><button id="zoomOut" type="button">−</button><button id="resetZoom" type="button">Reset</button><button id="zoomIn" type="button">+</button><button id="closeViewer" type="button">Close</button></div></div><div class="viewport" id="viewport"><img id="viewerImage" alt=""></div></dialog>
<script>
const sourceTabs=[...document.querySelectorAll('.tab')],sourcePanels=[...document.querySelectorAll('.source-panel')];
function hashFor(source,run){{return `#${{source}}/${{run}}`;}} function currentRun(source){{const tabs=[...document.querySelectorAll(`.run-tab[data-source="${{source}}"]`)];return tabs.find(tab=>tab.getAttribute('aria-selected')==='true')?.dataset.run || tabs[0]?.dataset.run || 'all';}}
function selectRun(source,run,focus=false,updateHash=true){{const tabs=[...document.querySelectorAll(`.run-tab[data-source="${{source}}"]`)];const panels=[...document.querySelectorAll(`#source-panel-${{source}} .run-panel`)];if(!tabs.some(tab=>tab.dataset.run===run))run='all';tabs.forEach(tab=>{{const active=tab.dataset.run===run;tab.setAttribute('aria-selected',String(active));if(active&&focus)tab.focus();}});panels.forEach(panel=>panel.hidden=panel.dataset.runPanel!==run);if(updateHash&&history.replaceState)history.replaceState(null,'',hashFor(source,run));}}
function selectSource(source,focus=false,run=null){{if(!sourceTabs.some(tab=>tab.dataset.source===source))source='mixed';sourceTabs.forEach(tab=>{{const active=tab.dataset.source===source;tab.setAttribute('aria-selected',String(active));if(active&&focus)tab.focus();}});sourcePanels.forEach(panel=>panel.hidden=panel.dataset.sourcePanel!==source);selectRun(source,run||currentRun(source),false,true);}}
sourceTabs.forEach(tab=>tab.addEventListener('click',()=>selectSource(tab.dataset.source)));document.querySelector('.tabs').addEventListener('keydown',event=>{{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const current=sourceTabs.findIndex(tab=>tab.getAttribute('aria-selected')==='true');const next=event.key==='Home'?0:event.key==='End'?sourceTabs.length-1:event.key==='ArrowRight'?(current+1)%sourceTabs.length:(current-1+sourceTabs.length)%sourceTabs.length;selectSource(sourceTabs[next].dataset.source,true);}});
document.querySelectorAll('.run-tab').forEach(tab=>tab.addEventListener('click',()=>selectRun(tab.dataset.source,tab.dataset.run)));document.querySelectorAll('.run-tabs').forEach(nav=>nav.addEventListener('keydown',event=>{{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const tabs=[...nav.querySelectorAll('.run-tab')],current=tabs.findIndex(tab=>tab.getAttribute('aria-selected')==='true');const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:event.key==='ArrowRight'?(current+1)%tabs.length:(current-1+tabs.length)%tabs.length;selectRun(tabs[next].dataset.source,tabs[next].dataset.run,true);}}));
const requested=location.hash.slice(1).split('/');selectSource(requested[0]||'mixed',false,requested[1]||'all');
const viewer=document.getElementById('viewer'),viewport=document.getElementById('viewport'),image=document.getElementById('viewerImage');let scale=1,x=0,y=0,drag=false,startX=0,startY=0;function render(){{image.style.transform=`translate(calc(-50% + ${{x}}px),calc(-50% + ${{y}}px)) scale(${{scale}})`;}}function fit(){{if(!image.naturalWidth)return;scale=Math.min(1,(viewport.clientWidth-36)/image.naturalWidth,(viewport.clientHeight-86)/image.naturalHeight);x=0;y=0;render();}}function zoom(factor){{scale=Math.min(8,Math.max(.5,scale*factor));render();}}image.addEventListener('load',fit);document.querySelectorAll('.chart-button').forEach(button=>button.addEventListener('click',()=>{{image.src=button.dataset.src;image.alt=button.dataset.title;document.getElementById('viewerTitle').textContent=button.dataset.title;viewer.showModal();if(image.complete)fit();}}));document.getElementById('closeViewer').onclick=()=>viewer.close();document.getElementById('zoomIn').onclick=()=>zoom(1.25);document.getElementById('zoomOut').onclick=()=>zoom(.8);document.getElementById('resetZoom').onclick=fit;viewport.addEventListener('wheel',event=>{{event.preventDefault();zoom(event.deltaY<0?1.15:.87);}},{{passive:false}});viewport.addEventListener('pointerdown',event=>{{drag=true;startX=event.clientX-x;startY=event.clientY-y;viewport.setPointerCapture(event.pointerId);viewport.classList.add('dragging');}});viewport.addEventListener('pointermove',event=>{{if(!drag)return;x=event.clientX-startX;y=event.clientY-startY;render();}});viewport.addEventListener('pointerup',()=>{{drag=false;viewport.classList.remove('dragging');}});viewer.addEventListener('click',event=>{{if(event.target===viewer)viewer.close();}});
</script></body></html>'''
    output_path.write_text(page, encoding="utf-8")
    return output_path


def write_dashboard(df, cols, output_path, source_path, subtitle, provenance_note):
    cards = build_cards(df, cols)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_name, source_built_at, source_full = source_provenance(source_path)
    dashboard = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fund Backtest Dashboard — Excess Annualized Return</title>
  <style>
    :root{{--ink:#172033;--muted:#667085;--line:#dce2ea;--surface:#fff;--accent:#176b5b;--accent-soft:#e8f4f1;--bg:#f3f5f7;--pos:#12855b;--neg:#c9362c}}
    *{{box-sizing:border-box}}
    body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}}
    header{{position:sticky;top:0;z-index:10;padding:20px clamp(18px,4vw,52px);background:rgba(243,245,247,.94);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}}
    header h1{{margin:0 0 5px;font-size:clamp(1.45rem,3vw,2.2rem)}}
    header p{{margin:0;color:var(--muted)}}
    .source{{margin-top:6px!important;font-size:.82rem}}
    .source code{{padding:1px 5px;border-radius:5px;background:var(--accent-soft);color:var(--accent);font-size:.8rem}}
    .master-link{{display:inline-block;margin-bottom:9px;color:var(--accent);font-size:.84rem;font-weight:800;text-decoration:none}}
    .master-link:hover,.master-link:focus-visible{{text-decoration:underline}}
    main{{display:grid;gap:22px;padding:28px clamp(16px,3vw,42px) 56px;max-width:1900px;margin:auto}}
    .fund-card{{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 8px 26px rgba(19,33,55,.06)}}
    .card-heading,.card-heading>div,.metrics{{display:flex;align-items:center}}
    .card-heading{{justify-content:space-between;gap:18px;margin-bottom:13px}}
    .card-heading>div:first-child{{gap:10px;min-width:0}}
    .rank{{display:grid;place-items:center;min-width:38px;height:30px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-weight:800}}
    h2{{font-size:clamp(1rem,2vw,1.35rem);margin:0;overflow-wrap:anywhere}}
    .headline{{display:flex;flex-direction:column!important;align-items:flex-end!important;white-space:nowrap}}
    .headline span{{font-size:.76rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}}
    .headline strong{{font-size:1.35rem}}
    .headline.pos strong{{color:var(--pos)}}
    .headline.neg strong{{color:var(--neg)}}
    .metrics{{flex-wrap:wrap;gap:8px;margin-bottom:14px}}
    .metrics span{{padding:7px 10px;border-radius:9px;background:#f7f8fa;color:var(--muted);font-size:.84rem}}
    .metrics b{{color:var(--ink)}}
    .chart-button{{display:block;position:relative;width:100%;padding:0;border:0;border-radius:12px;overflow:hidden;background:#e8ebef;cursor:zoom-in}}
    .chart-button img{{display:block;width:100%;height:auto}}
    .zoom-hint{{position:absolute;right:12px;bottom:12px;padding:7px 10px;border-radius:8px;background:rgba(16,24,40,.78);color:#fff;font-size:.78rem;opacity:0;transition:opacity .18s}}
    .chart-button:hover .zoom-hint,.chart-button:focus-visible .zoom-hint{{opacity:1}}
    dialog{{width:calc(100vw - 24px);height:calc(100vh - 24px);max-width:none;max-height:none;padding:0;border:0;border-radius:16px;background:#111827;overflow:hidden}}
    dialog::backdrop{{background:rgba(3,8,18,.82)}}
    .viewer-bar{{position:absolute;inset:0 0 auto 0;z-index:3;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 14px;background:rgba(17,24,39,.9);color:white}}
    .viewer-bar strong{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .controls{{display:flex;gap:7px}}
    .controls button{{border:1px solid #667085;background:#263246;color:white;border-radius:8px;padding:7px 11px;cursor:pointer}}
    .viewport{{width:100%;height:100%;overflow:hidden;cursor:grab;touch-action:none}}
    .viewport.dragging{{cursor:grabbing}}
    #viewerImage{{position:absolute;left:50%;top:50%;max-width:none;transform-origin:center;user-select:none;pointer-events:none}}
    @media (min-width:1200px){{main{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
    @page{{size:A4 landscape;margin:8mm}}
    @media print{{
      body{{background:#fff}}
      header,dialog,.zoom-hint{{display:none!important}}
      main{{display:block;max-width:none;padding:0;margin:0}}
      .fund-card{{height:194mm;margin:0;padding:4mm;border:0;border-radius:0;box-shadow:none;overflow:hidden;break-inside:avoid;page-break-inside:avoid;break-after:page;page-break-after:always}}
      .fund-card:last-child{{break-after:auto;page-break-after:auto}}
      .card-heading{{margin-bottom:2mm}}
      .metrics{{margin-bottom:2mm;gap:1.5mm}}
      .metrics span{{padding:1.5mm 2mm}}
      .chart-button{{height:158mm;border-radius:0;cursor:default;overflow:hidden}}
      .chart-button img{{width:100%;height:100%;object-fit:contain}}
    }}
  </style>
</head>
<body>
  <header>
    <a class="master-link" href="dashboard.html">← Master dashboard</a>
    <h1>Fund Backtest Dashboard — Excess Annualized Return</h1>
    <p>{len(df)} funds · sorted by excess annualized return (strategy − buy &amp; hold) · {subtitle} · generated {generated_at}</p>
    <p class="source">Source <code title="{html.escape(source_full, quote=True)}">{html.escape(source_name)}</code> last written {source_built_at} — {html.escape(provenance_note)}</p>
  </header>
  <main>{''.join(cards) if cards else '<p>No completed results were available.</p>'}</main>
  <dialog id="viewer">
    <div class="viewer-bar"><strong id="viewerTitle">Chart</strong><div class="controls"><button id="zoomOut" type="button">−</button><button id="resetZoom" type="button">Reset</button><button id="zoomIn" type="button">+</button><button id="closeViewer" type="button">Close</button></div></div>
    <div class="viewport" id="viewport"><img id="viewerImage" alt=""></div>
  </dialog>
  <script>
    const viewer=document.getElementById('viewer'), viewport=document.getElementById('viewport'), image=document.getElementById('viewerImage');
    let scale=1,x=0,y=0,drag=false,startX=0,startY=0;
    function render(){{image.style.transform=`translate(calc(-50% + ${{x}}px),calc(-50% + ${{y}}px)) scale(${{scale}})`}}
    function fit(){{if(!image.naturalWidth)return;scale=Math.min(1,(viewport.clientWidth-36)/image.naturalWidth,(viewport.clientHeight-86)/image.naturalHeight);x=0;y=0;render()}}
    function reset(){{fit()}}
    function zoom(factor){{scale=Math.min(8,Math.max(.5,scale*factor));render()}}
    image.addEventListener('load',fit);
    document.querySelectorAll('.chart-button').forEach(button=>button.addEventListener('click',()=>{{image.src=button.dataset.src;image.alt=button.dataset.title;document.getElementById('viewerTitle').textContent=button.dataset.title;viewer.showModal();if(image.complete)fit()}}));
    document.getElementById('closeViewer').onclick=()=>viewer.close();
    document.getElementById('zoomIn').onclick=()=>zoom(1.25);document.getElementById('zoomOut').onclick=()=>zoom(.8);document.getElementById('resetZoom').onclick=reset;
    viewport.addEventListener('wheel',event=>{{event.preventDefault();zoom(event.deltaY<0?1.15:.87)}},{{passive:false}});
    viewport.addEventListener('pointerdown',event=>{{drag=true;startX=event.clientX-x;startY=event.clientY-y;viewport.setPointerCapture(event.pointerId);viewport.classList.add('dragging')}});
    viewport.addEventListener('pointermove',event=>{{if(!drag)return;x=event.clientX-startX;y=event.clientY-startY;render()}});
    viewport.addEventListener('pointerup',()=>{{drag=false;viewport.classList.remove('dragging')}});
    viewer.addEventListener('click',event=>{{if(event.target===viewer)viewer.close()}});
  </script>
</body>
</html>"""
    output_path.write_text(dashboard, encoding="utf-8")
    return output_path


def write_pdf(df, cols, pdf_path, source_path):
    # The HTML header is display:none in print, so the PDF needs its own provenance line.
    source_name, source_built_at, _ = source_provenance(source_path)
    provenance = f"Source {source_name} · last written {source_built_at}"

    def render(path):
        with PdfPages(path) as pdf:
            for rank, (_, row) in enumerate(df.iterrows(), start=1):
                chart_path = Path(str(row[cols["chart"]]))
                if not chart_path.exists():
                    continue
                figure = plt.figure(figsize=(11.69, 8.27), facecolor="white")
                fund_label = str(row.get("fund_label", "Unknown fund"))
                excess = safe_float(row, cols["excess"])
                excess_color = "#12855b" if np.isfinite(excess) and excess >= 0 else "#c9362c"
                figure.text(0.045, 0.948, f"#{rank}  {fund_label}", fontsize=17, fontweight="bold", color="#172033", va="top")
                figure.text(
                    0.955, 0.948,
                    f"Excess annualized {excess:+.2f}%" if np.isfinite(excess) else "Excess annualized n/a",
                    fontsize=15, fontweight="bold", color=excess_color, ha="right", va="top",
                )
                config = run_config_label(row)
                duration = run_years(row)
                metrics_line = (
                    f"Strategy annualized {safe_float(row, cols['adaptive_annualized']):+.2f}%    |    "
                    f"Buy & hold annualized {safe_float(row, cols['buy_hold_annualized']):+.2f}%    |    "
                    f"Strategy total {safe_float(row, cols['adaptive_return']):+.2f}%    |    "
                    f"Max drawdown {safe_float(row, cols['max_dd']):.2f}%    |    "
                    + (f"Run years {duration}    |    " if duration else "")
                    + f"Through {row.get(cols['through'], 'n/a')}"
                    + (f"    |    Run {config}" if config else "")
                )
                figure.text(0.045, 0.895, metrics_line, fontsize=9.5, color="#596579", va="top")
                # Footer, not header: the metrics line above is wide enough to collide.
                figure.text(0.955, 0.014, provenance, fontsize=7, color="#98a1b0", ha="right", va="bottom")
                chart_axis = figure.add_axes([0.035, 0.042, 0.93, 0.813])
                chart_axis.imshow(plt.imread(chart_path))
                chart_axis.set_axis_off()
                pdf.savefig(figure)
                plt.close(figure)

    try:
        render(pdf_path)
        return pdf_path
    except PermissionError:
        fallback = REPORTS_DIR / f"{pdf_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        render(fallback)
        print(f"Warning: {pdf_path} is locked. Saved PDF to {fallback}")
        return fallback


def resolve_path(value):
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def main():
    args = parse_args()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # --summary-file is an explicit request for the snapshot path.
    source = "summary" if args.summary_file else args.source

    if source == "history":
        source_path = resolve_path(args.history_file) if args.history_file else DEFAULT_HISTORY_FILE
        if not source_path.exists():
            raise FileNotFoundError(
                f"Run history not found: {source_path}. Run a backtest first, or pass --history-file."
            )
        cols = HISTORY_COLUMNS
        rankings, considered = load_excess_horizon_rankings(
            source_path, cols, args.top_funds
        )
        df = rankings["mixed"]["views"]["all"]
        subtitle = "best run per fund, ranked from the run history"
        provenance_note = (
            f"ranking computed here from {considered} run(s) in this file, so it is current with it."
        )
        suffix = ""
    else:
        source_path = resolve_path(args.summary_file) if args.summary_file else newest_summary_file()
        if not source_path.exists():
            raise FileNotFoundError(f"Summary file not found: {source_path}")
        cols = WINDOW_COLUMNS[args.window]
        df = load_ranked_results(source_path, cols, args.top_funds)
        considered = None
        subtitle = (
            "latest re-run window" if args.window == "latest" else "historical backtest window"
        )
        provenance_note = (
            "a snapshot — figures reflect the run history as of that time, not any later runs."
        )
        suffix = f"_summary_{args.window}"

    if df.empty:
        print(f"No usable rows with existing charts found in {source_path}. Nothing to render.")
        return 0

    dashboard_output = REPORTS_DIR / f"dashboard_excess_annualized{suffix}.html"
    if source == "history":
        dashboard_path = render_excess_horizon_dashboard(
            rankings, dashboard_output, source_path, considered, cols
        )
    else:
        dashboard_path = write_dashboard(
            df, cols, dashboard_output, source_path, subtitle, provenance_note,
        )
    pdf_path = write_pdf(df, cols, REPORTS_DIR / f"dashboard_excess_annualized{suffix}.pdf", source_path)

    print(f"Source ({source}): {source_path}")
    if considered is not None:
        print(f"Ranked {len(df)} fund(s) from {considered} run(s) by excess annualized return:")
    else:
        print(f"Ranked {len(df)} fund(s) by excess annualized return ({args.window} window):")
    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        config = run_config_label(row)
        detail = f"   [{config}]" if config else ""
        print(f"  #{rank:>2}  {str(row.get('fund_label','?')):<9}  {pct(row, cols['excess']):>9}{detail}")
    print(f"\nDashboard saved to: {dashboard_path}")
    print(f"One-fund-per-page PDF saved to: {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
