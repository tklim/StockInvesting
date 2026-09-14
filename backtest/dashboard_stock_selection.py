"""Build a price-derived, diversified long-term stock-selection dashboard.

The score is deliberately independent from the adaptive trading strategy.  A
current strategy signal may be displayed as timing context, but changing that
signal cannot alter the stock-selection score or rank.
"""

from __future__ import annotations

import argparse
import html
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from common import fund_group_from_label


SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
REPORTS_DIR = SCRIPT_DIR / "outputs" / "reports"
TUNINGS_DIR = SCRIPT_DIR / "outputs" / "tunings"
DEFAULT_TICKERS_FILE = SCRIPT_DIR / "tickers.txt"
DEFAULT_METADATA_FILE = SCRIPT_DIR / "selection_groups.csv"
DEFAULT_HTML_OUTPUT = REPORTS_DIR / "dashboard_stock_selection.html"
DEFAULT_CSV_OUTPUT = REPORTS_DIR / "dashboard_stock_selection.csv"

TRAILING_HORIZONS = (3, 5, 10)
HISTORICAL_AGES = (1, 2, 3, 4, 5, 10)
HISTORICAL_HORIZONS = (3, 5, 10)
MIN_HISTORY_YEARS = 4.95
MIN_PERSISTENCE_PANELS = 8
FRESHNESS_DAYS = 7
RETURN_WEIGHTS = {3: 5.0, 5: 10.0, 10: 10.0}
DEFAULT_YEARS_AGO = (0, 1, 2, 3, 4, 5)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Build the long-term, price-derived stock-selection dashboard."
    )
    parser.add_argument("--tickers-file", default=str(DEFAULT_TICKERS_FILE))
    parser.add_argument("--metadata-file", default=str(DEFAULT_METADATA_FILE))
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument(
        "--summary-file",
        default="",
        help="Final-backtest summary used only for the timing overlay. Default: newest file.",
    )
    parser.add_argument("--primary-benchmark", default="SPY")
    parser.add_argument("--secondary-benchmark", default="QQQ")
    parser.add_argument("--shortlist-size", type=int, default=10)
    parser.add_argument("--group-cap", type=int, default=3)
    parser.add_argument(
        "--years-ago",
        nargs="+",
        type=int,
        choices=(0, 1, 2, 3, 4, 5),
        default=DEFAULT_YEARS_AGO,
        metavar="YEARS",
        help="Point-in-time selection snapshots to render (default: 0 1 2 3).",
    )
    parser.add_argument("--html-output", default=str(DEFAULT_HTML_OUTPUT))
    parser.add_argument("--csv-output", default=str(DEFAULT_CSV_OUTPUT))
    return parser.parse_args(argv)


def _resolved(path, base=SCRIPT_DIR):
    value = Path(path)
    return value if value.is_absolute() else base / value


def load_ticker_universe(path=DEFAULT_TICKERS_FILE):
    """Read comment-aware ticker text and reject duplicates."""
    path = _resolved(path)
    tickers = []
    seen = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        ticker = raw.split("#", 1)[0].strip().upper()
        if not ticker:
            continue
        if ticker in seen:
            raise ValueError(f"Duplicate ticker {ticker!r} in {path} at line {line_number}")
        seen.add(ticker)
        tickers.append(ticker)
    if not tickers:
        raise ValueError(f"No tickers found in {path}")
    return tickers


def load_selection_metadata(path, tickers):
    """Load and fully validate the stable role/industry mapping."""
    path = _resolved(path)
    frame = pd.read_csv(path, dtype=str).fillna("")
    required = {"ticker", "role", "industry_group"}
    missing_columns = sorted(required - set(frame.columns))
    if missing_columns:
        raise ValueError(f"Selection metadata missing columns: {missing_columns}")
    frame = frame[["ticker", "role", "industry_group"]].copy()
    frame["ticker"] = frame["ticker"].str.strip().str.upper()
    frame["role"] = frame["role"].str.strip().str.lower()
    frame["industry_group"] = frame["industry_group"].str.strip()
    duplicates = sorted(frame.loc[frame["ticker"].duplicated(), "ticker"].unique())
    if duplicates:
        raise ValueError(f"Duplicate metadata tickers: {duplicates}")
    invalid_roles = sorted(set(frame["role"]) - {"candidate", "benchmark"})
    if invalid_roles:
        raise ValueError(f"Invalid metadata roles: {invalid_roles}")
    if (frame["industry_group"] == "").any():
        blank = sorted(frame.loc[frame["industry_group"] == "", "ticker"])
        raise ValueError(f"Missing industry group for: {blank}")
    expected, actual = set(tickers), set(frame["ticker"])
    if expected != actual:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"Metadata/universe mismatch; missing={missing}, extra={extra}")
    return frame.set_index("ticker", drop=False)


def _load_price_item(ticker, data_dir):
    source = Path(data_dir) / f"{ticker}.csv"
    item = {
        "ticker": ticker,
        "data_file": source,
        "price_column": "",
        "values": pd.DataFrame(),
        "history_years": np.nan,
        "data_start": "",
        "data_end": "",
        "anomaly_reason": "",
    }
    if not source.is_file():
        item["anomaly_reason"] = "Price file missing"
        return item
    try:
        raw = pd.read_csv(source, low_memory=False)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        item["anomaly_reason"] = f"Price file unreadable: {exc}"
        return item
    if "Date" not in raw.columns:
        item["anomaly_reason"] = "Date column missing"
        return item
    price_column = next(
        (column for column in ("Adj Close", "Close", "NAV") if column in raw.columns),
        None,
    )
    if price_column is None:
        item["anomaly_reason"] = "Adjusted/close price column missing"
        return item
    values = pd.DataFrame(
        {
            "Date": pd.to_datetime(raw["Date"], errors="coerce"),
            "Price": pd.to_numeric(raw[price_column], errors="coerce"),
        }
    ).dropna(subset=["Date", "Price"])
    nonpositive = int((values["Price"] <= 0).sum())
    values = values[values["Price"] > 0].sort_values("Date")
    duplicates = int(values["Date"].duplicated(keep="last").sum())
    values = values.drop_duplicates("Date", keep="last").reset_index(drop=True)
    reasons = []
    if nonpositive:
        reasons.append(f"{nonpositive} non-positive price(s)")
    if len(values) < 2:
        reasons.append("Insufficient valid observations")
    if len(values) >= 2 and price_column != "Close":
        extreme = values["Price"].pct_change().abs().gt(5.0)
        if extreme.any():
            reasons.append("Adjusted-price daily move exceeds 500%")
    item.update(
        {
            "price_column": price_column,
            "values": values,
            "duplicate_dates_resolved": duplicates,
            "anomaly_reason": "; ".join(reasons),
        }
    )
    if len(values) >= 2:
        start, end = values["Date"].iloc[0], values["Date"].iloc[-1]
        item.update(
            {
                "history_years": (end - start).days / 365.25,
                "data_start": start.strftime("%Y-%m-%d"),
                "data_end": end.strftime("%Y-%m-%d"),
                "latest_date": end,
            }
        )
    return item


def load_price_universe(tickers, data_dir=DATA_DIR):
    data_dir = _resolved(data_dir)
    return {ticker: _load_price_item(ticker, data_dir) for ticker in tickers}


def price_item_as_of(item, as_of_date):
    """Return an item containing only information available on the common as-of date."""
    snapshot = item.copy()
    values = item.get("values")
    if values is None or values.empty:
        return snapshot
    anchor = pd.Timestamp(as_of_date)
    values = values[values["Date"] <= anchor].copy().reset_index(drop=True)
    snapshot["values"] = values
    snapshot["data_start"] = ""
    snapshot["data_end"] = ""
    snapshot["history_years"] = np.nan
    snapshot.pop("latest_date", None)
    if len(values) < 2:
        snapshot["anomaly_reason"] = "Insufficient valid observations as of anchor date"
        return snapshot
    start, end = values["Date"].iloc[0], values["Date"].iloc[-1]
    reasons = []
    if snapshot.get("price_column") != "Close":
        if values["Price"].pct_change().abs().gt(5.0).any():
            reasons.append("Adjusted-price daily move exceeds 500%")
    snapshot.update(
        {
            "history_years": (end - start).days / 365.25,
            "data_start": start.strftime("%Y-%m-%d"),
            "data_end": end.strftime("%Y-%m-%d"),
            "latest_date": end,
            "anomaly_reason": "; ".join(reasons),
        }
    )
    return snapshot


def _price_window(item, years, target_end=None):
    values = item.get("values")
    if values is None or values.empty:
        return None
    target_end = pd.Timestamp(target_end) if target_end is not None else values["Date"].iloc[-1]
    end_candidates = values[values["Date"] <= target_end]
    if end_candidates.empty:
        return None
    end_row = end_candidates.iloc[-1]
    target_start = end_row["Date"] - pd.DateOffset(years=int(years))
    start_candidates = values[
        (values["Date"] >= target_start) & (values["Date"] <= end_row["Date"])
    ]
    if len(start_candidates) < 2:
        return None
    start_row = start_candidates.iloc[0]
    elapsed_days = (end_row["Date"] - start_row["Date"]).days
    if elapsed_days < years * 365.25 - 14:
        return None
    elapsed_years = elapsed_days / 365.25
    annualized = (
        (float(end_row["Price"]) / float(start_row["Price"])) ** (1.0 / elapsed_years)
        - 1.0
    ) * 100.0
    return {
        "annualized": annualized,
        "start": start_row["Date"],
        "end": end_row["Date"],
        "values": values[
            (values["Date"] >= start_row["Date"]) & (values["Date"] <= end_row["Date"])
        ].copy(),
    }


def _aligned_annualized(item, start, end):
    values = item.get("values")
    if values is None or values.empty:
        return np.nan
    aligned = values[(values["Date"] >= start) & (values["Date"] <= end)]
    if len(aligned) < 2:
        return np.nan
    elapsed_years = (aligned["Date"].iloc[-1] - aligned["Date"].iloc[0]).days / 365.25
    if elapsed_years <= 0:
        return np.nan
    return (
        (float(aligned["Price"].iloc[-1]) / float(aligned["Price"].iloc[0]))
        ** (1.0 / elapsed_years)
        - 1.0
    ) * 100.0


def _percentile(series, higher_is_better=True):
    if series is None:
        return pd.Series(dtype=float)
    if not isinstance(series, pd.Series):
        series = pd.Series([series])
    clean = pd.to_numeric(series, errors="coerce")
    ranked = clean if higher_is_better else -clean
    return ranked.rank(pct=True, method="average")


def _drawdown_details(values, max_points=260):
    """Return a compact five-year drawdown series and the worst peak-to-trough event."""
    frame = values[["Date", "Price"]].dropna().reset_index(drop=True)
    if frame.empty:
        return {
            "max_drawdown_5y_pct": np.nan,
            "max_drawdown_peak_date": "",
            "max_drawdown_trough_date": "",
            "max_drawdown_recovery_date": "",
            "max_drawdown_duration_days": np.nan,
            "max_drawdown_recovery_duration_days": np.nan,
            "drawdown_points": [],
        }
    prices = frame["Price"].to_numpy(dtype=float)
    running_peaks = np.maximum.accumulate(prices)
    drawdown_pct = (prices / running_peaks - 1.0) * 100.0
    trough_position = int(np.argmin(drawdown_pct))
    peak_price = running_peaks[trough_position]
    peak_positions = np.flatnonzero(
        np.isclose(prices[: trough_position + 1], peak_price, rtol=1e-10, atol=1e-12)
    )
    peak_position = int(peak_positions[-1])
    recovery_positions = np.flatnonzero(prices[trough_position + 1 :] >= peak_price)
    recovery_position = (
        int(trough_position + 1 + recovery_positions[0])
        if len(recovery_positions)
        else None
    )
    step = max(1, int(np.ceil(len(frame) / max_points)))
    selected_positions = set(range(0, len(frame), step))
    selected_positions.update({0, peak_position, trough_position, len(frame) - 1})
    if recovery_position is not None:
        selected_positions.add(recovery_position)
    points = [
        (frame.loc[position, "Date"].strftime("%Y-%m-%d"), float(drawdown_pct[position]))
        for position in sorted(selected_positions)
    ]
    return {
        "max_drawdown_5y_pct": abs(float(drawdown_pct[trough_position])),
        "max_drawdown_peak_date": frame.loc[peak_position, "Date"].strftime("%Y-%m-%d"),
        "max_drawdown_trough_date": frame.loc[trough_position, "Date"].strftime("%Y-%m-%d"),
        "max_drawdown_recovery_date": (
            frame.loc[recovery_position, "Date"].strftime("%Y-%m-%d")
            if recovery_position is not None
            else ""
        ),
        "max_drawdown_duration_days": int(
            (frame.loc[trough_position, "Date"] - frame.loc[peak_position, "Date"]).days
        ),
        "max_drawdown_recovery_duration_days": (
            int(
                (frame.loc[recovery_position, "Date"] - frame.loc[trough_position, "Date"]).days
            )
            if recovery_position is not None
            else np.nan
        ),
        "drawdown_points": points,
    }


def build_benchmark_reference_rows(
    candidate_rows,
    prices,
    metadata,
    freshest_date,
    primary_benchmark="SPY",
    secondary_benchmark="QQQ",
):
    """Calculate display-only benchmark references without changing candidate ranks.

    The values use the same price-derived component definitions and candidate
    peer distributions as the selector.  They are deliberately kept separate
    from candidate rows: SPY and QQQ cannot receive a rank or enter a
    shortlist, even when the interactive table is sorted.
    """
    primary_benchmark = primary_benchmark.upper()
    secondary_benchmark = secondary_benchmark.upper()
    eligible = candidate_rows[
        (candidate_rows["eligibility"] == "eligible")
        & candidate_rows["score"].notna()
    ]
    candidate_tickers = eligible["ticker"].tolist()
    reference_rows = []

    for ticker in (primary_benchmark, secondary_benchmark):
        item = prices[ticker]
        windows = {
            horizon: _price_window(item, horizon, target_end=freshest_date)
            for horizon in TRAILING_HORIZONS
        }
        history_years = item.get("history_years", np.nan)
        reasons = []
        if item.get("anomaly_reason"):
            reasons.append(item["anomaly_reason"])
        if not np.isfinite(history_years) or history_years < MIN_HISTORY_YEARS:
            reasons.append(f"Under {MIN_HISTORY_YEARS:.2f} years of usable history")
        if item.get("latest_date") is None or (freshest_date - item["latest_date"]).days > FRESHNESS_DAYS:
            reasons.append("Price history is stale")
        if windows[5] is None:
            reasons.append("Complete 5Y window unavailable")

        record = {
            "ticker": ticker,
            "role": "benchmark",
            "industry_group": metadata.loc[ticker, "industry_group"],
            "data_file": str(item.get("data_file", "")),
            "price_column": item.get("price_column", ""),
            "data_start": item.get("data_start", ""),
            "data_end": item.get("data_end", ""),
            "history_years": history_years,
            "eligibility": "benchmark",
            "exclusion_reason": "; ".join(reasons),
            "shortlisted": False,
            "raw_rank": np.nan,
            "shortlist_rank": np.nan,
            "shortlist_reason": "Benchmark reference — ranked for comparison; never selected",
            "reference_score": True,
            "coverage": "High" if history_years >= 10 else "Medium",
        }
        for horizon, window in windows.items():
            record[f"cagr_{horizon}y_pct"] = window["annualized"] if window else np.nan

        if reasons or eligible.empty:
            record.update(
                {
                    "score": np.nan,
                    "persistence_panels": 0,
                    "max_drawdown_5y_pct": np.nan,
                    "max_drawdown_peak_date": "",
                    "max_drawdown_trough_date": "",
                    "max_drawdown_recovery_date": "",
                    "max_drawdown_duration_days": np.nan,
                    "max_drawdown_recovery_duration_days": np.nan,
                    "drawdown_points": [],
                    "volatility_5y_pct": np.nan,
                    "risk_warning": "Unavailable",
                }
            )
            reference_rows.append(record)
            continue

        return_score = 0.0
        for horizon, weight in RETURN_WEIGHTS.items():
            value = record[f"cagr_{horizon}y_pct"]
            if not np.isfinite(value) and horizon == 10:
                percentile = 0.5
            elif np.isfinite(value):
                percentile = float(
                    _percentile(
                        pd.concat(
                            [
                                eligible[f"cagr_{horizon}y_pct"],
                                pd.Series([value], dtype=float),
                            ],
                            ignore_index=True,
                        )
                    ).iloc[-1]
                )
            else:
                percentile = np.nan
            if not np.isfinite(percentile):
                reasons.append(f"{horizon}Y return percentile unavailable")
                break
            return_score += weight * percentile

        persistence = []
        benchmark_beats = {primary_benchmark: [], secondary_benchmark: []}
        for age in HISTORICAL_AGES:
            for horizon in HISTORICAL_HORIZONS:
                target_end = freshest_date - pd.DateOffset(years=age)
                peer_returns = []
                for candidate in candidate_tickers:
                    window = _price_window(prices[candidate], horizon, target_end)
                    if window is not None:
                        peer_returns.append(window["annualized"])
                benchmark_window = _price_window(item, horizon, target_end)
                if benchmark_window is None or not peer_returns:
                    continue
                percentile = _percentile(
                    pd.Series(peer_returns + [benchmark_window["annualized"]], dtype=float)
                ).iloc[-1]
                persistence.append(float(percentile))
                for comparator in benchmark_beats:
                    comparator_return = _aligned_annualized(
                        prices[comparator], benchmark_window["start"], benchmark_window["end"]
                    )
                    if np.isfinite(comparator_return):
                        benchmark_beats[comparator].append(
                            float(benchmark_window["annualized"] > comparator_return)
                        )

        risk = _drawdown_details(windows[5]["values"])
        daily = windows[5]["values"]["Price"].pct_change().dropna()
        risk["volatility_5y_pct"] = float(daily.std() * np.sqrt(252)) * 100.0
        if len(persistence) < MIN_PERSISTENCE_PANELS:
            reasons.append(f"Only {len(persistence)} persistence panels; {MIN_PERSISTENCE_PANELS} required")
        if not benchmark_beats[primary_benchmark] or not benchmark_beats[secondary_benchmark]:
            reasons.append("Benchmark comparison unavailable")

        if not reasons:
            persistence_values = np.asarray(persistence, dtype=float)
            persistence_score = (
                15.0 * float(np.median(persistence_values))
                + 5.0 * float((persistence_values >= 0.75).mean())
                + 5.0 * float((persistence_values > 0.25).mean())
            )
            drawdown_score = float(
                _percentile(
                    pd.concat(
                        [eligible["max_drawdown_5y_pct"], pd.Series([risk["max_drawdown_5y_pct"]])],
                        ignore_index=True,
                    ),
                    False,
                ).iloc[-1]
            )
            volatility_score = float(
                _percentile(
                    pd.concat(
                        [eligible["volatility_5y_pct"], pd.Series([risk["volatility_5y_pct"]])],
                        ignore_index=True,
                    ),
                    False,
                ).iloc[-1]
            )
            primary_rate = float(np.mean(benchmark_beats[primary_benchmark]))
            secondary_rate = float(np.mean(benchmark_beats[secondary_benchmark]))
            record.update(
                {
                    "score": min(100.0, max(0.0, return_score + persistence_score + 15.0 * drawdown_score + 10.0 * volatility_score + 10.0 * primary_rate + 5.0 * secondary_rate + 10.0 * min(float(history_years) / 10.0, 1.0))),
                    "persistence_panels": len(persistence),
                    "return_score": return_score,
                    "persistence_score": persistence_score,
                    "risk_score": 15.0 * drawdown_score + 10.0 * volatility_score,
                    "benchmark_score": 10.0 * primary_rate + 5.0 * secondary_rate,
                    "confidence_score": 10.0 * min(float(history_years) / 10.0, 1.0),
                    "primary_benchmark": primary_benchmark,
                    "primary_beat_rate_pct": primary_rate * 100.0,
                    "secondary_benchmark": secondary_benchmark,
                    "secondary_beat_rate_pct": secondary_rate * 100.0,
                }
            )
        else:
            record.update({"score": np.nan, "persistence_panels": len(persistence)})
        record.update(risk)
        max_dd = risk["max_drawdown_5y_pct"]
        volatility = risk["volatility_5y_pct"]
        record["risk_warning"] = (
            "High historical risk" if max_dd > 50 or volatility > 50 else "Elevated historical risk" if max_dd > 35 or volatility > 35 else "Lower historical risk"
        )
        record["exclusion_reason"] = "; ".join(reasons)
        reference_rows.append(record)
    return pd.DataFrame(reference_rows)


def _latest_summary_path(path=""):
    if path:
        candidate = _resolved(path)
        return candidate if candidate.is_file() else None
    candidates = sorted(
        TUNINGS_DIR.glob("final_backtest_summary_*.csv"),
        key=lambda value: value.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def load_timing_overlay(summary_path, freshest_date):
    """Return ticker timing context. These values never enter score calculation."""
    summary_path = _latest_summary_path(summary_path)
    if summary_path is None:
        return {}, None
    try:
        frame = pd.read_csv(summary_path, low_memory=False).fillna("")
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        return {}, summary_path
    if "fund_label" not in frame.columns:
        return {}, summary_path
    if "status" in frame.columns:
        frame = frame[frame["status"].astype(str).str.lower() == "completed"]
    overlay = {}
    for _, row in frame.iterrows():
        ticker = fund_group_from_label(row.get("fund_label", ""))
        if not ticker:
            continue
        timing_date = pd.to_datetime(row.get("latest_data_end"), errors="coerce")
        stale = pd.isna(timing_date) or (freshest_date - timing_date).days > FRESHNESS_DAYS
        overlay[ticker] = {
            "timing_signal": "Unavailable (stale)" if stale else str(row.get("ga_signal", "") or "Unavailable"),
            "last_trade_action": "" if stale else str(row.get("last_trade_action", "") or ""),
            "last_trade_date": "" if stale else str(row.get("last_trade_date", "") or ""),
            "timing_data_end": "" if pd.isna(timing_date) else timing_date.strftime("%Y-%m-%d"),
            "timing_excess_annualized_pct": (
                np.nan
                if stale
                else pd.to_numeric(row.get("latest_excess_annualized_return_pct"), errors="coerce")
            ),
            "timing_status": "stale" if stale else "current",
        }
    return overlay, summary_path


def historical_timing_overlay(tickers):
    """Return an explicit no-look-ahead timing state for historical selection views."""
    return {
        ticker: {
            "timing_signal": "Unavailable (historical selection replay)",
            "last_trade_action": "",
            "last_trade_date": "",
            "timing_data_end": "",
            "timing_excess_annualized_pct": np.nan,
            "timing_status": "historical_unavailable",
        }
        for ticker in tickers
    }


def build_selection_snapshots(
    tickers,
    metadata,
    prices,
    years_ago=DEFAULT_YEARS_AGO,
    primary_benchmark="SPY",
    secondary_benchmark="QQQ",
    shortlist_size=10,
    group_cap=3,
    current_timing_overlay=None,
):
    """Replay selection scoring at each requested common, point-in-time anchor."""
    usable_latest = [
        item.get("latest_date") for item in prices.values() if item.get("latest_date") is not None
    ]
    if not usable_latest:
        raise ValueError("No usable price histories found")
    common_latest = max(usable_latest)
    benchmark_values = prices.get(primary_benchmark.upper(), {}).get("values")
    if benchmark_values is None or benchmark_values.empty:
        raise ValueError(f"Primary benchmark {primary_benchmark} has no usable price history")
    snapshots = []
    requested_ages = tuple(dict.fromkeys(int(age) for age in years_ago))
    for years in requested_ages:
        target_anchor = common_latest - pd.DateOffset(years=years)
        anchor_candidates = benchmark_values[benchmark_values["Date"] <= target_anchor]
        if anchor_candidates.empty:
            raise ValueError(
                f"Primary benchmark {primary_benchmark} has no observation on or before {target_anchor:%Y-%m-%d}"
            )
        anchor = anchor_candidates["Date"].iloc[-1]
        snapshot_prices = {
            ticker: price_item_as_of(item, anchor) for ticker, item in prices.items()
        }
        overlay = (
            current_timing_overlay or {}
            if years == 0
            else historical_timing_overlay(tickers)
        )
        rows, _ = compute_selection_scores(
            tickers,
            metadata,
            snapshot_prices,
            primary_benchmark=primary_benchmark,
            secondary_benchmark=secondary_benchmark,
            shortlist_size=shortlist_size,
            group_cap=group_cap,
            timing_overlay=overlay,
            as_of_date=anchor,
        )
        rows["years_ago"] = years
        rows["as_of_date"] = anchor.strftime("%Y-%m-%d")
        benchmark_rows = build_benchmark_reference_rows(
            rows,
            snapshot_prices,
            metadata,
            anchor,
            primary_benchmark=primary_benchmark,
            secondary_benchmark=secondary_benchmark,
        )
        benchmark_rows["years_ago"] = years
        benchmark_rows["as_of_date"] = anchor.strftime("%Y-%m-%d")
        displayed_ranking = pd.concat([rows, benchmark_rows], ignore_index=True)
        displayed_ranking["display_rank"] = np.nan
        scored_display = displayed_ranking["score"].notna()
        rank_order = displayed_ranking.loc[scored_display].sort_values(
            ["score", "ticker"], ascending=[False, True]
        )
        displayed_ranking.loc[rank_order.index, "display_rank"] = np.arange(
            1, len(rank_order) + 1
        )
        rank_map = displayed_ranking.set_index("ticker")["display_rank"]
        rows["display_rank"] = rows["ticker"].map(rank_map)
        benchmark_rows["display_rank"] = benchmark_rows["ticker"].map(rank_map)
        snapshots.append(
            {
                "years_ago": years,
                "as_of_date": anchor,
                "rows": rows,
                "benchmark_rows": benchmark_rows,
                "id": "current" if years == 0 else f"{years}y-ago",
                "label": "Current" if years == 0 else f"{years}Y ago",
            }
        )
    return snapshots, common_latest


def compute_selection_scores(
    tickers,
    metadata,
    prices,
    primary_benchmark="SPY",
    secondary_benchmark="QQQ",
    shortlist_size=10,
    group_cap=3,
    timing_overlay=None,
    as_of_date=None,
):
    """Return candidate rows scored independently from the optional timing overlay."""
    primary_benchmark = primary_benchmark.upper()
    secondary_benchmark = secondary_benchmark.upper()
    benchmark_names = (primary_benchmark, secondary_benchmark)
    for benchmark in benchmark_names:
        if benchmark not in prices or metadata.loc[benchmark, "role"] != "benchmark":
            raise ValueError(f"Benchmark {benchmark} is missing or not classified as benchmark")

    usable_latest = [
        item.get("latest_date")
        for item in prices.values()
        if item.get("latest_date") is not None
    ]
    if not usable_latest:
        raise ValueError("No usable price histories found")
    freshest_date = pd.Timestamp(as_of_date) if as_of_date is not None else max(usable_latest)
    candidate_tickers = [
        ticker for ticker in tickers if metadata.loc[ticker, "role"] == "candidate"
    ]
    records = {}
    trailing_windows = {ticker: {} for ticker in candidate_tickers}
    base_eligible = []

    for ticker in candidate_tickers:
        item = prices[ticker]
        reasons = []
        if item.get("anomaly_reason"):
            reasons.append(item["anomaly_reason"])
        history_years = item.get("history_years", np.nan)
        if not np.isfinite(history_years) or history_years < MIN_HISTORY_YEARS:
            reasons.append(f"Under {MIN_HISTORY_YEARS:.2f} years of usable history")
        latest_date = item.get("latest_date")
        if latest_date is None or (freshest_date - latest_date).days > FRESHNESS_DAYS:
            reasons.append("Price history is stale")
        for horizon in TRAILING_HORIZONS:
            trailing_windows[ticker][horizon] = _price_window(
                item, horizon, target_end=freshest_date
            )
        if trailing_windows[ticker][5] is None:
            reasons.append("Complete 5Y window unavailable")
        if not reasons:
            base_eligible.append(ticker)
        records[ticker] = {
            "ticker": ticker,
            "role": "candidate",
            "industry_group": metadata.loc[ticker, "industry_group"],
            "data_file": str(item.get("data_file", "")),
            "price_column": item.get("price_column", ""),
            "data_start": item.get("data_start", ""),
            "data_end": item.get("data_end", ""),
            "history_years": history_years,
            "eligibility": "eligible" if not reasons else "ineligible",
            "exclusion_reason": "; ".join(reasons),
            "fundamentals_status": "REVIEW_REQUIRED",
        }
        for horizon in TRAILING_HORIZONS:
            window = trailing_windows[ticker][horizon]
            records[ticker][f"cagr_{horizon}y_pct"] = (
                window["annualized"] if window is not None else np.nan
            )

    trailing_percentiles = {}
    for horizon in TRAILING_HORIZONS:
        values = pd.Series(
            {
                ticker: records[ticker][f"cagr_{horizon}y_pct"]
                for ticker in base_eligible
            },
            dtype=float,
        )
        trailing_percentiles[horizon] = _percentile(values)

    historical_percentiles = {ticker: [] for ticker in base_eligible}
    benchmark_beats = {
        ticker: {primary_benchmark: [], secondary_benchmark: []}
        for ticker in base_eligible
    }
    for age in HISTORICAL_AGES:
        for horizon in HISTORICAL_HORIZONS:
            panel = {}
            windows = {}
            for ticker in base_eligible:
                target_end = freshest_date - pd.DateOffset(years=age)
                window = _price_window(prices[ticker], horizon, target_end)
                if window is not None:
                    panel[ticker] = window["annualized"]
                    windows[ticker] = window
            percentiles = _percentile(pd.Series(panel, dtype=float))
            for ticker, percentile in percentiles.items():
                historical_percentiles[ticker].append(float(percentile))
                window = windows[ticker]
                for benchmark in benchmark_names:
                    benchmark_return = _aligned_annualized(
                        prices[benchmark], window["start"], window["end"]
                    )
                    if np.isfinite(benchmark_return):
                        benchmark_beats[ticker][benchmark].append(
                            float(window["annualized"] > benchmark_return)
                        )

    risk_rows = {}
    for ticker in base_eligible:
        window = trailing_windows[ticker][5]
        values = window["values"]["Price"]
        daily = values.pct_change().dropna()
        risk_rows[ticker] = _drawdown_details(window["values"])
        risk_rows[ticker]["volatility_5y_pct"] = float(daily.std() * np.sqrt(252)) * 100.0
    risk_frame = pd.DataFrame.from_dict(risk_rows, orient="index")
    drawdown_pct = _percentile(risk_frame.get("max_drawdown_5y_pct"), False)
    volatility_pct = _percentile(risk_frame.get("volatility_5y_pct"), False)

    for ticker in candidate_tickers:
        record = records[ticker]
        if ticker not in base_eligible:
            continue
        persistence = np.asarray(historical_percentiles[ticker], dtype=float)
        record["persistence_panels"] = int(len(persistence))
        if len(persistence) < MIN_PERSISTENCE_PANELS:
            record["eligibility"] = "ineligible"
            record["exclusion_reason"] = (
                f"Only {len(persistence)} persistence panels; {MIN_PERSISTENCE_PANELS} required"
            )
            continue
        primary_hits = benchmark_beats[ticker][primary_benchmark]
        secondary_hits = benchmark_beats[ticker][secondary_benchmark]
        if not primary_hits or not secondary_hits:
            record["eligibility"] = "ineligible"
            record["exclusion_reason"] = "Benchmark comparison unavailable"
            continue

        return_score = 0.0
        for horizon, weight in RETURN_WEIGHTS.items():
            percentile = trailing_percentiles[horizon].get(ticker, np.nan)
            if not np.isfinite(percentile) and horizon == 10:
                percentile = 0.5
            if not np.isfinite(percentile):
                record["eligibility"] = "ineligible"
                record["exclusion_reason"] = f"{horizon}Y return percentile unavailable"
                break
            return_score += float(percentile) * weight
        if record["eligibility"] != "eligible":
            continue

        persistence_score = (
            15.0 * float(np.median(persistence))
            + 5.0 * float((persistence >= 0.75).mean())
            + 5.0 * float((persistence > 0.25).mean())
        )
        risk_score = (
            15.0 * float(drawdown_pct[ticker])
            + 10.0 * float(volatility_pct[ticker])
        )
        primary_rate = float(np.mean(primary_hits))
        secondary_rate = float(np.mean(secondary_hits))
        benchmark_score = 10.0 * primary_rate + 5.0 * secondary_rate
        confidence_score = 10.0 * min(float(record["history_years"]) / 10.0, 1.0)
        score = min(
            100.0,
            max(
                0.0,
                return_score
                + persistence_score
                + risk_score
                + benchmark_score
                + confidence_score,
            ),
        )
        record.update(
            {
                "score": score,
                "return_score": return_score,
                "persistence_score": persistence_score,
                "risk_score": risk_score,
                "benchmark_score": benchmark_score,
                "confidence_score": confidence_score,
                "max_drawdown_5y_pct": risk_rows[ticker]["max_drawdown_5y_pct"],
                "max_drawdown_peak_date": risk_rows[ticker]["max_drawdown_peak_date"],
                "max_drawdown_trough_date": risk_rows[ticker]["max_drawdown_trough_date"],
                "max_drawdown_recovery_date": risk_rows[ticker]["max_drawdown_recovery_date"],
                "max_drawdown_duration_days": risk_rows[ticker]["max_drawdown_duration_days"],
                "max_drawdown_recovery_duration_days": risk_rows[ticker]["max_drawdown_recovery_duration_days"],
                "drawdown_points": risk_rows[ticker]["drawdown_points"],
                "volatility_5y_pct": risk_rows[ticker]["volatility_5y_pct"],
                "primary_benchmark": primary_benchmark,
                "primary_beat_rate_pct": primary_rate * 100.0,
                "secondary_benchmark": secondary_benchmark,
                "secondary_beat_rate_pct": secondary_rate * 100.0,
                "coverage": "High" if record["history_years"] >= 10 else "Medium",
            }
        )
        max_dd = record["max_drawdown_5y_pct"]
        volatility = record["volatility_5y_pct"]
        record["risk_warning"] = (
            "High historical risk"
            if max_dd > 50 or volatility > 50
            else "Elevated historical risk"
            if max_dd > 35 or volatility > 35
            else "Lower historical risk"
        )

    timing_overlay = timing_overlay or {}
    for ticker, record in records.items():
        timing = {
            "timing_signal": "Unavailable",
            "last_trade_action": "",
            "last_trade_date": "",
            "timing_data_end": "",
            "timing_excess_annualized_pct": np.nan,
            "timing_status": "unavailable",
        }
        timing.update(timing_overlay.get(ticker, {}))
        record.update(timing)

    scored = sorted(
        (record for record in records.values() if np.isfinite(record.get("score", np.nan))),
        key=lambda record: (-record["score"], record["ticker"]),
    )
    group_counts = Counter()
    selected = 0
    for raw_rank, record in enumerate(scored, 1):
        record["raw_rank"] = raw_rank
        group = record["industry_group"]
        if selected >= shortlist_size:
            record["shortlist_reason"] = f"Outside diversified top {shortlist_size}"
        elif group_counts[group] >= group_cap:
            record["shortlist_reason"] = f"Industry cap reached ({group_cap})"
        else:
            selected += 1
            group_counts[group] += 1
            record["shortlisted"] = True
            record["shortlist_rank"] = selected
            record["shortlist_reason"] = "Selected"

    for record in records.values():
        record.setdefault("shortlisted", False)
        record.setdefault("raw_rank", np.nan)
        record.setdefault("shortlist_rank", np.nan)
        if record["eligibility"] != "eligible":
            record["shortlist_reason"] = record["exclusion_reason"]
        else:
            record.setdefault(
                "shortlist_reason", f"Outside diversified top {shortlist_size}"
            )
        record.setdefault("persistence_panels", 0)
        record.setdefault("coverage", "Insufficient")
        record.setdefault("risk_warning", "Unavailable")

    result = pd.DataFrame(records.values())
    result["_sort_score"] = pd.to_numeric(result.get("score"), errors="coerce")
    result = result.sort_values(
        ["_sort_score", "ticker"], ascending=[False, True], na_position="last"
    ).drop(columns="_sort_score").reset_index(drop=True)
    return result, freshest_date


def _number(value, decimals=1, suffix=""):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(number):
        return "n/a"
    return f"{number:.{decimals}f}{suffix}"


def _sort_attribute(value):
    """Return a stable, safe sort key for a rendered table row."""
    if value is None or pd.isna(value):
        return ""
    return html.escape(str(value), quote=True)


def _month_year(value):
    date = pd.to_datetime(value, errors="coerce")
    return date.strftime("%b %Y") if not pd.isna(date) else "n/a"


def _duration_label(days):
    """Format a calendar-day duration with a readable month approximation."""
    try:
        number = float(days)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(number) or number < 0:
        return "n/a"
    return f"{int(round(number))} days ({number / 30.4375:.1f} mo)"


def _drawdown_chart(row):
    """Render the price-derived 5Y drawdown path and its peak-to-trough event."""
    points = row.get("drawdown_points", [])
    if not isinstance(points, (list, tuple)) or len(points) < 2:
        return ""
    parsed = []
    for date, drawdown in points:
        timestamp = pd.to_datetime(date, errors="coerce")
        try:
            value = float(drawdown)
        except (TypeError, ValueError):
            continue
        if not pd.isna(timestamp) and np.isfinite(value):
            parsed.append((timestamp, value))
    if len(parsed) < 2:
        return ""
    start, end = parsed[0][0], parsed[-1][0]
    span_days = max((end - start).days, 1)
    left, top, width, height = 38.0, 20.0, 412.0, 82.0
    worst = min(value for _, value in parsed)
    floor = min(-5.0, worst * 1.08)

    def x_value(date):
        return left + ((date - start).days / span_days) * width

    def y_value(drawdown):
        return top + (drawdown / floor) * height

    path = " ".join(
        f"{x_value(date):.1f},{y_value(drawdown):.1f}" for date, drawdown in parsed
    )
    peak_date = str(row.get("max_drawdown_peak_date", "") or "")
    trough_date = str(row.get("max_drawdown_trough_date", "") or "")
    peak_x = x_value(pd.to_datetime(peak_date)) if peak_date else left
    trough_x = x_value(pd.to_datetime(trough_date)) if trough_date else left
    trough_y = y_value(worst)
    ticker = html.escape(str(row.get("ticker", "stock")))
    peak_label = html.escape(_month_year(peak_date))
    trough_label = html.escape(_month_year(trough_date))
    drawdown_label = _number(row.get("max_drawdown_5y_pct"), 1, "%")
    drawdown_duration = _duration_label(row.get("max_drawdown_duration_days"))
    recovery_duration = _duration_label(row.get("max_drawdown_recovery_duration_days"))
    recovery_date = str(row.get("max_drawdown_recovery_date", "") or "")
    recovery = (
        f"Recovered {html.escape(_month_year(recovery_date))}"
        if recovery_date
        else "Not recovered within the 5Y window"
    )
    return f'''<figure class="drawdown-chart"><figcaption><b>5Y drawdown timeline</b><span>Red marks the worst peak-to-trough decline.</span></figcaption>
      <svg viewBox="0 0 470 137" role="img" aria-label="{ticker} five-year drawdown: peak {peak_label}, trough {trough_label}, maximum decline {drawdown_label}">
        <line class="dd-axis" x1="{left}" y1="{top}" x2="{left + width}" y2="{top}"/><line class="dd-axis" x1="{left}" y1="{top + height}" x2="{left + width}" y2="{top + height}"/>
        <polyline class="dd-path" points="{path}"/>
        <line class="dd-event-line" x1="{peak_x:.1f}" y1="{top}" x2="{peak_x:.1f}" y2="{top + height}"/><line class="dd-event-line" x1="{trough_x:.1f}" y1="{top}" x2="{trough_x:.1f}" y2="{top + height}"/>
        <rect class="dd-peak" x="{peak_x - 3:.1f}" y="{top - 3:.1f}" width="6" height="6"/><circle class="dd-trough" cx="{trough_x:.1f}" cy="{trough_y:.1f}" r="4"/>
        <text class="dd-label" x="4" y="{top + 4:.1f}">0%</text><text class="dd-label" x="2" y="{top + height:.1f}">−{drawdown_label}</text>
        <text class="dd-label" x="{left}" y="126">{html.escape(_month_year(start))}</text><text class="dd-label" x="{left + width}" y="126" text-anchor="end">{html.escape(_month_year(end))}</text>
      </svg>
      <p><span class="dd-event">Peak {peak_label}</span><span class="dd-event">Trough {trough_label} · −{drawdown_label}</span><span>{recovery}</span><span>Drawdown duration {html.escape(drawdown_duration)}</span><span>Recovery duration {html.escape(recovery_duration) if recovery_date else "Not reached"}</span></p>
    </figure>'''


def _card(row, snapshot_id="current"):
    ticker = html.escape(str(row["ticker"]))
    group = html.escape(str(row["industry_group"]))
    risk_class = "high" if str(row.get("risk_warning", "")).startswith("High") else "elevated" if str(row.get("risk_warning", "")).startswith("Elevated") else "lower"
    timing = html.escape(str(row.get("timing_signal", "Unavailable")))
    timing_detail = " · ".join(
        value
        for value in (
            str(row.get("last_trade_action", "") or ""),
            str(row.get("last_trade_date", "") or ""),
        )
        if value
    ) or "No current trade detail"
    components = (
        ("Return", row.get("return_score"), 25),
        ("Persistence", row.get("persistence_score"), 25),
        ("Risk", row.get("risk_score"), 25),
        ("Benchmarks", row.get("benchmark_score"), 15),
        ("Confidence", row.get("confidence_score"), 10),
    )
    component_html = "".join(
        f'<span><small>{html.escape(label)}</small><b>{_number(value)}/{maximum}</b></span>'
        for label, value, maximum in components
    )
    gates = (
        ("quality", "Financial quality and free cash flow reviewed"),
        ("balance", "Balance sheet and refinancing risk reviewed"),
        ("valuation", "Valuation versus history and peers is acceptable"),
        ("filing", "Latest filing, guidance, thesis, and risks reviewed"),
    )
    gate_html = "".join(
        f'<label><input type="checkbox" data-gate="{html.escape(snapshot_id)}|{ticker}|{key}"> {html.escape(label)}</label>'
        for key, label in gates
    )
    return f'''<article class="candidate-card" data-ticker="{ticker}">
      <div class="card-head"><span class="rank">#{int(row["shortlist_rank"])}</span><div><h2>{ticker}</h2><p>{group}</p></div><strong>{_number(row.get("score"))}</strong></div>
      <div class="components">{component_html}</div>
      <div class="metrics">
        <span>3Y CAGR <b>{_number(row.get("cagr_3y_pct"), 1, "%")}</b></span>
        <span>5Y CAGR <b>{_number(row.get("cagr_5y_pct"), 1, "%")}</b></span>
        <span>10Y CAGR <b>{_number(row.get("cagr_10y_pct"), 1, "%")}</b></span>
        <span>5Y drawdown <b>−{_number(row.get("max_drawdown_5y_pct"), 1, "%")}</b></span>
        <span>5Y volatility <b>{_number(row.get("volatility_5y_pct"), 1, "%")}</b></span>
        <span>History <b>{_number(row.get("history_years"), 1, "Y")}</b></span>
      </div>
      {_drawdown_chart(row)}
      <div class="benchmarks"><span>Beat {html.escape(str(row.get("primary_benchmark", "SPY")))} <b>{_number(row.get("primary_beat_rate_pct"), 0, "%")}</b></span><span>Beat {html.escape(str(row.get("secondary_benchmark", "QQQ")))} <b>{_number(row.get("secondary_beat_rate_pct"), 0, "%")}</b></span><span>{int(row.get("persistence_panels", 0))} persistence panels</span></div>
      <p class="risk {risk_class}">{html.escape(str(row.get("risk_warning", "Unavailable")))}</p>
      <div class="timing"><span>Timing overlay</span><strong>{timing}</strong><small>{html.escape(timing_detail)} · data through {html.escape(str(row.get("timing_data_end", "") or "n/a"))} · not scored</small></div>
      <fieldset class="gate"><legend>Fundamentals gate · <span data-gate-status="{ticker}">Review required</span></legend>{gate_html}</fieldset>
    </article>'''


def _snapshot_panel(snapshot, shortlist_size, group_cap, active=False):
    """Render one independently sortable point-in-time selection result."""
    rows = snapshot["rows"]
    benchmark_rows = snapshot.get("benchmark_rows", pd.DataFrame())
    snapshot_id = str(snapshot["id"])
    shortlist = rows[rows["shortlisted"].fillna(False)].sort_values("shortlist_rank")
    candidates = len(rows)
    eligible = int((rows["eligibility"] == "eligible").sum())
    excluded = candidates - eligible
    cards = "".join(_card(row, snapshot_id) for _, row in shortlist.iterrows())
    table_rows = []
    table_rows_source = pd.concat([rows, benchmark_rows], ignore_index=True)
    rank_column = "display_rank" if "display_rank" in table_rows_source.columns else "raw_rank"
    table_rows_source = table_rows_source.sort_values(
        [rank_column, "ticker"], na_position="last"
    )
    for _, row in table_rows_source.iterrows():
        is_benchmark = str(row.get("role", "")) == "benchmark"
        rank = _number(row.get("display_rank", row.get("raw_rank")), 0)
        rank = "—" if rank == "n/a" else rank
        score = _number(row.get("score"))
        reason = row.get("shortlist_reason", "") or row.get("exclusion_reason", "")
        sort_attributes = {
            "rank": row.get("display_rank", row.get("raw_rank")),
            "ticker": row.get("ticker"),
            "industry": row.get("industry_group"),
            "score": row.get("score"),
            "cagr": row.get("cagr_5y_pct"),
            "drawdown": row.get("max_drawdown_5y_pct"),
            "coverage": row.get("coverage"),
            "status": reason,
        }
        attributes = " ".join(
            f'data-{key}="{_sort_attribute(value)}"'
            for key, value in sort_attributes.items()
        )
        row_class = "benchmark-row" if is_benchmark else "selected-row" if bool(row.get("shortlisted", False)) else ""
        benchmark_attribute = "true" if is_benchmark else "false"
        table_rows.append(
            f'''<tr class="{row_class}" data-benchmark="{benchmark_attribute}" {attributes}><td>{rank}</td><td><b>{html.escape(str(row["ticker"]))}</b></td><td>{html.escape(str(row["industry_group"]))}</td><td>{score}</td><td>{_number(row.get("cagr_5y_pct"),1,"%")}</td><td>{_number(row.get("max_drawdown_5y_pct"),1,"%")}</td><td>{html.escape(str(row.get("coverage","Insufficient")))}</td><td>{html.escape(str(reason))}</td></tr>'''
        )
    label = html.escape(str(snapshot["label"]))
    as_of_date = pd.Timestamp(snapshot["as_of_date"]).strftime("%Y-%m-%d")
    hidden = "" if active else " hidden"
    return f'''<section class="snapshot-panel" role="tabpanel" id="snapshot-panel-{snapshot_id}" data-snapshot-panel="{snapshot_id}" aria-labelledby="snapshot-tab-{snapshot_id}"{hidden}>
      <div class="snapshot-asof"><b>{label} selection replay</b><span>Common as-of date: {as_of_date}. Every score and chart uses prices available on or before this date.</span></div>
      <section class="summary"><div><span>Candidates</span><strong>{candidates}</strong></div><div><span>Score eligible</span><strong>{eligible}</strong></div><div><span>Diversified shortlist</span><strong>{len(shortlist)} of {shortlist_size}</strong></div><div><span>Excluded</span><strong>{excluded}</strong></div></section>
      <div class="section-head"><div><h2>Complete candidate ranking</h2><p>Click a column name to sort. SPY and QQQ are ranked benchmark references for comparison, but never considered for selection.</p></div></div>
      <div class="table-wrap"><table class="candidate-ranking" id="candidateRanking-{snapshot_id}"><thead><tr><th scope="col" aria-sort="ascending"><button class="table-sort" type="button" data-sort-key="rank">Rank <span class="sort-indicator" aria-hidden="true">▲</span></button></th><th scope="col" aria-sort="none"><button class="table-sort" type="button" data-sort-key="ticker">Ticker <span class="sort-indicator" aria-hidden="true"></span></button></th><th scope="col" aria-sort="none"><button class="table-sort" type="button" data-sort-key="industry">Industry group <span class="sort-indicator" aria-hidden="true"></span></button></th><th scope="col" aria-sort="none"><button class="table-sort" type="button" data-sort-key="score">Score <span class="sort-indicator" aria-hidden="true"></span></button></th><th scope="col" aria-sort="none"><button class="table-sort" type="button" data-sort-key="cagr">5Y CAGR <span class="sort-indicator" aria-hidden="true"></span></button></th><th scope="col" aria-sort="none"><button class="table-sort" type="button" data-sort-key="drawdown">5Y drawdown <span class="sort-indicator" aria-hidden="true"></span></button></th><th scope="col" aria-sort="none"><button class="table-sort" type="button" data-sort-key="coverage">Coverage <span class="sort-indicator" aria-hidden="true"></span></button></th><th scope="col" aria-sort="none"><button class="table-sort" type="button" data-sort-key="status">Selection status <span class="sort-indicator" aria-hidden="true"></span></button></th></tr></thead><tbody>{''.join(table_rows)}</tbody></table></div>
      <aside class="selection-explainer"><p><b>Selection status:</b> <i>Selected</i> means the stock was eligible and survived the maximum {group_cap} per industry group; other rows show the reason it was capped, outside the top {shortlist_size}, or ineligible. <i>Benchmark reference</i> means SPY or QQQ: its display-only score uses the same price-derived components and candidate peer distributions, so it receives a comparison rank but is never selected.</p><p><b>Score (0–100):</b> price-derived return strength 25 points, historical persistence 25, lower drawdown and volatility 25, historical SPY/QQQ consistency 15, and usable-history confidence 10. The adaptive timing overlay does not affect the score or rank.</p></aside>
      <div class="section-head"><div><h2>Diversified shortlist</h2><p>Greedy score order, maximum {group_cap} per industry group.</p></div><button class="reset-gates" type="button" data-reset-snapshot="{snapshot_id}">Reset fundamentals checks</button></div>
      <section class="ranking-grid">{cards or '<p>No candidates met the selection rules.</p>'}</section>
    </section>'''


def _all_rankings_panel(snapshots, active=False):
    """Render the requested snapshots as side-by-side ranked stock columns."""
    columns = []
    max_rows = 0
    for snapshot in snapshots:
        rows = snapshot["rows"]
        benchmark_rows = snapshot.get("benchmark_rows", pd.DataFrame())
        ranking = pd.concat([rows, benchmark_rows], ignore_index=True)
        rank_column = "display_rank" if "display_rank" in ranking.columns else "raw_rank"
        ranking = ranking.sort_values([rank_column, "ticker"], na_position="last")
        entries = []
        for _, row in ranking.iterrows():
            rank = _number(row.get("display_rank", row.get("raw_rank")), 0)
            rank = f"#{rank}" if rank != "n/a" else "Unranked"
            ticker = html.escape(str(row.get("ticker", "")))
            score = _number(row.get("score"))
            is_benchmark = str(row.get("role", "")) == "benchmark"
            cell_class = "ranking-cell benchmark-cell" if is_benchmark else "ranking-cell"
            ticker_attribute = _sort_attribute(row.get("ticker"))
            entries.append(
                f'<div class="{cell_class}" data-ticker="{ticker_attribute}" role="button" tabindex="0" aria-label="{ticker}, {rank}, score {score}"><span class="all-rank">{rank}</span> <b>{ticker}</b> <small>({score})</small></div>'
            )
        columns.append((snapshot, entries))
        max_rows = max(max_rows, len(entries))

    header_cells = "".join(
        f'<th scope="col">{html.escape(str(snapshot["label"]))}</th>'
        for snapshot, _ in columns
    )
    body_rows = []
    for index in range(max_rows):
        body_rows.append(
            "<tr>"
            + "".join(
                f'<td>{entries[index] if index < len(entries) else ""}</td>'
                for _, entries in columns
            )
            + "</tr>"
        )
    hidden = "" if active else " hidden"
    return f'''<section class="snapshot-panel all-rankings-panel" role="tabpanel" id="snapshot-panel-all" data-snapshot-panel="all" aria-labelledby="snapshot-tab-all"{hidden}>
      <div class="snapshot-asof"><b>All selection rankings</b><span>Each column is the complete ranked list for that point-in-time replay. Benchmark references are included for comparison and are never selected.</span></div>
      <div class="section-head"><div><h2>Rankings side by side</h2><p>Stocks are ordered from highest to lowest display rank within each column.</p></div></div>
      <div class="table-wrap"><table class="all-ranking" id="allRankings"><thead><tr>{header_cells}</tr></thead><tbody>{''.join(body_rows)}</tbody></table></div>
    </section>'''


def render_selection_dashboard(
    rows,
    output_path,
    tickers_path,
    metadata_path,
    data_dir,
    freshest_date,
    summary_path=None,
    shortlist_size=10,
    group_cap=3,
    snapshots=None,
):
    output_path = _resolved(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if snapshots is None:
        snapshots = [
            {
                "years_ago": 0,
                "as_of_date": freshest_date,
                "rows": rows,
                "id": "current",
                "label": "Current",
            }
        ]
    active_id = "current" if any(snapshot["id"] == "current" for snapshot in snapshots) else snapshots[0]["id"]
    clock_tabs = "".join(
        f'<button class="clock-tab" type="button" role="tab" id="snapshot-tab-{html.escape(str(snapshot["id"]))}" data-snapshot="{html.escape(str(snapshot["id"]))}" aria-controls="snapshot-panel-{html.escape(str(snapshot["id"]))}" aria-selected="{str(snapshot["id"] == active_id).lower()}">{html.escape(str(snapshot["label"]))}</button>'
        for snapshot in snapshots
    )
    clock_tabs += '<button class="clock-tab" type="button" role="tab" id="snapshot-tab-all" data-snapshot="all" aria-controls="snapshot-panel-all" aria-selected="false">Show All</button>'
    snapshot_panels = "".join(
        _snapshot_panel(snapshot, shortlist_size, group_cap, snapshot["id"] == active_id)
        for snapshot in snapshots
    )
    snapshot_panels += _all_rankings_panel(snapshots)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary_name = Path(summary_path).name if summary_path else "unavailable"
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Long-Term Stock Selection</title><script>(()=>{{const key='stockSelection.theme.v1';let theme='';try{{theme=localStorage.getItem(key)||''}}catch(e){{}}if(theme!=='light'&&theme!=='dark')theme=matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';document.documentElement.dataset.theme=theme;document.documentElement.style.colorScheme=theme;}})();</script><style>
    :root{{--ink:#152337;--muted:#647183;--line:#d9e2e5;--paper:#fff;--bg:#f4f7f5;--green:#0c6b58;--soft:#e0f1eb;--amber:#a8640b;--red:#b44444;--notice-bg:#fff4dd;--notice-ink:#734806;--subtle:#f3f6f5;--chart-bg:#fafcfb;--selected-row:#e6f4ed;--benchmark-row:#e8effa;--benchmark-ink:#203f6f;--benchmark-border:#315c9b;--th-bg:#edf3f1;--card-shadow:rgba(20,35,55,.05);--high-bg:#f9dddd;--elevated-bg:#fff0d8;--complete-bg:#edf8f4;color-scheme:light}}
    :root[data-theme=dark]{{--ink:#e8eef7;--muted:#aeb9c8;--line:#34465a;--paper:#162231;--bg:#0d1520;--green:#78d9bf;--soft:#173d35;--amber:#f2b75e;--red:#ff8b8b;--notice-bg:#3a2d17;--notice-ink:#ffd894;--subtle:#202e3d;--chart-bg:#111c28;--selected-row:#173a32;--benchmark-row:#1b304b;--benchmark-ink:#b9d5ff;--benchmark-border:#73a7ef;--th-bg:#202f3d;--card-shadow:rgba(0,0,0,.28);--high-bg:#45272b;--elevated-bg:#45351f;--complete-bg:#173a32;color-scheme:dark}}
    *{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}}header{{padding:22px clamp(16px,4vw,48px);border-bottom:1px solid var(--line);background:var(--paper)}}.header-top{{display:flex;align-items:center;justify-content:space-between;gap:14px}}.header-links{{min-width:0}}header a{{color:var(--green);font-weight:800;text-decoration:none}}.theme-toggle{{display:inline-flex;align-items:center;gap:7px;white-space:nowrap;font-weight:800}}.theme-icon{{font-size:1rem;line-height:1}}h1{{margin:12px 0 6px;font-size:clamp(1.7rem,4vw,2.8rem);letter-spacing:-.04em}}header p{{max-width:1000px;margin:5px 0;color:var(--muted)}}.provenance{{font-size:.78rem;overflow-wrap:anywhere}}main{{padding:22px clamp(16px,4vw,48px) 56px}}.clock-tabs{{display:flex;gap:8px;margin:18px 0;overflow-x:auto;padding-bottom:2px}}.clock-tab{{flex:0 0 auto;font-weight:800}}.clock-tab[aria-selected=true]{{border-color:#6db49f;background:var(--soft);color:var(--green)}}.snapshot-asof{{display:flex;flex-wrap:wrap;gap:8px 14px;margin:0 0 10px;color:var(--muted);font-size:.8rem}}.snapshot-asof b{{color:var(--ink)}}.summary{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:18px}}.summary div{{padding:14px;border:1px solid var(--line);border-radius:14px;background:var(--paper)}}.summary span{{display:block;color:var(--muted);font-size:.72rem;text-transform:uppercase}}.summary strong{{display:block;margin-top:5px;font-size:1.15rem}}.notice{{padding:13px 15px;border-left:4px solid var(--amber);border-radius:10px;background:var(--notice-bg);color:var(--notice-ink)}}.section-head{{display:flex;justify-content:space-between;gap:12px;align-items:end;margin:26px 0 12px}}.section-head h2{{margin:0}}.section-head p{{margin:0;color:var(--muted)}}.ranking-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.candidate-card{{padding:15px;border:1px solid var(--line);border-radius:16px;background:var(--paper);box-shadow:0 7px 22px var(--card-shadow)}}.card-head{{display:flex;align-items:center;gap:10px}}.card-head .rank{{display:grid;place-items:center;min-width:36px;height:30px;border-radius:999px;background:var(--soft);color:var(--green);font-weight:850}}.card-head h2{{margin:0;font-size:1.15rem}}.card-head p{{margin:2px 0 0;color:var(--muted);font-size:.78rem}}.card-head>strong{{margin-left:auto;color:var(--green);font-size:1.65rem}}.components{{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin:12px 0}}.components span,.metrics span,.benchmarks span{{padding:7px;border-radius:8px;background:var(--subtle)}}.components small{{display:block;color:var(--muted);font-size:.65rem}}.components b{{font-size:.78rem}}.metrics,.benchmarks{{display:flex;gap:6px;flex-wrap:wrap}}.metrics span,.benchmarks span{{color:var(--muted);font-size:.73rem}}.metrics b,.benchmarks b{{color:var(--ink)}}.drawdown-chart{{margin:12px 0 10px;padding:9px;border:1px solid var(--line);border-radius:10px;background:var(--chart-bg)}}.drawdown-chart figcaption{{display:flex;justify-content:space-between;gap:8px;align-items:baseline;font-size:.73rem}}.drawdown-chart figcaption span{{color:var(--muted);font-size:.67rem}}.drawdown-chart svg{{display:block;width:100%;height:auto;margin-top:5px;overflow:visible}}.dd-axis{{stroke:var(--line);stroke-width:1}}.dd-path{{fill:none;stroke:var(--green);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}}.dd-event-line{{stroke:var(--red);stroke-width:1;stroke-dasharray:3 3;opacity:.72}}.dd-peak,.dd-trough{{fill:var(--red);stroke:var(--paper);stroke-width:1.5}}.dd-label{{fill:var(--muted);font-size:9px}}.drawdown-chart p{{display:flex;gap:8px;flex-wrap:wrap;margin:3px 0 0;color:var(--muted);font-size:.68rem}}.dd-event{{color:var(--red);font-weight:800}}.risk{{display:inline-block;margin:10px 0;padding:5px 8px;border-radius:999px;font-size:.72rem;font-weight:800}}.risk.high{{background:var(--high-bg);color:var(--red)}}.risk.elevated{{background:var(--elevated-bg);color:var(--amber)}}.risk.lower{{background:var(--soft);color:var(--green)}}.timing{{display:grid;gap:2px;padding:10px;border:1px dashed var(--line);border-radius:10px}}.timing span,.timing small{{color:var(--muted);font-size:.7rem}}.gate{{display:grid;gap:6px;margin-top:11px;padding:10px;border:1px solid var(--line);border-radius:10px}}.gate legend{{font-size:.75rem;font-weight:800}}.gate label{{font-size:.75rem}}.gate.complete{{border-color:#6db49f;background:var(--complete-bg)}}.table-wrap{{overflow-x:auto;border:1px solid var(--line);border-radius:14px;background:var(--paper)}}.selection-explainer{{margin:10px 0 0;padding:11px 13px;border-left:4px solid var(--green);background:var(--soft);color:var(--ink);font-size:.76rem;line-height:1.45}}.selection-explainer p{{margin:3px 0}}table{{width:100%;min-width:950px;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:left;font-size:.78rem}}.candidate-ranking tbody tr.selected-row td{{background:var(--selected-row)}}.candidate-ranking tbody tr.benchmark-row td{{background:var(--benchmark-row);color:var(--benchmark-ink);font-weight:650}}.candidate-ranking tbody tr.benchmark-row td:first-child{{border-left:4px solid var(--benchmark-border)}}th{{position:sticky;top:0;background:var(--th-bg);color:var(--muted)}}.table-sort{{padding:0;border:0;border-radius:0;background:transparent;color:inherit;font:inherit;font-weight:800;cursor:pointer}}.table-sort:hover,.table-sort:focus-visible{{color:var(--green);text-decoration:underline}}.sort-indicator{{display:inline-block;min-width:1.1em;color:var(--green)}}footer{{margin-top:22px;color:var(--muted);font-size:.75rem}}button{{padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--paper);color:var(--ink);cursor:pointer}}
    .sr-only{{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}}.all-ranking{{min-width:1000px;table-layout:fixed}}.all-ranking th,.all-ranking td{{padding:7px 10px}}.all-ranking td{{vertical-align:top;white-space:nowrap}}.ranking-cell{{line-height:1.35;cursor:pointer;transition:background .12s ease,color .12s ease}}.ranking-cell b{{font-size:.82rem}}.ranking-cell small{{color:var(--muted);font-size:.68rem}}.all-rank{{color:var(--green);font-size:.7rem;font-weight:800}}.benchmark-cell{{color:var(--benchmark-ink)}}.all-ranking .ranking-cell:hover,.all-ranking .ranking-cell:focus-visible,.all-ranking .ranking-cell.ticker-highlight{{background:var(--soft);color:var(--ink);outline:none}}.all-ranking .ranking-cell.ticker-highlight small,.all-ranking .ranking-cell:hover small,.all-ranking .ranking-cell:focus-visible small{{color:inherit}}
    @media(min-width:1500px){{.ranking-grid{{grid-template-columns:repeat(3,minmax(0,1fr))}}.candidate-card{{padding:13px}}}}@media(min-width:2100px){{.ranking-grid{{grid-template-columns:repeat(4,minmax(0,1fr))}}}}@media(max-width:850px){{.summary{{grid-template-columns:repeat(2,1fr)}}.ranking-grid{{grid-template-columns:1fr}}.components{{grid-template-columns:repeat(3,1fr)}}}}@media(max-width:520px){{.summary{{grid-template-columns:1fr 1fr}}.section-head{{display:block}}.section-head button{{margin-top:8px}}}}
    </style></head><body><header><div class="header-top"><div class="header-links"><a href="dashboard.html">← Master dashboard</a> · <a href="dashboard_stock_selection_backtest.html">Selection backtest</a> · <a href="dashboard_stock_selection_score_analysis.html">Score analysis</a></div><button class="theme-toggle" type="button" data-theme-toggle aria-pressed="false"><span class="theme-icon" aria-hidden="true">☾</span><span data-theme-label>Dark mode</span></button></div><h1>Long-Term Stock Selection</h1><p>Moderate-risk, 5+ year research shortlist. Price history determines the score; fundamentals must be reviewed separately, and adaptive-strategy signals are timing context only.</p><p class="provenance">Generated {generated_at} · prices through {freshest_date.strftime('%Y-%m-%d')} · universe {html.escape(str(tickers_path))} · groups {html.escape(str(metadata_path))} · timing {html.escape(summary_name)}</p></header><main>
    <p class="notice"><b>Research support only:</b> this ranking is not a buy recommendation and does not evaluate current valuation, financial quality, tax, suitability, or position size.</p>
    <nav class="clock-tabs" role="tablist" aria-label="Turn Back The Clock"><span class="sr-only">Turn Back The Clock</span>{clock_tabs}</nav>
    {snapshot_panels}
    <footer>Weights: return 25 · persistence 25 · risk 25 · benchmark consistency 15 · data confidence 10. Inputs are local adjusted-price histories from {html.escape(str(data_dir))}.</footer>
    <script>(()=>{{const themeKey='stockSelection.theme.v1',themeToggle=document.querySelector('[data-theme-toggle]'),themeLabel=document.querySelector('[data-theme-label]'),themeIcon=themeToggle?.querySelector('.theme-icon');const renderTheme=theme=>{{const dark=theme==='dark';document.documentElement.dataset.theme=theme;document.documentElement.style.colorScheme=theme;themeToggle?.setAttribute('aria-pressed',String(dark));themeToggle?.setAttribute('aria-label',dark?'Switch to light mode':'Switch to dark mode');if(themeLabel)themeLabel.textContent=dark?'Light mode':'Dark mode';if(themeIcon)themeIcon.textContent=dark?'☀':'☾';}};renderTheme(document.documentElement.dataset.theme||'light');themeToggle?.addEventListener('click',()=>{{const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';renderTheme(theme);try{{localStorage.setItem(themeKey,theme)}}catch(e){{}}}});const key='stockSelection.fundamentals.v2',boxes=[...document.querySelectorAll('[data-gate]')],clockTabs=[...document.querySelectorAll('.clock-tab')],snapshotPanels=[...document.querySelectorAll('[data-snapshot-panel]')];let state={{}};try{{state=JSON.parse(localStorage.getItem(key)||'{{}}')}}catch(e){{state={{}}}}const renderGates=()=>{{document.querySelectorAll('.candidate-card').forEach(card=>{{const own=[...card.querySelectorAll('[data-gate]')],done=own.length>0&&own.every(box=>box.checked),label=card.querySelector('[data-gate-status]');card.querySelector('.gate').classList.toggle('complete',done);if(label)label.textContent=done?'Gate complete':'Review required';}})}};boxes.forEach(box=>{{box.checked=Boolean(state[box.dataset.gate]);box.addEventListener('change',()=>{{state[box.dataset.gate]=box.checked;try{{localStorage.setItem(key,JSON.stringify(state))}}catch(e){{}}renderGates();}})}});document.querySelectorAll('[data-reset-snapshot]').forEach(button=>button.addEventListener('click',()=>{{const snapshot=button.dataset.resetSnapshot;boxes.filter(box=>box.dataset.gate.startsWith(`${{snapshot}}|`)).forEach(box=>{{box.checked=false;delete state[box.dataset.gate];}});try{{localStorage.setItem(key,JSON.stringify(state))}}catch(e){{}}renderGates();}}));const selectSnapshot=(snapshot,focus=false,updateHash=true)=>{{if(!clockTabs.some(tab=>tab.dataset.snapshot===snapshot))snapshot=clockTabs[0]?.dataset.snapshot||'current';clockTabs.forEach(tab=>{{const active=tab.dataset.snapshot===snapshot;tab.setAttribute('aria-selected',String(active));if(active&&focus)tab.focus();}});snapshotPanels.forEach(panel=>panel.hidden=panel.dataset.snapshotPanel!==snapshot);if(updateHash&&history.replaceState)history.replaceState(null,'',`#${{snapshot}}`);}};clockTabs.forEach(tab=>tab.addEventListener('click',()=>selectSnapshot(tab.dataset.snapshot)));document.querySelector('.clock-tabs').addEventListener('keydown',event=>{{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const current=clockTabs.findIndex(tab=>tab.getAttribute('aria-selected')==='true');const next=event.key==='Home'?0:event.key==='End'?clockTabs.length-1:event.key==='ArrowRight'?(current+1)%clockTabs.length:(current-1+clockTabs.length)%clockTabs.length;selectSnapshot(clockTabs[next].dataset.snapshot,true);}});const sortTable=(table,keyName,direction)=>{{const body=table.tBodies[0],rows=[...body.rows],factor=direction==='asc'?1:-1;rows.sort((left,right)=>{{const a=left.dataset[keyName]||'',b=right.dataset[keyName]||'',aNumber=Number(a),bNumber=Number(b),aIsNumber=a!==''&&Number.isFinite(aNumber),bIsNumber=b!==''&&Number.isFinite(bNumber);if(aIsNumber&&bIsNumber&&aNumber!==bNumber)return(aNumber-bNumber)*factor;if(aIsNumber!==bIsNumber)return aIsNumber?-1:1;const compared=a.localeCompare(b,undefined,{{numeric:true,sensitivity:'base'}});return compared?compared*factor:left.dataset.ticker.localeCompare(right.dataset.ticker);}});rows.forEach(row=>body.appendChild(row));}};document.querySelectorAll('.candidate-ranking').forEach(table=>{{let sortKey='rank',sortDirection='asc';const buttons=[...table.querySelectorAll('.table-sort')],updateHeaders=()=>buttons.forEach(button=>{{const active=button.dataset.sortKey===sortKey,header=button.closest('th'),indicator=button.querySelector('.sort-indicator');header.setAttribute('aria-sort',active?(sortDirection==='asc'?'ascending':'descending'):'none');indicator.textContent=active?(sortDirection==='asc'?'▲':'▼'):'';}});buttons.forEach(button=>button.addEventListener('click',()=>{{const nextKey=button.dataset.sortKey;sortDirection=nextKey===sortKey?(sortDirection==='asc'?'desc':'asc'):'asc';sortKey=nextKey;sortTable(table,sortKey,sortDirection);updateHeaders();}}));updateHeaders();}});const requested=location.hash.slice(1);selectSnapshot(requested||clockTabs[0]?.dataset.snapshot||'current',false,false);window.addEventListener('hashchange',()=>selectSnapshot(location.hash.slice(1),false,false));renderGates();}})();</script>
    </main></body></html>'''
    all_ranking_script = """<script>
    (() => {
      const cells = [...document.querySelectorAll('.all-ranking [data-ticker]')];
      if (!cells.length) return;
      let selectedTicker = '';
      const updatePressed = () => cells.forEach(cell => cell.setAttribute('aria-pressed', String(Boolean(selectedTicker) && cell.dataset.ticker === selectedTicker)));
      const clearHighlight = () => cells.forEach(cell => cell.classList.remove('ticker-highlight'));
      const highlight = ticker => cells.forEach(cell => cell.classList.toggle('ticker-highlight', cell.dataset.ticker === ticker));
      const restore = () => {
        if (selectedTicker) highlight(selectedTicker);
        else clearHighlight();
        updatePressed();
      };
      cells.forEach(cell => {
        cell.addEventListener('mouseenter', () => highlight(cell.dataset.ticker));
        cell.addEventListener('mouseleave', restore);
        cell.addEventListener('focus', () => highlight(cell.dataset.ticker));
        cell.addEventListener('blur', restore);
        cell.addEventListener('click', () => {
          selectedTicker = selectedTicker === cell.dataset.ticker ? '' : cell.dataset.ticker;
          restore();
        });
        cell.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            cell.click();
          } else if (event.key === 'Escape') {
            selectedTicker = '';
            restore();
            cell.blur();
          }
        });
      });
    })();
    </script>"""
    page = page.replace("</main></body></html>", all_ranking_script + "</main></body></html>")
    output_path.write_text(page, encoding="utf-8")
    return output_path


def write_selection_csv(rows, output_path):
    output_path = _resolved(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export = rows.drop(columns=["drawdown_points"], errors="ignore").copy()
    export = export.replace([np.inf, -np.inf], np.nan).fillna("")
    export.to_csv(output_path, index=False)
    return output_path


def build_selection_dashboard(
    tickers_file=DEFAULT_TICKERS_FILE,
    metadata_file=DEFAULT_METADATA_FILE,
    data_dir=DATA_DIR,
    summary_file="",
    primary_benchmark="SPY",
    secondary_benchmark="QQQ",
    shortlist_size=10,
    group_cap=3,
    years_ago=DEFAULT_YEARS_AGO,
    html_output=DEFAULT_HTML_OUTPUT,
    csv_output=DEFAULT_CSV_OUTPUT,
):
    tickers_file = _resolved(tickers_file)
    metadata_file = _resolved(metadata_file)
    data_dir = _resolved(data_dir)
    tickers = load_ticker_universe(tickers_file)
    metadata = load_selection_metadata(metadata_file, tickers)
    prices = load_price_universe(tickers, data_dir)
    usable_dates = [item.get("latest_date") for item in prices.values() if item.get("latest_date") is not None]
    if not usable_dates:
        raise ValueError("No usable price histories found")
    freshest_date = max(usable_dates)
    timing, resolved_summary = load_timing_overlay(summary_file, freshest_date)
    snapshots, freshest_date = build_selection_snapshots(
        tickers,
        metadata,
        prices,
        years_ago=years_ago,
        primary_benchmark=primary_benchmark,
        secondary_benchmark=secondary_benchmark,
        shortlist_size=shortlist_size,
        group_cap=group_cap,
        current_timing_overlay=timing,
    )
    current_snapshot = next(
        (snapshot for snapshot in snapshots if snapshot["years_ago"] == 0), snapshots[0]
    )
    rows = current_snapshot["rows"]
    html_path = render_selection_dashboard(
        rows,
        html_output,
        tickers_file,
        metadata_file,
        data_dir,
        freshest_date,
        resolved_summary,
        shortlist_size,
        group_cap,
        snapshots=snapshots,
    )
    csv_path = write_selection_csv(
        pd.concat([snapshot["rows"] for snapshot in snapshots], ignore_index=True),
        csv_output,
    )
    return {
        "rows": rows,
        "snapshots": snapshots,
        "html": html_path,
        "csv": csv_path,
        "freshest_date": freshest_date,
        "summary": resolved_summary,
        "universe_count": len(tickers),
        "candidate_count": int((metadata["role"] == "candidate").sum()),
        "benchmark_count": int((metadata["role"] == "benchmark").sum()),
    }


def main(argv=None):
    args = parse_args(argv)
    result = build_selection_dashboard(
        tickers_file=args.tickers_file,
        metadata_file=args.metadata_file,
        data_dir=args.data_dir,
        summary_file=args.summary_file,
        primary_benchmark=args.primary_benchmark,
        secondary_benchmark=args.secondary_benchmark,
        shortlist_size=args.shortlist_size,
        group_cap=args.group_cap,
        years_ago=args.years_ago,
        html_output=args.html_output,
        csv_output=args.csv_output,
    )
    shortlist = result["rows"][result["rows"]["shortlisted"]].sort_values("shortlist_rank")
    print(
        f"Universe: {result['universe_count']} ({result['candidate_count']} candidates, "
        f"{result['benchmark_count']} benchmarks)"
    )
    for _, row in shortlist.iterrows():
        print(
            f"#{int(row['shortlist_rank']):>2} {row['ticker']:<5} "
            f"score {row['score']:.1f} · {row['industry_group']}"
        )
    print(f"HTML: {result['html']}")
    print(f"CSV:  {result['csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
