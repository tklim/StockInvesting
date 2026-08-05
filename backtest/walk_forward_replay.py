"""Durable walk-forward replay artifacts and deterministic schedule evaluation."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pandas as pd


REPLAY_SCHEMA_VERSION = 1
# Legacy source data can be re-serialized or refreshed with tiny floating-point
# differences. Accept drift up to 0.001 percentage points while keeping the
# structural replay checks (dates, rows, schedule, and hashes) exact.
METRIC_TOLERANCE_PCT = 1e-3

PARAMETER_ALIASES = {
    "short_ema": "best_short_ema",
    "long_ema": "best_long_ema",
    "stop_loss": "best_stop_loss_pct",
    "cooldown": "best_cooldown",
    "drawdown_exit_pct": "best_drawdown_exit_pct",
    "reentry_rebound_pct": "best_reentry_rebound_pct",
    "rsi_oversold": "best_rsi_oversold",
    "rsi_overbought": "best_rsi_overbought",
    "exposure_multiplier": "best_exposure_multiplier",
}

REQUIRED_SCHEDULE_COLUMNS = {
    "window_sequence",
    "train_start",
    "train_end",
    "test_start",
    "test_end",
}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_artifact_path(path, base_dir):
    return Path(path).resolve().relative_to(Path(base_dir).resolve()).as_posix()


def resolve_artifact_path(path_value, base_dir):
    path = Path(str(path_value))
    return path if path.is_absolute() else Path(base_dir) / path


def _canonical_snapshot_frame(data):
    frame = data.copy()
    if "Date" not in frame.columns:
        index_name = frame.index.name or "index"
        frame = frame.reset_index().rename(columns={index_name: "Date", "index": "Date"})
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame = frame.dropna(subset=["Date"]).sort_values("Date")
    frame = frame.drop_duplicates(subset=["Date"], keep="last")
    return frame


def run_artifact_dir(base_dir, fund_label, run_id):
    return (
        Path(base_dir)
        / "outputs"
        / "funds"
        / str(fund_label)
        / "runs"
        / str(run_id)
    )


def save_replay_artifacts(data, schedule, base_dir, fund_label, run_id):
    run_dir = run_artifact_dir(base_dir, fund_label, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = run_dir / "source_snapshot.csv"
    schedule_path = run_dir / "parameter_schedule.csv"

    snapshot = _canonical_snapshot_frame(data)
    normalized_schedule = normalize_schedule(schedule)
    snapshot.to_csv(snapshot_path, index=False)
    normalized_schedule.to_csv(schedule_path, index=False)

    return {
        "replay_schema_version": REPLAY_SCHEMA_VERSION,
        "source_snapshot_file": relative_artifact_path(snapshot_path, base_dir),
        "source_snapshot_sha256": sha256_file(snapshot_path),
        "parameter_schedule_file": relative_artifact_path(schedule_path, base_dir),
        "parameter_schedule_sha256": sha256_file(schedule_path),
        "replay_status": "artifacts_recorded",
        "schedule_window_count": len(normalized_schedule),
    }


def load_replay_artifacts(metadata, base_dir):
    snapshot_path = resolve_artifact_path(metadata["source_snapshot_file"], base_dir)
    schedule_path = resolve_artifact_path(metadata["parameter_schedule_file"], base_dir)
    expected_snapshot_hash = str(metadata.get("source_snapshot_sha256", "")).strip()
    expected_schedule_hash = str(metadata.get("parameter_schedule_sha256", "")).strip()
    if not snapshot_path.exists() or not schedule_path.exists():
        raise FileNotFoundError("Replay snapshot or parameter schedule is missing")
    if expected_snapshot_hash and sha256_file(snapshot_path) != expected_snapshot_hash:
        raise ValueError(f"Replay snapshot hash mismatch: {snapshot_path}")
    if expected_schedule_hash and sha256_file(schedule_path) != expected_schedule_hash:
        raise ValueError(f"Parameter schedule hash mismatch: {schedule_path}")

    snapshot = pd.read_csv(snapshot_path)
    snapshot["Date"] = pd.to_datetime(snapshot["Date"], errors="coerce")
    snapshot = snapshot.dropna(subset=["Date"]).sort_values("Date").set_index("Date")
    schedule = normalize_schedule(pd.read_csv(schedule_path))
    return snapshot, schedule, snapshot_path, schedule_path


def normalize_schedule(schedule):
    frame = pd.DataFrame(schedule).copy()
    missing = sorted(REQUIRED_SCHEDULE_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"Parameter schedule is missing required columns: {missing}")
    for target, legacy in PARAMETER_ALIASES.items():
        if target not in frame.columns and legacy in frame.columns:
            frame[target] = frame[legacy]
    missing_params = sorted(set(PARAMETER_ALIASES) - set(frame.columns))
    if missing_params:
        raise ValueError(f"Parameter schedule is missing parameters: {missing_params}")

    frame["window_sequence"] = pd.to_numeric(
        frame["window_sequence"], errors="raise"
    ).astype(int)
    for column in ["train_start", "train_end", "test_start", "test_end"]:
        frame[column] = pd.to_datetime(frame[column], errors="raise")
    frame = frame.sort_values(["window_sequence", "test_start"]).reset_index(drop=True)
    if "test_end_exclusive" not in frame.columns:
        exclusive_ends = []
        for index, row in frame.iterrows():
            if "offset_months" in frame.columns and not pd.isna(row.get("offset_months")):
                exclusive_ends.append(
                    row["test_start"]
                    + pd.DateOffset(months=int(round(float(row["offset_months"]))))
                )
            elif index + 1 < len(frame):
                exclusive_ends.append(frame.iloc[index + 1]["test_start"])
            else:
                exclusive_ends.append(row["test_end"] + pd.Timedelta(days=1))
        frame["test_end_exclusive"] = exclusive_ends
    else:
        frame["test_end_exclusive"] = pd.to_datetime(
            frame["test_end_exclusive"], errors="raise"
        )
    validate_schedule(frame)
    return frame


def validate_schedule(schedule):
    if schedule.empty:
        raise ValueError("Parameter schedule is empty")
    if schedule["window_sequence"].duplicated().any():
        raise ValueError("Parameter schedule contains duplicate window_sequence values")
    if schedule["test_start"].duplicated().any():
        raise ValueError("Parameter schedule contains duplicate test_start values")
    if not schedule["window_sequence"].tolist() == list(
        range(1, len(schedule) + 1)
    ):
        raise ValueError("Parameter schedule window_sequence values must be contiguous")
    if (schedule["train_start"] >= schedule["train_end"]).any():
        raise ValueError("Parameter schedule contains an invalid training window")
    if (schedule["train_end"] != schedule["test_start"]).any():
        raise ValueError("Each training window must end at its test_start")
    for index in range(len(schedule) - 1):
        current_end = schedule.iloc[index]["test_end_exclusive"]
        next_start = schedule.iloc[index + 1]["test_start"]
        if current_end != next_start:
            raise ValueError("Parameter schedule contains a gap or overlap")


def load_schedule_from_tuning_history(path, run_id):
    return load_schedule_from_tuning_history_with_metadata(path, run_id)


def _parse_ordered_values(value, defaults):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return list(defaults)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "default", "default grid"}:
        return list(defaults)
    return [
        float(token)
        for token in text.strip("[]()").replace(";", ",").split(",")
        if token.strip()
    ]


def _search_order(row, run_metadata):
    metadata = run_metadata or {}
    pop_values = _parse_ordered_values(metadata.get("pop_ranges"), [10])
    gen_values = _parse_ordered_values(
        metadata.get("gen_ranges"),
        pop_values,
    )
    mutation_values = _parse_ordered_values(
        metadata.get("mutation_rates"),
        [0.01, 0.05, 0.1, 0.15],
    )
    crossover_values = _parse_ordered_values(
        metadata.get("crossover_rates"),
        [0.6, 0.7, 0.8, 0.9],
    )

    def position(values, value):
        numeric = float(value)
        for index, candidate in enumerate(values):
            if abs(candidate - numeric) <= 1e-12:
                return index
        return len(values)

    return (
        position(pop_values, row.get("pop_size")),
        position(gen_values, row.get("generations")),
        position(mutation_values, row.get("mutation_rate")),
        position(crossover_values, row.get("crossover_rate")),
    )


def load_schedule_from_tuning_history_with_metadata(path, run_id, run_metadata=None):
    history = pd.read_csv(path, low_memory=False)
    if "run_id" not in history.columns:
        raise ValueError(f"Tuning history has no run_id column: {path}")
    selected = history[history["run_id"].astype(str) == str(run_id)].copy()
    if "best" in selected.columns:
        best = selected["best"].astype(str).str.lower().isin(["true", "1", "yes"])
        selected = selected[best]
    if selected.empty:
        raise ValueError(f"No winning parameter windows found for run {run_id}")

    if run_metadata and str(run_metadata.get("reuse_tuned_params", "")).lower() not in {
        "true",
        "1",
        "yes",
    }:
        raise ValueError(
            "Tuning history cannot recover the applied schedule when "
            "reuse_tuned_params was disabled"
        )

    # The historical tuner marks every maximum-score tie as best=True, while
    # the applied parameter set is the first maximum encountered by the
    # itertools product loop. Reconstruct that original search ordering rather
    # than depending on pandas' tie ordering in the persisted CSV.
    selected["_search_order"] = selected.apply(
        lambda row: _search_order(row, run_metadata),
        axis=1,
    )
    selected = (
        selected.sort_values(["window_sequence", "_search_order"])
        .drop_duplicates(subset=["window_sequence"], keep="first")
        .drop(columns=["_search_order"])
    )
    return normalize_schedule(selected)


def load_schedule_from_window_history(path, run_id):
    history = pd.read_csv(path, low_memory=False)
    if "run_id" not in history.columns:
        raise ValueError(f"Window history has no run_id column: {path}")
    selected = history[history["run_id"].astype(str) == str(run_id)].copy()
    if selected.empty:
        raise ValueError(f"No applied parameter windows found for run {run_id}")
    return normalize_schedule(selected)


def load_recorded_schedule(
    window_history_path,
    tuning_history_path,
    run_id,
    run_metadata=None,
):
    """Load the applied schedule, falling back to deterministic tuning recovery."""
    window_error = None
    if window_history_path and Path(window_history_path).exists():
        try:
            return (
                load_schedule_from_window_history(window_history_path, run_id),
                "window_history",
            )
        except Exception as exc:
            window_error = exc

    try:
        schedule = load_schedule_from_tuning_history_with_metadata(
            tuning_history_path,
            run_id,
            run_metadata=run_metadata,
        )
        return schedule, "tuning_history"
    except Exception as tuning_error:
        if window_error is not None:
            raise ValueError(
                f"Applied-window recovery failed: {window_error}; "
                f"tuning fallback failed: {tuning_error}"
            ) from tuning_error
        raise


def _number(row, key, integer=False, default=None):
    value = row.get(key, default)
    if pd.isna(value):
        value = default
    if value is None:
        raise ValueError(f"Missing schedule value: {key}")
    return int(round(float(value))) if integer else float(value)


def _flag(value, default=False):
    """Parse a boolean that may arrive as a real bool or a CSV string."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return default if pd.isna(value) else bool(value)
    return str(value).strip().lower() in ("true", "1", "yes")


def extract_carry_exit_params(params, default_rsi_oversold=30):
    """Exit-relevant subset of a window's params, used by the grandfather
    transition policy so a carried position keeps the exit rules of the
    window that opened it. Works for live best_params dicts and for
    schedule rows recovered from CSV."""
    return {
        "short_ema": _number(params, "short_ema", integer=True),
        "long_ema": _number(params, "long_ema", integer=True),
        "stop_loss_pct": _number(params, "stop_loss"),
        "use_take_profit": _flag(params.get("use_take_profit", False)),
        "take_profit_pct": _number(params, "take_profit_pct", default=10.0),
        "drawdown_exit_pct": _number(params, "drawdown_exit_pct"),
        "rsi_oversold": _number(
            params, "rsi_oversold", integer=True, default=default_rsi_oversold
        ),
    }


def advance_carry_exit_params(active_exit_params, carry_state, window_params,
                              default_rsi_oversold=30):
    """Roll the grandfathered exit params forward after a window is evaluated.

    Keeps the existing params only while the position that entered the window
    is still open; a position opened (or fully re-cycled) inside the window is
    governed by that window's params; flat means nothing to grandfather."""
    if not carry_state or float(carry_state.get("position", 0.0) or 0.0) <= 1e-9:
        return None
    if carry_state.get("carried_position_open") and active_exit_params is not None:
        return active_exit_params
    return extract_carry_exit_params(window_params, default_rsi_oversold)


def evaluate_parameter_window(
    lookback_data,
    next_period_data,
    params,
    portfolio_value,
    carry_state,
    backtest_fn,
    strategy_profile,
    default_rsi_period,
    debug=False,
    carry_exit_params=None,
):
    if next_period_data.empty:
        raise ValueError("Cannot replay an empty test window")
    eval_data = pd.concat([lookback_data, next_period_data]).sort_index()
    eval_data = eval_data[~eval_data.index.duplicated(keep="last")]
    trade_start_idx = len(eval_data) - len(next_period_data)
    config = {
        "use_rsi_filter": True,
        "rsi_oversold": _number(params, "rsi_oversold", integer=True),
        "rsi_overbought": _number(params, "rsi_overbought", integer=True),
        "rsi_period": _number(
            params, "rsi_period", integer=True, default=default_rsi_period
        ),
        "use_trend_filter": False,
        "use_stop_loss": True,
        "stop_loss_pct": _number(params, "stop_loss"),
        "use_take_profit": bool(params.get("use_take_profit", False)),
        "take_profit_pct": _number(
            params, "take_profit_pct", default=10.0
        ),
        "cooldown_period": _number(params, "cooldown", integer=True),
        "drawdown_exit_pct": _number(params, "drawdown_exit_pct"),
        "reentry_rebound_pct": _number(params, "reentry_rebound_pct"),
        "exposure_multiplier": _number(
            params, "exposure_multiplier", default=1.0
        ),
        "start_invested": carry_state is None,
        "trade_start_idx": trade_start_idx,
        "debug": debug,
        "strategy_profile_name": strategy_profile,
    }
    if carry_exit_params is not None:
        # Only forwarded when the grandfather policy is active, so backtest
        # functions without the kwarg keep working under policy "none".
        config["carry_exit_params"] = carry_exit_params
    return backtest_fn(
        eval_data,
        _number(params, "short_ema", integer=True),
        _number(params, "long_ema", integer=True),
        portfolio_value,
        initial_state=carry_state,
        return_state=True,
        **config,
    )


def replay_parameter_schedule(
    data,
    schedule,
    initial_capital,
    strategy_profile,
    backtest_fn,
    metrics_fn,
    default_rsi_period,
    transition_policy="none",
):
    frame = data.copy()
    if "Date" in frame.columns:
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
        frame = frame.dropna(subset=["Date"]).set_index("Date")
    frame.index = pd.to_datetime(frame.index)
    frame = frame.sort_index()
    normalized_schedule = normalize_schedule(schedule)

    portfolio_value = float(initial_capital)
    carry_state = None
    active_exit_params = None
    grandfather = str(transition_policy or "none") == "grandfather"
    portfolio_history = []
    adaptive_results = []
    all_trades = []
    trade_count = 0

    for index, params in normalized_schedule.iterrows():
        train_start = params["train_start"]
        test_start = params["test_start"]
        test_end_exclusive = params["test_end_exclusive"]
        lookback_data = frame[
            (frame.index >= train_start) & (frame.index < test_start)
        ].copy()
        next_period_data = frame[
            (frame.index >= test_start) & (frame.index < test_end_exclusive)
        ].copy()
        if len(lookback_data) < 50:
            raise ValueError(
                f"Insufficient warm-up data for window {params['window_sequence']}"
            )

        result = evaluate_parameter_window(
            lookback_data,
            next_period_data,
            params,
            portfolio_value,
            carry_state,
            backtest_fn,
            strategy_profile,
            default_rsi_period,
            carry_exit_params=active_exit_params if grandfather else None,
        )
        (
            df_result,
            _,
            num_trades,
            trades,
            _,
            _,
            _,
            _,
            _,
            carry_state,
        ) = result
        if grandfather:
            active_exit_params = advance_carry_exit_params(
                active_exit_params, carry_state, params
            )
        portfolio_value = float(df_result["Portfolio_Value"].iloc[-1])
        trade_count += int(num_trades)
        all_trades.extend(trades)
        portfolio_history.append(
            df_result[["Date", "Portfolio_Value", "Position", "Exposure"]].copy()
            if "Date" in df_result.columns
            else df_result.reset_index().rename(columns={"index": "Date"})
        )
        adaptive_results.append(df_result.copy())

    adaptive_df = pd.concat(adaptive_results, ignore_index=True)
    if "Date" in adaptive_df.columns:
        adaptive_df["Date"] = pd.to_datetime(adaptive_df["Date"], errors="coerce")
        adaptive_df = (
            adaptive_df.dropna(subset=["Date"])
            .drop_duplicates(subset=["Date"], keep="last")
            .sort_values("Date")
            .reset_index(drop=True)
        )
    portfolio_df = pd.concat(portfolio_history, ignore_index=True)
    metrics = metrics_fn(adaptive_df, all_trades, initial_capital)
    return {
        "adaptive_df": adaptive_df,
        "portfolio_df": portfolio_df,
        "trades": all_trades,
        "trade_count": trade_count,
        "carry_state": carry_state,
        "final_portfolio_value": portfolio_value,
        "metrics": metrics,
        "schedule": normalized_schedule,
        "window_count": len(normalized_schedule),
        "transition_policy": str(transition_policy or "none"),
    }


def assert_metrics_match(actual, expected, tolerance=METRIC_TOLERANCE_PCT):
    mapping = {
        "adaptive_return": "source_adaptive_return_pct",
        "buy_hold_return": "source_buy_hold_return_pct",
        "excess_return": "source_excess_return_pct",
        "adaptive_annualized_return": "source_adaptive_annualized_return_pct",
        "buy_hold_annualized_return": "source_buy_hold_annualized_return_pct",
        "excess_annualized_return": "source_excess_annualized_return_pct",
    }
    mismatches = []
    for metric_key, expected_key in mapping.items():
        if expected_key not in expected or pd.isna(expected.get(expected_key)):
            continue
        actual_value = float(actual[metric_key])
        expected_value = float(expected[expected_key])
        if abs(actual_value - expected_value) > tolerance:
            mismatches.append(
                f"{metric_key}: replay={actual_value:.12f}, source={expected_value:.12f}"
            )
    if mismatches:
        raise ValueError(
            "Exact replay metrics do not match the source run: " + "; ".join(mismatches)
        )
