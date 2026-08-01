"""Audit and selectively rebuild the best legacy walk-forward run per ticker."""

from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

import final_backtest_from_summary as final_report
from walk_forward_replay import (
    load_replay_artifacts,
    sha256_file,
)


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = SCRIPT_DIR / "outputs"
TUNINGS_DIR = OUTPUTS_DIR / "tunings"
BATCHES_DIR = OUTPUTS_DIR / "rebuild_batches"
DEFAULT_RUN_HISTORY = TUNINGS_DIR / "backtest_run_history.csv"

TERMINAL_EXACT_STATUSES = {
    "already_replay_complete",
    "exact_replay",
}
LATEST_ELIGIBLE_STATUSES = {
    "source_unavailable",
    "exact_failed",
    "latest_run_failed",
    "latest_run_untracked",
    "latest_running",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Freeze one highest non-zero annualized-excess winner per ticker, "
            "recover exact legacy replay artifacts, and optionally launch "
            "lineage-tracked latest-data replacements."
        )
    )
    parser.add_argument(
        "--mode",
        choices=["audit", "exact", "both"],
        default="audit",
        help="audit is non-GA; exact persists recoverable artifacts; both also runs latest-data replacements",
    )
    parser.add_argument(
        "--summary-file",
        default=str(DEFAULT_RUN_HISTORY),
        help="Run-history CSV used to freeze the winners",
    )
    parser.add_argument(
        "--fund-label",
        action="append",
        default=[],
        help="Optional ticker filter; repeat for multiple tickers",
    )
    parser.add_argument(
        "--batch-id",
        help="Optional batch ID; defaults to the current timestamp",
    )
    parser.add_argument(
        "--resume-manifest",
        help="Resume an existing manifest instead of selecting winners again",
    )
    parser.add_argument(
        "--skip-dashboards",
        action="store_true",
        help="Do not regenerate the final dashboard cohort after exact/both execution",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable for isolated backtest and dashboard subprocesses",
    )
    return parser.parse_args()


def is_blank(value):
    return value is None or pd.isna(value) or not str(value).strip()


def truthy(value):
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def clean_text(value, default=""):
    return default if is_blank(value) else str(value).strip()


def safe_float(row, key, default=0.0):
    value = row.get(key, default)
    if is_blank(value):
        return float(default)
    return float(value)


def safe_int(row, key, default=0):
    return int(round(safe_float(row, key, default)))


def number_tokens(value, integer=False):
    text = clean_text(value)
    if text.lower() in {"", "nan", "none", "default", "default grid"}:
        return []
    tokens = [
        token
        for token in text.strip("[]()").replace(";", ",").replace("|", ",").split(",")
        if token.strip()
    ]
    if integer:
        return [str(int(round(float(token)))) for token in tokens]
    return [format(float(token), ".15g") for token in tokens]


def save_manifest(frame, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temp_path, index=False)
    temp_path.replace(path)


def mutable_frame(frame):
    """Avoid pandas 3 strict-dtype failures while updating CSV-backed status rows."""
    return frame.astype(object)


def process_is_running(pid):
    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            int(pid),
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        # Access denied still means the process exists but cannot be queried.
        return ctypes.windll.kernel32.GetLastError() == 5
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ProcessLookupError, ValueError):
        return False


@contextmanager
def batch_lock(manifest_path):
    """Prevent two resume commands from launching duplicate lineage runs."""
    lock_path = Path(str(manifest_path) + ".batch.lock")
    token = f"{os.getpid()}\n"
    while True:
        try:
            descriptor = os.open(
                str(lock_path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
            try:
                os.write(descriptor, token.encode("utf-8"))
            finally:
                os.close(descriptor)
            break
        except FileExistsError:
            try:
                owner = int(lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                owner = 0
            if owner and process_is_running(owner):
                raise RuntimeError(
                    f"Rebuild manifest is already active in PID {owner}: "
                    f"{manifest_path}"
                )
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
    try:
        yield
    finally:
        try:
            if lock_path.read_text(encoding="utf-8").strip() == str(os.getpid()):
                lock_path.unlink()
        except (FileNotFoundError, OSError):
            pass


def current_input_for_ticker(ticker, row):
    canonical = SCRIPT_DIR / "data" / f"{ticker}.csv"
    if canonical.exists():
        return canonical
    selected, _ = final_report.choose_data_file(row)
    return selected if selected and selected.exists() else None


def frozen_input_path(batch_dir, ticker):
    return Path(batch_dir) / "inputs" / f"{ticker}.csv"


def freeze_input(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or sha256_file(destination) != sha256_file(source):
        shutil.copy2(source, destination)
    return sha256_file(destination)


def exact_replay_audit(row, ticker, preferred_file):
    price_column = clean_text(row.get("price_column"), "Adj Close")
    strategy_profile = clean_text(row.get("strategy_profile"), "generic")
    initial_capital = safe_float(row, "initial_capital", 10000)
    metadata = final_report.artifact_metadata_for_row(row, ticker)
    if metadata:
        snapshot, schedule, _, _ = load_replay_artifacts(
            metadata,
            final_report.REPO_ROOT,
        )
        final_report.replay_once(
            snapshot,
            schedule,
            row,
            initial_capital,
            strategy_profile,
            price_column,
        )
        return {
            "status": "already_replay_complete",
            "exact_eligible": True,
            "exact_candidate": "archived snapshot",
            "schedule_window_count": len(schedule),
            "schedule_recovery_source": "parameter_schedule",
            "exact_error": "",
        }

    try:
        _, schedule, _, metadata, candidate = final_report.recover_legacy_replay(
            row,
            ticker,
            preferred_file,
            price_column,
            initial_capital,
            strategy_profile,
            persist=False,
        )
        return {
            "status": "exact_eligible",
            "exact_eligible": True,
            "exact_candidate": str(candidate),
            "schedule_window_count": len(schedule),
            "schedule_recovery_source": metadata.get(
                "schedule_recovery_source",
                "",
            ),
            "exact_error": "",
        }
    except Exception as exc:
        return {
            "status": "source_unavailable",
            "exact_eligible": False,
            "exact_candidate": "",
            "schedule_window_count": "",
            "schedule_recovery_source": "",
            "exact_error": str(exc),
        }


def select_winners(summary_path, fund_filters):
    raw = pd.read_csv(summary_path, low_memory=False)
    normalized = final_report.normalize_run_history(raw)
    selected = final_report.select_best_run_rows(
        normalized,
        fund_label=None,
        top_funds=0,
    )
    if fund_filters:
        wanted = {value.upper() for value in fund_filters}
        selected = selected[
            selected["canonical_fund_label"].astype(str).str.upper().isin(wanted)
        ].copy()
    return selected.sort_values("canonical_fund_label").reset_index(drop=True)


def create_manifest(summary_path, batch_id, fund_filters):
    selected = select_winners(summary_path, fund_filters)
    if selected.empty:
        raise ValueError("No eligible winner rows were selected")
    batch_dir = BATCHES_DIR / batch_id
    records = []
    for _, row in selected.iterrows():
        record = row.to_dict()
        ticker = clean_text(row.get("canonical_fund_label") or row.get("fund_label"))
        source = current_input_for_ticker(ticker, row)
        frozen_path = frozen_input_path(batch_dir, ticker)
        input_hash = ""
        input_error = ""
        if source is None:
            input_error = "No current ticker CSV is available"
        else:
            input_hash = freeze_input(source, frozen_path)

        audit = exact_replay_audit(row, ticker, frozen_path if frozen_path.exists() else source)
        record.update(
            {
                "rebuild_batch_id": batch_id,
                "ticker": ticker,
                "ranking_metric": "source_excess_annualized_return_pct",
                "ranking_value": row.get("source_excess_annualized_return_pct", ""),
                "selected_source_run_id": row.get("source_run_id", ""),
                "input_source_file": str(source) if source else "",
                "input_snapshot_file": str(frozen_path) if frozen_path.exists() else "",
                "input_snapshot_sha256": input_hash,
                "input_error": input_error,
                "rebuild_status": audit["status"],
                "exact_eligible": audit["exact_eligible"],
                "exact_candidate": audit["exact_candidate"],
                "exact_error": audit["exact_error"],
                "schedule_window_count": audit["schedule_window_count"],
                "schedule_recovery_source": audit["schedule_recovery_source"],
                "result_run_id": "",
                "result_error": "",
                "dashboard_status": "",
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        records.append(record)
    manifest = pd.DataFrame(records)
    manifest_path = batch_dir / "manifest.csv"
    save_manifest(manifest, manifest_path)
    return manifest, manifest_path


def history_paths_for_ticker(ticker, primary_path):
    paths = [Path(primary_path)]
    fund_path = (
        OUTPUTS_DIR
        / "funds"
        / ticker
        / "tunings"
        / f"{ticker}-backtest_run_history.csv"
    )
    if fund_path.exists():
        paths.append(fund_path)
    return paths


def update_exact_history(run_id, ticker, metadata, primary_path):
    updates = {
        **metadata,
        "replay_status": "exact_replay",
        "schedule_window_count": metadata.get("schedule_window_count", ""),
    }
    for path in history_paths_for_ticker(ticker, primary_path):
        history = mutable_frame(pd.read_csv(path, low_memory=False))
        if "run_id" not in history.columns:
            continue
        mask = history["run_id"].astype(str) == str(run_id)
        if not mask.any():
            continue
        for column, value in updates.items():
            if column not in history.columns:
                history[column] = pd.Series(
                    [None] * len(history),
                    index=history.index,
                    dtype=object,
                )
            else:
                history[column] = history[column].astype(object)
            history.loc[mask, column] = value
        final_report.bt.write_csv_with_lock_resilience(
            history,
            path,
            purpose=f"Exact replay metadata update ({ticker})",
        )


def update_legacy_replay_status(run_id, ticker, status, error, primary_path):
    updates = {
        "replay_status": status,
        "replay_error": error,
    }
    for path in history_paths_for_ticker(ticker, primary_path):
        history = mutable_frame(pd.read_csv(path, low_memory=False))
        if "run_id" not in history.columns:
            continue
        mask = history["run_id"].astype(str) == str(run_id)
        if not mask.any():
            continue
        for column, value in updates.items():
            if column not in history.columns:
                history[column] = pd.Series(
                    [None] * len(history),
                    index=history.index,
                    dtype=object,
                )
            else:
                history[column] = history[column].astype(object)
            history.loc[mask, column] = value
        final_report.bt.write_csv_with_lock_resilience(
            history,
            path,
            purpose=f"Legacy replay status update ({ticker})",
        )


def persist_exact_replay(row, ticker, primary_path):
    preferred = Path(clean_text(row.get("input_snapshot_file")))
    price_column = clean_text(row.get("price_column"), "Adj Close")
    strategy_profile = clean_text(row.get("strategy_profile"), "generic")
    initial_capital = safe_float(row, "initial_capital", 10000)
    _, schedule, _, metadata, candidate = final_report.recover_legacy_replay(
        row,
        ticker,
        preferred,
        price_column,
        initial_capital,
        strategy_profile,
        persist=True,
    )
    metadata["replay_status"] = "exact_replay"
    metadata["schedule_window_count"] = len(schedule)
    update_exact_history(
        clean_text(row.get("selected_source_run_id") or row.get("source_run_id")),
        ticker,
        metadata,
        primary_path,
    )
    return metadata, candidate


def add_pair(command, flag, row, lower_key, upper_key, integer=False):
    lower = row.get(lower_key)
    upper = row.get(upper_key)
    if is_blank(lower) or is_blank(upper):
        return
    if integer:
        values = [str(int(round(float(lower)))), str(int(round(float(upper))))]
    else:
        values = [format(float(lower), ".15g"), format(float(upper), ".15g")]
    command.extend([flag, *values])


def build_latest_command(row, python_executable):
    ticker = clean_text(row.get("ticker"))
    source_run_id = clean_text(
        row.get("selected_source_run_id") or row.get("source_run_id")
    )
    command = [
        python_executable,
        str(SCRIPT_DIR / "backtest_stocks.py"),
        "--data-file",
        clean_text(row.get("input_snapshot_file")),
        "--fund-group",
        ticker,
        "--lookback-years",
        format(safe_float(row, "lookback_years"), ".15g"),
        "--offset-months",
        str(safe_int(row, "offset_months")),
        "--initial-capital",
        format(safe_float(row, "initial_capital", 10000), ".15g"),
        "--price-column",
        clean_text(row.get("price_column"), "Adj Close"),
        "--strategy-profile",
        clean_text(row.get("strategy_profile"), "generic"),
        "--profile-override-preset",
        clean_text(row.get("profile_override_preset"), "default"),
        "--ga-search-preset",
        clean_text(row.get("ga_search_preset"), "grid"),
        "--rebuild-source-run-id",
        source_run_id,
        "--rebuild-batch-id",
        clean_text(row.get("rebuild_batch_id")),
        "--rebuild-mode",
        "latest_data",
    ]

    pop_values = number_tokens(row.get("pop_ranges"), integer=True) or ["10"]
    gen_values = number_tokens(row.get("gen_ranges"), integer=True) or pop_values
    command.extend(["--pop_ranges", *pop_values, "--gen_ranges", *gen_values])

    seed = clean_text(row.get("ga_seed"))
    if seed.lower() not in {"", "deterministic", "none", "nan"}:
        command.extend(["--ga-seed", str(int(round(float(seed))))])
    mutation_values = number_tokens(row.get("mutation_rates"))
    if mutation_values:
        command.extend(["--mutation-rates", *mutation_values])
    crossover_values = number_tokens(row.get("crossover_rates"))
    if crossover_values:
        command.extend(["--crossover-rates", *crossover_values])
    if truthy(row.get("reuse_tuned_params")):
        command.append("--reuse-tuned-params")

    add_pair(command, "--short-ema-bounds", row, "short_ema_min", "short_ema_max", True)
    add_pair(command, "--long-ema-bounds", row, "long_ema_min", "long_ema_max", True)
    add_pair(
        command,
        "--rsi-oversold-bounds",
        row,
        "rsi_oversold_min",
        "rsi_oversold_max",
        True,
    )
    add_pair(
        command,
        "--rsi-overbought-bounds",
        row,
        "rsi_overbought_min",
        "rsi_overbought_max",
        True,
    )
    add_pair(command, "--stop-loss-bounds", row, "stop_loss_min", "stop_loss_max")
    add_pair(command, "--cooldown-bounds", row, "cooldown_min", "cooldown_max", True)
    add_pair(
        command,
        "--drawdown-exit-bounds",
        row,
        "drawdown_exit_min",
        "drawdown_exit_max",
    )
    add_pair(
        command,
        "--reentry-rebound-bounds",
        row,
        "reentry_rebound_min",
        "reentry_rebound_max",
    )
    return command


def find_lineage_run(primary_path, batch_id, source_run_id):
    history = pd.read_csv(primary_path, low_memory=False)
    required = {"rebuild_batch_id", "rebuild_source_run_id", "run_id"}
    if not required.issubset(history.columns):
        return ""
    matches = history[
        (history["rebuild_batch_id"].astype(str) == str(batch_id))
        & (history["rebuild_source_run_id"].astype(str) == str(source_run_id))
    ]
    if matches.empty:
        return ""
    if "run_completed_at" in matches.columns:
        matches = matches.sort_values("run_completed_at")
    return str(matches.iloc[-1]["run_id"])


def verify_frozen_input(row):
    path = Path(clean_text(row.get("input_snapshot_file")))
    if not path.exists():
        raise FileNotFoundError(f"Frozen input is missing: {path}")
    expected = clean_text(row.get("input_snapshot_sha256"))
    actual = sha256_file(path)
    if expected and actual != expected:
        raise ValueError(f"Frozen input hash mismatch: {path}")


def execute_latest_run(row, python_executable, primary_path):
    verify_frozen_input(row)
    batch_id = clean_text(row.get("rebuild_batch_id"))
    source_run_id = clean_text(
        row.get("selected_source_run_id") or row.get("source_run_id")
    )
    existing = find_lineage_run(primary_path, batch_id, source_run_id)
    if existing:
        return existing
    command = build_latest_command(row, python_executable)
    completed = subprocess.run(command, cwd=SCRIPT_DIR, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Latest-data backtest exited with code {completed.returncode}"
        )
    result_run_id = find_lineage_run(primary_path, batch_id, source_run_id)
    if not result_run_id:
        raise RuntimeError(
            "Backtest completed but no lineage-matching run-history row was found"
        )
    return result_run_id


def build_dashboard_cohort(manifest, primary_path, batch_dir):
    history = pd.read_csv(primary_path, low_memory=False)
    selected_ids = []
    for _, row in manifest.iterrows():
        result_id = clean_text(row.get("result_run_id"))
        selected_ids.append(
            result_id
            or clean_text(
                row.get("selected_source_run_id") or row.get("source_run_id")
            )
        )
    cohort = history[history["run_id"].astype(str).isin(selected_ids)].copy()
    order = {run_id: index for index, run_id in enumerate(selected_ids)}
    cohort["_batch_order"] = cohort["run_id"].astype(str).map(order)
    cohort = cohort.sort_values("_batch_order").drop(columns=["_batch_order"])
    path = Path(batch_dir) / "dashboard_run_history.csv"
    cohort.to_csv(path, index=False)
    return path


def regenerate_dashboards(manifest, primary_path, batch_dir, python_executable):
    cohort_path = build_dashboard_cohort(manifest, primary_path, batch_dir)
    command = [
        python_executable,
        str(SCRIPT_DIR / "final_backtest_from_summary.py"),
        "--summary-file",
        str(cohort_path),
        "--top-funds",
        "0",
    ]
    completed = subprocess.run(command, cwd=SCRIPT_DIR, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Final dashboard regeneration exited with code {completed.returncode}"
        )
    return cohort_path


def print_manifest_summary(manifest, manifest_path):
    columns = [
        "ticker",
        "selected_source_run_id",
        "ranking_value",
        "rebuild_status",
        "schedule_window_count",
        "exact_candidate",
        "result_run_id",
    ]
    available = [column for column in columns if column in manifest.columns]
    print()
    print(manifest[available].to_string(index=False))
    print(f"\nManifest: {manifest_path}")


def run_batch(args):
    summary_path = Path(args.summary_file)
    if not summary_path.is_absolute():
        summary_path = SCRIPT_DIR / summary_path
    if args.resume_manifest:
        manifest_path = Path(args.resume_manifest)
        if not manifest_path.is_absolute():
            manifest_path = SCRIPT_DIR / manifest_path
        manifest = mutable_frame(pd.read_csv(manifest_path, low_memory=False))
        batch_dir = manifest_path.parent
    else:
        batch_id = args.batch_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        manifest, manifest_path = create_manifest(
            summary_path,
            batch_id,
            args.fund_label,
        )
        manifest = mutable_frame(manifest)
        batch_dir = manifest_path.parent

    with batch_lock(manifest_path):
        return execute_locked_batch(
            args,
            manifest,
            manifest_path,
            batch_dir,
            summary_path,
        )


def execute_locked_batch(args, manifest, manifest_path, batch_dir, summary_path):
    if args.mode == "audit":
        print_manifest_summary(manifest, manifest_path)
        return 0

    for index in manifest.index:
        row = manifest.loc[index]
        ticker = clean_text(row.get("ticker"))
        status = clean_text(row.get("rebuild_status"))
        if status == "already_replay_complete":
            metadata = final_report.artifact_metadata_for_row(row, ticker)
            if metadata:
                _, schedule, _, _ = load_replay_artifacts(
                    metadata,
                    final_report.REPO_ROOT,
                )
                metadata = {
                    **metadata,
                    "replay_schema_version": row.get(
                        "replay_schema_version",
                        1,
                    )
                    if not is_blank(row.get("replay_schema_version"))
                    else 1,
                    "replay_status": "exact_replay",
                    "schedule_window_count": len(schedule),
                }
                update_exact_history(
                    clean_text(
                        row.get("selected_source_run_id")
                        or row.get("source_run_id")
                    ),
                    ticker,
                    metadata,
                    summary_path,
                )
        if status == "exact_eligible" or (
            status == "exact_failed" and truthy(row.get("exact_eligible"))
        ):
            try:
                metadata, candidate = persist_exact_replay(
                    row,
                    ticker,
                    summary_path,
                )
                manifest.loc[index, "rebuild_status"] = "exact_replay"
                manifest.loc[index, "exact_candidate"] = str(candidate)
                manifest.loc[index, "schedule_window_count"] = metadata.get(
                    "schedule_window_count",
                    "",
                )
                manifest.loc[index, "result_error"] = ""
            except Exception as exc:
                manifest.loc[index, "rebuild_status"] = "exact_failed"
                manifest.loc[index, "result_error"] = str(exc)
            manifest.loc[index, "updated_at"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            save_manifest(manifest, manifest_path)

    for index in manifest.index:
        row = manifest.loc[index]
        if clean_text(row.get("rebuild_status")) not in {
            "source_unavailable",
            "exact_failed",
        }:
            continue
        update_legacy_replay_status(
            clean_text(
                row.get("selected_source_run_id") or row.get("source_run_id")
            ),
            clean_text(row.get("ticker")),
            "source_unavailable",
            clean_text(row.get("exact_error") or row.get("result_error")),
            summary_path,
        )

    if args.mode == "both":
        for index in manifest.index:
            row = manifest.loc[index]
            status = clean_text(row.get("rebuild_status"))
            if status not in LATEST_ELIGIBLE_STATUSES:
                continue
            manifest.loc[index, "rebuild_status"] = "latest_running"
            manifest.loc[index, "updated_at"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            save_manifest(manifest, manifest_path)
            try:
                result_run_id = execute_latest_run(
                    manifest.loc[index],
                    args.python,
                    summary_path,
                )
                manifest.loc[index, "rebuild_status"] = "rebuilt_latest_data"
                manifest.loc[index, "result_run_id"] = result_run_id
                manifest.loc[index, "result_error"] = ""
            except Exception as exc:
                manifest.loc[index, "rebuild_status"] = "latest_run_failed"
                manifest.loc[index, "result_error"] = str(exc)
            manifest.loc[index, "updated_at"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            save_manifest(manifest, manifest_path)

    if not args.skip_dashboards:
        try:
            cohort = regenerate_dashboards(
                manifest,
                summary_path,
                batch_dir,
                args.python,
            )
            manifest["dashboard_status"] = "regenerated"
            manifest["dashboard_run_history_file"] = str(cohort)
            manifest["dashboard_error"] = ""
        except Exception as exc:
            manifest["dashboard_status"] = "failed"
            manifest["dashboard_error"] = str(exc)
        save_manifest(manifest, manifest_path)

    print_manifest_summary(manifest, manifest_path)
    failures = manifest["rebuild_status"].astype(str).isin(
        ["exact_failed", "latest_run_failed", "latest_run_untracked"]
    )
    return 1 if failures.any() else 0


def main():
    return run_batch(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
