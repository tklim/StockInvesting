# Sweep analysis toolkit

Ticker-agnostic tools for reading the parameter-sweep results that
`backtest_stocks.py` writes. Point them at any fund group and they work the
same way.

```bash
# console report for one ticker
python backtest/analysis/summarize.py --fund AAPL

# interactive HTML dashboard, opened in the browser
python backtest/analysis/dashboard.py --fund MSFT --open

# one strategy profile only -- required when comparing profiles
python backtest/analysis/summarize.py --fund NVDA --profile generic-bh-reachable
python backtest/analysis/dashboard.py --fund NVDA --profile generic-bh-reachable

# everything, for every ticker that has results
python backtest/analysis/summarize.py --all-funds
python backtest/analysis/dashboard.py --all-funds
```

No third-party dependencies — standard library only. Run the commands from the
repo root, or from this folder; both work.

## Files

| File | What it does |
|---|---|
| `sweep_data.py` | Shared loader. Ticker handling, depth/slice derivation and the no-leverage rule live here and nowhere else. |
| `summarize.py` | Console report: leaderboard, per-dimension medians, per-cell reproducibility. |
| `dashboard.py` | Self-contained HTML dashboard, seven annotated charts. |
| `transitions.py` | Window-boundary diagnostics: how often exits right after an offset-month parameter switch are artifacts of the switch ("phantom exits") rather than the market. Reads `runs/*/transition_report.csv`; only runs made after the diagnostics were added have one. |

Dashboards are written to
`backtest/outputs/funds/<FUND>/<FUND>-sweep-dashboard.html` — a single file with
no external assets, so it opens offline and can be emailed as-is.

## Where the data comes from

```
backtest/outputs/funds/<FUND>/tunings/<FUND>-backtest_run_history.csv
```

`<FUND>` is the fund **group** (the bare ticker). History slices of the same
ticker — `AAPL`, `AAPL-3Y`, `AAPL-4Y` — all live in that one file and are told
apart by the `fund_slice_label` column. A new ticker needs no configuration:
run the backtest, then run these tools.

## Conventions these tools apply

**Excess annualized return is the headline metric.** Strategy annualized minus
buy & hold annualized over the same window. Absolute return can't be compared
across history depths or tickers; excess return can.

**Leverage is disqualified.** Runs with `last_exposure_multiplier > 1.0` are
excluded by default (`--include-leveraged` to override). A win bought with
leverage is not a win the strategy is allowed to take.

**Degenerate runs are dropped.** A lookback equal to the history depth leaves no
out-of-sample period; those runs complete with an empty window and report 0% for
both strategy and benchmark. They are artifacts, not results.

**Batch naming.** The `run*.bat` sweeps all use generations = population / 2, so
those are shown as `run4`, `run20`, and so on. Any other pop/gen pair is shown
as `pop/gen` so an ad-hoc run never masquerades as a standard batch.

**Profiles are separate experiments.** A ticker's history accumulates runs from
different `--strategy-profile` values, and their medians are not comparable.
Both tools print the profile mix and shout `!! POOLED across N profiles` when
more than one is present; pass `--profile <name>` to isolate one.
`dashboard.py --profile` writes `<FUND>-<profile>-sweep-dashboard.html` so it
never overwrites the pooled build.

**Depth labels** come from the `-NY` slice suffix when present, otherwise from
the actual span of the data file. A fund with no slices still gets a real depth
bucket.

**Running years = history depth − lookback.** The out-of-sample window a run is
actually scored on, and the sweep's biggest comparability trap. A 4Y file with a
3Y lookback is judged on *one* year; a 5Y file with a 1Y lookback is judged on
four. The identity was verified against the recorded `backtest_start` /
`backtest_end` on every AAPL combo and agrees to within 0.01 years. Runs with
0 running years produce an empty window and are the degenerate rows dropped
above.

## Reading the dashboard

Filters at the top scope every chart at once. The **Median run / Best run**
toggle is the one that matters: median answers *is this region reliably good*,
best answers *what is the ceiling here*. They disagree wherever one lucky seed
sits in an otherwise poor cell — which is the single most common way to fool
yourself with this data.

1. **Heatmaps** — lookback × offset, split by history depth. Where the wins are.
2. **Dimension effects** — median at each level. Flat bars mean no knob to turn.
3. **Running years** — how much out-of-sample evidence each run rests on. Check
   whether the wins cluster in the shortest bucket, and whether the median holds
   up as the window lengthens; an edge that fades with more evidence is not one.
4. **Correlation strength** — Spearman rho per factor. Watch *GA budget*: near
   zero means more compute buys consistency at a mediocre value, not a better
   result. The rho is pooled, so confirm anything interesting per-cell.
5. **Return vs risk** — the main scatter. Upper-left is what you want.
6. **Supporting scatters** — trade count, time invested, GA budget, Sharpe.
7. **Reproducibility** — every run inside each repeated cell. **Read this before
   trusting any single number.** Where the spread within a cell exceeds the gap
   between cells, ranking configurations by their best run is ranking luck.
8. **Table** — everything, sortable.

Each chart carries a Remarks block that recomputes from whatever is filtered, so
the commentary stays true for whichever ticker you point it at.

## A caution worth keeping in view

Excess return rewards a *weak benchmark* as much as a strong strategy. Across
the ten tickers swept so far, the median buy & hold return and the median excess
return are strongly negatively correlated: the strategy looks best precisely on
the names that went nowhere. Before concluding a ticker suits the strategy,
check what buy & hold actually did on it — a positive excess against a falling
benchmark is a defensive result, not a growth one.
