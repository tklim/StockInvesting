"""Aggregate window-boundary transition diagnostics across runs.

Reads the per-run transition reports that backtest_stocks.py writes:

    backtest/outputs/funds/<FUND>/runs/<RUN_ID>/transition_report.csv

Each row is one walk-forward window boundary; the columns of interest are
`boundary_exit_count` (exits inside the first K bars of the window) and
`phantom_exit` (an exit that fired under the new window's thresholds but would
not have fired under the previous window's). This tool answers: how often are
trades artifacts of the offset-month parameter switch rather than the market?

Runs made before the diagnostics existed have no report and are skipped.

Usage:
    python backtest/analysis/transitions.py --fund MSFT
    python backtest/analysis/transitions.py --all-funds
    python backtest/analysis/transitions.py --fund MSFT --profile generic
"""
from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict

from sweep_data import FUNDS_DIR, _f, _i, discover_funds


def _truthy(value) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")


def report_paths(fund: str, funds_dir: str = FUNDS_DIR):
    runs_dir = os.path.join(funds_dir, fund, "runs")
    if not os.path.isdir(runs_dir):
        return []
    out = []
    for run_id in sorted(os.listdir(runs_dir)):
        path = os.path.join(runs_dir, run_id, "transition_report.csv")
        if os.path.exists(path):
            out.append(path)
    return out


def load_rows(fund: str, funds_dir: str = FUNDS_DIR, profile: str | None = None):
    rows = []
    for path in report_paths(fund, funds_dir):
        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if profile and row.get("strategy_profile", "") != profile:
                    continue
                row.setdefault("fund_group", fund)
                rows.append(row)
    return rows


def summarize(rows):
    """Aggregate by (fund, offset) -> transition stats."""
    cells = defaultdict(lambda: {
        "runs": set(), "windows": 0, "carried_in": 0,
        "boundary_windows": 0, "boundary_exits": 0,
        "phantom_windows": 0, "phantom_exits": 0,
        "jump_sum": 0.0, "policies": set(),
    })
    for row in rows:
        key = (row.get("fund_group", "?"), "%sM" % _i(row.get("offset_months"), 0))
        cell = cells[key]
        cell["runs"].add(row.get("run_id", ""))
        cell["windows"] += 1
        if (_f(row.get("incoming_position"), 0.0) or 0.0) > 0:
            cell["carried_in"] += 1
        boundary = _i(row.get("boundary_exit_count"), 0)
        phantom = _i(row.get("phantom_exit_count"), 0)
        cell["boundary_exits"] += boundary
        cell["phantom_exits"] += phantom
        if boundary:
            cell["boundary_windows"] += 1
        if _truthy(row.get("phantom_exit")):
            cell["phantom_windows"] += 1
        cell["jump_sum"] += _f(row.get("param_jump_distance"), 0.0) or 0.0
        policy = row.get("transition_policy", "")
        if policy:
            cell["policies"].add(policy)
    return cells


def check_data_vintages(rows):
    """Warn when pooled rows span more than one data vintage.

    Derived slice files roll forward silently, so two runs of the "same"
    configuration can sit in the history having traded different periods.
    Comparing them looks valid and is not -- this has invalidated three real
    A/B comparisons. Runs predating the fingerprint have a blank value and are
    reported separately rather than assumed to match.
    """
    by_fund = defaultdict(set)
    unknown = defaultdict(int)
    for row in rows:
        fund = row.get("fund_group", "?")
        fp = str(row.get("data_fingerprint", "")).strip()
        if fp:
            by_fund[fund].add(fp[:12])
        else:
            unknown[fund] += 1
    warned = False
    for fund in sorted(set(list(by_fund) + list(unknown))):
        prints = by_fund.get(fund, set())
        if len(prints) > 1:
            warned = True
            print("!! %s pools %d DATA VINTAGES (%s) -- runs below traded"
                  % (fund, len(prints), ", ".join(sorted(prints))))
            print("   different periods and are NOT directly comparable.")
        if unknown.get(fund):
            warned = True
            print("!! %s has %d run(s) with no data fingerprint (recorded before"
                  % (fund, unknown[fund]))
            print("   fingerprinting existed); their vintage cannot be verified.")
    if warned:
        print()


def print_report(cells):
    if not cells:
        print("No transition reports found. Only runs made after the transition")
        print("diagnostics were added produce transition_report.csv; re-run the")
        print("backtest to generate them.")
        return
    header = (
        "fund", "offset", "runs", "windows", "carried-in",
        "boundary win", "phantom win", "phantom exits", "avg param jump", "policy",
    )
    fmt = "%-8s %-7s %5s %8s %11s %13s %12s %14s %15s %-12s"
    print(fmt % header)
    print("-" * 116)
    for (fund, offset), cell in sorted(cells.items()):
        windows = cell["windows"]
        print(fmt % (
            fund, offset, len(cell["runs"]), windows, cell["carried_in"],
            "%d (%.0f%%)" % (cell["boundary_windows"],
                             100.0 * cell["boundary_windows"] / windows if windows else 0.0),
            "%d (%.0f%%)" % (cell["phantom_windows"],
                             100.0 * cell["phantom_windows"] / windows if windows else 0.0),
            cell["phantom_exits"],
            "%.3f" % (cell["jump_sum"] / windows if windows else 0.0),
            ",".join(sorted(cell["policies"])) or "none",
        ))
    print()
    print("boundary win = windows with any exit in the first bars after the")
    print("parameter switch; phantom win = windows where such an exit would not")
    print("have fired under the previous window's thresholds (SELL rows are")
    print("threshold-only approximations; the EMA regime gate is not re-simulated).")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fund", help="fund group, e.g. MSFT")
    parser.add_argument("--all-funds", action="store_true",
                        help="aggregate every fund that has transition reports")
    parser.add_argument("--profile", help="restrict to one strategy profile")
    args = parser.parse_args(argv)

    if not args.fund and not args.all_funds:
        parser.error("pass --fund <TICKER> or --all-funds")
    funds = discover_funds() if args.all_funds else [args.fund]

    rows = []
    for fund in funds:
        rows.extend(load_rows(fund, profile=args.profile))
    check_data_vintages(rows)
    print_report(summarize(rows))


if __name__ == "__main__":
    main()
