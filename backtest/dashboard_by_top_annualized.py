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
    python dashboard_by_top_annualized.py --basis buy-hold --derive-buyhold-horizons 20y 10y 5y 4y 3y 2y 1y
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
        choices=("20y", "10y", "5y", "4y", "3y", "2y", "1y"),
        default=("20y", "10y", "5y", "4y", "3y", "2y", "1y"),
        metavar="HORIZON",
        help="Regenerate every eligible ticker in each selected buy-and-hold horizon "
             "from local price history. --derive-missing-horizons is a compatibility "
             "alias. Default: all supported horizons. "
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
    ("2y", "2 years", (1.75, 2.25)),
    ("1y", "1 year", (0.75, 1.25)),
)
DEFAULT_DERIVED_BUY_HOLD_HORIZONS = tuple(
    key for key, _, _ in BUY_HOLD_HORIZONS if key != "mixed"
)

# Source-data horizon bucket for the two-axis "top annualized" dashboard. Unlike
# BUY_HOLD_HORIZONS this has an "other" catch-all and omits 2y/1y: they exist there
# only because buy-and-hold can derive them from local price data, while the top
# ranking is purely history-derived.
TOP_SOURCE_HORIZONS = (
    ("mixed", "Mixed", None),
    ("20y", "20 years", (19.0, 21.0)),
    ("10y", "10 years", (9.0, 11.0)),
    ("5y", "5 years", (4.75, 5.25)),
    ("4y", "4 years", (3.75, 4.25)),
    ("3y", "3 years", (2.75, 3.25)),
    ("other", "Other", None),
)

TOP_HISTORY_COLUMNS = {
    "adaptive": ADAPTIVE_COLUMN,
    "buy_hold": BUY_HOLD_COLUMN,
    "chart": CHART_COLUMN,
}


def safe_float(row, key, default=np.nan):
    value = row.get(key, default)
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
    for key, _, year_range in TOP_SOURCE_HORIZONS:
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


def load_local_buy_hold_price_series(data_dir=None, years=10):
    """Return eligible full-ticker local price windows for one horizon.

    Each result carries its raw price observations and matching provenance.  It
    is shared by the derived rankings and the consolidated comparison charts,
    keeping both views on precisely the same eligibility and trailing-window
    rules.
    """
    data_dir = Path(data_dir or REPO_ROOT / "data")
    series = []
    for source in sorted(data_dir.glob("*.csv")):
        # Full ticker files are the source for a derived horizon window;
        # -3Y/-4Y/-5Y slices cannot provide an independent comparison.
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
        series.append(
            {
                "ticker": source.stem,
                "data_file": str(source),
                "price_column": price_column,
                "data_start": start.strftime("%Y-%m-%d"),
                "data_end": end.strftime("%Y-%m-%d"),
                "source_years": elapsed_days / 365.25,
                "values": window.reset_index(drop=True),
            }
        )
    return sorted(series, key=lambda item: item["ticker"])


def build_data_derived_buy_hold_rows(data_dir=None, years=10):
    """Rank full local price histories by a trailing buy-and-hold window."""
    rows = []
    for item in load_local_buy_hold_price_series(data_dir, years):
        values = item["values"]
        annualized = (
            (values["Price"].iloc[-1] / values["Price"].iloc[0])
            ** (1 / item["source_years"])
            - 1
        ) * 100
        ticker = item["ticker"]
        rows.append(
            {
                "fund_label": ticker,
                "fund_slice_label": ticker,
                "data_file": item["data_file"],
                "price_column": item["price_column"],
                "data_start": item["data_start"],
                "data_end": item["data_end"],
                "backtest_start": item["data_start"],
                "backtest_end": item["data_end"],
                "_ticker": ticker,
                "_row_label": ticker,
                "_top": annualized,
                "_buy_hold": annualized,
                "_adaptive": np.nan,
                "_winner": BUY_HOLD_LABEL,
                "_source_years": item["source_years"],
                "_data_derived": True,
            }
        )
    return pd.DataFrame(rows).sort_values(["_top", "_ticker"], ascending=[False, True]).reset_index(drop=True) if rows else pd.DataFrame()


def load_buy_hold_horizon_rankings(
    history_path, top_funds=0,
    derived_horizons=DEFAULT_DERIVED_BUY_HOLD_HORIZONS,
):
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


def _top_winner(adaptive, buy_hold):
    """Attribution badge for a run's top-annualized number."""
    if adaptive is not None and adaptive >= buy_hold:
        return STRATEGY_LABEL
    return BUY_HOLD_LABEL


def prepare_top_candidates(history_path, basis):
    """Load completed chart-backed rows tagged with source/run year buckets.

    The two-axis top-annualized dashboard ranks by ``_top`` = max(strategy ann.,
    buy & hold ann.) per run, with ``_winner`` recording which of the two produced
    it. Source horizon and run-year bucket are derived from the data and scored
    windows independently, exactly as the excess dashboard does.
    """
    df = pd.read_csv(history_path, low_memory=False)
    considered = len(df)

    if "run_status" in df.columns:
        status = df["run_status"].fillna("completed").astype(str).str.lower()
        df = df[status.isin(["completed", "nan", ""])]

    required = ("adaptive", "buy_hold", "chart")
    missing = [key for key in required if TOP_HISTORY_COLUMNS[key] not in df.columns]
    if missing:
        raise ValueError(
            f"Run history is missing required column(s): "
            f"{[TOP_HISTORY_COLUMNS[key] for key in missing]}"
        )

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
        df["_winner"] = df[["_adaptive", "_buy_hold"]].apply(
            lambda series: _top_winner(series["_adaptive"], series["_buy_hold"]),
            axis=1,
        )

    df = df.dropna(subset=["_top"])
    df = df[df[CHART_COLUMN].notna()]
    df = df[df[CHART_COLUMN].map(lambda path: Path(str(path)).exists())].copy()

    date_columns = ("data_start", "data_end", "backtest_start", "backtest_end")
    missing_dates = [column for column in date_columns if column not in df.columns]
    if missing_dates:
        raise ValueError(f"Run history is missing required column(s): {missing_dates}")

    df["_source_years"] = df.apply(
        lambda row: elapsed_years(row, "data_start", "data_end"), axis=1
    )
    df["_scored_years"] = df.apply(
        lambda row: elapsed_years(row, "backtest_start", "backtest_end", "data_end"),
        axis=1,
    )
    df = df.dropna(subset=["_source_years", "_scored_years"])
    if df.empty:
        return df, considered

    df["_row_label"] = df.get("fund_slice_label")
    if "fund_slice_label" in df.columns:
        df["_row_label"] = df["fund_slice_label"].fillna("").astype(str).str.strip()
    else:
        df["_row_label"] = ""
    df.loc[df["_row_label"] == "", "_row_label"] = df["fund_label"].astype(str)

    df["_ticker"] = df["_row_label"].map(fund_group_from_label)
    df["_source_horizon"] = df["_source_years"].map(source_horizon_key)
    df["_run_bucket"] = df["_scored_years"].map(run_year_bucket)

    if "run_started_at" in df.columns:
        df["_started"] = pd.to_datetime(df["run_started_at"], errors="coerce")
    else:
        df["_started"] = pd.NaT
    return df.sort_values(["_top", "_started"], ascending=[False, False]), considered


def ranked_top_rows(candidates, top_funds=0):
    """Best candidate per ticker by top-annualized return; newest run breaks ties."""
    if candidates.empty:
        return candidates.copy()
    candidates = candidates.sort_values(["_top", "_started"], ascending=[False, False])
    ranked = (
        candidates.groupby("_ticker", sort=False, as_index=False)
        .head(1)
        .sort_values(["_top", "_started"], ascending=[False, False])
    )
    if top_funds and top_funds > 0:
        ranked = ranked.head(top_funds)
    return ranked.reset_index(drop=True)


def load_top_annualized_horizon_rankings(history_path, basis, cols=TOP_HISTORY_COLUMNS, top_funds=0):
    """Build Source years x Run years rankings for the top-annualized dashboard."""
    candidates, considered = prepare_top_candidates(history_path, basis)
    rankings = {}
    for key, label, _ in TOP_SOURCE_HORIZONS:
        scoped = (
            candidates
            if key == "mixed"
            else candidates[candidates["_source_horizon"] == key]
        )
        run_buckets = (
            sorted(
                scoped["_run_bucket"].dropna().unique().tolist(),
                key=run_year_bucket_sort_key,
            )
            if not scoped.empty
            else []
        )
        views = {"all": ranked_top_rows(scoped, top_funds)}
        for bucket in run_buckets:
            views[bucket] = ranked_top_rows(
                scoped[scoped["_run_bucket"] == bucket], top_funds
            )
        rankings[key] = {
            "label": label,
            "candidate_count": len(scoped),
            "run_buckets": run_buckets,
            "views": views,
        }
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


def _comparison_horizon_key(source_years):
    """Select the closest available price-comparison tab for a historical row."""
    if source_years is None or pd.isna(source_years):
        return None
    for key, _, year_range in BUY_HOLD_HORIZONS:
        if year_range is not None and year_range[0] <= source_years <= year_range[1]:
            return key
    candidates = [
        (abs(source_years - sum(year_range) / 2), key)
        for key, _, year_range in BUY_HOLD_HORIZONS
        if year_range is not None
    ]
    return min(candidates)[1] if candidates else None


def _scored_years_value(row):
    start = pd.to_datetime(row.get("backtest_start"), errors="coerce")
    end = pd.to_datetime(row.get("backtest_end") or row.get("data_end"), errors="coerce")
    if pd.isna(start) or pd.isna(end) or end <= start:
        return float("nan")
    return (end - start).days / 365.25


def _buy_hold_ranking_table(rows, key):
    """Render a compact, sortable table from the same ranked rows as the cards."""
    table_rows = []
    for rank, (_, row) in enumerate(rows.iterrows(), start=1):
        ticker = html.escape(str(row.get("_ticker", "Unknown")))
        top_value = pd.to_numeric(row.get("_top"), errors="coerce")
        strategy_value = pd.to_numeric(row.get("_adaptive"), errors="coerce")
        source_value = pd.to_numeric(row.get("_source_years"), errors="coerce")
        scored_value = _scored_years_value(row)
        source_text = f"{source_value:.1f}Y" if pd.notna(source_value) else "n/a"
        scored_text = f"{scored_value:.1f}Y" if pd.notna(scored_value) else "n/a"
        if key == "mixed":
            source_value = scored_value
            source_text = scored_text
        comparison_key = _comparison_horizon_key(row.get("_source_years"))
        annualized = html.escape(format_pct(top_value))
        annualized_html = (
            f'<a class="table-return" href="#{comparison_key}" title="View the {comparison_key.removesuffix("y")}-year comparison">{annualized}</a>'
            if key == "mixed" and comparison_key
            else annualized
        )
        tone = "neg" if pd.notna(top_value) and top_value < 0 else "pos"
        through = html.escape(str(row.get("data_end", "n/a")))
        table_rows.append(
            f'''<tr><td class="table-rank" data-sort-value="{rank}">{rank}</td>
              <td data-sort-value="{ticker}"><b>{ticker}</b></td>
              <td class="{tone}" data-sort-value="{top_value if pd.notna(top_value) else ''}">{annualized_html}</td>
              <td data-sort-value="{source_value if pd.notna(source_value) else ''}">{source_text}</td>
              <td data-sort-value="{scored_value if pd.notna(scored_value) else ''}">{scored_text}</td>
              <td data-sort-value="{strategy_value if pd.notna(strategy_value) else ''}">{html.escape(format_pct(strategy_value))}</td>
              <td data-sort-value="{through}">{through}</td></tr>'''
        )
    return f'''<div class="table-view" data-view-content="table" hidden>
      <div class="table-wrap" tabindex="0"><table class="ranking-table">
        <caption>Stock ranking — compact sortable view</caption>
        <thead><tr>
          <th><button class="table-sort" data-sort-type="number">Rank</button></th>
          <th><button class="table-sort" data-sort-type="text">Ticker</button></th>
          <th><button class="table-sort" data-sort-type="number" data-sort-desc="true">Buy &amp; hold ann.</button></th>
          <th><button class="table-sort" data-sort-type="number">Source years</button></th>
          <th><button class="table-sort" data-sort-type="number">Scored years</button></th>
          <th><button class="table-sort" data-sort-type="number">Strategy ann.</button></th>
          <th><button class="table-sort" data-sort-type="text">Through</button></th>
        </tr></thead><tbody>{''.join(table_rows)}</tbody>
      </table></div></div>'''


COMPARISON_COLORS = (
    "#176b5b", "#2f6fed", "#b54708", "#7a3e9d", "#c9362c", "#007a8a",
    "#8a5a00", "#4f46e5", "#a61b57", "#0f766e", "#7c2d12", "#365314",
    "#1d4ed8", "#9f1239", "#6d28d9", "#047857",
)


def _comparison_points(values, start, end, low, high):
    """Map one normalized series to the shared consolidated-chart viewport."""
    if len(values) > 240:
        indexes = np.linspace(0, len(values) - 1, 240, dtype=int)
        values = values.iloc[indexes]
    normalized = 10000.0 * values["Price"] / values["Price"].iloc[0]
    date_span = max((end - start).days, 1)
    value_span = max(high - low, 1.0)
    xs = 58 + ((values["Date"] - start).dt.days / date_span) * 724
    ys = 188 - ((normalized - low) / value_span) * 148
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return points, float(normalized.iloc[-1])


def consolidated_buy_hold_svg(series, years):
    """Render a normalized local-price comparison for one source-data horizon."""
    if not series:
        return '<div class="comparison-missing">No eligible local price histories are available for this comparison.</div>'

    start = min(item["values"]["Date"].iloc[0] for item in series)
    end = max(item["values"]["Date"].iloc[-1] for item in series)
    normalized_sets = [
        10000.0 * item["values"]["Price"] / item["values"]["Price"].iloc[0]
        for item in series
    ]
    low = min(float(values.min()) for values in normalized_sets)
    high = max(float(values.max()) for values in normalized_sets)
    pad = max((high - low) * 0.08, 500.0)
    low = max(0.0, low - pad)
    high += pad

    lines = []
    legend = []
    for index, item in enumerate(series):
        color = COMPARISON_COLORS[index % len(COMPARISON_COLORS)]
        points, final_value = _comparison_points(item["values"], start, end, low, high)
        ticker = html.escape(item["ticker"])
        total_return = (final_value / 10000.0 - 1) * 100
        lines.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.4" '
            f'stroke-linecap="round" stroke-linejoin="round"><title>{ticker}: '
            f'${final_value:,.0f} ({total_return:+.2f}%)</title></polyline>'
        )
        legend.append(
            f'<li><i style="background:{color}"></i><b>{ticker}</b> '
            f'${final_value:,.0f} · {total_return:+.2f}% · {item["source_years"]:.1f}Y</li>'
        )

    start_label = start.strftime("%Y-%m-%d")
    end_label = end.strftime("%Y-%m-%d")
    period_note = (
        "Each line uses up to 20 years of available local history and begins on its own first available date; start dates vary."
        if years == 20
        else f"Each line starts at $10,000 on the shared trailing {years}-year window."
    )
    chart = f"""
      <div class="consolidated-chart" role="group" aria-label="{years}-year normalized local-price comparison">
        <div class="comparison-heading"><div><h2>Local-price normalized growth</h2>
          <p>{period_note} This is a buy-and-hold comparison, not a strategy result.</p></div>
          <span>{len(series)} tickers · {start_label} to {end_label}</span></div>
        <svg viewBox="0 0 840 230" role="img" aria-label="Normalized $10,000 buy-and-hold comparison for {years} years">
          <line x1="58" y1="188" x2="782" y2="188" stroke="#dce2ea"/>
          <line x1="58" y1="114" x2="782" y2="114" stroke="#e9edf2" stroke-dasharray="4 5"/>
          <text x="4" y="34" fill="#667085" font-size="11">${high:,.0f}</text>
          <text x="4" y="190" fill="#667085" font-size="11">${low:,.0f}</text>
          <text x="58" y="214" fill="#667085" font-size="11">{start_label}</text>
          <text x="782" y="214" text-anchor="end" fill="#667085" font-size="11">{end_label}</text>
          {''.join(lines)}
        </svg>
        <ul class="comparison-legend">{''.join(legend)}</ul>
      </div>
    """
    return "\n".join(line.rstrip() for line in chart.splitlines())


BUY_HOLD_GROUPED_STYLE = """
  :root{--ink:#172033;--muted:#667085;--line:#dce2ea;--surface:#fff;--accent:#176b5b;--accent-soft:#e8f4f1;--bg:#f3f5f7;--pos:#12855b;--neg:#c9362c}
  *{box-sizing:border-box} [hidden]{display:none!important}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}
  body.dark{--ink:#edf2f7;--muted:#a8b3c2;--line:#344252;--surface:#18222d;--accent:#72d2bb;--accent-soft:#203e3c;--bg:#0d141c;--pos:#72d2bb;--neg:#ff8177}
  body.dark header{background:rgba(13,20,28,.96)}body.dark .source code,body.dark .chips span{background:#22303d;color:var(--muted)}body.dark .consolidated-chart,body.dark .rank-card,body.dark .table-wrap{box-shadow:0 8px 24px rgba(0,0,0,.24)}body.dark .simple-chart{background:#111b25}body.dark .ranking-table th{background:#202d39}body.dark .ranking-table tbody tr:hover{background:#22303d}body.dark .consolidated-chart svg line{stroke:#405060}body.dark .consolidated-chart svg text{fill:#a8b3c2}
  header{position:sticky;top:0;z-index:10;padding:17px clamp(16px,4vw,48px) 13px;background:rgba(243,245,247,.96);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
  .back-link{display:inline-flex;align-items:center;margin-bottom:7px;color:var(--accent);font-size:.78rem;font-weight:800;text-decoration:none}.back-link:hover{text-decoration:underline}
  .title-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px}.title-row h1{margin:0}.theme-toggle{margin-left:auto;padding:7px 11px;border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--ink);font:inherit;font-size:.78rem;font-weight:800;cursor:pointer}.theme-toggle:hover,.theme-toggle:focus-visible{border-color:var(--accent);color:var(--accent)}
  h1{margin:0 0 4px;font-size:clamp(1.4rem,3vw,2.05rem)} header p{margin:0;color:var(--muted);font-size:.88rem}
  .historical-link{display:inline-flex;align-items:center;padding:7px 11px;border:1px solid #8fc5b6;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-size:.78rem;font-weight:800;text-decoration:none}.historical-link:hover,.historical-link:focus-visible{text-decoration:underline}
  .source{margin-top:5px;font-size:.76rem}.source code{padding:1px 5px;border-radius:5px;background:var(--accent-soft);color:var(--accent)}
  .tabs{display:flex;gap:7px;overflow-x:auto;margin-top:12px;padding-bottom:2px}
  .tab{flex:0 0 auto;padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--ink);font:inherit;font-size:.8rem;font-weight:750;cursor:pointer}
  .tab[aria-selected="true"]{border-color:#8fc5b6;background:var(--accent-soft);color:var(--accent)}
  main{margin:0;padding:24px clamp(16px,4vw,48px) 56px}
  .group-note{margin:0 0 14px;color:var(--muted);font-size:.87rem}
  .consolidated-chart{margin:0 0 18px;padding:15px;border:1px solid var(--line);border-radius:16px;background:var(--surface);box-shadow:0 7px 22px rgba(19,33,55,.05)}
  .comparison-heading{display:flex;justify-content:space-between;gap:14px;align-items:start}.comparison-heading h2{font-size:1rem}.comparison-heading p{margin:4px 0 0;color:var(--muted);font-size:.8rem;line-height:1.4}.comparison-heading>span{flex:0 0 auto;color:var(--muted);font-size:.76rem;text-align:right}
  .consolidated-chart svg{display:block;width:100%;height:auto;max-height:250px;margin-top:12px}.comparison-legend{display:flex;flex-wrap:wrap;gap:6px 12px;margin:8px 0 0;padding:0;list-style:none;color:var(--muted);font-size:.73rem}.comparison-legend li{white-space:nowrap}.comparison-legend i{display:inline-block;width:9px;height:9px;margin-right:4px;border-radius:999px}.comparison-legend b{color:var(--ink)}
  .view-switch{display:flex;gap:7px;margin:0 0 12px}.view-toggle{padding:7px 10px;border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--ink);font:inherit;font-size:.76rem;font-weight:750;cursor:pointer}.view-toggle[aria-pressed="true"]{border-color:#8fc5b6;background:var(--accent-soft);color:var(--accent)}
  .table-view{min-width:0}.table-wrap{overflow:visible;border:1px solid var(--line);border-radius:14px;background:var(--surface);box-shadow:0 7px 22px rgba(19,33,55,.05)}.ranking-table{width:100%;border-collapse:collapse;font-size:.78rem;white-space:nowrap}.ranking-table caption{padding:10px 12px;text-align:left;color:var(--muted);font-size:.75rem;font-weight:700}.ranking-table th{position:sticky;top:0;z-index:1;background:#f7f9fb;border-bottom:1px solid var(--line);text-align:left}.ranking-table td{padding:8px 10px;border-bottom:1px solid #edf0f4}.ranking-table tbody tr:last-child td{border-bottom:0}.ranking-table tbody tr:hover{background:#f8fafc}.ranking-table .table-rank{color:var(--muted);font-weight:800}.ranking-table .pos{color:var(--pos);font-weight:850}.ranking-table .neg{color:var(--neg);font-weight:850}.table-sort{width:100%;padding:8px 10px;border:0;background:transparent;color:var(--muted);font:inherit;font-weight:800;text-align:left;cursor:pointer}.table-sort:hover,.table-sort:focus-visible{color:var(--accent)}.table-return{color:inherit;text-decoration:none}.table-return:hover{text-decoration:underline}
  .ranking-grid{display:grid;gap:14px;grid-template-columns:repeat(2,minmax(0,1fr))}
  .rank-card{min-width:0;padding:15px;border:1px solid var(--line);border-radius:16px;background:var(--surface);box-shadow:0 7px 22px rgba(19,33,55,.05)}
  .card-head{display:flex;align-items:center;gap:10px}.rank{display:grid;place-items:center;min-width:36px;height:29px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-weight:850}
  h2{margin:0;font-size:1.12rem}.headline{margin-left:auto;text-align:right}.headline small{display:block;color:var(--muted);font-size:.66rem;text-transform:uppercase;letter-spacing:.05em}.headline strong{font-size:1.22rem}.headline.pos strong{color:var(--pos)}.headline.neg strong{color:var(--neg)}.headline-link{text-decoration:none}.headline-link:hover strong{text-decoration:underline}
  .chips{display:flex;flex-wrap:wrap;gap:6px;margin:11px 0}.chips span{padding:6px 8px;border-radius:8px;background:#f7f8fa;color:var(--muted);font-size:.75rem}.chips b{color:var(--ink)}
  .simple-chart{margin:0;padding:7px 9px 8px;border-radius:11px;background:#f8faf9}.simple-chart svg{display:block;width:100%;height:auto;max-height:150px}
  .chart-endpoints{display:grid;grid-template-columns:1fr 1fr;gap:14px;color:var(--muted);font-size:.73rem}.endpoint{display:grid;gap:2px}.endpoint-end{text-align:right}.endpoint-date{font-weight:750;color:var(--ink)}.endpoint small{margin-right:4px;font-size:.66rem;text-transform:uppercase;letter-spacing:.035em}.endpoint strong{color:var(--ink)}
  .chart-missing,.comparison-missing,.empty{padding:34px 18px;border:1px dashed #bcc5cf;border-radius:14px;background:rgba(255,255,255,.55);color:var(--muted);text-align:center}
  @media(min-width:1500px){.ranking-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.rank-card{padding:12px}.chips{margin:8px 0;gap:5px}.chips span{padding:5px 7px;font-size:.72rem}.simple-chart svg{height:112px;max-height:112px}}
  @media(min-width:2100px){.ranking-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.simple-chart svg{height:96px;max-height:96px}}
  @media(max-width:760px){.comparison-heading{display:block}.comparison-heading>span{display:block;margin-top:7px;text-align:left}.ranking-grid{grid-template-columns:1fr}.chart-endpoints{grid-template-columns:1fr;gap:8px}.endpoint-end{text-align:left}}
"""


def render_buy_hold_horizon_dashboard(
    rankings, output_path, source_path, considered, comparison_data_dir=None
):
    source_name, source_built_at, source_full = source_provenance(source_path)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    comparisons = {
        key: load_local_buy_hold_price_series(comparison_data_dir, int(key.removesuffix("y")))
        for key, _, _ in BUY_HOLD_HORIZONS
        if key != "mixed"
    }
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
            scored_years = _scored_years(row)
            source_years_text = (
                f"{float(source_years):.1f}Y"
                if source_years is not None and pd.notna(source_years)
                else "n/a"
            )
            comparison_key = _comparison_horizon_key(source_years)
            mixed_summary = key == "mixed"
            if mixed_summary:
                # The summary's return is scored over this run window, so show
                # that same duration in both chips and send readers to the
                # corresponding standardized comparison tab for the chart.
                source_years_text = scored_years
                simple_chart = simple_buy_hold_svg(row)
                chart_html = simple_chart or '<div class="chart-missing">Simple price chart unavailable for this run.</div>'
                headline_tag = "a" if comparison_key else "div"
                headline_href = (
                    f' href="#{comparison_key}" title="View the {comparison_key.removesuffix("y")}-year comparison"'
                    if comparison_key
                    else ""
                )
                headline_class = "headline headline-link" if comparison_key else "headline"
            else:
                simple_chart = simple_buy_hold_svg(row)
                chart_html = simple_chart or '<div class="chart-missing">Simple price chart unavailable for this run.</div>'
                headline_tag = "div"
                headline_href = ""
                headline_class = "headline"
            top_value = pd.to_numeric(row.get("_top"), errors="coerce")
            headline_class += " pos" if pd.notna(top_value) and top_value >= 0 else " neg"
            data_derived = bool(row.get("_data_derived", False))
            provenance_chip = (
                '<span>Comparison <b>Derived from local price data</b></span>'
                if data_derived
                else f'<span>Winning run <b>{descriptor}</b></span>'
            )
            cards.append(
                f"""<article class="rank-card">
                  <div class="card-head"><span class="rank">#{rank}</span><h2>{ticker}</h2>
                    <{headline_tag} class="{headline_class}"{headline_href}><small>Buy &amp; hold annualized</small><strong>{format_pct(row.get('_top'))}</strong></{headline_tag}>
                  </div>
                  <div class="chips">
                    <span>Source years <b>{source_years_text}</b></span>
                    <span>Scored years <b>{scored_years}</b></span>
                    <span>Strategy ann. <b>{format_pct(row.get('_adaptive'))}</b></span>
                    <span>Through <b>{html.escape(str(row.get('data_end', 'n/a')))}</b></span>
                    {provenance_chip}
                  </div>{chart_html}
                </article>"""
            )
        cards_content = (
            f'<div class="ranking-grid">{"".join(cards)}</div>'
            if cards
            else f'<div class="empty">No valid {html.escape(label)} source-data runs with usable ranking evidence are currently available.</div>'
        )
        content = (
            f'<div class="view-switch" role="group" aria-label="Display mode for {html.escape(label)}">'
            f'<button class="view-toggle" type="button" data-view="chart" aria-pressed="true">Chart cards</button>'
            f'<button class="view-toggle" type="button" data-view="table" aria-pressed="false">Compact table</button></div>'
            f'<div data-view-content="chart">{cards_content}</div>{_buy_hold_ranking_table(rows, key)}'
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
        comparison_html = (
            consolidated_buy_hold_svg(comparisons[key], int(key.removesuffix("y")))
            if key != "mixed"
            else ""
        )
        panels.append(
            f'<section role="tabpanel" id="panel-{key}" aria-labelledby="tab-{key}" '
            f'{"hidden" if index else ""}><p class="group-note">{html.escape(note)} '
            f'{html.escape(evidence_note)}</p>{comparison_html}{content}</section>'
        )

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fund Backtest Dashboard — Buy &amp; Hold Annualized by Source Years</title>
<style>{BUY_HOLD_GROUPED_STYLE}</style></head><body>
<header><a class="back-link" href="dashboard.html">← Master dashboard</a><div class="title-row"><h1>Buy &amp; Hold Annualized Ranking</h1><a class="historical-link" href="dashboard_top_buyhold_historical.html">Turn Back The Clock</a><button id="themeToggle" class="theme-toggle" type="button" aria-pressed="false">Dark mode</button></div>
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
  function selectRequestedHash(){{const requested=location.hash.slice(1);if(tabs.some(tab=>tab.dataset.group===requested))selectGroup(requested);}}
  selectRequestedHash();window.addEventListener('hashchange',selectRequestedHash);
  document.querySelectorAll('.view-toggle').forEach(button=>button.addEventListener('click',()=>{{
    const panel=button.closest('[role="tabpanel"]'),view=button.dataset.view;
    panel.querySelectorAll('.view-toggle').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
    panel.querySelectorAll('[data-view-content]').forEach(item=>item.hidden=item.dataset.viewContent!==view);
  }}));
  document.querySelectorAll('.ranking-table').forEach(table=>table.querySelectorAll('.table-sort').forEach((button,index)=>button.addEventListener('click',()=>{{
    const body=table.tBodies[0],type=button.dataset.sortType,descending=button.dataset.sortedDesc==='true' ? false : button.dataset.sortDesc==='true';
    const rows=[...body.rows].sort((left,right)=>{{const a=left.cells[index].dataset.sortValue,b=right.cells[index].dataset.sortValue;let result=type==='number'?(Number(a||'-Infinity')-Number(b||'-Infinity')):a.localeCompare(b);return descending?-result:result;}});
    body.append(...rows);[...body.rows].forEach((row,rank)=>{{row.cells[0].textContent=rank+1;row.cells[0].dataset.sortValue=rank+1;}});
    table.querySelectorAll('.table-sort').forEach(item=>{{item.dataset.sortedDesc='';item.removeAttribute('aria-sort');}});button.dataset.sortedDesc=String(descending);button.setAttribute('aria-sort',descending?'descending':'ascending');
  }})));
  const themeToggle=document.getElementById('themeToggle');
  function setTheme(dark,save=true){{document.body.classList.toggle('dark',dark);themeToggle.setAttribute('aria-pressed',String(dark));themeToggle.textContent=dark?'Light mode':'Dark mode';if(save){{try{{localStorage.setItem('buyhold-theme',dark?'dark':'light')}}catch(error){{}}}}}}
  let savedTheme=null;try{{savedTheme=localStorage.getItem('buyhold-theme')}}catch(error){{}}
  setTheme(savedTheme?savedTheme==='dark':window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches,false);themeToggle.addEventListener('click',()=>setTheme(!document.body.classList.contains('dark')));
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


TOP_GROUPED_STYLE = """
  :root{--ink:#172033;--muted:#667085;--line:#dce2ea;--surface:#fff;--accent:#176b5b;--accent-soft:#e8f4f1;--bg:#f3f5f7;--pos:#12855b;--neg:#c9362c}
  *{box-sizing:border-box} [hidden]{display:none!important}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}
  header{position:sticky;top:0;z-index:10;padding:17px clamp(16px,4vw,48px) 13px;background:rgba(243,245,247,.96);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
  .master-link{display:inline-block;margin-bottom:8px;color:var(--accent);font-size:.83rem;font-weight:800;text-decoration:none}.master-link:hover,.master-link:focus-visible{text-decoration:underline}
  h1{margin:0 0 4px;font-size:clamp(1.4rem,3vw,2.05rem)} header p{margin:0;color:var(--muted);font-size:.88rem}
  .source{margin-top:5px;font-size:.76rem}.source code{padding:1px 5px;border-radius:5px;background:var(--accent-soft);color:var(--accent)}
  .tabs,.run-tabs{display:flex;gap:7px;overflow-x:auto;padding-bottom:2px}.tabs{margin-top:12px}.run-tabs{margin:0 0 14px}
  .tab,.run-tab{flex:0 0 auto;padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--ink);font:inherit;font-size:.8rem;font-weight:750;cursor:pointer}
  .tab[aria-selected=true],.run-tab[aria-selected=true]{border-color:#8fc5b6;background:var(--accent-soft);color:var(--accent)}
  main{margin:0;padding:24px clamp(16px,4vw,48px) 56px}.group-note{margin:0 0 14px;color:var(--muted);font-size:.87rem}
  .ranking-grid{display:grid;gap:14px;grid-template-columns:repeat(2,minmax(0,1fr))}
  .rank-card{min-width:0;padding:15px;border:1px solid var(--line);border-radius:16px;background:var(--surface);box-shadow:0 7px 22px rgba(19,33,55,.05)}
  .card-head{display:flex;align-items:center;gap:10px}.rank{display:grid;place-items:center;min-width:36px;height:29px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-weight:850}
  h2{margin:0;font-size:1.12rem;overflow-wrap:anywhere}.headline{margin-left:auto;text-align:right}.headline small{display:block;color:var(--muted);font-size:.66rem;text-transform:uppercase;letter-spacing:.05em}.headline strong{font-size:1.22rem}.headline.pos strong{color:var(--pos)}.headline.neg strong{color:var(--neg)}
  .badge{display:inline-block;margin-left:8px;padding:3px 9px;border-radius:999px;background:#eef1f5;color:#4a5568;font-size:.72rem;font-weight:700;text-transform:none;letter-spacing:0;vertical-align:middle}
  .badge.strategy{background:#e8f4f1;color:#176b5b}.badge.market{background:#fdf0e6;color:#96591f}
  .chips{display:flex;flex-wrap:wrap;gap:6px;margin:11px 0}.chips span{padding:6px 8px;border-radius:8px;background:#f7f8fa;color:var(--muted);font-size:.75rem}.chips b{color:var(--ink)}
  .chart-button{display:block;position:relative;width:100%;padding:0;border:0;border-radius:11px;overflow:hidden;background:#e8ebef;cursor:zoom-in}.chart-button img{display:block;width:100%;height:auto}.zoom-hint{position:absolute;right:9px;bottom:9px;padding:5px 8px;border-radius:7px;background:rgba(16,24,40,.78);color:#fff;font-size:.72rem;opacity:0;transition:opacity .18s}.chart-button:hover .zoom-hint,.chart-button:focus-visible .zoom-hint{opacity:1}
  .empty{padding:34px 18px;border:1px dashed #bcc5cf;border-radius:14px;background:rgba(255,255,255,.55);color:var(--muted);text-align:center}
  dialog{width:calc(100vw - 24px);height:calc(100vh - 24px);max-width:none;max-height:none;padding:0;border:0;border-radius:16px;background:#111827;overflow:hidden}dialog::backdrop{background:rgba(3,8,18,.82)}.viewer-bar{position:absolute;inset:0 0 auto 0;z-index:3;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 14px;background:rgba(17,24,39,.9);color:#fff}.viewer-bar strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.controls{display:flex;gap:7px}.controls button{border:1px solid #667085;background:#263246;color:#fff;border-radius:8px;padding:7px 11px;cursor:pointer}.viewport{width:100%;height:100%;overflow:hidden;cursor:grab;touch-action:none}.viewport.dragging{cursor:grabbing}#viewerImage{position:absolute;left:50%;top:50%;max-width:none;transform-origin:center;user-select:none;pointer-events:none}
  @media(min-width:1500px){.ranking-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.rank-card{padding:12px}.chips{margin:8px 0;gap:5px}.chips span{padding:5px 7px;font-size:.72rem}}@media(min-width:2100px){.ranking-grid{grid-template-columns:repeat(4,minmax(0,1fr))}}@media(max-width:760px){.ranking-grid{grid-template-columns:1fr}}
"""


def _winner_badge_html(row):
    winner = row.get("_winner")
    if not winner or str(winner) == "nan":
        return ""
    variant = "market" if "hold" in str(winner).lower() else "strategy"
    return f'<span class="badge {variant}">{html.escape(str(winner))}</span>'


def build_grouped_top_annualized_cards(rows, cols):
    cards = []
    for rank, (_, row) in enumerate(rows.iterrows(), start=1):
        chart_path = Path(str(row[cols["chart"]]))
        chart_src = os.path.relpath(chart_path, REPORTS_DIR).replace(os.sep, "/")
        ticker = html.escape(str(row.get("_ticker") or row.get("fund_label", "Unknown fund")))
        top_value = safe_float(row, "_top")
        top_class = "pos" if np.isfinite(top_value) and top_value >= 0 else "neg"
        config = slice_descriptor(row)
        config_chip = f"<span>Winning run <b>{html.escape(config)}</b></span>" if config else ""
        cards.append(
            f'''<article class="rank-card">
              <div class="card-head"><span class="rank">#{rank}</span><h2>{ticker}</h2>
                <div class="headline {top_class}"><small>Top annualized</small><strong>{format_pct(row.get('_top'))}</strong>{_winner_badge_html(row)}</div>
              </div>
              <div class="chips">
                <span>Source years <b>{safe_float(row, '_source_years'):.1f}Y</b></span>
                <span>Run years <b>{run_years(row) or 'n/a'}</b></span>
                <span>Strategy ann. <b>{format_pct(row.get('_adaptive'))}</b></span>
                <span>Buy &amp; hold ann. <b>{format_pct(row.get('_buy_hold'))}</b></span>
                <span>Through <b>{html.escape(str(row.get('data_end', 'n/a')))}</b></span>
                {config_chip}
              </div>
              <button class="chart-button" type="button" data-src="{html.escape(chart_src, quote=True)}" data-title="{ticker}" aria-label="Open zoomable chart for {ticker}">
                <img src="{html.escape(chart_src, quote=True)}" alt="Strategy chart for {ticker}" loading="lazy"><span class="zoom-hint">Click to zoom</span>
              </button>
            </article>'''
        )
    return "".join(cards)


def render_top_annualized_horizon_dashboard(
    rankings, output_path, source_path, considered, basis, cols=TOP_HISTORY_COLUMNS
):
    """Render the two-axis run-history dashboard: Source years x Run years."""
    source_name, source_built_at, source_full = source_provenance(source_path)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = "Top Annualized Return" if basis != "strategy" else "Strategy Annualized Return"
    basis_note = (
        "Best annualized return per ticker — whichever of strategy or buy &amp; hold is higher, "
        "with the source badged on each card"
        if basis == "best"
        else "Strategy annualized return per ticker"
    )
    tabs, panels = [], []
    for index, (key, label, _) in enumerate(TOP_SOURCE_HORIZONS):
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
            content = f'<div class="ranking-grid">{build_grouped_top_annualized_cards(rows, cols)}</div>' if not rows.empty else '<div class="empty">No valid completed runs match this Source years and Run years comparison.</div>'
            run_panels.append(
                f'<div role="tabpanel" class="run-panel" id="run-panel-{key}-{bucket}" data-run-panel="{bucket}" {"" if run_index == 0 else "hidden"}>{content}</div>'
            )
        note = (
            "Best annualized run per ticker regardless of source or scored duration."
            if key == "mixed"
            else f"Best annualized run per ticker from approximately {label.lower()} source data."
        )
        panels.append(
            f'<section role="tabpanel" class="source-panel" id="source-panel-{key}" data-source-panel="{key}" aria-labelledby="source-tab-{key}" {"" if index == 0 else "hidden"}><p class="group-note">{html.escape(note)} {group["candidate_count"]} eligible run(s); choose a scored duration to narrow the comparison.</p><div class="run-tabs" role="tablist" aria-label="Run years for {html.escape(label)}">{"".join(run_tabs)}</div>{"".join(run_panels)}</section>'
        )

    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fund Backtest Dashboard — {html.escape(title)} by Source Years</title><style>{TOP_GROUPED_STYLE}</style></head><body>
<header><a class="master-link" href="dashboard.html">← Master dashboard</a><h1>{html.escape(title)} Ranking</h1><p>{html.escape(basis_note)}, grouped by source-data horizon and scored run duration · generated {generated_at}</p><p class="source">Source <code title="{html.escape(source_full, quote=True)}">{html.escape(source_name)}</code> last written {source_built_at} — ranking computed from {considered} run(s) with existing charts.</p><nav class="tabs" role="tablist" aria-label="Source years">{"".join(tabs)}</nav></header><main>{"".join(panels)}</main>
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
    elif args.basis == "best" and not args.per_slice:
        horizon_rankings, horizon_considered = load_top_annualized_horizon_rankings(
            history_path, args.basis, TOP_HISTORY_COLUMNS, args.top_funds
        )
        html_path = render_top_annualized_horizon_dashboard(
            horizon_rankings,
            REPORTS_DIR / f"{base}.html",
            history_path,
            horizon_considered,
            args.basis,
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
