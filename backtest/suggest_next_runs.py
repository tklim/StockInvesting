"""Recommend the next backtest runs from the collected tuning history.

Two modelling levels are available:

  --level run     (default) Models outputs/tunings/backtest_run_history.csv:
                  one row = one complete chained walk-forward backtest. The
                  decision variables are the GA *search bounds* you pass on
                  the command line, and the objective defaults to excess
                  annualized return vs buy & hold. This is the honest signal:
                  it is measured out-of-sample across the whole chain.

  --level window  Models outputs/tunings/backtest_tuning_history.csv: one row
                  = one walk-forward window's in-sample GA fit. Useful for
                  understanding which strategy parameters the GA gravitates
                  toward, but a poor optimization target -- annualizing a
                  90-day window compounds a single lucky quarter into a
                  headline number the chained backtest never reproduces.

In both cases the data is grouped by (fund_label, lookback_years), a
Random-Forest surrogate is fit per group, and an Expected-Improvement
acquisition proposes new configurations. Groups with too little data get a
space-filling exploration design instead of a meaningless surrogate.

Writes a recommendations CSV and prints ready-to-run backtest_stocks.py
commands. Never launches runs itself.
"""

import argparse
import shlex
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold, cross_val_score

from experiment_runner import BOUND_SPEC, WIDE_BASELINE, sobol_bounds

SCRIPT_DIR = Path(__file__).resolve().parent
TUNINGS_DIR = SCRIPT_DIR / "outputs" / "tunings"
WINDOW_HISTORY = TUNINGS_DIR / "backtest_tuning_history.csv"
RUN_HISTORY = TUNINGS_DIR / "backtest_run_history.csv"
DEFAULT_OUT = TUNINGS_DIR / "next_run_recommendations.csv"

# Global GA search-space limits (mirrors backtest_stocks.py defaults).
GLOBAL_BOUNDS = {name: (spec["lo"], spec["hi"]) for name, spec in BOUND_SPEC.items()}
MIN_SPANS = {name: spec["min_span"] for name, spec in BOUND_SPEC.items()}

BOUND_FEATURES = [f"{name}_{edge}" for name in BOUND_SPEC for edge in ("min", "max")]

# --- run level -------------------------------------------------------------
RUN_CONFIG_FEATURES = ["offset_months", "pop_ranges", "gen_ranges",
                       "mutation_rate", "crossover_rate"]
RUN_FEATURES = BOUND_FEATURES + RUN_CONFIG_FEATURES
RUN_OBJECTIVES = ["excess_annualized_return_pct", "adaptive_annualized_return_pct",
                  "excess_return_pct", "sharpe", "score"]

# --- window level ----------------------------------------------------------
STRATEGY_FEATURES = ["short_ema", "long_ema", "stop_loss", "cooldown",
                     "drawdown_exit_pct", "reentry_rebound_pct",
                     "rsi_oversold", "rsi_overbought"]
WINDOW_CONFIG_FEATURES = ["offset_months", "pop_size", "generations",
                          "mutation_rate", "crossover_rate"]
WINDOW_FEATURES = STRATEGY_FEATURES + WINDOW_CONFIG_FEATURES
WINDOW_TARGET = "adaptive_annualized_return_pct"

GA_GRID = {
    "pop_ranges": [4, 10],
    "gen_ranges": [2, 4, 10],
    "mutation_rate": [0.01, 0.05, 0.1, 0.15],
    "crossover_rate": [0.6, 0.7, 0.8, 0.9],
    "offset_months": [3, 6, 12],
}


def annualized_return_from_pct(total_return_pct, start_date, end_date):
    """Convert a total return percentage over a date range into annualized return.

    Same behavior as backtest_stocks.annualized_return_from_pct (kept local
    because importing backtest_stocks triggers heavy module-level setup).
    """
    if start_date is None or end_date is None:
        return 0.0
    try:
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        if pd.isna(start_ts) or pd.isna(end_ts):
            return 0.0
        days = (end_ts - start_ts).days
        growth = 1 + (float(total_return_pct) / 100)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if days <= 0:
        return 0.0
    if growth <= 0:
        return -100.0
    return (growth ** (365.25 / days) - 1) * 100


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--level", choices=["run", "window"], default="run",
                        help="Model complete backtests (run) or per-window GA fits "
                             "(window). Default: run")
    parser.add_argument("--objective", default=None,
                        help="Target column to maximize. Default at run level: "
                             "excess_annualized_return_pct")
    parser.add_argument("--history", default=None,
                        help="History CSV to read (defaults per --level)")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="Recommendations CSV to write")
    parser.add_argument("--funds", nargs="+", default=None,
                        help="Restrict to these fund labels (default: all)")
    parser.add_argument("--lookbacks", nargs="+", type=float, default=None,
                        help="Restrict to these lookback_years values (default: all)")
    parser.add_argument("--top-n", type=int, default=3,
                        help="Recommendations per (fund, lookback) group (default: 3)")
    parser.add_argument("--min-rows", type=int, default=4,
                        help="Skip groups with fewer rows than this (default: 4)")
    parser.add_argument("--min-model-rows", type=int, default=12,
                        help="Minimum rows to fit the RF surrogate; smaller groups get "
                             "a space-filling exploration design (default: 12)")
    parser.add_argument("--candidates", type=int, default=20000,
                        help="Candidate pool size for the acquisition search")
    parser.add_argument("--pop", type=int, default=None,
                        help="Force GA population in emitted commands (e.g. 4 for cheap screening)")
    parser.add_argument("--gen", type=int, default=None,
                        help="Force GA generations in emitted commands")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for sampling and the surrogate (default: 42)")
    args = parser.parse_args()
    if args.objective is None:
        args.objective = ("excess_annualized_return_pct" if args.level == "run"
                          else WINDOW_TARGET)
    if args.history is None:
        args.history = str(RUN_HISTORY if args.level == "run" else WINDOW_HISTORY)
    return args


# --------------------------------------------------------------------------
# data loading
# --------------------------------------------------------------------------

def load_run_history(path, objective, funds=None, lookbacks=None):
    df = pd.read_csv(path)
    # 'default grid' appears where no explicit rate was passed; those runs
    # cannot be placed in the design space, so they are dropped.
    df["mutation_rate"] = pd.to_numeric(df.get("mutation_rates"), errors="coerce")
    df["crossover_rate"] = pd.to_numeric(df.get("crossover_rates"), errors="coerce")
    for col in RUN_FEATURES + [objective, "lookback_years"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "run_status" in df.columns:
        df = df[df["run_status"] == "completed"]
    df = df.dropna(subset=RUN_FEATURES + [objective, "fund_label", "lookback_years"])
    if funds:
        df = df[df["fund_label"].isin(funds)]
    if lookbacks:
        df = df[df["lookback_years"].isin(lookbacks)]
    return df


def load_window_history(path, objective, funds=None, lookbacks=None):
    df = pd.read_csv(path)
    for col in WINDOW_FEATURES + ["adaptive_return_pct", "lookback_years"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=WINDOW_FEATURES + ["adaptive_return_pct", "test_start",
                                             "test_end", "fund_label", "lookback_years"])
    dedupe_keys = [c for c in ["fund_label", "lookback_years", "offset_months",
                               "window_sequence", "param_set_id"] if c in df.columns]
    df = df.drop_duplicates(subset=dedupe_keys, keep="last")
    df[WINDOW_TARGET] = [
        annualized_return_from_pct(r, s, e)
        for r, s, e in zip(df["adaptive_return_pct"], df["test_start"], df["test_end"])
    ]
    if objective not in df.columns:
        raise SystemExit(f"Objective '{objective}' not available at window level.")
    df = df.dropna(subset=[objective])
    if funds:
        df = df[df["fund_label"].isin(funds)]
    if lookbacks:
        df = df[df["lookback_years"].isin(lookbacks)]
    return df


# --------------------------------------------------------------------------
# candidate generation
# --------------------------------------------------------------------------

def sample_run_candidates(n, rng, seed):
    """Valid (min, max) bound pairs crossed with the GA hyperparameter grid.

    Bounds come from the same space-filling scheme the experiment runner uses,
    so recommendations live in the space the screening design explored.
    """
    cands = sobol_bounds(n, seed).astype(float)
    for col in RUN_CONFIG_FEATURES:
        cands[col] = rng.choice(GA_GRID[col], size=n).astype(float)
    return cands[RUN_FEATURES]


def sample_window_candidates(group, n, rng):
    pool = {}
    for col in STRATEGY_FEATURES:
        lo, hi = group[col].min(), group[col].max()
        pad = 0.1 * (hi - lo) if hi > lo else max(abs(hi) * 0.1, 1.0)
        lo, hi = lo - pad, hi + pad
        if col in GLOBAL_BOUNDS:
            g_lo, g_hi = GLOBAL_BOUNDS[col]
            lo, hi = max(lo, g_lo), min(hi, g_hi)
        if col in ("short_ema", "long_ema", "cooldown", "rsi_oversold", "rsi_overbought"):
            pool[col] = rng.integers(int(np.floor(lo)), int(np.ceil(hi)) + 1, size=n)
        else:
            pool[col] = rng.uniform(lo, hi, size=n)
    grid_alias = {"pop_size": "pop_ranges", "generations": "gen_ranges"}
    for col in WINDOW_CONFIG_FEATURES:
        pool[col] = rng.choice(GA_GRID[grid_alias.get(col, col)], size=n)
    return pd.DataFrame(pool)[WINDOW_FEATURES]


def expected_improvement(model, X_cand, best_y):
    preds = np.stack([tree.predict(X_cand.values) for tree in model.estimators_])
    mu = preds.mean(axis=0)
    sigma = preds.std(axis=0)
    sigma_safe = np.where(sigma > 1e-9, sigma, 1e-9)
    z = (mu - best_y) / sigma_safe
    ei = (mu - best_y) * norm.cdf(z) + sigma_safe * norm.pdf(z)
    ei[sigma <= 1e-9] = 0.0
    return mu, sigma, ei


def fit_surrogate(X, y, seed, cv_min_rows=20):
    model = RandomForestRegressor(n_estimators=400, random_state=seed, n_jobs=-1)
    model.fit(X.values, y.values)
    cv_note = ""
    if len(X) >= cv_min_rows:
        folds = min(5, len(X) // 4)
        if folds >= 2:
            cv = cross_val_score(
                RandomForestRegressor(n_estimators=200, random_state=seed, n_jobs=-1),
                X.values, y.values,
                cv=KFold(folds, shuffle=True, random_state=seed), scoring="r2")
            cv_note = f"{folds}-fold CV R2 = {cv.mean():+.2f}"
    return model, cv_note


# --------------------------------------------------------------------------
# window-level helpers (bounds are derived from a cluster of candidates)
# --------------------------------------------------------------------------

def narrowed_bounds(top_rows):
    bounds = {}
    for col, (g_lo, g_hi) in GLOBAL_BOUNDS.items():
        lo = int(np.floor(np.percentile(top_rows[col], 10)))
        hi = int(np.ceil(np.percentile(top_rows[col], 90)))
        lo, hi = max(lo, g_lo), min(hi, g_hi)
        span = MIN_SPANS[col]
        if hi - lo < span:
            mid = (hi + lo) / 2
            lo = int(max(g_lo, np.floor(mid - span / 2)))
            hi = int(min(g_hi, lo + span))
            lo = max(g_lo, hi - span)
        bounds[col] = (lo, hi)
    return bounds


def marginal_best(top_rows, col, levels, target):
    present = top_rows[top_rows[col].isin(levels)]
    if not present.empty:
        return present.groupby(col)[target].mean().idxmax()
    snapped = top_rows[col].apply(lambda v: min(levels, key=lambda l: abs(l - v)))
    if not snapped.empty:
        return snapped.mode().iloc[0]
    return levels[len(levels) // 2]


# --------------------------------------------------------------------------
# recommendation
# --------------------------------------------------------------------------

def regime_warning(group, strong_trend_pct=15.0):
    """Flag groups where buy & hold sets a high bar.

    A strategy that sits in cash part of the time faces a headwind when the
    benchmark compounds fast, and excess return correlates about -0.66 with
    benchmark strength across the runs collected so far. The correlation is
    a tendency, not a law: GOOGL over a 2024-2026 test window beat a +38.9%/yr
    benchmark by 6.3 points. Treat this as "expect a hard time and check the
    result is not just a short-window artifact", not as "do not bother".
    """
    if "buy_hold_annualized_return_pct" not in group.columns:
        return ""
    bh = group["buy_hold_annualized_return_pct"].mean()
    if pd.isna(bh) or bh < strong_trend_pct:
        return ""
    return (f"note: buy & hold returns {bh:+.1f}%/yr here, a high bar -- most "
            f"configurations lose to it, and wins on short test windows are "
            f"often noise rather than edge")


def base_record(fund, lookback, rank, method, group, objective, n_rows):
    return {
        "fund_label": fund,
        "lookback_years": lookback,
        "rank": rank,
        "method": method,
        "objective": objective,
        "n_history_rows": n_rows,
        "best_observed": round(group[objective].max(), 3) if n_rows else None,
    }


def recommend_run_level(group, fund, lookback, args, rng):
    """One candidate = one runnable configuration, so no translation step."""
    objective = args.objective
    n = len(group)
    recs, cv_note = [], ""

    if n >= args.min_model_rows:
        X, y = group[RUN_FEATURES], group[objective]
        # Runs are expensive, so the surrogate starts early -- report its CV
        # from the same threshold, so no rf_ei ranking is ever shown without
        # the accompanying honesty check.
        model, cv_note = fit_surrogate(X, y, args.seed, cv_min_rows=args.min_model_rows)
        cands = sample_run_candidates(args.candidates, rng, args.seed)
        mu, sigma, ei = expected_improvement(model, cands, y.max())
        order = np.argsort(-ei)[: args.top_n]
        method = "rf_ei"
        for rank, idx in enumerate(order, start=1):
            rec = base_record(fund, lookback, rank, method, group, objective, n)
            rec.update({
                "pred_mean": round(float(mu[idx]), 3),
                "pred_std": round(float(sigma[idx]), 3),
                "expected_improvement": round(float(ei[idx]), 4),
            })
            rec.update({c: int(cands.iloc[idx][c]) for c in BOUND_FEATURES})
            rec["offset_months"] = int(cands.iloc[idx]["offset_months"])
            rec["pop_ranges"] = int(cands.iloc[idx]["pop_ranges"])
            rec["gen_ranges"] = int(cands.iloc[idx]["gen_ranges"])
            rec["mutation_rate"] = float(cands.iloc[idx]["mutation_rate"])
            rec["crossover_rate"] = float(cands.iloc[idx]["crossover_rate"])
            recs.append(rec)
    else:
        # Too few runs for a surrogate to mean anything: explore instead of
        # exploit. A space-filling design plus the wide-bounds control gives
        # the next round something worth modelling.
        design = sobol_bounds(max(args.top_n - 1, 1), args.seed + int(lookback * 10))
        for rank in range(1, args.top_n + 1):
            rec = base_record(fund, lookback, rank, "explore_sobol", group, objective, n)
            rec.update({"pred_mean": None, "pred_std": None, "expected_improvement": None})
            if rank == args.top_n:
                rec.update(WIDE_BASELINE)
                rec["method"] = "control_wide"
            else:
                rec.update({c: int(v) for c, v in design.iloc[rank - 1].items()})
            rec["offset_months"] = int(rng.choice(GA_GRID["offset_months"]))
            rec["pop_ranges"] = 4
            rec["gen_ranges"] = 2
            rec["mutation_rate"] = 0.05
            rec["crossover_rate"] = 0.7
            recs.append(rec)
    return recs, cv_note


def recommend_window_level(group, fund, lookback, args, rng):
    objective = args.objective
    n = len(group)
    recs, cv_note = [], ""
    if n >= max(args.min_model_rows, 30):
        X, y = group[WINDOW_FEATURES], group[objective]
        model, cv_note = fit_surrogate(X, y, args.seed, cv_min_rows=40)
        cands = sample_window_candidates(group, args.candidates, rng)
        mu, sigma, ei = expected_improvement(model, cands, y.max())
        order = np.argsort(-ei)
        cluster = 50
        for rank in range(1, args.top_n + 1):
            idx = order[(rank - 1) * cluster: rank * cluster]
            if len(idx) == 0:
                break
            top_rows = cands.iloc[idx].copy()
            top_rows[objective] = mu[idx]
            rec = base_record(fund, lookback, rank, "rf_ei", group, objective, n)
            rec.update({
                "pred_mean": round(float(mu[idx].mean()), 3),
                "pred_std": round(float(sigma[idx].mean()), 3),
                "expected_improvement": round(float(ei[idx].mean()), 4),
            })
            for col, (lo, hi) in narrowed_bounds(top_rows).items():
                rec[f"{col}_min"], rec[f"{col}_max"] = lo, hi
            rec["offset_months"] = int(marginal_best(top_rows, "offset_months",
                                                     GA_GRID["offset_months"], objective))
            rec["pop_ranges"] = int(marginal_best(top_rows, "pop_size",
                                                  GA_GRID["pop_ranges"], objective))
            rec["gen_ranges"] = int(marginal_best(top_rows, "generations",
                                                 GA_GRID["gen_ranges"], objective))
            rec["mutation_rate"] = float(marginal_best(top_rows, "mutation_rate",
                                                       GA_GRID["mutation_rate"], objective))
            rec["crossover_rate"] = float(marginal_best(top_rows, "crossover_rate",
                                                        GA_GRID["crossover_rate"], objective))
            recs.append(rec)
    else:
        top_rows = group.nlargest(max(2, int(np.ceil(n * 0.25))), objective)
        rec = base_record(fund, lookback, 1, "quantile", group, objective, n)
        rec.update({"pred_mean": None, "pred_std": None, "expected_improvement": None})
        for col, (lo, hi) in narrowed_bounds(top_rows).items():
            rec[f"{col}_min"], rec[f"{col}_max"] = lo, hi
        rec["offset_months"] = int(marginal_best(top_rows, "offset_months",
                                                 GA_GRID["offset_months"], objective))
        rec["pop_ranges"] = int(marginal_best(top_rows, "pop_size",
                                              GA_GRID["pop_ranges"], objective))
        rec["gen_ranges"] = int(marginal_best(top_rows, "generations",
                                             GA_GRID["gen_ranges"], objective))
        rec["mutation_rate"] = float(marginal_best(top_rows, "mutation_rate",
                                                   GA_GRID["mutation_rate"], objective))
        rec["crossover_rate"] = float(marginal_best(top_rows, "crossover_rate",
                                                    GA_GRID["crossover_rate"], objective))
        recs.append(rec)
    return recs, cv_note


def command_for(rec, seed, pop=None, gen=None):
    lookback = float(rec["lookback_years"])
    lookback_str = str(int(lookback)) if lookback.is_integer() else str(lookback)
    parts = [
        "python", "backtest_stocks.py",
        "--data-file", f"data/{rec['fund_label']}.csv",
        "--lookback-years", lookback_str,
        "--offset-months", str(rec["offset_months"]),
        "--pop_ranges", str(pop if pop else rec["pop_ranges"]),
        "--gen_ranges", str(gen if gen else rec["gen_ranges"]),
        "--mutation-rates", str(rec["mutation_rate"]),
        "--crossover-rates", str(rec["crossover_rate"]),
        "--short-ema-bounds", str(rec["short_ema_min"]), str(rec["short_ema_max"]),
        "--long-ema-bounds", str(rec["long_ema_min"]), str(rec["long_ema_max"]),
        "--rsi-oversold-bounds", str(rec["rsi_oversold_min"]), str(rec["rsi_oversold_max"]),
        "--rsi-overbought-bounds", str(rec["rsi_overbought_min"]), str(rec["rsi_overbought_max"]),
        "--ga-seed", str(seed),
        "--reuse-tuned-params",
    ]
    return " ".join(shlex.quote(p) for p in parts)


def main():
    args = parse_args()
    rng = np.random.default_rng(args.seed)

    if args.level == "run":
        df = load_run_history(args.history, args.objective, args.funds, args.lookbacks)
        recommend = recommend_run_level
    else:
        df = load_window_history(args.history, args.objective, args.funds, args.lookbacks)
        recommend = recommend_window_level

    if df.empty:
        print(f"No usable rows in {args.history} after filtering.")
        return

    print(f"Level: {args.level} | objective: {args.objective} | "
          f"{len(df)} usable rows from {Path(args.history).name}\n")

    all_recs, commands = [], []
    for (fund, lookback), group in df.groupby(["fund_label", "lookback_years"]):
        if len(group) < args.min_rows:
            print(f"[skip    ] {fund} lookback={lookback}: {len(group)} rows "
                  f"(< --min-rows {args.min_rows})")
            continue
        recs, cv_note = recommend(group, fund, lookback, args, rng)
        method = recs[0]["method"] if recs else "-"
        note = f" | {cv_note}" if cv_note else ""
        print(f"[{method:13s}] {fund:6s} lookback={lookback:>4} | n={len(group):4d} | "
              f"best observed={group[args.objective].max():+8.2f}{note}")
        warning = regime_warning(group)
        if warning:
            print(f"{'':15s} {warning}")
        for rec in recs:
            rec["command"] = command_for(rec, args.seed, args.pop, args.gen)
            all_recs.append(rec)
            commands.append((fund, lookback, rec["rank"], rec["method"], rec["command"]))

    if not all_recs:
        print("No recommendations produced.")
        return

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_recs).to_csv(out_path, index=False)
    print(f"\nWrote {len(all_recs)} recommendations to {out_path}")

    print("\nSuggested next runs (run from the backtest/ directory):")
    for fund, lookback, rank, method, cmd in commands:
        print(f"\n# {fund} lookback={lookback} rank={rank} [{method}]")
        print(cmd)


if __name__ == "__main__":
    main()
