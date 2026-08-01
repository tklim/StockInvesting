"""Systematic backtest experiment harness.

Three subcommands drive a closed optimization loop:

  plan    Build a batch of run configurations (space-filling Sobol design,
          or recommendations from suggest_next_runs.py) into a queue CSV.
  run     Execute queued configurations via backtest_stocks.py, resumable,
          with a wall-clock budget. Results land in the shared run history.
  report  Join the queue against outputs/tunings/backtest_run_history.csv
          and summarize which configurations actually won.

The objective throughout is run-level (chained walk-forward) excess
annualized return vs buy & hold -- not the per-window GA fitness, which
is measured in-sample and inflated by annualizing 90-day windows.
"""

import argparse
import multiprocessing as mp
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from common import LockTimeout, file_lock

SCRIPT_DIR = Path(__file__).resolve().parent
BACKTEST_SCRIPT = SCRIPT_DIR / "backtest_stocks.py"
RUN_HISTORY = SCRIPT_DIR / "outputs" / "tunings" / "backtest_run_history.csv"
DEFAULT_QUEUE = SCRIPT_DIR / "outputs" / "tunings" / "experiment_queue.csv"

# Global GA search-space limits (mirrors backtest_stocks.py defaults) and the
# minimum width each swept bound must keep so the GA still has room to search.
BOUND_SPEC = {
    "short_ema": {"lo": 2, "hi": 60, "min_span": 6},
    "long_ema": {"lo": 30, "hi": 300, "min_span": 40},
    "rsi_oversold": {"lo": 10, "hi": 40, "min_span": 6},
    "rsi_overbought": {"lo": 60, "hi": 90, "min_span": 6},
}
WIDE_BASELINE = {
    "short_ema_min": 2, "short_ema_max": 60,
    "long_ema_min": 30, "long_ema_max": 300,
    "rsi_oversold_min": 10, "rsi_oversold_max": 40,
    "rsi_overbought_min": 60, "rsi_overbought_max": 90,
}

QUEUE_COLUMNS = [
    "experiment_id", "batch", "source", "fund_label", "data_dir",
    "lookback_years", "offset_months",
    "strategy_profile",
    "pop_ranges", "gen_ranges", "mutation_rate", "crossover_rate", "ga_seed",
    "short_ema_min", "short_ema_max", "long_ema_min", "long_ema_max",
    "rsi_oversold_min", "rsi_oversold_max", "rsi_overbought_min", "rsi_overbought_max",
    "status", "claimed_by", "claimed_at", "run_id", "duration_seconds",
    "adaptive_annualized_return_pct", "buy_hold_annualized_return_pct",
    "excess_annualized_return_pct", "sharpe", "max_dd_pct", "trade_count",
    "time_invested_pct", "error",
]
# Rows a worker has taken but not yet finished. Kept distinct from "pending"
# so a second worker never picks up in-flight work.
CLAIMED_STATUS = "running"
CONFIG_COLUMNS = [
    "fund_label", "data_dir", "lookback_years", "offset_months", "strategy_profile",
    "pop_ranges", "gen_ranges",
    "mutation_rate", "crossover_rate", "ga_seed",
    "short_ema_min", "short_ema_max", "long_ema_min", "long_ema_max",
    "rsi_oversold_min", "rsi_oversold_max", "rsi_overbought_min", "rsi_overbought_max",
]
RESULT_COLUMNS = [
    "adaptive_annualized_return_pct", "buy_hold_annualized_return_pct",
    "excess_annualized_return_pct", "sharpe", "max_dd_pct", "trade_count",
    "time_invested_pct",
]


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------

def sobol_bounds(n, seed):
    """Space-filling sample of (min, max) pairs for each swept bound.

    Samples a lower edge and a width rather than two independent edges, so
    every drawn pair is valid (min < max) and respects the minimum span.
    """
    # Imported lazily: only `plan` samples a design, but `run` spawns one
    # worker process per core and each would otherwise pay scipy's import
    # cost in memory for nothing. That overhead is enough to exhaust the
    # pagefile at high worker counts.
    from scipy.stats import qmc

    names = list(BOUND_SPEC)
    sampler = qmc.Sobol(d=2 * len(names), scramble=True, seed=seed)
    # Sobol' only keeps its balance properties at powers of two, so draw the
    # next power up and trim rather than requesting an arbitrary n.
    m = max(1, int(np.ceil(np.log2(max(n, 1)))))
    raw = sampler.random_base2(m)[:n]
    out = {}
    for i, name in enumerate(names):
        spec = BOUND_SPEC[name]
        lo_u, width_u = raw[:, 2 * i], raw[:, 2 * i + 1]
        span = spec["hi"] - spec["lo"]
        lo = spec["lo"] + lo_u * (span - spec["min_span"])
        max_width = spec["hi"] - lo
        width = spec["min_span"] + width_u * (max_width - spec["min_span"])
        out[f"{name}_min"] = np.round(lo).astype(int)
        out[f"{name}_max"] = np.round(lo + width).astype(int)
    return pd.DataFrame(out)


def replicate_across_seeds(rows, run_seeds):
    """Duplicate each row once per value in run_seeds, setting ga_seed on the copy.

    ga_seed drives the GA's own random draws inside backtest_stocks.py, so
    this is what turns a single-draw result into a robustness check -- a
    "best" configuration that only wins under one seed was never a real
    effect (see OPTIMIZATION_LOOP.md's seed guardrail). Every planning path
    must route its rows through this before returning them; a path that
    builds rows and returns them directly silently drops --run-seeds, which
    is exactly what happened to plan_from_recommendations before this helper
    was extracted out of plan_sobol.
    """
    replicated = []
    for row in rows:
        for seed in run_seeds:
            r = dict(row)
            r["ga_seed"] = seed
            replicated.append(r)
    return pd.DataFrame(replicated)


def plan_sobol(args):
    rng = np.random.default_rng(args.seed)
    # --pop/--gen default to None so --from-recommendations can detect "unset";
    # the design path wants concrete cheap-screening values.
    pop = args.pop if args.pop is not None else 4
    gen = args.gen if args.gen is not None else 2
    rows = []
    for fund in args.funds:
        for lookback in args.lookbacks:
            # per_group=0 means "no bound search, controls only" -- e.g. for a
            # multi-seed robustness check where narrowing bounds isn't the point.
            if args.per_group > 0:
                design = sobol_bounds(args.per_group, args.seed)
                for i in range(len(design)):
                    row = {
                        "source": "sobol",
                        "fund_label": fund,
                        "data_dir": args.data_dir,
                        "strategy_profile": args.strategy_profile,
                        "lookback_years": lookback,
                        "offset_months": int(rng.choice(args.offsets)),
                        "pop_ranges": pop,
                        "gen_ranges": gen,
                        "mutation_rate": float(rng.choice(args.mutations)),
                        "crossover_rate": float(rng.choice(args.crossovers)),
                    }
                    row.update(design.iloc[i].to_dict())
                    rows.append(row)
            # Wide-bounds control, one per offset, so every group has an
            # untuned reference point to measure narrowing against.
            for offset in args.offsets:
                control = {
                    "source": "control_wide",
                    "fund_label": fund,
                    "data_dir": args.data_dir,
                    "strategy_profile": args.strategy_profile,
                    "lookback_years": lookback,
                    "offset_months": int(offset),
                    "pop_ranges": pop,
                    "gen_ranges": gen,
                    "mutation_rate": args.mutations[0],
                    "crossover_rate": args.crossovers[0],
                }
                control.update(WIDE_BASELINE)
                rows.append(control)
    return replicate_across_seeds(rows, args.run_seeds)


def plan_from_recommendations(args):
    rec_path = Path(args.from_recommendations)
    recs = pd.read_csv(rec_path)
    if args.funds:
        recs = recs[recs["fund_label"].isin(args.funds)]
    if args.lookbacks:
        recs = recs[recs["lookback_years"].isin(args.lookbacks)]
    rows = []
    for _, r in recs.iterrows():
        rows.append({
            "source": f"recommend_rank{int(r['rank'])}",
            "fund_label": r["fund_label"],
            "data_dir": r.get("data_dir", args.data_dir),
            "strategy_profile": r.get("strategy_profile", args.strategy_profile),
            "lookback_years": r["lookback_years"],
            "offset_months": int(r["offset_months"]),
            # Honour the recommendation's own GA settings unless the caller
            # explicitly overrides them. These used to read args.pop/args.gen
            # first, but those carry non-None argparse defaults (4/2), so the
            # default silently discarded whatever GA strength the recommender
            # asked for -- every --from-recommendations batch quietly ran at
            # pop=4/gen=2 regardless of the CSV.
            "pop_ranges": args.pop if args.pop is not None else int(r.get("pop_ranges", 4)),
            "gen_ranges": args.gen if args.gen is not None else int(r.get("gen_ranges", 2)),
            "mutation_rate": float(r["mutation_rate"]),
            "crossover_rate": float(r["crossover_rate"]),
            "short_ema_min": int(r["short_ema_min"]), "short_ema_max": int(r["short_ema_max"]),
            "long_ema_min": int(r["long_ema_min"]), "long_ema_max": int(r["long_ema_max"]),
            "rsi_oversold_min": int(r["rsi_oversold_min"]),
            "rsi_oversold_max": int(r["rsi_oversold_max"]),
            "rsi_overbought_min": int(r["rsi_overbought_min"]),
            "rsi_overbought_max": int(r["rsi_overbought_max"]),
        })
    return replicate_across_seeds(rows, args.run_seeds)


def cmd_plan(args):
    queue_path = Path(args.queue)
    if args.from_recommendations:
        new = plan_from_recommendations(args)
    else:
        new = plan_sobol(args)

    queue_path.parent.mkdir(parents=True, exist_ok=True)
    # The read (existing rows + batch/experiment_id numbering), dedupe, and
    # write must happen as one unit under the lock. A `run` process can be
    # mid-batch, periodically reloading and rewriting this same file as its
    # own experiments complete; reading existing state outside the lock would
    # let a race window open between "we decided batch=N, experiment_id=X..."
    # here and the write below, risking a duplicate/colliding id.
    try:
        with file_lock(queue_path, on_message=print):
            existing = (pd.read_csv(queue_path) if queue_path.exists()
                       else pd.DataFrame(columns=QUEUE_COLUMNS))
            # Queues written before a column was added (e.g. strategy_profile)
            # simply lack it; materialize it as NA so dedupe keys line up.
            for col in QUEUE_COLUMNS:
                if col not in existing.columns:
                    existing[col] = None
            batch = 1 if existing.empty else int(existing["batch"].max()) + 1
            new["batch"] = batch
            new["status"] = "pending"
            # Randomize execution order. Controls would otherwise sit at the
            # end of each group and be the first thing dropped when a budget
            # cuts the batch short -- losing the very comparison the batch
            # exists to make. Shuffling also decorrelates results from
            # anything that drifts over the run, such as CPU contention.
            new = new.sample(frac=1, random_state=args.seed).reset_index(drop=True)
            start_id = 0 if existing.empty else int(existing["experiment_id"].max()) + 1
            new["experiment_id"] = range(start_id, start_id + len(new))

            if args.dedupe and not existing.empty:
                key = CONFIG_COLUMNS
                merged = new.merge(existing[key].drop_duplicates(), on=key,
                                   how="left", indicator=True)
                before = len(new)
                new = new[merged["_merge"].values == "left_only"]
                if before != len(new):
                    print(f"Dropped {before - len(new)} configurations already queued.")

            combined = pd.concat([existing, new], ignore_index=True)
            combined = combined.reindex(columns=QUEUE_COLUMNS)
            combined.to_csv(queue_path, index=False)
    except LockTimeout:
        print(f"Could not acquire lock on {queue_path} (another process is using it "
              f"-- likely `run` mid-batch). Try again in a moment.")
        return

    print(f"Batch {batch}: queued {len(new)} configurations "
          f"({len(combined)} total) -> {queue_path}")
    if len(new):
        print(new.groupby(["fund_label", "lookback_years"]).size().to_string())


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------

def profile_of(row):
    """Strategy profile for a queue row. Rows queued before the column existed
    load as NaN and must keep meaning what they meant when they ran: generic."""
    value = row.get("strategy_profile")
    if value is None or (isinstance(value, float) and np.isnan(value)) or str(value) == "":
        return "generic"
    return str(value)


def datadir_of(row):
    """Data directory for a queue row. Rows queued before the column existed
    load as NaN and must keep meaning what they meant when they ran: data/."""
    value = row.get("data_dir")
    if value is None or (isinstance(value, float) and np.isnan(value)) or str(value) == "":
        return "data"
    return str(value)


def build_command(row):
    lookback = float(row["lookback_years"])
    lookback_str = str(int(lookback)) if lookback.is_integer() else str(lookback)
    return [
        sys.executable, str(BACKTEST_SCRIPT),
        "--data-file", f"{datadir_of(row)}/{row['fund_label']}.csv",
        "--lookback-years", lookback_str,
        "--offset-months", str(int(row["offset_months"])),
        "--pop_ranges", str(int(row["pop_ranges"])),
        "--gen_ranges", str(int(row["gen_ranges"])),
        "--mutation-rates", str(row["mutation_rate"]),
        "--crossover-rates", str(row["crossover_rate"]),
        "--short-ema-bounds", str(int(row["short_ema_min"])), str(int(row["short_ema_max"])),
        "--long-ema-bounds", str(int(row["long_ema_min"])), str(int(row["long_ema_max"])),
        "--rsi-oversold-bounds", str(int(row["rsi_oversold_min"])), str(int(row["rsi_oversold_max"])),
        "--rsi-overbought-bounds", str(int(row["rsi_overbought_min"])), str(int(row["rsi_overbought_max"])),
        "--ga-seed", str(int(row["ga_seed"])),
        "--strategy-profile", profile_of(row),
        "--reuse-tuned-params",
    ]


def latest_run_row(row, started_after):
    """Newest completed run-history row matching this queue row's full
    configuration, started at/after the moment we launched the subprocess.

    Matching on fund + start time alone is not enough: with --workers > 1,
    several backtests of the same fund overlap, and each worker would grab
    whichever of them wrote its history row last -- three of twelve rows in
    the first parallel batch were cross-matched to another worker's result
    this way. Every config column the queue controls must participate in the
    match; seeds alone distinguish otherwise-identical replicate rows.
    """
    if not RUN_HISTORY.exists():
        return None
    try:
        hist = pd.read_csv(RUN_HISTORY)
    except (pd.errors.EmptyDataError, PermissionError):
        return None
    # fund_label holds the fund GROUP (AAPL), so it no longer separates a
    # data/AAPL.csv run from a data/AAPL-3Y.csv slice sweep running alongside it.
    # fund_slice_label carries the data-file label; queue rows always launch
    # <fund>.csv, so the queue's fund_label IS the slice for its own runs. Rows
    # written before the column existed keep fund_label's old slice value.
    if "fund_slice_label" in hist.columns:
        slice_labels = hist["fund_slice_label"].fillna(hist["fund_label"])
    else:
        slice_labels = hist["fund_label"]
    hist = hist[slice_labels == row["fund_label"]]
    if hist.empty:
        return None
    hist = hist[pd.to_datetime(hist["run_started_at"], errors="coerce") >= started_after]
    # Same fund can be backtested from different data directories (e.g. the
    # 5-year data/ vs the 20-year data_long/); the data_file path is what
    # distinguishes them, so a data_long run must not match a data/ history row.
    data_dir = datadir_of(row)
    if "data_file" in hist.columns:
        parent = hist["data_file"].astype(str).map(lambda p: Path(p).parent.name)
        hist = hist[parent == data_dir]
        if hist.empty:
            return None
    # History stores ga_seed as text because "deterministic" is a legal value.
    matchers = {
        "lookback_years": float(row["lookback_years"]),
        "offset_months": int(row["offset_months"]),
        "strategy_profile": profile_of(row),
        "ga_seed": str(int(row["ga_seed"])),
        "pop_ranges": int(row["pop_ranges"]),
        "gen_ranges": int(row["gen_ranges"]),
        "short_ema_min": int(row["short_ema_min"]), "short_ema_max": int(row["short_ema_max"]),
        "long_ema_min": int(row["long_ema_min"]), "long_ema_max": int(row["long_ema_max"]),
        "rsi_oversold_min": int(row["rsi_oversold_min"]),
        "rsi_oversold_max": int(row["rsi_oversold_max"]),
        "rsi_overbought_min": int(row["rsi_overbought_min"]),
        "rsi_overbought_max": int(row["rsi_overbought_max"]),
    }
    for col, want in matchers.items():
        if col not in hist.columns:
            continue
        if col in ("strategy_profile", "ga_seed"):
            hist = hist[hist[col].astype(str) == want]
        else:
            hist = hist[pd.to_numeric(hist[col], errors="coerce") == want]
        if hist.empty:
            return None
    return hist.sort_values("run_started_at").iloc[-1]


def _pin_object_dtypes(df):
    # Columns that are entirely empty load as float64; assigning strings into
    # them later would raise, so pin them to object up front.
    for col in ("run_id", "error", "status", "source", "claimed_by", "claimed_at"):
        if col not in df.columns:
            df[col] = None
        df[col] = df[col].astype(object)
    return df


def worker_token():
    return f"pid{os.getpid()}@{socket.gethostname()}"


def claim_next_pending(queue_path, batch=None, stale_minutes=180, owner=None):
    """Atomically take ownership of one pending row.

    Concurrent workers are the point here: `run` used to snapshot the pending
    list once and iterate it, so two runners would both execute the same
    rows. Instead each worker re-reads the queue under the lock, flips a
    single row to `running` with its own token, and writes back before doing
    any work -- so a row can only ever be handed out once.

    Rows stuck in `running` past `stale_minutes` are returned to `pending`:
    a worker killed mid-backtest (Ctrl-C, crash, machine sleep) would
    otherwise strand its row forever. The threshold must exceed the longest
    plausible backtest, or a slow-but-healthy run gets stolen and executed
    twice; at pop=15/gen=15 with short offsets that can be ~2 hours, hence
    the 180 minute default.

    Returns the claimed row, or None when there is genuinely nothing left.
    Raises LockTimeout so the caller can decide whether to retry.
    """
    with file_lock(queue_path, on_message=lambda _m: None):
        queue = pd.read_csv(queue_path)
        queue = _pin_object_dtypes(queue)

        now = pd.Timestamp.now()
        running = queue["status"] == CLAIMED_STATUS
        if running.any() and stale_minutes:
            claimed_at = pd.to_datetime(queue.loc[running, "claimed_at"], errors="coerce")
            cutoff = now - pd.Timedelta(minutes=stale_minutes)
            # NaT (never stamped) counts as stale -- it can only come from an
            # interrupted claim, so leaving it would strand the row.
            stale_ids = queue.loc[running].index[(claimed_at < cutoff) | claimed_at.isna()]
            if len(stale_ids):
                queue.loc[stale_ids, "status"] = "pending"
                queue.loc[stale_ids, ["claimed_by", "claimed_at"]] = None

        available = queue["status"] == "pending"
        if batch is not None:
            available &= queue["batch"] == batch
        if not available.any():
            queue.to_csv(queue_path, index=False)
            return None

        idx = queue.index[available][0]
        queue.loc[idx, "status"] = CLAIMED_STATUS
        queue.loc[idx, "claimed_by"] = owner or worker_token()
        queue.loc[idx, "claimed_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
        row = queue.loc[idx].copy()
        queue.to_csv(queue_path, index=False)
        return row


def update_queue_row(queue_path, experiment_id, updates):
    """Reload the queue fresh, patch one row by experiment_id, write back.

    A `plan` invocation can append rows to this same file while `run` is
    mid-batch. Patching a snapshot taken at startup and overwriting the whole
    file with it (the original design) silently erases any such concurrent
    additions on the next save. Reloading immediately before every write
    means those additions survive -- this is only ever patching the one row
    this process is responsible for, never asserting the rest of the file's
    contents. Returns the reloaded, patched DataFrame, or None if the lock
    could not be acquired (the result is lost for this round; --limit/--batch
    reruns of `run` will simply see the row still pending).
    """
    try:
        with file_lock(queue_path, on_message=print):
            queue = pd.read_csv(queue_path)
            queue = _pin_object_dtypes(queue)
            mask = queue["experiment_id"] == experiment_id
            if not mask.any():
                return queue
            for col, value in updates.items():
                queue.loc[mask, col] = value
            queue.to_csv(queue_path, index=False)
            return queue
    except LockTimeout:
        print(f"  (could not save result for exp {experiment_id}: lock timeout; "
              f"row stays pending)")
        return None


def execute_one(row, queue_path, args, tag=""):
    """Run one claimed configuration and record its outcome."""
    experiment_id = int(row["experiment_id"])
    cmd = build_command(row)
    label = (f"{tag}exp {experiment_id} "
             f"{row['fund_label']} {row['lookback_years']}Y/{int(row['offset_months'])}M "
             f"ema({int(row['short_ema_min'])}-{int(row['short_ema_max'])},"
             f"{int(row['long_ema_min'])}-{int(row['long_ema_max'])})")

    launched = pd.Timestamp(datetime.now()).floor("s")
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=SCRIPT_DIR, capture_output=True,
                              text=True, timeout=args.timeout_seconds)
        elapsed = time.time() - t0
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:]
            updates = {"status": "failed",
                       "error": tail[0][:300] if tail else f"exit {proc.returncode}"}
            print(f"{label}  FAILED ({elapsed:.0f}s)", flush=True)
        else:
            result = latest_run_row(row, launched)
            updates = {"status": "completed", "duration_seconds": round(elapsed, 1)}
            if result is not None:
                updates["run_id"] = result["run_id"]
                for col in RESULT_COLUMNS:
                    if col in result:
                        updates[col] = result[col]
                print(f"{label}  excess_ann={result['excess_annualized_return_pct']:+7.2f}%  "
                      f"ann={result['adaptive_annualized_return_pct']:+7.2f}%  "
                      f"({elapsed:.0f}s)", flush=True)
            else:
                updates["error"] = "no matching run-history row"
                print(f"{label}  done, result not matched ({elapsed:.0f}s)", flush=True)
    except subprocess.TimeoutExpired:
        updates = {"status": "timeout", "error": f"exceeded {args.timeout_seconds}s"}
        print(f"{label}  TIMEOUT (>{args.timeout_seconds}s)", flush=True)

    update_queue_row(queue_path, experiment_id, updates)


def worker_loop(args, worker_index=0):
    """Claim-and-execute until the queue drains or the budget runs out.

    Safe to run in many processes at once: every row is handed out exactly
    once by claim_next_pending()'s locked claim, so workers never duplicate
    each other's work.
    """
    queue_path = Path(args.queue)
    owner = worker_token()
    tag = f"[w{worker_index}] " if args.workers > 1 else ""
    deadline = time.time() + args.budget_minutes * 60 if args.budget_minutes else None
    executed = 0

    while True:
        if deadline and time.time() > deadline:
            print(f"{tag}budget reached; stopping (ran {executed}).", flush=True)
            break
        if args.limit and executed >= args.limit:
            print(f"{tag}limit of {args.limit} reached (ran {executed}).", flush=True)
            break
        try:
            row = claim_next_pending(queue_path, batch=args.batch,
                                     stale_minutes=args.stale_minutes, owner=owner)
        except LockTimeout:
            # Heavy contention between workers, not an error -- back off briefly.
            time.sleep(1.0)
            continue
        if row is None:
            print(f"{tag}no work left (ran {executed}).", flush=True)
            break
        execute_one(row, queue_path, args, tag=tag)
        executed += 1
    return executed


def cmd_run(args):
    queue_path = Path(args.queue)
    if not queue_path.exists():
        print(f"No queue at {queue_path}; run `plan` first.")
        return

    workers = max(1, args.workers)
    if workers == 1:
        worker_loop(args, 0)
    else:
        # Each worker is its own process because the actual work is a
        # subprocess.run of backtest_stocks.py; threads would serialise on
        # nothing useful and complicate Ctrl-C handling.
        print(f"Starting {workers} workers against {queue_path.name}\n", flush=True)
        procs = [mp.Process(target=worker_loop, args=(args, i)) for i in range(workers)]
        for p in procs:
            p.start()
        try:
            for p in procs:
                p.join()
        except KeyboardInterrupt:
            print("\nInterrupted; terminating workers "
                  "(claimed rows return to pending after --stale-minutes).")
            for p in procs:
                p.terminate()
            for p in procs:
                p.join()

    try:
        with file_lock(queue_path, on_message=print):
            queue = pd.read_csv(queue_path)
    except LockTimeout:
        print("Could not read final queue state (locked); run `report` for totals.")
        return

    counts = queue["status"].value_counts().to_dict()
    print(f"\nQueue: {counts.get('completed', 0)} completed, "
          f"{counts.get('pending', 0)} pending, "
          f"{counts.get(CLAIMED_STATUS, 0)} running, "
          f"{counts.get('failed', 0) + counts.get('timeout', 0)} failed/timeout")


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def cmd_report(args):
    queue = pd.read_csv(args.queue)
    done = queue[queue["status"] == "completed"].copy()
    if done.empty:
        print("No completed experiments yet.")
        return
    done["beat_bh"] = done["excess_annualized_return_pct"] > 0

    print("=== Per-group outcome ===")
    grp = done.groupby(["fund_label", "lookback_years"]).agg(
        n=("experiment_id", "size"),
        best_excess=("excess_annualized_return_pct", "max"),
        median_excess=("excess_annualized_return_pct", "median"),
        beat_bh=("beat_bh", "sum"),
        best_ann=("adaptive_annualized_return_pct", "max"),
    ).round(2)
    print(grp.to_string())

    print("\n=== Wide control vs swept bounds ===")
    src = done.assign(kind=np.where(done["source"] == "control_wide", "wide control", "swept"))
    print(src.groupby("kind")["excess_annualized_return_pct"]
          .agg(["count", "mean", "median", "max"]).round(2).to_string())

    print(f"\n=== Top {args.top} configurations by excess annualized return ===")
    cols = ["fund_label", "lookback_years", "offset_months", "source",
            "short_ema_min", "short_ema_max", "long_ema_min", "long_ema_max",
            "rsi_oversold_min", "rsi_oversold_max",
            "excess_annualized_return_pct", "adaptive_annualized_return_pct", "sharpe"]
    print(done.nlargest(args.top, "excess_annualized_return_pct")[cols]
          .round(2).to_string(index=False))

    print(f"\nOverall: {done['beat_bh'].sum()}/{len(done)} "
          f"({100 * done['beat_bh'].mean():.1f}%) beat buy & hold | "
          f"mean excess = {done['excess_annualized_return_pct'].mean():+.2f}%")

    report_regime(args)


def report_regime(args):
    """Relate strategy edge to how strongly buy & hold performed.

    A strategy that holds cash part of the time can only add value when being
    out of the market helps, so a strong benchmark is a headwind no parameter
    choice can overcome. Reads the full run history rather than just this
    queue, since the pattern needs every fund to be visible.
    """
    if not RUN_HISTORY.exists():
        return
    hist = pd.read_csv(RUN_HISTORY)
    hist = hist[hist.get("run_status") == "completed"].dropna(
        subset=["buy_hold_annualized_return_pct", "excess_annualized_return_pct"])
    if len(hist) < 10:
        return

    print("\n=== Regime check: strategy edge vs benchmark strength "
          f"(all {len(hist)} runs in history) ===")
    corr = hist["buy_hold_annualized_return_pct"].corr(
        hist["excess_annualized_return_pct"])
    by_fund = hist.groupby("fund_label").agg(
        runs=("run_id", "size"),
        buy_hold_ann=("buy_hold_annualized_return_pct", "mean"),
        mean_excess=("excess_annualized_return_pct", "mean"),
        best_excess=("excess_annualized_return_pct", "max"),
        beat_bh=("excess_annualized_return_pct", lambda s: int((s > 0).sum())),
    ).round(2).sort_values("buy_hold_ann")
    print(by_fund.to_string())
    print(f"\ncorr(buy & hold annualized, excess annualized) = {corr:+.3f}")
    print("Negative correlation means the stronger the benchmark, the worse the "
          "strategy does against it.\nA strong benchmark is a reliable "
          "disqualifier; a weak one is not a reliable qualifier (see TSLA).")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE), help="Experiment queue CSV")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plan", help="Queue a batch of run configurations")
    p.add_argument("--funds", nargs="+", default=["AAPL", "MSFT", "GOOGL"])
    p.add_argument("--lookbacks", nargs="+", type=float, default=[2.0, 3.0])
    p.add_argument("--offsets", nargs="+", type=int, default=[6, 12])
    p.add_argument("--per-group", type=int, default=8, help="Sobol points per (fund, lookback)")
    # Default None, not 4/2, so --from-recommendations can tell "caller said
    # nothing" (use the recommendation's own GA settings) apart from "caller
    # explicitly asked for 4". The Sobol path substitutes 4/2 itself.
    p.add_argument("--pop", type=int, default=None,
                   help="GA population (default: 4 for the Sobol/control design; "
                        "for --from-recommendations, defaults to whatever the "
                        "recommendation specifies)")
    p.add_argument("--gen", type=int, default=None,
                   help="GA generations (default: 2 for the Sobol/control design; "
                        "for --from-recommendations, defaults to whatever the "
                        "recommendation specifies)")
    p.add_argument("--mutations", nargs="+", type=float, default=[0.01, 0.05, 0.1])
    p.add_argument("--crossovers", nargs="+", type=float, default=[0.6, 0.7, 0.8])
    p.add_argument("--strategy-profile", default="generic",
                   help="backtest_stocks.py strategy profile for every queued row "
                        "(default: generic, matching all pre-existing history)")
    p.add_argument("--data-dir", default="data",
                   help="Directory (relative to backtest/) holding <fund>.csv price files "
                        "for every queued row, e.g. 'data' (5-year) or 'data_long' "
                        "(20-year, includes 2008/2020 crashes). Default: data")
    p.add_argument("--run-seeds", nargs="+", type=int, default=[42],
                   help="ga_seed value(s) for every queued row (Sobol, control, or "
                        "--from-recommendations alike); each row is replicated once per "
                        "seed so results can be checked for seed-to-seed stability "
                        "(default: 42)")
    p.add_argument("--seed", type=int, default=7, help="Design/sampling seed")
    p.add_argument("--from-recommendations", default=None,
                   help="Queue configs from a suggest_next_runs.py CSV instead of Sobol")
    p.add_argument("--dedupe", action="store_true", default=True)
    p.set_defaults(func=cmd_plan)

    r = sub.add_parser("run", help="Execute pending configurations")
    r.add_argument("--batch", type=int, default=None)
    r.add_argument("--limit", type=int, default=None,
                   help="Max configurations *per worker* (default: unlimited)")
    r.add_argument("--budget-minutes", type=float, default=None)
    r.add_argument("--timeout-seconds", type=int, default=900)
    r.add_argument("--workers", type=int, default=1,
                   help="Parallel workers. Each backtest is single-threaded, so up to "
                        "roughly one per physical core is useful; leave headroom if the "
                        "machine is doing anything else (default: 1)")
    r.add_argument("--stale-minutes", type=float, default=180,
                   help="Reclaim rows stuck in 'running' longer than this, so a killed "
                        "worker's row is not stranded. Must exceed the longest plausible "
                        "backtest or a slow healthy run gets executed twice (default: 180)")
    r.set_defaults(func=cmd_run)

    rep = sub.add_parser("report", help="Summarize completed experiments")
    rep.add_argument("--top", type=int, default=12)
    rep.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
