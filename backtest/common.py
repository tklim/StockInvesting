import os
import random
import re
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR  # backtest module is self-contained: data/ and outputs/ live inside backtest/
DATA_DIR = REPO_ROOT / "data"
OUTPUTS_DIR = REPO_ROOT / "outputs"
LOGS_DIR = OUTPUTS_DIR / "logs"
CHARTS_DIR = OUTPUTS_DIR / "charts"
TUNINGS_DIR = OUTPUTS_DIR / "tunings"
REPORTS_DIR = OUTPUTS_DIR / "reports"
TOTAL_RETURN_METHOD_COLUMN = "TotalReturnMethod"
REINVESTED_TOTAL_RETURN_METHOD = "reinvested_dividend_index_v1"
LEGACY_TOTAL_RETURN_METHOD = "legacy_unspecified"
NOT_APPLICABLE_TOTAL_RETURN_METHOD = "not_applicable"


# --- Cross-process file locking -------------------------------------------------
# run10a.bat and run10b.bat are meant to run at the same time and both append to the
# shared history CSVs in outputs/tunings/. Concurrent appends interleave mid-line and
# silently lose rows, and the read-modify-write path (widening columns, refreshing the
# top-5 sets) can drop a whole process's rows without raising anything. PermissionError
# retries do not help: two Python processes never trigger one on Windows.
#
# The sentinel below is an O_CREAT|O_EXCL create, which is atomic on Windows and POSIX.
# Locks are stale-breakable on purpose: the SIGINT handler in backtest_stocks.py calls
# os._exit(), which skips finally blocks, and the .bat loops are routinely Ctrl-C'd, so
# an orphaned lock file is expected rather than exceptional.
LOCK_TIMEOUT_SECONDS = 120
LOCK_STALE_SECONDS = 900
LOCK_POLL_INITIAL_SECONDS = 0.05
LOCK_POLL_MAX_SECONDS = 1.0


class LockTimeout(Exception):
    """Raised when a file lock could not be acquired within the timeout."""


def lock_path_for(path):
    return Path(str(path) + ".lock")


def _lock_is_stale(lock_path, stale_seconds):
    try:
        return (time.time() - lock_path.stat().st_mtime) > stale_seconds
    except FileNotFoundError:
        return False


def _break_stale_lock(lock_path, on_message=None):
    try:
        owner = lock_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        owner = "unknown"
    try:
        lock_path.unlink()
        if on_message:
            on_message(f"Breaking stale lock {lock_path} (held by {owner}).")
    except FileNotFoundError:
        pass  # another process broke it first; just retry


@contextmanager
def file_lock(path, timeout=LOCK_TIMEOUT_SECONDS, stale_seconds=LOCK_STALE_SECONDS,
              on_message=None):
    """Serialise access to `path` across processes.

    Raises LockTimeout if the lock cannot be taken within `timeout` seconds, letting
    callers fall back to their own degradation path instead of blocking forever.
    """
    lock_path = lock_path_for(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    token = f"pid={os.getpid()} host={os.environ.get('COMPUTERNAME', '')} at={datetime.now():%Y-%m-%d %H:%M:%S}"

    deadline = time.monotonic() + timeout
    delay = LOCK_POLL_INITIAL_SECONDS
    acquired = False
    while not acquired:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, token.encode("utf-8"))
            finally:
                os.close(fd)
            acquired = True
        except FileExistsError:
            if _lock_is_stale(lock_path, stale_seconds):
                _break_stale_lock(lock_path, on_message)
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LockTimeout(f"Could not acquire {lock_path} within {timeout}s")
            # Jitter keeps run10a and run10b from retrying in lockstep; the clamp keeps
            # the backoff from sleeping past the caller's deadline.
            time.sleep(min(delay + random.uniform(0, delay), remaining))
            delay = min(delay * 2, LOCK_POLL_MAX_SECONDS)

    try:
        yield
    finally:
        # Only remove the lock if it is still ours - a stale-breaker may have taken it.
        try:
            if lock_path.read_text(encoding="utf-8", errors="replace").strip() == token:
                lock_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def resolve_repo_path(path_value):
    path = Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


def ensure_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_fund_label(value):
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
    return cleaned or "UnknownFund"


def fund_label_from_data_file(path_value):
    stem = Path(path_value).stem
    match = re.match(r"(.+)_nav_\d+Y(?:_\d{8}_\d{6})?$", stem, re.IGNORECASE)
    return sanitize_fund_label(match.group(1) if match else stem)


def fund_group_from_label(label):
    """Return the base fund grouping for a (possibly slice-suffixed) fund label.

    A history-slice suffix like ``-3Y`` / ``-4Y`` (used to backtest a truncated
    data window) is stripped so every slice of the same ticker groups under one
    output folder, e.g. ``AAPL-3Y`` -> ``AAPL``, ``AAPL-4Y`` -> ``AAPL``,
    ``AAPL`` -> ``AAPL``. Labels without such a suffix (including legacy
    ``manulife_*`` codes) pass through unchanged.
    """
    stripped = re.sub(r"-\d+Y$", "", str(label or "").strip(), flags=re.IGNORECASE)
    return sanitize_fund_label(stripped)


def annualized_return_from_pct(total_return_pct, start_date, end_date):
    if start_date is None or end_date is None:
        return np.nan
    try:
        total_return = float(total_return_pct) / 100.0
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        days = (end_ts - start_ts).days
    except (TypeError, ValueError, OverflowError):
        return np.nan
    if pd.isna(start_ts) or pd.isna(end_ts) or days <= 0 or (1 + total_return) <= 0:
        return np.nan
    return (((1 + total_return) ** (365.25 / days)) - 1) * 100


def annualize_return_series(total_return_pct, start_series, end_series):
    total_return = pd.to_numeric(total_return_pct, errors="coerce") / 100.0
    start_dates = pd.to_datetime(start_series, errors="coerce")
    end_dates = pd.to_datetime(end_series, errors="coerce")
    day_counts = (end_dates - start_dates).dt.days

    valid = (
        total_return.notna()
        & start_dates.notna()
        & end_dates.notna()
        & (day_counts > 0)
        & ((1 + total_return) > 0)
    )
    annualized = pd.Series(np.nan, index=total_return.index, dtype=float)
    annualized.loc[valid] = (((1 + total_return.loc[valid]) ** (365.25 / day_counts.loc[valid])) - 1) * 100
    return annualized


def dividend_reinvested_index(nav_values, dividend_values):
    """Build a NAV-based total-return index with distributions reinvested."""
    nav = pd.to_numeric(pd.Series(nav_values), errors="coerce").astype(float)
    dividends = pd.to_numeric(pd.Series(dividend_values), errors="coerce").fillna(0.0).astype(float)
    if len(nav) != len(dividends):
        raise ValueError("NAV and dividend series must have the same length.")
    if nav.empty:
        return pd.Series(dtype=float, index=nav.index, name="TotalReturn")
    if (~np.isfinite(nav)).any() or (nav <= 0).any():
        raise ValueError("NAV values must all be finite and greater than zero.")
    if (~np.isfinite(dividends)).any() or (dividends < 0).any():
        raise ValueError("Dividend values must all be finite and non-negative.")

    growth = (nav + dividends) / nav.shift(1)
    growth.iloc[0] = 1.0
    total_return = nav.iloc[0] * growth.cumprod()
    total_return.index = getattr(nav_values, "index", nav.index)
    total_return.name = "TotalReturn"
    return total_return


def calculate_rsi(prices, period=14):
    """Calculate RSI, treating one-sided and flat windows explicitly."""
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs.replace([np.inf, -np.inf], np.nan).fillna(0)))
    rsi[avg_loss == 0] = 100.0
    rsi[(avg_gain == 0) & (avg_loss == 0)] = 50.0
    return rsi.fillna(50.0)


def infer_total_return_method(df, price_column):
    """Identify the return-series construction used by a data frame."""
    if str(price_column) != "TotalReturn":
        return NOT_APPLICABLE_TOTAL_RETURN_METHOD
    if TOTAL_RETURN_METHOD_COLUMN not in df.columns:
        return LEGACY_TOTAL_RETURN_METHOD

    methods = (
        df[TOTAL_RETURN_METHOD_COLUMN]
        .dropna()
        .astype(str)
        .str.strip()
    )
    methods = methods[methods.ne("")].unique().tolist()
    if not methods:
        return LEGACY_TOTAL_RETURN_METHOD
    if len(methods) > 1:
        raise ValueError(f"Data contains multiple TotalReturn methods: {methods}")
    return methods[0]


def save_csv(df, path, allow_fallback=True, **kwargs):
    path = Path(path)
    ensure_dir(path.parent)
    try:
        df.to_csv(path, index=False, **kwargs)
        return path
    except PermissionError:
        if not allow_fallback:
            raise
        fallback = path.with_name(f"{path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{path.suffix}")
        df.to_csv(fallback, index=False, **kwargs)
        print(f"Warning: {path} is locked. Saved fallback CSV to {fallback}")
        return fallback
