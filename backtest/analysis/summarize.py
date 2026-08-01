"""Console summary of a fund's parameter sweep.

    python backtest/analysis/summarize.py --fund AAPL
    python backtest/analysis/summarize.py --fund MSFT --top 15
    python backtest/analysis/summarize.py --all-funds

Reports the leaderboard, the per-dimension medians, and -- most importantly --
the spread of repeated runs within each parameter cell, which is what separates
a reproducible configuration from a lucky seed.
"""
from __future__ import annotations

import argparse

import sweep_data as sd


def fmt(v, d=2):
    return ("+" if v >= 0 else "") + ("%." + str(d) + "f") % v


def section(title):
    print()
    print(title)
    print("-" * len(title))


def report(fund, top_n=12, include_leveraged=False, profile=None):
    runs = sd.load_runs(fund)
    if not runs:
        print("%s: no completed runs." % fund)
        return
    available = sd.profile_mix(runs)
    runs = sd.filter_profile(runs, profile)
    if not runs:
        print("%s: no runs for profile %r. Available: %s"
              % (fund, profile, ", ".join("%s (%d)" % p for p in available)))
        return
    total = len(runs)
    lev = [d for d in runs if d["exp"] > sd.MAX_EXPOSURE]
    data = runs if include_leveraged else sd.unleveraged(runs)
    if not data:
        print("%s: all %d runs are leveraged; pass --include-leveraged to see them." % (fund, total))
        return

    print()
    print("=" * 78)
    print("%s  --  %d completed runs (%d leveraged%s)"
          % (fund, total, len(lev), "" if include_leveraged else ", excluded"))
    # Never let a blended aggregate pass as a single experiment.
    mix = sd.profile_mix(data)
    if profile and profile != "all":
        print("profile filter      : %s" % profile)
    elif len(mix) > 1:
        print("!! POOLED across %d profiles: %s" % (len(mix), ", ".join("%s (%d)" % p for p in mix)))
        print("   These are different experiments -- pass --profile <name> to separate them.")
    else:
        print("profile             : %s" % mix[0][0])
    print("=" * 78)

    pos = [d for d in data if d["excA"] > 0]
    med = sd.median([d["excA"] for d in data])
    print("runs analysed      : %d" % len(data))
    print("beat buy & hold    : %d (%.1f%%)" % (len(pos), 100.0 * len(pos) / len(data) if data else 0))
    print("median excess ann. : %s%%" % (fmt(med) if med is not None else "n/a"))

    section("Top %d by excess annualized return" % top_n)
    print("  %-4s %-7s %-6s %-5s %9s %9s %7s %7s %7s %6s"
          % ("depth", "batch", "lookbk", "off", "excess", "strategy", "B&H", "sharpe", "maxDD", "trades"))
    for d in sorted(data, key=lambda x: -x["excA"])[:top_n]:
        print("  %-4s %-7s %-6s %-5s %9s %9.2f %7.2f %7.2f %7.2f %6d"
              % (d["depth"], d["batch"], "%gY" % d["lb"], "%dM" % d["off"],
                 fmt(d["excA"]), d["adaptA"], d["bhA"], d["sharpe"], d["dd"], d["trades"]))

    for label, key, fmt_lvl in (
        ("Batch (GA population/generations)", "batch", str),
        ("History depth", "depth", str),
        ("Lookback", "lb", lambda v: "%gY" % v),
        ("Offset", "off", lambda v: "%dM" % v),
    ):
        section("Median excess by %s" % label.lower())
        groups = sd.group_by(data, lambda d, k=key: d[k])
        order = sorted(groups, key=lambda v: -(sd.median([x["excA"] for x in groups[v]]) or 0))
        for lvl in order:
            g = groups[lvl]
            m = sd.median([x["excA"] for x in g])
            best = max(x["excA"] for x in g)
            flag = "  <- few runs" if len(g) < 3 else ""
            print("  %-10s median %8s   best %8s   n=%-4d%s"
                  % (fmt_lvl(lvl), fmt(m), fmt(best), len(g), flag))

    section("Reproducibility: spread within each cell (>=3 runs)")
    cells = {k: v for k, v in sd.group_by(data, sd.cell_key).items() if len(v) >= 3}
    if not cells:
        print("  No cell has three or more runs yet -- repeat some configurations")
        print("  before drawing conclusions from any single result.")
    else:
        print("  %-16s %8s %8s %8s %7s %6s"
              % ("cell", "median", "best", "worst", "spread", "wins"))
        ranked = sorted(cells, key=lambda k: -(sd.median([x["excA"] for x in cells[k]]) or 0))
        for k in ranked[:top_n]:
            v = [x["excA"] for x in cells[k]]
            npos = sum(1 for x in v if x > 0)
            cell = "%s %gY/%dM" % (k[0], k[1], k[2])
            print("  %-16s %8s %8s %8s %7.1f %3d/%-3d"
                  % (cell, fmt(sd.median(v)), fmt(max(v)), fmt(min(v)),
                     max(v) - min(v), npos, len(v)))
        best_cell = ranked[0]
        v = [x["excA"] for x in cells[best_cell]]
        npos = sum(1 for x in v if x > 0)
        print()
        print("  Best cell %s %gY/%dM: %d of %d runs beat buy & hold, spread %.1f points."
              % (best_cell[0], best_cell[1], best_cell[2], npos, len(v), max(v) - min(v)))
        if 0 < npos < len(v):
            print("  Mixed outcomes at identical settings -- treat this as a seed-stability")
            print("  question, and repeat it across seeds before trusting the best number.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fund", help="fund group / ticker, e.g. AAPL")
    ap.add_argument("--all-funds", action="store_true", help="report every fund found")
    ap.add_argument("--top", type=int, default=12, help="rows per ranked list (default 12)")
    ap.add_argument("--include-leveraged", action="store_true",
                    help="include runs with exposure above 1.0x (disqualified by default)")
    ap.add_argument("--profile", default=None,
                    help="restrict to one strategy profile, e.g. generic-bh-reachable. "
                         "Omit to pool (the header will warn when more than one is present)")
    ap.add_argument("--funds-dir", default=sd.FUNDS_DIR)
    args = ap.parse_args()

    available = sd.discover_funds(args.funds_dir)
    if args.all_funds:
        targets = available
    elif args.fund:
        targets = [args.fund]
    else:
        ap.error("give --fund <TICKER> or --all-funds. Available: %s" % ", ".join(available))

    for fund in targets:
        try:
            report(fund, args.top, args.include_leveraged, args.profile)
        except FileNotFoundError as exc:
            print(exc)
            print("Available funds: %s" % ", ".join(available))


if __name__ == "__main__":
    main()
