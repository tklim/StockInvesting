"""Decide empirically whether --ga-search-preset grid is worth 16x the compute of focused.

The GA seed is derived from mutation_rate and crossover_rate (backtest_stocks.py:1801),
so the 16-cell grid is 16 confounded random restarts rather than a hyperparameter sweep.
Picking the max of 16 in-sample scores may just be selecting on noise. The only honest
test is out-of-sample: run both presets over identical walk-forward windows and compare
period_excess_return_pct, paired window by window.

Usage:
    python backtest/compare_presets.py --run            # execute the paired sweep (long)
    python backtest/compare_presets.py --run --dry-run  # show the plan and exit
    python backtest/compare_presets.py                  # analyse whatever history exists

The sweep is resumable: combinations already present in backtest_window_history.csv are
skipped, so it can be interrupted and restarted.
"""
import argparse
import math
import subprocess
import sys
import time
from itertools import product

import numpy as np
import pandas as pd

from common import DATA_DIR, TUNINGS_DIR, fund_label_from_data_file

SCRIPT = "backtest_stocks.py"
WINDOW_HISTORY = TUNINGS_DIR / "backtest_window_history.csv"

# focused = 1 GA run per window; grid = 4 mutation rates x 4 crossover rates
# (backtest_stocks.py:1902). This ratio is the whole point of the comparison.
GRID_CELLS = 16
FOCUSED_CELLS = 1

PRIMARY_METRIC = "period_excess_return_pct"
SECONDARY_METRICS = ["period_sharpe", "period_max_dd_pct"]

# Identical config except ga_search_preset => a fair paired comparison.
PAIR_KEY = [
    "fund_label",
    "price_column",
    "strategy_profile",
    "lookback_years",
    "offset_months",
    "pop_ranges",
    "gen_ranges",
    "window_sequence",
]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="store_true",
                        help="Execute the paired sweep before analysing")
    parser.add_argument("--dry-run", action="store_true",
                        help="With --run, list the planned invocations and exit")
    parser.add_argument("--tickers", nargs="+", default=None,
                        help="Tickers to sweep (default: every CSV in backtest/data/)")
    parser.add_argument("--lookback-years", nargs="+", type=float, default=[2, 3],
                        help="Lookback values to sweep (default: 2 3)")
    parser.add_argument("--offset-months", nargs="+", type=int, default=[6, 12],
                        help="Offset values to sweep (default: 6 12)")
    parser.add_argument("--pop", type=int, default=10, help="GA population (default: 10)")
    parser.add_argument("--gen", type=int, default=10, help="GA generations (default: 10)")
    parser.add_argument("--price-column", default="Adj Close")
    parser.add_argument("--strategy-profile", default="generic")
    parser.add_argument("--force", action="store_true",
                        help="Re-run combinations already present in the window history")
    return parser.parse_args()


# --------------------------------------------------------------------------- sweep


def discover_tickers():
    return sorted(path.stem for path in DATA_DIR.glob("*.csv"))


def load_window_history():
    if not WINDOW_HISTORY.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(WINDOW_HISTORY)
    except PermissionError:
        sys.exit(f"Cannot read {WINDOW_HISTORY} (locked - close it in Excel and retry).")


def already_run(history, ticker, lookback, offset, preset, args):
    """True when this exact configuration already produced windows."""
    if history.empty or args.force:
        return False
    match = (
        (history["fund_label"] == fund_label_from_data_file(f"{ticker}.csv"))
        & (np.isclose(history["lookback_years"], lookback))
        & (history["offset_months"] == offset)
        & (history["ga_search_preset"] == preset)
        & (history["pop_ranges"] == args.pop)
        & (history["gen_ranges"] == args.gen)
        & (history["price_column"] == args.price_column)
        & (history["strategy_profile"] == args.strategy_profile)
    )
    return bool(match.any())


def build_command(ticker, lookback, offset, preset, args):
    return [
        sys.executable,
        str(DATA_DIR.parent / SCRIPT),
        "--data-file", f"{ticker}.csv",
        "--lookback-years", str(lookback),
        "--offset-months", str(offset),
        "--pop_ranges", str(args.pop),
        "--gen_ranges", str(args.gen),
        "--ga-search-preset", preset,
        "--price-column", args.price_column,
        "--strategy-profile", args.strategy_profile,
        # focused forces this on internally; set it for grid so search breadth is the
        # only difference between the two arms.
        "--reuse-tuned-params",
    ]


def run_sweep(args):
    tickers = args.tickers or discover_tickers()
    if not tickers:
        sys.exit(f"No ticker CSVs found in {DATA_DIR}.")

    history = load_window_history()
    planned, skipped = [], 0
    # focused first: it is 16x cheaper, so an interrupted sweep still leaves a usable arm.
    for preset in ("focused", "grid"):
        for ticker, lookback, offset in product(tickers, args.lookback_years, args.offset_months):
            if already_run(history, ticker, lookback, offset, preset, args):
                skipped += 1
                continue
            planned.append((ticker, lookback, offset, preset))

    grid_runs = sum(1 for p in planned if p[3] == "grid")
    focused_runs = len(planned) - grid_runs
    ga_units = grid_runs * GRID_CELLS + focused_runs * FOCUSED_CELLS

    print(f"Tickers:   {len(tickers)} ({', '.join(tickers)})")
    print(f"Lookbacks: {args.lookback_years}   Offsets: {args.offset_months}")
    print(f"Planned:   {len(planned)} runs ({focused_runs} focused + {grid_runs} grid)")
    print(f"Skipped:   {skipped} already in window history (use --force to redo)")
    print(f"Cost:      ~{ga_units} GA optimisations per walk-forward window")
    print(f"           grid arm is {GRID_CELLS}x focused - expect it to dominate wall clock\n")

    if args.dry_run:
        for ticker, lookback, offset, preset in planned:
            print(f"  {preset:8s} {ticker:6s} lookback={lookback} offset={offset}")
        return

    started = time.time()
    failures = []
    for index, (ticker, lookback, offset, preset) in enumerate(planned, start=1):
        label = f"[{index}/{len(planned)}] {preset:8s} {ticker:6s} {lookback}Y/{offset}M"
        run_started = time.time()
        result = subprocess.run(build_command(ticker, lookback, offset, preset, args),
                                capture_output=True, text=True)
        elapsed = time.time() - run_started
        if result.returncode == 0:
            print(f"{label}  ok  {elapsed:6.1f}s")
        else:
            failures.append((ticker, lookback, offset, preset))
            tail = (result.stderr or result.stdout).strip().splitlines()
            print(f"{label}  FAILED ({elapsed:.1f}s): {tail[-1] if tail else 'no output'}")

    print(f"\nSweep finished in {(time.time() - started) / 60:.1f} min, "
          f"{len(failures)} failure(s).")
    for failure in failures:
        print(f"  failed: {failure}")


# ------------------------------------------------------------------------ analysis


def build_pairs(history, metric=PRIMARY_METRIC):
    """Inner-join grid against focused on identical config + window."""
    needed = set(PAIR_KEY + ["ga_search_preset", metric])
    missing = needed - set(history.columns)
    if missing:
        sys.exit(f"Window history is missing columns: {sorted(missing)}")

    usable = history.dropna(subset=[metric]).copy()
    arms = {}
    for preset in ("grid", "focused"):
        arm = usable[usable["ga_search_preset"] == preset]
        # A config can be re-run; seeds are deterministic, so duplicates are identical.
        arm = arm.drop_duplicates(subset=PAIR_KEY, keep="last")
        arms[preset] = arm[PAIR_KEY + [metric]].rename(columns={metric: preset})

    pairs = arms["grid"].merge(arms["focused"], on=PAIR_KEY, how="inner")
    pairs["diff"] = pairs["grid"] - pairs["focused"]
    return pairs


def bootstrap_ci(values, iterations=20000, alpha=0.05, seed=0):
    rng = np.random.default_rng(seed)
    values = np.asarray(values, dtype=float)
    draws = rng.choice(values, size=(iterations, values.size), replace=True).mean(axis=1)
    return np.quantile(draws, alpha / 2), np.quantile(draws, 1 - alpha / 2)


def sign_test_p(values):
    """Exact two-sided sign test; no scipy dependency."""
    values = np.asarray(values, dtype=float)
    positive = int((values > 0).sum())
    negative = int((values < 0).sum())
    trials = positive + negative
    if trials == 0:
        return 1.0
    smaller = min(positive, negative)
    tail = sum(math.comb(trials, k) for k in range(smaller + 1)) / (2 ** trials)
    return min(1.0, 2 * tail)


def describe(pairs, metric, higher_is_better=True):
    diffs = pairs["diff"].to_numpy(dtype=float)
    n = diffs.size
    mean = diffs.mean()
    low, high = bootstrap_ci(diffs)
    p_value = sign_test_p(diffs)
    wins = int((diffs > 0).sum())

    print(f"  paired windows      {n}")
    print(f"  grid mean           {pairs['grid'].mean():+.3f}")
    print(f"  focused mean        {pairs['focused'].mean():+.3f}")
    print(f"  mean difference     {mean:+.3f}  (grid - focused)")
    print(f"  95% bootstrap CI    [{low:+.3f}, {high:+.3f}]")
    print(f"  grid wins           {wins}/{n} windows ({100 * wins / n:.0f}%)")
    print(f"  sign test p         {p_value:.3f}")
    return {"n": n, "mean": mean, "low": low, "high": high, "p": p_value,
            "higher_is_better": higher_is_better}


def verdict(stats):
    n, mean, low, high = stats["n"], stats["mean"], stats["low"], stats["high"]
    significant = low > 0 or high < 0

    print("\n" + "=" * 72)
    print("VERDICT")
    print("=" * 72)

    if n < 20:
        print(f"INCONCLUSIVE - only {n} paired windows. Run the sweep over more tickers")
        print("and lookback/offset combinations before drawing a conclusion.")
        if not significant:
            print("\nOn the evidence so far there is no measurable grid advantage, but the")
            print("sample is too small to act on.")
        return

    if not significant:
        print(f"NO MEASURABLE BENEFIT. The 95% CI [{low:+.3f}, {high:+.3f}] includes zero")
        print(f"across {n} paired windows, so grid's extra {GRID_CELLS}x compute buys no")
        print("detectable out-of-sample excess return.")
        print("\n  => Switch to --ga-search-preset focused. Same expected result, ~16x faster.")
        print("     In run10a.bat / run10b.bat change -GaSearchPreset grid to focused.")
    elif mean > 0:
        print(f"GRID IS BETTER by {mean:+.3f} pp of out-of-sample excess return per window")
        print(f"(95% CI [{low:+.3f}, {high:+.3f}], n={n}).")
        print(f"\n  => Keep grid, but note it costs {GRID_CELLS}x. Worth {mean:+.3f} pp/window?")
    else:
        print(f"FOCUSED IS BETTER by {-mean:.3f} pp per window (95% CI [{low:+.3f}, {high:+.3f}],")
        print(f"n={n}). Grid's max-of-{GRID_CELLS} selection is actively overfitting.")
        print("\n  => Switch to focused: cheaper AND better out of sample.")


def analyse(args):
    history = load_window_history()
    if history.empty:
        sys.exit("No window history yet. Run with --run first.")

    print("=" * 72)
    print(f"GRID vs FOCUSED - out-of-sample comparison ({PRIMARY_METRIC})")
    print("=" * 72)

    pairs = build_pairs(history, PRIMARY_METRIC)
    if pairs.empty:
        counts = history["ga_search_preset"].value_counts().to_dict()
        print(f"\nNo paired windows. Preset counts in history: {counts}")
        print("Both presets must run on identical ticker/lookback/offset/pop/gen configs.")
        print("Run: python backtest/compare_presets.py --run")
        return

    stats = describe(pairs, PRIMARY_METRIC)

    print(f"\nPer-fund breakdown ({PRIMARY_METRIC}):")
    per_fund = pairs.groupby("fund_label").agg(
        windows=("diff", "size"),
        grid=("grid", "mean"),
        focused=("focused", "mean"),
        mean_diff=("diff", "mean"),
    ).round(3)
    print(per_fund.to_string())

    for metric in SECONDARY_METRICS:
        secondary = build_pairs(history, metric)
        if secondary.empty:
            continue
        direction = "lower is better" if "dd" in metric else "higher is better"
        print(f"\n{metric} ({direction}):")
        print(f"  grid {secondary['grid'].mean():+.3f}   "
              f"focused {secondary['focused'].mean():+.3f}   "
              f"diff {secondary['diff'].mean():+.3f}   n={len(secondary)}")

    verdict(stats)


def main():
    args = parse_args()
    if args.run:
        run_sweep(args)
        if args.dry_run:
            return
        print()
    analyse(args)


if __name__ == "__main__":
    main()
