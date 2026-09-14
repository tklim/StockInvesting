"""Calibrate stock-selection component weights with one-year walk-forward tests.

This is an exploratory research tool.  It deliberately separates full-sample
weight search from nested out-of-sample evaluation and will not recommend a
production replacement unless strict validation gates pass.
"""

from __future__ import annotations

import argparse
import html
from collections import Counter
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

import dashboard_stock_selection as selection
import dashboard_stock_selection_backtest as backtest


SCRIPT_DIR = Path(__file__).resolve().parent
REPORTS_DIR = SCRIPT_DIR / "outputs" / "reports"
DEFAULT_HTML_OUTPUT = REPORTS_DIR / "dashboard_stock_selection_score_analysis.html"
DEFAULT_SUMMARY_OUTPUT = REPORTS_DIR / "dashboard_stock_selection_score_analysis.csv"
DEFAULT_COHORT_OUTPUT = REPORTS_DIR / "dashboard_stock_selection_score_analysis_cohorts.csv"

COMPONENTS = (
    ("return", "return_score", 25.0),
    ("persistence", "persistence_score", 25.0),
    ("risk", "risk_score", 25.0),
    ("benchmark", "benchmark_score", 15.0),
    ("confidence", "confidence_score", 10.0),
)
BASELINE_WEIGHTS = (25, 25, 25, 15, 10)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Analyze stock-selection score weights using one-year nested walk-forward cohorts."
    )
    parser.add_argument("--tickers-file", default=str(selection.DEFAULT_TICKERS_FILE))
    parser.add_argument("--metadata-file", default=str(selection.DEFAULT_METADATA_FILE))
    parser.add_argument("--data-dir", default=str(selection.DATA_DIR))
    parser.add_argument("--universe-history-file", default=str(backtest.DEFAULT_UNIVERSE_HISTORY))
    parser.add_argument("--walk-forward-years", type=int, default=10)
    parser.add_argument("--minimum-training-cohorts", type=int, default=4)
    parser.add_argument("--weight-step", type=int, default=5)
    parser.add_argument("--shortlist-size", type=int, default=10)
    parser.add_argument("--group-cap", type=int, default=3)
    parser.add_argument("--execution-lag-sessions", type=int, default=1)
    parser.add_argument("--one-way-cost-bps", type=float, default=10.0)
    parser.add_argument("--bootstrap-iterations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--primary-benchmark", default="SPY")
    parser.add_argument("--secondary-benchmark", default="QQQ")
    parser.add_argument("--html-output", default=str(DEFAULT_HTML_OUTPUT))
    parser.add_argument("--summary-output", default=str(DEFAULT_SUMMARY_OUTPUT))
    parser.add_argument("--cohort-output", default=str(DEFAULT_COHORT_OUTPUT))
    return parser.parse_args(argv)


def _resolved(path):
    value = Path(path)
    return value if value.is_absolute() else SCRIPT_DIR / value


def generate_weight_grid(step=5):
    """Generate a bounded, deterministic simplex of interpretable weights."""
    step = int(step)
    if step <= 0 or 100 % step:
        raise ValueError("weight_step must be a positive divisor of 100")
    ranges = (
        range(10, 46, step),  # return
        range(10, 41, step),  # persistence
        range(10, 46, step),  # risk
        range(5, 31, step),   # benchmark consistency
        range(5, 21, step),   # data confidence
    )
    weights = [tuple(values) for values in product(*ranges) if sum(values) == 100]
    if BASELINE_WEIGHTS not in weights:
        weights.append(BASELINE_WEIGHTS)
    return sorted(set(weights))


def _weight_label(weights):
    return "/".join(str(int(value)) for value in weights)


def _rank_and_select(rows, weights, shortlist_size, group_cap):
    """Apply weights to normalized baseline components and diversify greedily."""
    eligible = rows[
        (rows["eligibility"] == "eligible")
        & rows["score"].notna()
    ].copy()
    score = pd.Series(0.0, index=eligible.index)
    for weight, (_, column, maximum) in zip(weights, COMPONENTS):
        values = pd.to_numeric(eligible[column], errors="coerce") / maximum
        score = score + float(weight) * values
    eligible["analysis_score"] = score
    eligible = eligible.dropna(subset=["analysis_score"]).sort_values(
        ["analysis_score", "ticker"], ascending=[False, True]
    )
    counts = Counter()
    selected = []
    for row in eligible.itertuples():
        if counts[row.industry_group] >= group_cap:
            continue
        selected.append(row.ticker)
        counts[row.industry_group] += 1
        if len(selected) == shortlist_size:
            break
    return selected


def _cohort_result(cohort, weights, shortlist_size, group_cap):
    if "candidates" in cohort:
        scored = sorted(
            [
                (
                float(np.dot(candidate["components"], np.asarray(weights, dtype=float))),
                candidate["ticker"],
                candidate["industry_group"],
                )
                for candidate in cohort["candidates"]
            ],
            key=lambda item: (-item[0], item[1]),
        )
        counts = Counter()
        selected = []
        for _, ticker, industry_group in scored:
            if counts[industry_group] >= group_cap:
                continue
            selected.append(ticker)
            counts[industry_group] += 1
            if len(selected) == shortlist_size:
                break
    else:
        selected = _rank_and_select(cohort["rows"], weights, shortlist_size, group_cap)
    if len(selected) < shortlist_size:
        return None
    ticker_returns = cohort["returns"]
    selected_values = np.asarray([ticker_returns[ticker] for ticker in selected], dtype=float)
    portfolio_return = float(selected_values.mean())
    return {
        "weights": tuple(weights),
        "selected": selected,
        "portfolio_return_pct": portfolio_return,
        "spy_return_pct": cohort["spy_return_pct"],
        "qqq_return_pct": cohort["qqq_return_pct"],
        "eligible_universe_return_pct": cohort["eligible_universe_return_pct"],
        "excess_spy_pct": portfolio_return - cohort["spy_return_pct"],
        "excess_qqq_pct": portfolio_return - cohort["qqq_return_pct"],
        "excess_strict_pct": portfolio_return
        - max(cohort["spy_return_pct"], cohort["qqq_return_pct"]),
        "negative_holdings": int((selected_values < 0).sum()),
        "worst_holding_return_pct": float(selected_values.min()),
    }


def _objective(results):
    if not results:
        return -np.inf
    strict = np.asarray([row["excess_strict_pct"] for row in results], dtype=float)
    negative_holdings = np.asarray([row["negative_holdings"] for row in results], dtype=float)
    downside = float(np.sqrt(np.mean(np.square(np.minimum(strict, 0.0)))))
    return (
        float(np.median(strict))
        + 0.50 * float(np.mean(strict))
        + 0.50 * float(np.quantile(strict, 0.25))
        - 0.50 * downside
        - 0.10 * float(np.mean(negative_holdings))
    )


def _evaluate_weights(cohorts, weights, shortlist_size, group_cap):
    results = []
    for cohort in cohorts:
        result = _cohort_result(cohort, weights, shortlist_size, group_cap)
        if result is not None:
            results.append(result)
    return results


def _best_weights(cohorts, weight_grid, shortlist_size, group_cap):
    candidates = []
    for weights in weight_grid:
        results = _evaluate_weights(cohorts, weights, shortlist_size, group_cap)
        if len(results) != len(cohorts):
            continue
        candidates.append(
            (
                _objective(results),
                -sum(abs(value - baseline) for value, baseline in zip(weights, BASELINE_WEIGHTS)),
                tuple(-value for value in weights),
                weights,
                results,
            )
        )
    if not candidates:
        raise ValueError("No weight combination produced a complete top-10 portfolio")
    return max(candidates)[3], max(candidates)[4]


def _load_cohorts(args):
    tickers_file = _resolved(args.tickers_file)
    metadata_file = _resolved(args.metadata_file)
    data_dir = _resolved(args.data_dir)
    history_file = _resolved(args.universe_history_file)
    base_tickers = selection.load_ticker_universe(tickers_file)
    base_metadata = selection.load_selection_metadata(metadata_file, base_tickers)
    universe_history, history_path = backtest.load_universe_history(history_file)
    metadata = backtest._combined_metadata(base_metadata, universe_history)
    all_tickers = list(dict.fromkeys(base_tickers + universe_history["ticker"].tolist()))
    prices = selection.load_price_universe(all_tickers, data_dir)
    primary = args.primary_benchmark.upper()
    secondary = args.secondary_benchmark.upper()
    snapshots, latest_date = backtest._build_snapshots(
        range(args.walk_forward_years + 1),
        base_tickers,
        metadata,
        prices,
        universe_history,
        primary,
        secondary,
        args.shortlist_size,
        args.group_cap,
    )
    calendar = backtest._benchmark_calendar(prices, primary)
    cohorts = []
    for age in range(args.walk_forward_years, 0, -1):
        snapshot = snapshots[age]
        review = snapshots[age - 1]
        eligible = snapshot["rows"][snapshot["rows"]["eligibility"] == "eligible"]
        if len(eligible) < args.shortlist_size:
            continue
        eligible_tickers = eligible["ticker"].tolist()
        universe_portfolio = backtest.build_portfolio(
            f"score-analysis-{age}y",
            "eligible_universe",
            eligible_tickers,
            prices,
            calendar,
            snapshot["as_of_date"],
            review["as_of_date"],
            args.execution_lag_sessions,
            args.one_way_cost_bps,
        )
        spy = backtest.build_portfolio(
            f"score-analysis-{age}y", primary, [primary], prices, calendar,
            snapshot["as_of_date"], review["as_of_date"],
            args.execution_lag_sessions, args.one_way_cost_bps,
        )
        qqq = backtest.build_portfolio(
            f"score-analysis-{age}y", secondary, [secondary], prices, calendar,
            snapshot["as_of_date"], review["as_of_date"],
            args.execution_lag_sessions, args.one_way_cost_bps,
        )
        returns = universe_portfolio["holdings"].set_index("ticker")["net_return_pct"].to_dict()
        candidates = []
        for row in eligible.itertuples():
            normalized = []
            for _, column, maximum in COMPONENTS:
                value = float(getattr(row, column)) / maximum
                normalized.append(value)
            if all(np.isfinite(normalized)):
                candidates.append(
                    {
                        "ticker": row.ticker,
                        "industry_group": row.industry_group,
                        "components": np.asarray(normalized, dtype=float),
                    }
                )
        cohorts.append(
            {
                "age": age,
                "selection_date": pd.Timestamp(snapshot["as_of_date"]),
                "review_date": pd.Timestamp(review["as_of_date"]),
                "rows": snapshot["rows"],
                "returns": returns,
                "candidates": candidates,
                "validity_status": snapshot["validity_status"],
                "universe_label": snapshot["universe_label"],
                "spy_return_pct": spy["metrics"]["total_return_pct"],
                "qqq_return_pct": qqq["metrics"]["total_return_pct"],
                "eligible_universe_return_pct": universe_portfolio["metrics"]["total_return_pct"],
            }
        )
    return cohorts, prices, calendar, latest_date, history_path


def _bootstrap_difference(values, iterations, seed):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return np.nan, np.nan
    rng = np.random.default_rng(int(seed))
    samples = rng.choice(values, size=(int(iterations), len(values)), replace=True).mean(axis=1)
    return tuple(float(value) for value in np.quantile(samples, [0.025, 0.975]))


def _portfolio_risk_metrics(cohort, selected, prices, calendar, args, label):
    portfolio = backtest.build_portfolio(
        f"nested-{cohort['age']}y-{label}", label, selected, prices, calendar,
        cohort["selection_date"], cohort["review_date"],
        args.execution_lag_sessions, args.one_way_cost_bps,
    )
    return portfolio["metrics"]


def build_score_analysis(args):
    if args.walk_forward_years < args.minimum_training_cohorts + 1:
        raise ValueError("walk_forward_years must exceed minimum_training_cohorts")
    cohorts, prices, calendar, latest_date, history_path = _load_cohorts(args)
    if len(cohorts) < args.minimum_training_cohorts + 1:
        raise ValueError("Insufficient complete one-year cohorts for nested evaluation")
    grid = generate_weight_grid(args.weight_step)

    full_best, full_results = _best_weights(
        cohorts, grid, args.shortlist_size, args.group_cap
    )
    baseline_results = _evaluate_weights(
        cohorts, BASELINE_WEIGHTS, args.shortlist_size, args.group_cap
    )
    summary_rows = []
    for weights, label, results in (
        (BASELINE_WEIGHTS, "baseline", baseline_results),
        (full_best, "full_sample_exploratory", full_results),
    ):
        summary_rows.append(_summary_for_formula(label, weights, results))

    top_candidates = []
    for weights in grid:
        results = _evaluate_weights(cohorts, weights, args.shortlist_size, args.group_cap)
        if len(results) != len(cohorts):
            continue
        row = _summary_for_formula("candidate", weights, results)
        top_candidates.append(row)
    top_candidates = sorted(
        top_candidates,
        key=lambda row: (-row["objective"], row["baseline_distance"], row["weights"]),
    )[:25]

    nested_rows = []
    prior_selected = None
    for test_position in range(args.minimum_training_cohorts, len(cohorts)):
        training = cohorts[:test_position]
        test = cohorts[test_position]
        chosen, _ = _best_weights(training, grid, args.shortlist_size, args.group_cap)
        optimized = _cohort_result(test, chosen, args.shortlist_size, args.group_cap)
        baseline = _cohort_result(test, BASELINE_WEIGHTS, args.shortlist_size, args.group_cap)
        if optimized is None or baseline is None:
            continue
        optimized_metrics = _portfolio_risk_metrics(
            test, optimized["selected"], prices, calendar, args, "optimized"
        )
        baseline_metrics = _portfolio_risk_metrics(
            test, baseline["selected"], prices, calendar, args, "baseline"
        )
        turnover = (
            np.nan
            if prior_selected is None
            else (1.0 - len(set(prior_selected) & set(optimized["selected"])) / args.shortlist_size) * 100.0
        )
        prior_selected = optimized["selected"]
        for model, result, metrics in (
            ("nested_optimized", optimized, optimized_metrics),
            ("baseline", baseline, baseline_metrics),
        ):
            nested_rows.append(
                {
                    "model": model,
                    "selection_date": test["selection_date"].strftime("%Y-%m-%d"),
                    "review_date": test["review_date"].strftime("%Y-%m-%d"),
                    "holding_years": 1,
                    "training_cohorts": test_position,
                    "weights": _weight_label(chosen if model == "nested_optimized" else BASELINE_WEIGHTS),
                    **{name: int(value) for name, value in zip((item[0] for item in COMPONENTS), chosen if model == "nested_optimized" else BASELINE_WEIGHTS)},
                    "selected_tickers": " ".join(result["selected"]),
                    "portfolio_return_pct": result["portfolio_return_pct"],
                    "spy_return_pct": result["spy_return_pct"],
                    "qqq_return_pct": result["qqq_return_pct"],
                    "eligible_universe_return_pct": result["eligible_universe_return_pct"],
                    "excess_spy_pct": result["excess_spy_pct"],
                    "excess_qqq_pct": result["excess_qqq_pct"],
                    "negative_holdings": result["negative_holdings"],
                    "worst_holding_return_pct": result["worst_holding_return_pct"],
                    "annualized_volatility_pct": metrics["annualized_volatility_pct"],
                    "max_drawdown_pct": metrics["max_drawdown_pct"],
                    "sortino": metrics["sortino"],
                    "turnover_pct": turnover if model == "nested_optimized" else np.nan,
                    "validity_status": test["validity_status"],
                    "universe_label": test["universe_label"],
                }
            )
    nested = pd.DataFrame(nested_rows)
    optimized = nested[nested["model"] == "nested_optimized"].copy()
    baseline = nested[nested["model"] == "baseline"].copy()
    comparison = optimized.merge(
        baseline[["selection_date", "portfolio_return_pct", "sortino", "max_drawdown_pct"]],
        on="selection_date",
        suffixes=("", "_baseline"),
    )
    differences = comparison["portfolio_return_pct"] - comparison["portfolio_return_pct_baseline"]
    ci_low, ci_high = _bootstrap_difference(differences, args.bootstrap_iterations, args.seed)
    validated = optimized[optimized["validity_status"] == "validated"]
    promotion_passed = (
        len(validated) >= 10
        and float(validated["excess_spy_pct"].median()) > 0
        and float(validated["excess_qqq_pct"].median()) > 0
        and float(validated["sortino"].median()) > float(baseline["sortino"].median())
        and abs(float(validated["max_drawdown_pct"].min()))
        <= abs(float(baseline["max_drawdown_pct"].min())) + 2.0
        and np.isfinite(ci_low)
        and ci_low > 0
    )
    decision = (
        f"promote exploratory formula {_weight_label(full_best)}"
        if promotion_passed
        else "retain baseline; no replacement proved"
    )
    summary_rows.append(
        {
            "model": "nested_optimized_oos",
            "weights": "varies by training window",
            "return": np.nan,
            "persistence": np.nan,
            "risk": np.nan,
            "benchmark": np.nan,
            "confidence": np.nan,
            "cohort_count": len(optimized),
            "validated_cohorts": len(validated),
            "mean_return_pct": float(optimized["portfolio_return_pct"].mean()),
            "median_excess_spy_pct": float(optimized["excess_spy_pct"].median()),
            "median_excess_qqq_pct": float(optimized["excess_qqq_pct"].median()),
            "worst_return_pct": float(optimized["portfolio_return_pct"].min()),
            "negative_cohort_rate_pct": float((optimized["portfolio_return_pct"] < 0).mean() * 100.0),
            "average_negative_holdings": float(optimized["negative_holdings"].mean()),
            "objective": np.nan,
            "baseline_distance": np.nan,
            "mean_improvement_vs_baseline_pct": float(differences.mean()),
            "improvement_ci_low_pct": ci_low,
            "improvement_ci_high_pct": ci_high,
            "promotion_passed": promotion_passed,
        }
    )
    summary = pd.DataFrame(summary_rows + top_candidates)
    return {
        "summary": summary,
        "cohorts": nested,
        "top_candidates": pd.DataFrame(top_candidates),
        "full_best_weights": full_best,
        "weight_grid_count": len(grid),
        "latest_date": latest_date,
        "history_path": history_path,
        "decision": decision,
        "promotion_passed": promotion_passed,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "comparison": comparison,
        "args": args,
    }


def _summary_for_formula(model, weights, results):
    returns = np.asarray([row["portfolio_return_pct"] for row in results], dtype=float)
    return {
        "model": model,
        "weights": _weight_label(weights),
        **{name: int(value) for name, value in zip((item[0] for item in COMPONENTS), weights)},
        "cohort_count": len(results),
        "validated_cohorts": np.nan,
        "mean_return_pct": float(returns.mean()),
        "median_excess_spy_pct": float(np.median([row["excess_spy_pct"] for row in results])),
        "median_excess_qqq_pct": float(np.median([row["excess_qqq_pct"] for row in results])),
        "worst_return_pct": float(returns.min()),
        "negative_cohort_rate_pct": float((returns < 0).mean() * 100.0),
        "average_negative_holdings": float(np.mean([row["negative_holdings"] for row in results])),
        "objective": _objective(results),
        "baseline_distance": int(sum(abs(value - baseline) for value, baseline in zip(weights, BASELINE_WEIGHTS))),
        "mean_improvement_vs_baseline_pct": np.nan,
        "improvement_ci_low_pct": np.nan,
        "improvement_ci_high_pct": np.nan,
        "promotion_passed": False,
    }


def _fmt(value, decimals=1, suffix="%"):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{number:+.{decimals}f}{suffix}" if np.isfinite(number) else "n/a"


def render_html(result, output_path):
    output_path = _resolved(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = result["args"]
    summary = result["summary"]
    nested = result["cohorts"]
    full = summary[summary["model"] == "full_sample_exploratory"].iloc[0]
    oos = summary[summary["model"] == "nested_optimized_oos"].iloc[0]
    cohort_rows = []
    optimized = nested[nested["model"] == "nested_optimized"]
    for _, row in optimized.iterrows():
        cohort_rows.append(
            f"<tr><td>{row['selection_date']}</td><td>{row['review_date']}</td><td>{html.escape(row['weights'])}</td>"
            f"<td>{_fmt(row['portfolio_return_pct'])}</td><td>{_fmt(row['spy_return_pct'])}</td><td>{_fmt(row['qqq_return_pct'])}</td>"
            f"<td>{_fmt(row['excess_spy_pct'])}</td><td>{_fmt(row['excess_qqq_pct'])}</td><td>{int(row['negative_holdings'])}</td>"
            f"<td>{_fmt(row['max_drawdown_pct'])}</td><td>{_fmt(row['sortino'],2,'')}</td><td>{html.escape(row['validity_status'])}</td></tr>"
        )
    candidate_rows = []
    for _, row in result["top_candidates"].head(15).iterrows():
        candidate_rows.append(
            f"<tr><td>{html.escape(row['weights'])}</td><td>{_fmt(row['mean_return_pct'])}</td>"
            f"<td>{_fmt(row['median_excess_spy_pct'])}</td><td>{_fmt(row['median_excess_qqq_pct'])}</td>"
            f"<td>{_fmt(row['worst_return_pct'])}</td><td>{_fmt(row['negative_cohort_rate_pct'])}</td><td>{row['objective']:.2f}</td></tr>"
        )
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Stock Selection Score Analysis</title><style>
    :root{{--ink:#152337;--muted:#647183;--line:#d9e2e5;--paper:#fff;--bg:#f4f7f5;--green:#0c6b58;--amber:#a8640b;--red:#b44444;--soft:#e6f4ed}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}}header,main{{padding:22px clamp(16px,4vw,48px)}}header{{background:var(--paper);border-bottom:1px solid var(--line)}}header a{{color:var(--green);font-weight:800;text-decoration:none}}h1{{margin:12px 0 5px}}p{{line-height:1.5}}.notice,.decision{{padding:13px 15px;border-radius:10px;background:#fff4dd;border-left:4px solid var(--amber)}}.decision{{background:var(--soft);border-color:var(--green)}}.cards{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:18px 0}}.cards div{{padding:14px;background:var(--paper);border:1px solid var(--line);border-radius:12px}}.cards span{{display:block;color:var(--muted);font-size:.72rem;text-transform:uppercase}}.cards strong{{display:block;margin-top:5px;font-size:1.1rem}}section{{margin-top:28px}}.table-wrap{{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--paper)}}table{{width:100%;min-width:900px;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid var(--line);font-size:.77rem;text-align:left}}th{{background:#edf3f1;color:var(--muted)}}.bad{{color:var(--red);font-weight:800}}@media(max-width:800px){{.cards{{grid-template-columns:repeat(2,1fr)}}}}@media(max-width:480px){{.cards{{grid-template-columns:1fr}}}}
    </style></head><body><header><a href="dashboard_stock_selection.html">← Stock selection</a><h1>One-Year Score Calibration</h1><p>Nested annual walk-forward analysis of the five price-derived score components. Every portfolio exits at the next annual review.</p><p>Prices through {result['latest_date']:%Y-%m-%d} · {result['weight_grid_count']:,} constrained formulas tested · {args.one_way_cost_bps:.1f} bps each way</p></header><main>
    <p class="notice"><b>Validity warning:</b> historical membership is incomplete, so all current evidence is exploratory and affected by current-universe survivor bias. Full-sample winners are shown for diagnosis, not adoption.</p>
    <div class="cards"><div><span>Baseline weights</span><strong>25 / 25 / 25 / 15 / 10</strong></div><div><span>Full-sample candidate</span><strong>{html.escape(full['weights'])}</strong></div><div><span>Nested OOS cohorts</span><strong>{int(oos['cohort_count'])}</strong></div><div><span>Validated OOS cohorts</span><strong>{int(oos['validated_cohorts'])}</strong></div></div>
    <p class="decision"><b>Decision:</b> {html.escape(result['decision'])}. Nested mean improvement versus baseline {_fmt(oos['mean_improvement_vs_baseline_pct'])}; 95% bootstrap interval {_fmt(result['ci_low'])} to {_fmt(result['ci_high'])}.</p>
    <section><h2>How to read the proposed formula</h2><p>Weights are ordered as <b>return / persistence / risk / benchmark consistency / confidence</b>. The full-sample candidate is the strongest in-sample diagnostic. The nested rows are the honest test: each formula was selected using only older cohorts, then held exactly one year in the next unseen cohort.</p></section>
    <section><h2>Nested out-of-sample one-year cohorts</h2><div class="table-wrap"><table><thead><tr><th>Selected</th><th>Reviewed</th><th>Training-chosen weights</th><th>Top-10 return</th><th>SPY</th><th>QQQ</th><th>Excess SPY</th><th>Excess QQQ</th><th>Negative holdings</th><th>Max drawdown</th><th>Sortino</th><th>Validity</th></tr></thead><tbody>{''.join(cohort_rows)}</tbody></table></div></section>
    <section><h2>Top full-sample formulas — exploratory</h2><div class="table-wrap"><table><thead><tr><th>Weights</th><th>Mean return</th><th>Median excess SPY</th><th>Median excess QQQ</th><th>Worst year</th><th>Negative-year rate</th><th>Objective</th></tr></thead><tbody>{''.join(candidate_rows)}</tbody></table></div></section>
    <section><h2>Promotion rule</h2><p>A replacement requires at least ten <i>validated</i> independent one-year out-of-sample cohorts, positive median excess versus SPY and QQQ, better median Sortino than baseline, maximum drawdown no more than two percentage points worse, and a positive lower bootstrap bound for improvement. Otherwise the production 25/25/25/15/10 score remains.</p></section>
    <footer><p>Research support only. No fundamentals, valuation, taxes, position sizing, or trade execution are included.</p></footer></main></body></html>'''
    output_path.write_text(page, encoding="utf-8")
    return output_path


def write_csv(frame, output_path):
    output_path = _resolved(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.replace([np.inf, -np.inf], np.nan).to_csv(output_path, index=False, na_rep="")
    return output_path


def main(argv=None):
    args = parse_args(argv)
    result = build_score_analysis(args)
    html_path = render_html(result, args.html_output)
    summary_path = write_csv(result["summary"], args.summary_output)
    cohort_path = write_csv(result["cohorts"], args.cohort_output)
    print(f"Decision: {result['decision']}")
    print(f"Full-sample exploratory weights: {_weight_label(result['full_best_weights'])}")
    print(f"HTML:    {html_path}")
    print(f"Summary: {summary_path}")
    print(f"Cohorts: {cohort_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
