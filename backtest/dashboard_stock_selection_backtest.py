"""Rigorous, price-derived evaluation of long-term stock-selection snapshots.

The report deliberately distinguishes exploratory static-universe replays from
validated point-in-time universes.  Review-date shortlists are hindsight
comparators only and never influence historical scores.
"""

from __future__ import annotations

import argparse
import html
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import dashboard_stock_selection as selection


SCRIPT_DIR = Path(__file__).resolve().parent
REPORTS_DIR = SCRIPT_DIR / "outputs" / "reports"
DEFAULT_HTML_OUTPUT = REPORTS_DIR / "dashboard_stock_selection_backtest.html"
DEFAULT_CSV_OUTPUT = REPORTS_DIR / "dashboard_stock_selection_backtest.csv"
DEFAULT_SUMMARY_OUTPUT = REPORTS_DIR / "dashboard_stock_selection_backtest_summary.csv"
DEFAULT_NAV_OUTPUT = REPORTS_DIR / "dashboard_stock_selection_backtest_nav.csv"
DEFAULT_UNIVERSE_HISTORY = SCRIPT_DIR / "selection_universe_history.csv"
DEFAULT_YEARS_AGO = (1, 2, 3)
DEFAULT_HOLDING_YEARS = (1,)
MODEL_NAMES = ("baseline", "recency", "risk_adjusted", "combined")
TRADING_DAYS = 252.0
STALE_SESSION_DAYS = 7


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Build rigorous historical stock-selection cohort and walk-forward reports."
    )
    parser.add_argument("--tickers-file", default=str(selection.DEFAULT_TICKERS_FILE))
    parser.add_argument("--metadata-file", default=str(selection.DEFAULT_METADATA_FILE))
    parser.add_argument("--data-dir", default=str(selection.DATA_DIR))
    parser.add_argument(
        "--universe-history-file", default=str(DEFAULT_UNIVERSE_HISTORY)
    )
    parser.add_argument(
        "--years-ago",
        nargs="+",
        type=int,
        choices=(1, 2, 3),
        default=DEFAULT_YEARS_AGO,
        metavar="YEARS",
        help="Legacy cohort selection ages (default: 1 2 3).",
    )
    parser.add_argument(
        "--holding-years",
        nargs="+",
        type=int,
        choices=(1,),
        default=DEFAULT_HOLDING_YEARS,
        metavar="YEARS",
        help="Annual walk-forward holding horizon. Selections are always reviewed after 1Y.",
    )
    parser.add_argument("--walk-forward-years", type=int, default=10)
    parser.add_argument("--execution-lag-sessions", type=int, default=1)
    parser.add_argument("--one-way-cost-bps", type=float, default=10.0)
    parser.add_argument("--random-portfolios", type=int, default=5000)
    parser.add_argument("--random-seed", type=int, default=20260814)
    parser.add_argument("--primary-benchmark", default="SPY")
    parser.add_argument("--secondary-benchmark", default="QQQ")
    parser.add_argument("--shortlist-size", type=int, default=10)
    parser.add_argument("--group-cap", type=int, default=3)
    parser.add_argument("--html-output", default=str(DEFAULT_HTML_OUTPUT))
    parser.add_argument("--csv-output", default=str(DEFAULT_CSV_OUTPUT))
    parser.add_argument("--summary-output", default=str(DEFAULT_SUMMARY_OUTPUT))
    parser.add_argument("--nav-output", default=str(DEFAULT_NAV_OUTPUT))
    return parser.parse_args(argv)


def _resolved(path):
    value = Path(path)
    return value if value.is_absolute() else SCRIPT_DIR / value


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return np.nan
    return number if np.isfinite(number) else np.nan


def _number(value, decimals=2, suffix="%"):
    number = _finite(value)
    return "n/a" if not np.isfinite(number) else f"{number:+.{decimals}f}{suffix}"


def _endpoint(item, date):
    values = item.get("values")
    if values is None or values.empty:
        raise ValueError(f"{item.get('ticker', 'Unknown')} has no usable price history")
    available = values[values["Date"] <= pd.Timestamp(date)]
    if available.empty:
        raise ValueError(
            f"{item.get('ticker', 'Unknown')} has no price on or before {pd.Timestamp(date):%Y-%m-%d}"
        )
    row = available.iloc[-1]
    return float(row["Price"]), row["Date"].strftime("%Y-%m-%d")


def holding_returns(tickers, prices, start_date, end_date):
    """Compatibility helper reproducing the original zero-cost endpoint returns."""
    rows = []
    for ticker in tickers:
        start_price, actual_start = _endpoint(prices[ticker], start_date)
        end_price, actual_end = _endpoint(prices[ticker], end_date)
        rows.append(
            {
                "ticker": ticker,
                "start_date": actual_start,
                "end_date": actual_end,
                "start_price": start_price,
                "end_price": end_price,
                "holding_return_pct": (end_price / start_price - 1.0) * 100.0,
            }
        )
    return pd.DataFrame(rows)


def load_universe_history(path):
    """Load optional point-in-time membership without inferring missing dates."""
    path = _resolved(path)
    columns = [
        "ticker",
        "role",
        "industry_group",
        "valid_from",
        "valid_to",
        "membership_source",
        "membership_quality",
    ]
    if not path.is_file():
        return pd.DataFrame(columns=columns), path
    frame = pd.read_csv(path, dtype=str).fillna("")
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"Universe history missing columns: {missing}")
    frame = frame[columns].copy()
    frame["ticker"] = frame["ticker"].str.strip().str.upper()
    frame["role"] = frame["role"].str.strip().str.lower()
    frame["industry_group"] = frame["industry_group"].str.strip()
    frame["membership_quality"] = frame["membership_quality"].str.strip().str.lower()
    if (frame["ticker"] == "").any() or (frame["industry_group"] == "").any():
        raise ValueError("Universe history contains blank ticker or industry group")
    invalid_roles = sorted(set(frame["role"]) - {"candidate", "benchmark"})
    if invalid_roles:
        raise ValueError(f"Invalid universe-history roles: {invalid_roles}")
    invalid_quality = sorted(
        set(frame["membership_quality"]) - {"verified", "partial", "unknown"}
    )
    if invalid_quality:
        raise ValueError(f"Invalid universe-history quality: {invalid_quality}")
    for column in ("valid_from", "valid_to"):
        parsed = pd.to_datetime(frame[column], errors="coerce")
        invalid = frame[column].ne("") & parsed.isna()
        if invalid.any():
            raise ValueError(f"Universe history has invalid {column} date(s)")
        frame[f"_{column}"] = parsed
    reversed_intervals = (
        frame["_valid_from"].notna()
        & frame["_valid_to"].notna()
        & (frame["_valid_from"] > frame["_valid_to"])
    )
    if reversed_intervals.any():
        raise ValueError("Universe history contains valid_from after valid_to")
    return frame, path


def _combined_metadata(base_metadata, universe_history):
    records = base_metadata[["ticker", "role", "industry_group"]].copy()
    if not universe_history.empty:
        additions = universe_history[["ticker", "role", "industry_group"]].drop_duplicates(
            "ticker", keep="last"
        )
        records = pd.concat([records.reset_index(drop=True), additions], ignore_index=True)
        records = records.drop_duplicates("ticker", keep="last")
    return records.set_index("ticker", drop=False)


def _universe_at_anchor(
    anchor,
    base_tickers,
    metadata,
    universe_history,
    primary_benchmark,
    secondary_benchmark,
):
    """Use verified membership only when a verified candidate roster exists."""
    anchor = pd.Timestamp(anchor)
    if not universe_history.empty:
        active = universe_history[
            (universe_history["membership_quality"] == "verified")
            & (
                universe_history["_valid_from"].isna()
                | (universe_history["_valid_from"] <= anchor)
            )
            & (
                universe_history["_valid_to"].isna()
                | (universe_history["_valid_to"] >= anchor)
            )
        ]
        candidates = active.loc[active["role"] == "candidate", "ticker"].tolist()
        if candidates:
            tickers = list(dict.fromkeys(candidates + [primary_benchmark, secondary_benchmark]))
            return tickers, "validated", "verified point-in-time universe"
    return list(base_tickers), "exploratory", "static current universe"


def _anchor_for_age(benchmark_values, latest_date, years_ago):
    target = pd.Timestamp(latest_date) - pd.DateOffset(years=int(years_ago))
    candidates = benchmark_values[benchmark_values["Date"] <= target]
    if candidates.empty:
        raise ValueError(f"No benchmark date on or before {target:%Y-%m-%d}")
    return pd.Timestamp(candidates["Date"].iloc[-1])


def _build_snapshots(
    ages,
    base_tickers,
    metadata,
    prices,
    universe_history,
    primary_benchmark,
    secondary_benchmark,
    shortlist_size,
    group_cap,
):
    benchmark_values = prices[primary_benchmark]["values"]
    latest_date = pd.Timestamp(benchmark_values["Date"].iloc[-1])
    snapshots = {}
    for age in sorted(set(int(value) for value in ages)):
        anchor = _anchor_for_age(benchmark_values, latest_date, age)
        tickers, validity, universe_label = _universe_at_anchor(
            anchor,
            base_tickers,
            metadata,
            universe_history,
            primary_benchmark,
            secondary_benchmark,
        )
        missing_meta = sorted(set(tickers) - set(metadata.index))
        if missing_meta:
            raise ValueError(f"Universe membership missing metadata for: {missing_meta}")
        snapshot_prices = {
            ticker: selection.price_item_as_of(prices[ticker], anchor) for ticker in tickers
        }
        rows, _ = selection.compute_selection_scores(
            tickers,
            metadata,
            snapshot_prices,
            primary_benchmark=primary_benchmark,
            secondary_benchmark=secondary_benchmark,
            shortlist_size=shortlist_size,
            group_cap=group_cap,
            timing_overlay=selection.historical_timing_overlay(tickers),
            as_of_date=anchor,
        )
        rows["years_ago"] = age
        rows["as_of_date"] = anchor.strftime("%Y-%m-%d")
        snapshots[age] = {
            "years_ago": age,
            "as_of_date": anchor,
            "rows": rows,
            "tickers": tickers,
            "validity_status": validity,
            "universe_label": universe_label,
        }
    return snapshots, latest_date


def _shortlist(snapshot):
    return (
        snapshot["rows"][snapshot["rows"]["shortlisted"].fillna(False)]
        .sort_values("shortlist_rank")
        .reset_index(drop=True)
    )


def _eligible(snapshot):
    return snapshot["rows"][snapshot["rows"]["eligibility"] == "eligible"].copy()


def _benchmark_calendar(prices, benchmark):
    return pd.DatetimeIndex(prices[benchmark]["values"]["Date"]).drop_duplicates().sort_values()


def _entry_date(calendar, anchor, lag_sessions):
    anchor = pd.Timestamp(anchor)
    if lag_sessions < 0:
        raise ValueError("execution_lag_sessions cannot be negative")
    if lag_sessions == 0:
        candidates = calendar[calendar <= anchor]
        if candidates.empty:
            raise ValueError(f"No trading session on or before {anchor:%Y-%m-%d}")
        return pd.Timestamp(candidates[-1])
    candidates = calendar[calendar > anchor]
    if len(candidates) < lag_sessions:
        raise ValueError(f"No execution session {lag_sessions} day(s) after {anchor:%Y-%m-%d}")
    return pd.Timestamp(candidates[lag_sessions - 1])


def _exit_date(calendar, anchor):
    candidates = calendar[calendar <= pd.Timestamp(anchor)]
    if candidates.empty:
        raise ValueError(f"No review session on or before {pd.Timestamp(anchor):%Y-%m-%d}")
    return pd.Timestamp(candidates[-1])


def _aligned_series(item, calendar):
    raw = item["values"][["Date", "Price"]].dropna().drop_duplicates("Date", keep="last")
    raw = raw.sort_values("Date").set_index("Date")["Price"]
    union = raw.index.union(calendar).sort_values()
    aligned = raw.reindex(union).ffill().reindex(calendar)
    source_dates = pd.Series(raw.index, index=raw.index).reindex(union).ffill().reindex(calendar)
    age_days = pd.Series(calendar, index=calendar).sub(source_dates).dt.days
    if aligned.isna().any() or age_days.gt(STALE_SESSION_DAYS).any():
        raise ValueError(f"{item.get('ticker', 'Unknown')} has a stale/missing portfolio price")
    return aligned.astype(float)


def _portfolio_metrics(nav):
    nav = nav.dropna().astype(float)
    if len(nav) < 2:
        return {key: np.nan for key in (
            "total_return_pct", "cagr_pct", "annualized_volatility_pct",
            "max_drawdown_pct", "sortino", "calmar"
        )}
    elapsed_years = (nav.index[-1] - nav.index[0]).days / 365.25
    total_return = nav.iloc[-1] - 1.0
    cagr = nav.iloc[-1] ** (1.0 / elapsed_years) - 1.0 if elapsed_years > 0 else np.nan
    daily = nav.pct_change().dropna()
    volatility = daily.std(ddof=0) * np.sqrt(TRADING_DAYS)
    running_peak = pd.Series(
        np.maximum.accumulate(np.maximum(nav.to_numpy(dtype=float), 1.0)),
        index=nav.index,
    )
    drawdown = nav / running_peak - 1.0
    max_drawdown = float(drawdown.min())
    downside = daily[daily < 0]
    downside_deviation = np.sqrt(np.mean(np.square(downside))) * np.sqrt(TRADING_DAYS) if len(downside) else np.nan
    annualized_mean = daily.mean() * TRADING_DAYS
    sortino = annualized_mean / downside_deviation if np.isfinite(downside_deviation) and downside_deviation > 0 else np.nan
    calmar = cagr / abs(max_drawdown) if max_drawdown < 0 else np.nan
    return {
        "total_return_pct": total_return * 100.0,
        "cagr_pct": cagr * 100.0,
        "annualized_volatility_pct": volatility * 100.0,
        "max_drawdown_pct": max_drawdown * 100.0,
        "sortino": sortino,
        "calmar": calmar,
    }


def build_portfolio(
    portfolio_id,
    portfolio_type,
    tickers,
    prices,
    calendar,
    selection_date,
    review_date,
    execution_lag_sessions,
    one_way_cost_bps,
    model="baseline",
):
    """Build equal-initial-weight adjusted-price NAV with explicit costs."""
    entry = _entry_date(calendar, selection_date, execution_lag_sessions)
    exit_date = _exit_date(calendar, review_date)
    if entry >= exit_date:
        raise ValueError(f"Portfolio {portfolio_id} has entry date on/after review date")
    sessions = calendar[(calendar >= entry) & (calendar <= exit_date)]
    normalized = []
    for ticker in tickers:
        series = _aligned_series(prices[ticker], sessions)
        normalized.append((series / series.iloc[0]).rename(ticker))
    matrix = pd.concat(normalized, axis=1)
    gross_nav = matrix.mean(axis=1)
    cost_rate = max(float(one_way_cost_bps), 0.0) / 10000.0
    net_nav = gross_nav * (1.0 - cost_rate)
    net_nav.iloc[-1] *= 1.0 - cost_rate
    metrics = _portfolio_metrics(net_nav)
    ending_values = matrix.iloc[-1]
    ending_weights = ending_values / ending_values.sum()
    holdings = []
    for ticker in tickers:
        gross_return = (matrix[ticker].iloc[-1] - 1.0) * 100.0
        net_return = (matrix[ticker].iloc[-1] * (1.0 - cost_rate) ** 2 - 1.0) * 100.0
        holdings.append(
            {
                "portfolio_id": portfolio_id,
                "portfolio_type": portfolio_type,
                "model": model,
                "ticker": ticker,
                "selection_date": pd.Timestamp(selection_date).strftime("%Y-%m-%d"),
                "entry_date": entry.strftime("%Y-%m-%d"),
                "review_date": pd.Timestamp(review_date).strftime("%Y-%m-%d"),
                "exit_date": exit_date.strftime("%Y-%m-%d"),
                "start_price": float(matrix[ticker].iloc[0] * prices[ticker]["values"].loc[
                    prices[ticker]["values"]["Date"] <= entry, "Price"
                ].iloc[-1]),
                "end_price": float(prices[ticker]["values"].loc[
                    prices[ticker]["values"]["Date"] <= exit_date, "Price"
                ].iloc[-1]),
                "gross_return_pct": gross_return,
                "net_return_pct": net_return,
                "contribution_pct": net_return / len(tickers),
                "ending_weight_pct": float(ending_weights[ticker]) * 100.0,
            }
        )
    nav_rows = pd.DataFrame(
        {
            "portfolio_id": portfolio_id,
            "portfolio_type": portfolio_type,
            "model": model,
            "date": net_nav.index.strftime("%Y-%m-%d"),
            "nav": net_nav.values,
            "drawdown_pct": (
                net_nav
                / pd.Series(
                    np.maximum.accumulate(np.maximum(net_nav.to_numpy(dtype=float), 1.0)),
                    index=net_nav.index,
                )
                - 1.0
            ).values
            * 100.0,
        }
    )
    return {
        "portfolio_id": portfolio_id,
        "portfolio_type": portfolio_type,
        "model": model,
        "tickers": list(tickers),
        "entry_date": entry,
        "exit_date": exit_date,
        "metrics": metrics,
        "holdings": pd.DataFrame(holdings),
        "nav": nav_rows,
    }


def _return_12_1(item, anchor):
    values = item["values"]
    end = values[values["Date"] <= pd.Timestamp(anchor) - pd.DateOffset(months=1)]
    start = values[values["Date"] <= pd.Timestamp(anchor) - pd.DateOffset(months=12)]
    if end.empty or start.empty:
        return np.nan
    return (float(end["Price"].iloc[-1]) / float(start["Price"].iloc[-1]) - 1.0) * 100.0


def _excess_sortino(item, benchmark_item, anchor):
    start = pd.Timestamp(anchor) - pd.DateOffset(years=5)
    left = item["values"]
    right = benchmark_item["values"]
    left = left[(left["Date"] >= start) & (left["Date"] <= anchor)].set_index("Date")["Price"]
    right = right[(right["Date"] >= start) & (right["Date"] <= anchor)].set_index("Date")["Price"]
    frame = pd.concat([left.rename("asset"), right.rename("benchmark")], axis=1).dropna()
    if len(frame) < 252:
        return np.nan
    excess = frame.pct_change().dropna().eval("asset - benchmark")
    downside = excess[excess < 0]
    deviation = np.sqrt(np.mean(np.square(downside))) if len(downside) else np.nan
    return float(excess.mean() / deviation * np.sqrt(TRADING_DAYS)) if deviation > 0 else np.nan


def _rerank_variant(rows, shortlist_size, group_cap):
    rows = rows.copy()
    rows["shortlisted"] = False
    rows["shortlist_rank"] = np.nan
    rows["raw_rank"] = np.nan
    eligible = rows[np.isfinite(pd.to_numeric(rows["score"], errors="coerce"))].copy()
    eligible = eligible.sort_values(["score", "ticker"], ascending=[False, True])
    counts = Counter()
    selected = 0
    for raw_rank, index in enumerate(eligible.index, 1):
        rows.loc[index, "raw_rank"] = raw_rank
        group = rows.loc[index, "industry_group"]
        if selected >= shortlist_size:
            reason = f"Outside diversified top {shortlist_size}"
        elif counts[group] >= group_cap:
            reason = f"Industry cap reached ({group_cap})"
        else:
            selected += 1
            counts[group] += 1
            rows.loc[index, "shortlisted"] = True
            rows.loc[index, "shortlist_rank"] = selected
            reason = "Selected"
        rows.loc[index, "shortlist_reason"] = reason
    return rows.sort_values(["score", "ticker"], ascending=[False, True], na_position="last")


def score_variant(snapshot, prices, primary_benchmark, secondary_benchmark, model, shortlist_size, group_cap):
    """Apply predeclared score ablations using only snapshot-date information."""
    if model == "baseline":
        return snapshot["rows"].copy()
    rows = snapshot["rows"].copy()
    eligible = rows[
        (rows["eligibility"] == "eligible")
        & np.isfinite(pd.to_numeric(rows["score"], errors="coerce"))
    ].copy()
    tickers = eligible["ticker"].tolist()
    anchor = snapshot["as_of_date"]
    if model in {"recency", "combined"}:
        recency = pd.Series({ticker: _return_12_1(prices[ticker], anchor) for ticker in tickers})
        recency_pct = selection._percentile(recency)
        p3 = selection._percentile(eligible.set_index("ticker")["cagr_3y_pct"])
        p5 = selection._percentile(eligible.set_index("ticker")["cagr_5y_pct"])
        p10 = selection._percentile(eligible.set_index("ticker")["cagr_10y_pct"])
        for ticker in tickers:
            ten = p10.get(ticker, np.nan)
            ten = 0.5 if not np.isfinite(ten) else ten
            value = 5 * recency_pct.get(ticker, np.nan) + 5 * p3.get(ticker, np.nan) + 10 * p5.get(ticker, np.nan) + 5 * ten
            index = rows.index[rows["ticker"] == ticker][0]
            rows.loc[index, "return_score"] = value
    if model in {"risk_adjusted", "combined"}:
        spy = pd.Series({ticker: _excess_sortino(prices[ticker], prices[primary_benchmark], anchor) for ticker in tickers})
        qqq = pd.Series({ticker: _excess_sortino(prices[ticker], prices[secondary_benchmark], anchor) for ticker in tickers})
        spy_pct = selection._percentile(spy)
        qqq_pct = selection._percentile(qqq)
        for ticker in tickers:
            index = rows.index[rows["ticker"] == ticker][0]
            spy_value = spy_pct.get(ticker, np.nan)
            qqq_value = qqq_pct.get(ticker, np.nan)
            spy_value = 0.5 if not np.isfinite(spy_value) else spy_value
            qqq_value = 0.5 if not np.isfinite(qqq_value) else qqq_value
            rows.loc[index, "benchmark_score"] = 10 * spy_value + 5 * qqq_value
    for ticker in tickers:
        index = rows.index[rows["ticker"] == ticker][0]
        rows.loc[index, "score"] = sum(
            float(rows.loc[index, column])
            for column in ("return_score", "persistence_score", "risk_score", "benchmark_score", "confidence_score")
        )
    return _rerank_variant(rows, shortlist_size, group_cap)


def _rank_correlation(rows, returns):
    frame = rows[["ticker", "score"]].merge(returns[["ticker", "gross_return_pct"]], on="ticker")
    if len(frame) < 3:
        return np.nan
    return float(frame["score"].rank().corr(frame["gross_return_pct"].rank()))


def _random_percentile(eligible_rows, returns, selected_return, group_cap, shortlist_size, simulations, seed):
    if simulations <= 0:
        return np.nan
    frame = eligible_rows[["ticker", "industry_group"]].merge(
        returns[["ticker", "net_return_pct"]], on="ticker"
    )
    if len(frame) < shortlist_size:
        return np.nan
    rng = np.random.default_rng(int(seed))
    values = []
    records = frame.to_dict("records")
    for _ in range(int(simulations)):
        order = rng.permutation(len(records))
        counts = Counter()
        selected = []
        for position in order:
            record = records[int(position)]
            group = record["industry_group"]
            if counts[group] < group_cap:
                counts[group] += 1
                selected.append(record["net_return_pct"])
            if len(selected) == shortlist_size:
                break
        if len(selected) == shortlist_size:
            values.append(float(np.mean(selected)))
    return float(np.mean(np.asarray(values) <= selected_return) * 100.0) if values else np.nan


def _summary_row(cohort_id, cohort_kind, horizon, snapshot, portfolio, non_independent=False):
    row = {
        "cohort_id": cohort_id,
        "cohort_kind": cohort_kind,
        "holding_years": horizon,
        "selection_years_ago": snapshot["years_ago"],
        "selection_as_of_date": pd.Timestamp(snapshot["as_of_date"]).strftime("%Y-%m-%d"),
        "portfolio_type": portfolio["portfolio_type"],
        "model": portfolio["model"],
        "entry_date": portfolio["entry_date"].strftime("%Y-%m-%d"),
        "exit_date": portfolio["exit_date"].strftime("%Y-%m-%d"),
        "constituent_count": len(portfolio["tickers"]),
        "validity_status": snapshot["validity_status"],
        "universe_label": snapshot["universe_label"],
        "non_independent": bool(non_independent),
    }
    row.update(portfolio["metrics"])
    return row


def _bootstrap_ci(values, block_size, seed, iterations=2000):
    clean = np.asarray([value for value in values if np.isfinite(value)], dtype=float)
    if len(clean) < 2:
        return np.nan, np.nan
    rng = np.random.default_rng(int(seed))
    block_size = max(1, min(int(block_size), len(clean)))
    means = []
    for _ in range(iterations):
        sampled = []
        while len(sampled) < len(clean):
            start = int(rng.integers(0, len(clean)))
            sampled.extend(clean[(np.arange(block_size) + start) % len(clean)])
        means.append(float(np.mean(sampled[: len(clean)])))
    return tuple(np.percentile(means, [2.5, 97.5]))


def build_annual_refreshed_portfolio(
    portfolio_id,
    snapshots,
    oldest_age,
    prices,
    calendar,
    execution_lag_sessions,
    one_way_cost_bps,
    shortlist_size,
):
    """Chain annual top-10 cohorts and charge costs only on actual turnover."""
    available = []
    for age in range(oldest_age, -1, -1):
        tickers = _shortlist(snapshots[age])["ticker"].tolist()
        if len(tickers) != shortlist_size:
            if not available:
                continue
            break
        available.append(age)
    if len(available) < 2 or available[-1] != 0:
        return None
    cost_rate = max(float(one_way_cost_bps), 0.0) / 10000.0
    scale = 1.0
    nav_parts = []
    turnovers = []
    segment_rows = []
    for position, age in enumerate(available[:-1]):
        review_age = available[position + 1]
        snapshot = snapshots[age]
        next_snapshot = snapshots[review_age]
        tickers = _shortlist(snapshot)["ticker"].tolist()
        next_tickers = _shortlist(next_snapshot)["ticker"].tolist()
        if review_age == 0:
            segment_review = next_snapshot["as_of_date"]
        else:
            segment_review = _entry_date(
                calendar, next_snapshot["as_of_date"], execution_lag_sessions
            )
        segment = build_portfolio(
            f"{portfolio_id}-segment-{age}y",
            "annual_refreshed_segment",
            tickers,
            prices,
            calendar,
            snapshot["as_of_date"],
            segment_review,
            execution_lag_sessions,
            0.0,
        )
        raw = segment["nav"].copy()
        raw["date"] = pd.to_datetime(raw["date"])
        raw = raw.set_index("date")["nav"]
        if position == 0:
            scale *= 1.0 - cost_rate
        scaled = raw * scale
        if review_age == 0:
            turnover = 1.0
            scaled.iloc[-1] *= 1.0 - cost_rate
        else:
            turnover = 1.0 - len(set(tickers) & set(next_tickers)) / float(shortlist_size)
            scaled.iloc[-1] *= 1.0 - 2.0 * cost_rate * turnover
            turnovers.append(turnover)
        scale = float(scaled.iloc[-1])
        nav_parts.append(scaled)
        holdings = segment["holdings"].copy()
        holdings["rebalance_from_years_ago"] = age
        holdings["rebalance_to_years_ago"] = review_age
        holdings["rebalance_turnover_pct"] = turnover * 100.0
        segment_rows.append(holdings)
    nav = pd.concat(nav_parts).sort_index()
    nav = nav[~nav.index.duplicated(keep="last")]
    metrics = _portfolio_metrics(nav)
    nav_rows = pd.DataFrame(
        {
            "portfolio_id": portfolio_id,
            "portfolio_type": "annual_refreshed",
            "model": "baseline",
            "date": nav.index.strftime("%Y-%m-%d"),
            "nav": nav.values,
            "drawdown_pct": (
                nav
                / pd.Series(
                    np.maximum.accumulate(np.maximum(nav.to_numpy(dtype=float), 1.0)),
                    index=nav.index,
                )
                - 1.0
            ).values
            * 100.0,
        }
    )
    return {
        "portfolio_id": portfolio_id,
        "portfolio_type": "annual_refreshed",
        "model": "baseline",
        "tickers": _shortlist(snapshots[0])["ticker"].tolist(),
        "entry_date": pd.Timestamp(nav.index[0]),
        "exit_date": pd.Timestamp(nav.index[-1]),
        "metrics": metrics,
        "holdings": pd.concat(segment_rows, ignore_index=True),
        "nav": nav_rows,
        "average_turnover_pct": float(np.mean(turnovers) * 100.0) if turnovers else 0.0,
        "rebalance_count": len(turnovers),
        "oldest_age": available[0],
    }


def build_selection_backtest(
    tickers_file=selection.DEFAULT_TICKERS_FILE,
    metadata_file=selection.DEFAULT_METADATA_FILE,
    data_dir=selection.DATA_DIR,
    universe_history_file=DEFAULT_UNIVERSE_HISTORY,
    years_ago=DEFAULT_YEARS_AGO,
    holding_years=DEFAULT_HOLDING_YEARS,
    walk_forward_years=10,
    execution_lag_sessions=1,
    one_way_cost_bps=10.0,
    random_portfolios=5000,
    random_seed=20260814,
    primary_benchmark="SPY",
    secondary_benchmark="QQQ",
    shortlist_size=10,
    group_cap=3,
):
    """Build legacy cohorts, annual walk-forward cohorts, controls, and model diagnostics."""
    holding_years = tuple(dict.fromkeys(int(value) for value in holding_years))
    if holding_years != (1,):
        raise ValueError("Stock-selection portfolios must use exactly a one-year holding horizon")
    tickers_file = _resolved(tickers_file)
    metadata_file = _resolved(metadata_file)
    data_dir = _resolved(data_dir)
    universe_history_file = _resolved(universe_history_file)
    if (
        universe_history_file == DEFAULT_UNIVERSE_HISTORY
        and tickers_file != selection.DEFAULT_TICKERS_FILE
    ):
        universe_history_file = tickers_file.parent / "selection_universe_history.csv"
    primary_benchmark = primary_benchmark.upper()
    secondary_benchmark = secondary_benchmark.upper()
    base_tickers = selection.load_ticker_universe(tickers_file)
    base_metadata = selection.load_selection_metadata(metadata_file, base_tickers)
    universe_history, history_path = load_universe_history(universe_history_file)
    metadata = _combined_metadata(base_metadata, universe_history)
    all_tickers = list(dict.fromkeys(base_tickers + universe_history["ticker"].tolist()))
    prices = selection.load_price_universe(all_tickers, data_dir)
    max_age = max(max(int(value) for value in years_ago), int(walk_forward_years))
    snapshots, latest_date = _build_snapshots(
        range(max_age + 1),
        base_tickers,
        metadata,
        prices,
        universe_history,
        primary_benchmark,
        secondary_benchmark,
        shortlist_size,
        group_cap,
    )
    calendar = _benchmark_calendar(prices, primary_benchmark)
    reports = []
    holdings_exports = []
    nav_exports = []
    summary_rows = []

    def build_comparison(cohort_id, cohort_kind, start_age, review_age, model="baseline", include_report=False):
        start_snapshot = snapshots[start_age]
        review_snapshot = snapshots[review_age]
        model_rows = score_variant(
            start_snapshot, prices, primary_benchmark, secondary_benchmark,
            model, shortlist_size, group_cap
        )
        selected_rows = model_rows[model_rows["shortlisted"].fillna(False)].sort_values("shortlist_rank")
        if len(selected_rows) < shortlist_size:
            return None
        selected_tickers = selected_rows["ticker"].tolist()
        eligible_rows = model_rows[model_rows["eligibility"] == "eligible"].copy()
        review_rows = review_snapshot["rows"]
        review_tickers = review_rows[review_rows["shortlisted"].fillna(False)].sort_values("shortlist_rank")["ticker"].tolist()
        portfolio_specs = [
            ("selected", selected_tickers),
            ("eligible_universe", eligible_rows["ticker"].tolist()),
            (primary_benchmark, [primary_benchmark]),
            (secondary_benchmark, [secondary_benchmark]),
        ]
        if include_report and len(review_tickers) == shortlist_size:
            portfolio_specs.append(("review_hindsight", review_tickers))
        portfolios = {}
        for offset, (portfolio_type, portfolio_tickers) in enumerate(portfolio_specs):
            portfolio = build_portfolio(
                cohort_id,
                portfolio_type,
                portfolio_tickers,
                prices,
                calendar,
                start_snapshot["as_of_date"],
                review_snapshot["as_of_date"],
                execution_lag_sessions,
                one_way_cost_bps,
                model=model,
            )
            portfolios[portfolio_type] = portfolio
            summary_rows.append(
                _summary_row(
                    cohort_id,
                    cohort_kind,
                    start_age - review_age,
                    start_snapshot,
                    portfolio,
                    non_independent=(start_age - review_age) > 1,
                )
            )
            if cohort_kind != "model_evaluation":
                nav_exports.append(portfolio["nav"])
        selected_portfolio = portfolios["selected"]
        selected_holdings = selected_portfolio["holdings"].copy()
        rank_map = selected_rows.set_index("ticker")["shortlist_rank"].to_dict()
        score_map = selected_rows.set_index("ticker")["score"].to_dict()
        review_rank = review_rows[review_rows["shortlisted"].fillna(False)].set_index("ticker")["shortlist_rank"].to_dict()
        review_set = set(review_tickers)
        selected_holdings["historical_rank"] = selected_holdings["ticker"].map(rank_map)
        selected_holdings["historical_score"] = selected_holdings["ticker"].map(score_map)
        selected_holdings["still_review_top_10"] = selected_holdings["ticker"].isin(review_set)
        selected_holdings["review_rank"] = selected_holdings["ticker"].map(review_rank)
        selected_holdings["negative_return"] = selected_holdings["net_return_pct"] < 0
        selected_holdings["years_ago"] = start_age
        selected_holdings["review_years_ago"] = review_age
        selected_holdings["selection_as_of_date"] = start_snapshot["as_of_date"].strftime("%Y-%m-%d")
        selected_holdings["review_as_of_date"] = review_snapshot["as_of_date"].strftime("%Y-%m-%d")
        selected_holdings["validity_status"] = start_snapshot["validity_status"]
        selected_holdings["universe_label"] = start_snapshot["universe_label"]
        selected_holdings["holding_return_pct"] = selected_holdings["net_return_pct"]
        selected_holdings["start_date"] = selected_holdings["entry_date"]
        selected_holdings["end_date"] = selected_holdings["exit_date"]
        if cohort_kind != "model_evaluation":
            holdings_exports.append(selected_holdings)
        eligible_returns = portfolios["eligible_universe"]["holdings"]
        random_pct = (
            _random_percentile(
                eligible_rows,
                eligible_returns,
                selected_portfolio["metrics"]["total_return_pct"],
                group_cap,
                shortlist_size,
                random_portfolios,
                random_seed + start_age * 100 + review_age,
            )
            if cohort_kind != "model_evaluation"
            else np.nan
        )
        correlation = (
            _rank_correlation(eligible_rows, eligible_returns)
            if cohort_kind != "model_evaluation"
            else np.nan
        )
        top_two_gain = selected_holdings.nlargest(2, "contribution_pct")["contribution_pct"].sum()
        total_gain = selected_holdings["contribution_pct"].sum()
        concentration = top_two_gain / total_gain * 100.0 if total_gain > 0 else np.nan
        if include_report:
            reports.append(
                {
                    "cohort_id": cohort_id,
                    "years_ago": start_age,
                    "review_years_ago": review_age,
                    "start_date": start_snapshot["as_of_date"],
                    "end_date": review_snapshot["as_of_date"],
                    "historical_tickers": selected_tickers,
                    "review_tickers": review_tickers,
                    "overlap": sorted(set(selected_tickers) & review_set),
                    "outside_review_top_10": sorted(set(selected_tickers) - review_set),
                    "historical_portfolio_return_pct": selected_portfolio["metrics"]["total_return_pct"],
                    "review_portfolio_return_pct": portfolios.get("review_hindsight", selected_portfolio)["metrics"]["total_return_pct"],
                    "hindsight_gap_pct": portfolios.get("review_hindsight", selected_portfolio)["metrics"]["total_return_pct"] - selected_portfolio["metrics"]["total_return_pct"],
                    "negative_tickers": selected_holdings.loc[selected_holdings["negative_return"], "ticker"].tolist(),
                    "holdings": selected_holdings.sort_values("historical_rank"),
                    "portfolios": portfolios,
                    "random_percentile": random_pct,
                    "score_forward_spearman": correlation,
                    "top_two_gain_concentration_pct": concentration,
                    "validity_status": start_snapshot["validity_status"],
                    "universe_label": start_snapshot["universe_label"],
                }
            )
        return portfolios

    requested = tuple(dict.fromkeys(int(age) for age in years_ago))
    for age in requested:
        review_age = age - 1
        build_comparison(f"legacy-{age}y-to-{review_age}y", "legacy", age, review_age, include_report=True)

    walk_forward_cohorts = []
    for horizon in holding_years:
        for start_age in range(horizon, max_age + 1):
            review_age = start_age - horizon
            cohort_id = f"walk-{horizon}y-{start_age}y-to-{review_age}y"
            portfolios = build_comparison(cohort_id, "walk_forward", start_age, review_age)
            if portfolios:
                walk_forward_cohorts.append((horizon, start_age, review_age, cohort_id))

    annual_refreshed = build_annual_refreshed_portfolio(
        "annual-refreshed",
        snapshots,
        max_age,
        prices,
        calendar,
        execution_lag_sessions,
        one_way_cost_bps,
        shortlist_size,
    )
    annual_refreshed_rows = []
    if annual_refreshed:
        start_snapshot = snapshots[annual_refreshed["oldest_age"]]
        annual_row = _summary_row(
            "annual-refreshed",
            "annual_refreshed",
            annual_refreshed["oldest_age"],
            start_snapshot,
            annual_refreshed,
        )
        annual_row["average_turnover_pct"] = annual_refreshed["average_turnover_pct"]
        annual_row["rebalance_count"] = annual_refreshed["rebalance_count"]
        summary_rows.append(annual_row)
        annual_refreshed_rows.append(annual_row)
        nav_exports.append(annual_refreshed["nav"])
        annual_holdings = annual_refreshed["holdings"].copy()
        annual_holdings["cohort_id"] = "annual-refreshed"
        annual_holdings["cohort_kind"] = "annual_refreshed"
        annual_holdings["validity_status"] = start_snapshot["validity_status"]
        annual_holdings["universe_label"] = start_snapshot["universe_label"]
        holdings_exports.append(annual_holdings)
        oldest_selected_rows = _eligible(start_snapshot)
        comparator_specs = [
            (primary_benchmark, [primary_benchmark]),
            (secondary_benchmark, [secondary_benchmark]),
            ("eligible_universe", oldest_selected_rows["ticker"].tolist()),
        ]
        for portfolio_type, comparator_tickers in comparator_specs:
            comparator = build_portfolio(
                "annual-refreshed",
                portfolio_type,
                comparator_tickers,
                prices,
                calendar,
                start_snapshot["as_of_date"],
                snapshots[0]["as_of_date"],
                execution_lag_sessions,
                one_way_cost_bps,
            )
            comparator_row = _summary_row(
                "annual-refreshed",
                "annual_refreshed",
                annual_refreshed["oldest_age"],
                start_snapshot,
                comparator,
            )
            summary_rows.append(comparator_row)
            annual_refreshed_rows.append(comparator_row)
            nav_exports.append(comparator["nav"])

    model_rows = []
    one_year_ages = range(1, max_age + 1)
    for model in MODEL_NAMES:
        for start_age in one_year_ages:
            cohort_id = f"model-{model}-{start_age}y"
            before = len(summary_rows)
            portfolios = build_comparison(cohort_id, "model_evaluation", start_age, start_age - 1, model=model)
            if not portfolios:
                continue
            selected_summary = next(
                row for row in summary_rows[before:] if row["portfolio_type"] == "selected"
            )
            spy_summary = next(row for row in summary_rows[before:] if row["portfolio_type"] == primary_benchmark)
            qqq_summary = next(row for row in summary_rows[before:] if row["portfolio_type"] == secondary_benchmark)
            model_rows.append(
                {
                    "model": model,
                    "start_age": start_age,
                    "validity_status": snapshots[start_age]["validity_status"],
                    "cagr_pct": selected_summary["cagr_pct"],
                    "sortino": selected_summary["sortino"],
                    "max_drawdown_pct": selected_summary["max_drawdown_pct"],
                    "excess_spy_pct": selected_summary["total_return_pct"] - spy_summary["total_return_pct"],
                    "excess_qqq_pct": selected_summary["total_return_pct"] - qqq_summary["total_return_pct"],
                }
            )
    model_frame = pd.DataFrame(model_rows)
    model_evaluation = []
    if not model_frame.empty:
        baseline = model_frame[model_frame["model"] == "baseline"]
        baseline_validated = baseline[baseline["validity_status"] == "validated"]
        baseline_sortino = (
            float(baseline_validated["sortino"].median())
            if not baseline_validated.empty
            else np.nan
        )
        baseline_worst_dd = (
            abs(float(baseline_validated["max_drawdown_pct"].min()))
            if not baseline_validated.empty
            else np.nan
        )
        for model, group in model_frame.groupby("model", sort=False):
            independent = len(group)
            validated = group[group["validity_status"] == "validated"]
            promoted = (
                model != "baseline"
                and len(validated) >= 10
                and np.isfinite(baseline_sortino)
                and float(validated["excess_spy_pct"].median()) > 0
                and float(validated["excess_qqq_pct"].median()) > 0
                and float(validated["sortino"].median()) > baseline_sortino
                and abs(float(validated["max_drawdown_pct"].min())) <= baseline_worst_dd + 2.0
            )
            model_evaluation.append(
                {
                    "model": model,
                    "independent_1y_cohorts": independent,
                    "validated_1y_cohorts": len(validated),
                    "median_cagr_pct": float(group["cagr_pct"].median()),
                    "median_sortino": float(group["sortino"].median()),
                    "worst_max_drawdown_pct": float(group["max_drawdown_pct"].min()),
                    "median_excess_spy_pct": float(group["excess_spy_pct"].median()),
                    "median_excess_qqq_pct": float(group["excess_qqq_pct"].median()),
                    "promotion_passed": bool(promoted),
                }
            )
    model_evaluation = pd.DataFrame(model_evaluation)
    promoted_models = (
        model_evaluation.loc[model_evaluation["promotion_passed"], "model"].tolist()
        if not model_evaluation.empty else []
    )
    promotion_decision = promoted_models[0] if promoted_models else "baseline retained; no alternative proved"

    summary = pd.DataFrame(summary_rows)
    aggregates = []
    selected_walk = summary[
        (summary["cohort_kind"] == "walk_forward")
        & (summary["portfolio_type"] == "selected")
        & (summary["model"] == "baseline")
    ]
    for horizon, group in selected_walk.groupby("holding_years"):
        low, high = _bootstrap_ci(group["cagr_pct"], int(horizon), random_seed + int(horizon))
        aggregates.append(
            {
                "holding_years": int(horizon),
                "cohort_count": len(group),
                "mean_cagr_pct": float(group["cagr_pct"].mean()),
                "cagr_ci_low_pct": low,
                "cagr_ci_high_pct": high,
                "median_sortino": float(group["sortino"].median()),
                "worst_max_drawdown_pct": float(group["max_drawdown_pct"].min()),
                "non_independent": int(horizon) > 1,
            }
        )

    aggregate_frame = pd.DataFrame(aggregates)
    summary_additions = []
    if not aggregate_frame.empty:
        walk_export = aggregate_frame.copy()
        walk_export["cohort_id"] = walk_export["holding_years"].map(
            lambda value: f"walk-forward-{int(value)}y-aggregate"
        )
        walk_export["cohort_kind"] = "walk_forward_aggregate"
        walk_export["portfolio_type"] = "selected"
        walk_export["model"] = "baseline"
        summary_additions.append(walk_export)
    if not model_evaluation.empty:
        model_export = model_evaluation.copy()
        model_export["cohort_id"] = model_export["model"].map(
            lambda value: f"model-{value}-aggregate"
        )
        model_export["cohort_kind"] = "model_evaluation_aggregate"
        model_export["portfolio_type"] = "selected"
        summary_additions.append(model_export)
    summary_output = (
        pd.concat([summary, *summary_additions], ignore_index=True, sort=False)
        if summary_additions
        else summary
    )

    return {
        "reports": reports,
        "snapshots": snapshots,
        "export": pd.concat(holdings_exports, ignore_index=True) if holdings_exports else pd.DataFrame(),
        "summary": summary_output,
        "nav": pd.concat(nav_exports, ignore_index=True) if nav_exports else pd.DataFrame(),
        "walk_forward_aggregates": aggregate_frame,
        "annual_refreshed_summary": pd.DataFrame(annual_refreshed_rows),
        "model_evaluation": model_evaluation,
        "promotion_decision": promotion_decision,
        "latest_date": latest_date,
        "tickers_file": tickers_file,
        "metadata_file": metadata_file,
        "universe_history_file": history_path,
        "data_dir": data_dir,
        "execution_lag_sessions": execution_lag_sessions,
        "one_way_cost_bps": one_way_cost_bps,
        "random_portfolios": random_portfolios,
        "random_seed": random_seed,
        "primary_benchmark": primary_benchmark,
        "secondary_benchmark": secondary_benchmark,
    }


def _as_of_label(years_ago):
    return "Current" if years_ago == 0 else f"{years_ago}Y ago"


def _outside_label(review_years_ago):
    return "Outside current top 10" if review_years_ago == 0 else f"Outside {review_years_ago}Y-ago top 10"


def _holding_rows(report):
    rows = []
    for _, row in report["holdings"].iterrows():
        still = bool(row["still_review_top_10"])
        status = (
            f"Still {_as_of_label(report['review_years_ago']).lower()} top 10 (#{int(row['review_rank'])})"
            if still else _outside_label(report["review_years_ago"])
        )
        tone = "negative" if bool(row["negative_return"]) else "positive"
        status_class = "" if still else "outside-status"
        rows.append(
            f"<tr><td>#{int(row['historical_rank'])}</td><td><b>{html.escape(str(row['ticker']))}</b></td>"
            f"<td>{float(row['historical_score']):.1f}</td><td>{html.escape(str(row['entry_date']))}</td>"
            f"<td>{html.escape(str(row['exit_date']))}</td><td class=\"{tone}\">{_number(row['net_return_pct'])}</td>"
            f"<td>{_number(row['contribution_pct'])}</td><td>{_number(row['ending_weight_pct'])}</td>"
            f"<td class=\"{status_class}\">{html.escape(status)}</td></tr>"
        )
    return "".join(rows)


def _metrics_table(report):
    labels = ["selected", "SPY", "QQQ", "eligible_universe", "review_hindsight"]
    rows = []
    for label in labels:
        portfolio = report["portfolios"].get(label)
        if not portfolio:
            continue
        display_label = (
            "Current top-10 hindsight"
            if label == "review_hindsight" and report["review_years_ago"] == 0
            else f"{report['review_years_ago']}Y-ago top-10 hindsight"
            if label == "review_hindsight"
            else label
            if label in {"SPY", "QQQ"}
            else label.replace("_", " ").title()
        )
        metrics = portfolio["metrics"]
        rows.append(
            f"<tr><td>{html.escape(display_label)}</td>"
            f"<td>{_number(metrics['total_return_pct'])}</td><td>{_number(metrics['cagr_pct'])}</td>"
            f"<td>{_number(metrics['annualized_volatility_pct'])}</td><td>{_number(metrics['max_drawdown_pct'])}</td>"
            f"<td>{_number(metrics['sortino'], 2, '')}</td><td>{_number(metrics['calmar'], 2, '')}</td></tr>"
        )
    return "".join(rows)


def _nav_svg(report):
    series = []
    colors = {"selected": "#0c6b58", "SPY": "#315c9b", "QQQ": "#7a4aa0"}
    all_values = []
    for label in ("selected", "SPY", "QQQ"):
        frame = report["portfolios"][label]["nav"]
        values = frame["nav"].to_numpy(dtype=float)
        all_values.extend(values)
        series.append((label, values))
    low, high = min(all_values), max(all_values)
    span = max(high - low, 1e-9)
    paths = []
    for label, values in series:
        points = " ".join(
            f"{20 + index * 560 / max(len(values)-1,1):.1f},{126 - (value-low)/span*100:.1f}"
            for index, value in enumerate(values)
        )
        paths.append(f'<polyline points="{points}" fill="none" stroke="{colors[label]}" stroke-width="2"/>')
    selected = report["portfolios"]["selected"]["nav"]
    dd = selected["drawdown_pct"].to_numpy(dtype=float)
    dd_span = max(abs(min(dd)), 1e-9)
    dd_points = " ".join(
        f"{20 + index * 560 / max(len(dd)-1,1):.1f},{166 + abs(value)/dd_span*52:.1f}"
        for index, value in enumerate(dd)
    )
    return (
        '<figure class="nav-chart"><figcaption><b>Cumulative NAV and selected-portfolio drawdown</b>'
        '<span><i class="sel"></i>Selected <i class="spy"></i>SPY <i class="qqq"></i>QQQ</span></figcaption>'
        '<svg viewBox="0 0 600 230" role="img" aria-label="Portfolio NAV and drawdown chart">'
        '<line x1="20" y1="126" x2="580" y2="126" class="axis"/>' + "".join(paths)
        + '<line x1="20" y1="166" x2="580" y2="166" class="axis"/>'
        + f'<polyline points="{dd_points}" fill="none" stroke="#b44444" stroke-width="1.7"/>'
        + '</svg></figure>'
    )


def _walk_forward_table(frame):
    if frame.empty:
        return '<p class="notice">No walk-forward cohorts had a complete diversified shortlist.</p>'
    rows = []
    for _, row in frame.iterrows():
        interval = f"{_number(row['cagr_ci_low_pct'])} to {_number(row['cagr_ci_high_pct'])}"
        rows.append(
            f"<tr><td>{int(row['holding_years'])}Y</td><td>{int(row['cohort_count'])}</td>"
            f"<td>{_number(row['mean_cagr_pct'])}</td><td>{interval}</td>"
            f"<td>{_number(row['median_sortino'],2,'')}</td><td>{_number(row['worst_max_drawdown_pct'])}</td>"
            f"<td>{'Yes — block bootstrap' if row['non_independent'] else 'No'}</td></tr>"
        )
    return '<div class="table-wrap"><table><thead><tr><th>Hold</th><th>Cohorts</th><th>Mean CAGR</th><th>95% block-bootstrap CI</th><th>Median Sortino</th><th>Worst drawdown</th><th>Overlapping</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>'


def _annual_refreshed_table(frame):
    if frame.empty:
        return '<p class="notice">Annual refreshed strategy unavailable because a continuous sequence of complete top-10 snapshots was not available.</p>'
    rows = []
    for _, row in frame.iterrows():
        turnover = _number(row.get("average_turnover_pct"), 1, "%") if row["portfolio_type"] == "annual_refreshed" else "n/a"
        display_label = (
            str(row["portfolio_type"])
            if str(row["portfolio_type"]) in {"SPY", "QQQ"}
            else str(row["portfolio_type"]).replace("_", " ").title()
        )
        rows.append(
            f"<tr><td><b>{html.escape(display_label)}</b></td>"
            f"<td>{_number(row['total_return_pct'])}</td><td>{_number(row['cagr_pct'])}</td>"
            f"<td>{_number(row['annualized_volatility_pct'])}</td><td>{_number(row['max_drawdown_pct'])}</td>"
            f"<td>{_number(row['sortino'],2,'')}</td><td>{turnover}</td></tr>"
        )
    return '<div class="table-wrap"><table><thead><tr><th>Portfolio</th><th>Total return</th><th>CAGR</th><th>Volatility</th><th>Max drawdown</th><th>Sortino</th><th>Average turnover</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>'


def _model_table(frame, decision):
    if frame.empty:
        return '<p class="notice">Model evaluation unavailable.</p>'
    rows = []
    for _, row in frame.iterrows():
        rows.append(
            f"<tr><td><b>{html.escape(str(row['model']))}</b></td><td>{int(row['independent_1y_cohorts'])}</td>"
            f"<td>{int(row['validated_1y_cohorts'])}</td>"
            f"<td>{_number(row['median_cagr_pct'])}</td><td>{_number(row['median_sortino'],2,'')}</td>"
            f"<td>{_number(row['worst_max_drawdown_pct'])}</td><td>{_number(row['median_excess_spy_pct'])}</td>"
            f"<td>{_number(row['median_excess_qqq_pct'])}</td><td>{'PASS' if row['promotion_passed'] else 'No'}</td></tr>"
        )
    return (
        f'<p class="decision"><b>Promotion decision:</b> {html.escape(decision)}. Fundamentals remain non-scoring.</p>'
        '<div class="table-wrap"><table><thead><tr><th>Model</th><th>1Y cohorts</th><th>Validated cohorts</th><th>Median CAGR</th><th>Median Sortino</th><th>Worst drawdown</th><th>Median excess SPY</th><th>Median excess QQQ</th><th>Promotion</th></tr></thead><tbody>'
        + "".join(rows) + '</tbody></table></div>'
    )


def render_selection_backtest(result, output_path):
    output_path = _resolved(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sections = []
    for report in result["reports"]:
        age = report["years_ago"]
        review_age = report["review_years_ago"]
        negatives = ", ".join(report["negative_tickers"]) or "None"
        outside = ", ".join(report["outside_review_top_10"]) or "None"
        overlap = ", ".join(report["overlap"]) or "None"
        review_label = _as_of_label(review_age)
        selected_return = report["portfolios"]["selected"]["metrics"]["total_return_pct"]
        spy_return = report["portfolios"]["SPY"]["metrics"]["total_return_pct"]
        qqq_return = report["portfolios"]["QQQ"]["metrics"]["total_return_pct"]
        sections.append(
            f'''<section class="report-section" id="{age}y-to-{review_age}y">
              <div class="section-head"><div><h2>{age}Y-ago selection held to {review_label}</h2><p>Selection {report["start_date"]:%Y-%m-%d} · reviewed {report["end_date"]:%Y-%m-%d} · {html.escape(report["universe_label"])}</p></div><span class="validity {report["validity_status"]}">{report["validity_status"].title()}</span></div>
              <div class="summary-grid"><div><span>Still in {review_label.lower()} top 10</span><strong>{len(report["overlap"])} / 10</strong></div><div><span>Benchmark excess vs SPY</span><strong>{_number(selected_return - spy_return)}</strong></div><div><span>Benchmark excess vs QQQ</span><strong>{_number(selected_return - qqq_return)}</strong></div><div><span>Random-portfolio percentile</span><strong>{_number(report["random_percentile"],1,"")}</strong></div><div><span>Score predictive correlation</span><strong>{_number(report["score_forward_spearman"],2,"")}</strong></div><div><span>Contribution concentration · top two</span><strong>{_number(report["top_two_gain_concentration_pct"])}</strong></div></div>
              {_nav_svg(report)}
              <div class="table-wrap metrics-table"><table><thead><tr><th>Portfolio</th><th>Total return</th><th>CAGR</th><th>Volatility</th><th>Max drawdown</th><th>Sortino</th><th>Calmar</th></tr></thead><tbody>{_metrics_table(report)}</tbody></table></div>
              <div class="notes"><p><b>Overlap:</b> {html.escape(overlap)}</p><p class="outside-note"><b>{_outside_label(review_age)}:</b> {html.escape(outside)}</p><p><b>Negative holdings:</b> {html.escape(negatives)}</p></div>
              <div class="table-wrap"><table><thead><tr><th>Historical rank</th><th>Ticker</th><th>Score</th><th>Entry</th><th>Exit</th><th>Net return</th><th>Contribution</th><th>Ending weight</th><th>Review status</th></tr></thead><tbody>{_holding_rows(report)}</tbody></table></div>
            </section>'''
        )
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Rigorous Stock Selection Backtest</title><style>
    :root{{--ink:#152337;--muted:#647183;--line:#d9e2e5;--paper:#fff;--bg:#f4f7f5;--green:#0c6b58;--soft:#e0f1eb;--red:#b44444;--amber:#a8640b;--blue:#315c9b;--purple:#7a4aa0}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}}header{{padding:22px clamp(16px,4vw,48px);background:var(--paper);border-bottom:1px solid var(--line)}}header a{{color:var(--green);font-weight:800;text-decoration:none}}h1{{margin:12px 0 5px;font-size:clamp(1.7rem,4vw,2.6rem);letter-spacing:-.04em}}header p{{margin:5px 0;color:var(--muted)}}main{{padding:22px clamp(16px,4vw,48px) 56px}}.notice{{padding:12px 14px;border-left:4px solid var(--amber);background:#fff4dd;color:#734806;border-radius:8px}}.report-section{{margin-top:30px}}.section-head{{display:flex;justify-content:space-between;gap:12px;align-items:start}}.section-head h2{{margin:0}}.section-head p{{margin:4px 0 0;color:var(--muted)}}.validity{{padding:5px 8px;border-radius:999px;font-size:.72rem;font-weight:800}}.validity.exploratory{{background:#fff0d8;color:var(--amber)}}.validity.validated{{background:var(--soft);color:var(--green)}}.summary-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:12px 0}}.summary-grid div,.notes,.decision{{padding:13px;border:1px solid var(--line);border-radius:12px;background:var(--paper)}}.summary-grid span{{display:block;color:var(--muted);font-size:.73rem;text-transform:uppercase}}.summary-grid strong{{display:block;margin-top:5px;font-size:1.2rem}}.positive{{color:var(--green)}}.negative,.outside-note,.outside-status{{color:var(--red);font-weight:800}}.notes{{display:grid;gap:4px;margin:12px 0;font-size:.82rem}}.notes p{{margin:0}}.table-wrap{{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--paper)}}table{{width:100%;min-width:860px;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid var(--line);text-align:left;font-size:.77rem}}th{{background:#edf3f1;color:var(--muted)}}.metrics-table{{margin:12px 0}}.nav-chart{{margin:12px 0;padding:10px;border:1px solid var(--line);border-radius:12px;background:var(--paper)}}.nav-chart figcaption{{display:flex;justify-content:space-between;gap:10px;font-size:.78rem}}.nav-chart i{{display:inline-block;width:12px;height:3px;margin:0 4px 2px 10px}}.nav-chart .sel{{background:var(--green)}}.nav-chart .spy{{background:var(--blue)}}.nav-chart .qqq{{background:var(--purple)}}.nav-chart svg{{display:block;width:100%;max-height:260px}}.axis{{stroke:var(--line)}}.analysis-section{{margin-top:30px}}.decision{{border-left:4px solid var(--green)}}footer{{margin-top:24px;color:var(--muted);font-size:.76rem}}@media(max-width:850px){{.summary-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.nav-chart figcaption{{display:block}}}}@media(max-width:520px){{.summary-grid{{grid-template-columns:1fr}}.section-head{{display:block}}.validity{{display:inline-block;margin-top:8px}}}}
    </style></head><body><header><a href="dashboard_stock_selection.html">← Long-Term Stock Selection</a> · <a href="dashboard_stock_selection_score_analysis.html">One-year score analysis</a><h1>Rigorous Historical Selection Backtest</h1><p>Equal-initial-weight, price-derived paper portfolios with next-session entry, explicit costs, daily NAV, controls, and model diagnostics.</p><p>Generated {generated_at} · local prices through {result["latest_date"]:%Y-%m-%d}</p></header><main><p class="notice"><b>Validity warning:</b> current universe-history dates are incomplete, so real historical cohorts are exploratory static-current-universe replays. Review-date top-10 portfolios are hindsight controls, not investable historical choices. Defaults: {result["execution_lag_sessions"]} execution-session lag, {result["one_way_cost_bps"]:.1f} bps per purchase/sale, {result["random_portfolios"]:,} deterministic random portfolios (seed {result["random_seed"]}). No taxes or slippage beyond the stated cost.</p>
    <section class="analysis-section"><h2>Annual walk-forward evidence</h2><p>Static diversified top-10 cohorts. Multi-year cohorts overlap and use block-bootstrap confidence intervals.</p>{_walk_forward_table(result["walk_forward_aggregates"])}</section>
    <section class="analysis-section"><h2>Annually refreshed top 10</h2><p>The portfolio is refreshed after each annual point-in-time selection; transaction costs apply only to actual constituent turnover.</p>{_annual_refreshed_table(result["annual_refreshed_summary"])}</section>
    <section class="analysis-section"><h2>Predeclared model ablations</h2><p>Alternatives are evaluated on independent one-year cohorts. The production dashboard remains baseline unless every promotion gate passes.</p>{_model_table(result["model_evaluation"], result["promotion_decision"])}</section>
    {''.join(sections)}<footer>Inputs: local adjusted-price histories from {html.escape(str(result["data_dir"]))}; universe history {html.escape(str(result["universe_history_file"]))}. Research support only, not a recommendation or execution instruction.</footer></main></body></html>'''
    output_path.write_text(page, encoding="utf-8")
    return output_path


def write_backtest_csv(frame, output_path):
    output_path = _resolved(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.replace([np.inf, -np.inf], np.nan).to_csv(output_path, index=False, na_rep="")
    return output_path


def main(argv=None):
    args = parse_args(argv)
    result = build_selection_backtest(
        tickers_file=args.tickers_file,
        metadata_file=args.metadata_file,
        data_dir=args.data_dir,
        universe_history_file=args.universe_history_file,
        years_ago=args.years_ago,
        holding_years=args.holding_years,
        walk_forward_years=args.walk_forward_years,
        execution_lag_sessions=args.execution_lag_sessions,
        one_way_cost_bps=args.one_way_cost_bps,
        random_portfolios=args.random_portfolios,
        random_seed=args.random_seed,
        primary_benchmark=args.primary_benchmark,
        secondary_benchmark=args.secondary_benchmark,
        shortlist_size=args.shortlist_size,
        group_cap=args.group_cap,
    )
    html_path = render_selection_backtest(result, args.html_output)
    csv_path = write_backtest_csv(result["export"], args.csv_output)
    summary_path = write_backtest_csv(result["summary"], args.summary_output)
    nav_path = write_backtest_csv(result["nav"], args.nav_output)
    for report in result["reports"]:
        selected = report["portfolios"]["selected"]["metrics"]
        print(
            f"{report['years_ago']}Y ago to {_as_of_label(report['review_years_ago'])}: "
            f"net {_number(selected['total_return_pct'])} · CAGR {_number(selected['cagr_pct'])} · "
            f"MDD {_number(selected['max_drawdown_pct'])} · random percentile {_number(report['random_percentile'],1,'')}"
        )
    print(f"Model decision: {result['promotion_decision']}")
    print(f"HTML:    {html_path}")
    print(f"Holdings:{csv_path}")
    print(f"Summary: {summary_path}")
    print(f"NAV:     {nav_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
