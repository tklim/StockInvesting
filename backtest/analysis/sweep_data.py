"""Shared loader for backtest sweep run-histories.

Every analysis tool in this folder reads its data through here, so ticker
handling, slice/depth derivation and the leverage rule stay defined in exactly
one place.

Layout it expects (produced by backtest_stocks.py):

    backtest/outputs/funds/<FUND>/tunings/<FUND>-backtest_run_history.csv

`<FUND>` is the fund *group* (the bare ticker). History slices of the same
ticker -- `AAPL`, `AAPL-3Y`, `AAPL-4Y` -- all live in that one file and are
told apart by the `fund_slice_label` column.
"""
from __future__ import annotations

import csv
import os
import re
from datetime import date

# backtest/analysis/ -> backtest/outputs/
_HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.normpath(os.path.join(_HERE, os.pardir, "outputs"))
FUNDS_DIR = os.path.join(OUTPUTS_DIR, "funds")

# Runs whose exposure exceeds this are disqualified: the strategy may never
# invest more than 1.0x buy & hold, so a "win" bought with leverage is not a win.
MAX_EXPOSURE = 1.0


def _f(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value, default=0):
    v = _f(value)
    return default if v is None else int(v)


def discover_funds(funds_dir: str = FUNDS_DIR):
    """Return the fund groups that actually have a run history, sorted."""
    out = []
    if not os.path.isdir(funds_dir):
        return out
    for name in sorted(os.listdir(funds_dir)):
        if name.startswith("_"):  # _legacy_backup_*, _backfill_backup_*
            continue
        if os.path.exists(history_path(name, funds_dir)):
            out.append(name)
    return out


def history_path(fund: str, funds_dir: str = FUNDS_DIR) -> str:
    return os.path.join(funds_dir, fund, "tunings", "%s-backtest_run_history.csv" % fund)


def batch_label(pop: int, gen: int) -> str:
    """Name the GA configuration.

    The run*.bat sweeps all use generations = population / 2 (run4 = 4/2,
    run20 = 20/10), so those get their familiar `runN` name. Anything else is
    an ad-hoc configuration and is shown as `pop/gen` so it never masquerades
    as one of the standard batches.
    """
    if gen > 0 and pop == gen * 2:
        return "run%d" % pop
    return "%d/%d" % (pop, gen)


def depth_years(depth_lbl: str):
    """Numeric years from a depth label like '5Y'. None if unparseable."""
    m = re.match(r"(\d+)Y$", str(depth_lbl))
    return int(m.group(1)) if m else None


def depth_label(slice_label: str, data_start: str, data_end: str) -> str:
    """How much price history the run saw, as a short label like '3Y' or '5Y'.

    A `-NY` suffix on the slice label is authoritative when present; otherwise
    the span is measured from the data range, so a fund with no slices still
    gets a meaningful depth bucket.
    """
    m = re.search(r"-(\d+)Y$", str(slice_label or ""), re.IGNORECASE)
    if m:
        return "%sY" % m.group(1)
    try:
        y0, m0, d0 = (int(x) for x in str(data_start)[:10].split("-"))
        y1, m1, d1 = (int(x) for x in str(data_end)[:10].split("-"))
        years = (date(y1, m1, d1) - date(y0, m0, d0)).days / 365.25
        return "%dY" % max(1, int(round(years)))
    except (ValueError, TypeError):
        return "?"


def load_runs(fund: str, funds_dir: str = FUNDS_DIR, include_degenerate: bool = False):
    """Load one fund's completed runs as normalized dicts.

    Degenerate runs -- an empty backtest window, which reports 0% for both the
    strategy and buy & hold -- are dropped unless asked for; they are artifacts
    of a lookback that consumes the whole file, not results.
    """
    path = history_path(fund, funds_dir)
    if not os.path.exists(path):
        raise FileNotFoundError("No run history for %r at %s" % (fund, path))

    runs = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("run_status") != "completed":
                continue
            adapt = _f(r.get("adaptive_return_pct"))
            bh = _f(r.get("buy_hold_return_pct"))
            exc_a = _f(r.get("excess_annualized_return_pct"))
            if adapt is None or bh is None or exc_a is None:
                continue
            if not include_degenerate and adapt == 0 and bh == 0:
                continue
            slice_label = r.get("fund_slice_label") or r.get("fund_label") or fund
            pop, gen = _i(r.get("pop_ranges")), _i(r.get("gen_ranges"))
            depth = depth_label(slice_label, r.get("data_start"), r.get("data_end"))
            dy = depth_years(depth)
            lb = _f(r.get("lookback_years"), 0.0)
            # "Running years": history depth minus lookback = the out-of-sample
            # test window the run is actually scored on. Verified against the
            # recorded backtest_start/backtest_end to within 0.01y. A run on a
            # short window is judged on less evidence, so its result is noisier
            # -- this is the single biggest comparability trap in the sweep.
            running = round(dy - lb, 2) if dy is not None else None
            runs.append({
                "run_id": r.get("run_id", ""),
                "fund": fund,
                "slice": slice_label,
                # Which strategy variant produced this run. Pooling profiles
                # silently blends incomparable experiments, so every tool that
                # reports an aggregate should either filter on this or say which
                # profiles went into the number.
                "profile": r.get("strategy_profile", "") or "unknown",
                "depth": depth,
                "depth_y": dy,
                "ry": running,
                "batch": batch_label(pop, gen),
                "pop": pop,
                "gen": gen,
                "budget": pop * gen,
                "lb": _f(r.get("lookback_years"), 0.0),
                "off": _i(r.get("offset_months")),
                "adaptA": round(_f(r.get("adaptive_annualized_return_pct"), 0.0), 2),
                "bhA": round(_f(r.get("buy_hold_annualized_return_pct"), 0.0), 2),
                "excA": round(exc_a, 2),
                "sharpe": round(_f(r.get("sharpe"), 0.0), 3),
                "dd": round(_f(r.get("max_dd_pct"), 0.0), 2),
                "exp": round(_f(r.get("last_exposure_multiplier"), 1.0) or 1.0, 2),
                "trades": _i(r.get("trade_count")),
                "inv": round(_f(r.get("time_invested_pct"), 0.0), 1),
                "start": str(r.get("backtest_start") or "")[:10],
                "end": str(r.get("backtest_end") or "")[:10],
            })
    return runs


def unleveraged(runs):
    """Only the runs that honour the no-leverage rule."""
    return [d for d in runs if d["exp"] <= MAX_EXPOSURE]


def filter_profile(runs, profile):
    """Restrict to one strategy profile. `None` or 'all' keeps everything."""
    if not profile or profile == "all":
        return runs
    return [d for d in runs if d["profile"] == profile]


def profile_mix(runs):
    """Ordered (profile, count) pairs, most common first."""
    counts = {}
    for d in runs:
        counts[d["profile"]] = counts.get(d["profile"], 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def median(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def cell_key(run):
    """The parameter cell a run belongs to: depth + lookback + offset."""
    return (run["depth"], run["lb"], run["off"])


def group_by(runs, keyfunc):
    out = {}
    for r in runs:
        out.setdefault(keyfunc(r), []).append(r)
    return out


def depth_sort_key(label):
    m = re.match(r"(\d+)Y$", str(label))
    return (0, int(m.group(1))) if m else (1, 0)


def sorted_depths(runs):
    return sorted({d["depth"] for d in runs}, key=depth_sort_key)


def sorted_batches(runs):
    """Standard runN batches in population order, ad-hoc configs after."""
    def key(b):
        m = re.match(r"run(\d+)$", b)
        return (0, int(m.group(1)), "") if m else (1, 0, b)
    return sorted({d["batch"] for d in runs}, key=key)
