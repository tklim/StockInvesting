"""Download daily stock OHLCV data from Yahoo Finance into backtest/data/.

After each download, shorter-horizon CSVs (default 10Y, 5Y, 4Y, and 3Y) are derived by
slicing the downloaded data — no extra Yahoo Finance requests.

Usage:
    python download_data.py                     # tickers.txt, 20 years + 10Y/5Y/4Y/3Y slices
    python download_data.py --refresh-mode incremental
    python download_data.py --years 3 --derive-years 2
    python download_data.py --tickers AAPL MSFT
    python download_data.py --years 10 --derive-years 5 3
    python download_data.py --derive-only       # re-slice existing CSVs, no download
"""
import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
TICKERS_FILE = SCRIPT_DIR / "tickers.txt"
DEFAULT_YEARS = 20
DEFAULT_DERIVE_YEARS = (10, 5, 4, 3)
EXPECTED_COLUMNS = ("Date", "Open", "High", "Low", "Close", "Adj Close", "Volume")
DEFAULT_MAX_STALENESS_DAYS = 7
DEFAULT_DOWNLOAD_ATTEMPTS = 3
DEFAULT_RETRY_DELAYS_SECONDS = (2, 5)
DEFAULT_INCREMENTAL_OVERLAP_DAYS = 90
DEFAULT_FULL_RECONCILE_DAYS = 30
DOWNLOAD_METADATA_SUFFIX = ".download-meta.json"


def load_tickers(tickers_file=TICKERS_FILE):
    if not tickers_file.exists():
        raise FileNotFoundError(f"Ticker list not found: {tickers_file}")
    tickers = []
    for line in tickers_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            tickers.append(line.upper())
    return tickers


def safe_ticker_name(ticker):
    return ticker.replace("^", "").replace(".", "_")


def validate_price_frame(df, max_staleness_days=None, as_of=None):
    """Validate and normalize one daily OHLCV frame without reordering it."""
    if df is None or df.empty:
        raise ValueError("download returned no rows")

    frame = df.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    if "Date" not in frame.columns:
        frame = frame.reset_index()
    if "Date" not in frame.columns:
        raise ValueError("download is missing required column: Date")

    missing = [column for column in EXPECTED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"download is missing required columns: {missing}")

    frame = frame.loc[:, EXPECTED_COLUMNS].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    if frame["Date"].isna().any():
        raise ValueError("download contains invalid dates")
    if frame["Date"].duplicated().any():
        raise ValueError("download contains duplicate dates")
    if not frame["Date"].is_monotonic_increasing:
        raise ValueError("download dates are not strictly ascending")

    if max_staleness_days is not None:
        today = pd.Timestamp(as_of or pd.Timestamp.today()).normalize()
        latest = pd.Timestamp(frame["Date"].iloc[-1])
        if latest.tzinfo is not None:
            latest = latest.tz_localize(None)
        age_days = (today - latest.normalize()).days
        if age_days < 0:
            raise ValueError(f"download ends in the future: {latest:%Y-%m-%d}")
        if age_days > max_staleness_days:
            raise ValueError(
                f"download is stale: latest date {latest:%Y-%m-%d} is "
                f"{age_days} days old (maximum {max_staleness_days})"
            )
    return frame


def fetch_ticker_range(
    ticker,
    start_date,
    end_date,
    interval="1d",
    attempts=DEFAULT_DOWNLOAD_ATTEMPTS,
    retry_delays=DEFAULT_RETRY_DELAYS_SECONDS,
):
    """Fetch and validate one ticker date range with bounded retries."""
    if attempts <= 0:
        raise ValueError("attempts must be > 0")
    if not retry_delays:
        raise ValueError("retry_delays must not be empty")
    start_date = pd.Timestamp(start_date)
    end_date = pd.Timestamp(end_date)
    if start_date >= end_date:
        raise ValueError("download start date must be before end date")
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            downloaded = yf.download(
                ticker,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval=interval,
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            return validate_price_frame(
                downloaded,
                max_staleness_days=DEFAULT_MAX_STALENESS_DAYS,
            )
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            delay = retry_delays[min(attempt - 1, len(retry_delays) - 1)]
            print(
                f"    {ticker}: download attempt {attempt}/{attempts} failed "
                f"({exc}); retrying in {delay}s..."
            )
            time.sleep(delay)
    raise RuntimeError(
        f"download failed after {attempts} attempts: {last_error}"
    ) from last_error


def fetch_ticker_data(
    ticker,
    years,
    interval="1d",
    attempts=DEFAULT_DOWNLOAD_ATTEMPTS,
    retry_delays=DEFAULT_RETRY_DELAYS_SECONDS,
):
    """Fetch and validate a complete ticker history with bounded retries."""
    end_date = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
    start_date = end_date - pd.DateOffset(years=years)
    return fetch_ticker_range(
        ticker,
        start_date,
        end_date,
        interval=interval,
        attempts=attempts,
        retry_delays=retry_delays,
    )


def derive_slices(csv_file, df, derive_years, out_dir=None):
    """Write {stem}-{N}Y.csv slices of df covering the last N years of data.

    The cutoff is anchored to the data's last date, so slices stay consistent
    with the source file regardless of when the derivation runs. Returns a list
    of (years, csv_file, sliced_df); horizons the source doesn't reach back to
    are skipped with a warning.
    """
    out_dir = Path(out_dir) if out_dir else Path(csv_file).parent
    dates = pd.to_datetime(df["Date"])
    first_date, last_date = dates.iloc[0], dates.iloc[-1]
    results = []
    for years in derive_years:
        cutoff = last_date - pd.DateOffset(years=years)
        # Allow a few days of slack for weekends/holidays at the data start.
        if first_date > cutoff + pd.Timedelta(days=7):
            print(
                f"    skipping {years}Y slice: source data starts "
                f"{first_date.strftime('%Y-%m-%d')}, after cutoff {cutoff.strftime('%Y-%m-%d')}"
            )
            continue
        sliced = df[dates >= cutoff]
        slice_file = out_dir / f"{Path(csv_file).stem}-{years}Y.csv"
        sliced.to_csv(slice_file, index=False)
        results.append((years, slice_file, sliced))
    return results


def download_metadata_path(ticker, out_dir):
    return Path(out_dir) / f"{safe_ticker_name(ticker)}{DOWNLOAD_METADATA_SUFFIX}"


def load_download_metadata(ticker, out_dir):
    path = download_metadata_path(ticker, out_dir)
    if not path.exists():
        return None
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return metadata if isinstance(metadata, dict) else None


def build_download_metadata(ticker, df, refresh_mode, previous=None, overlap_days=None):
    refreshed_at = pd.Timestamp.now().isoformat()
    last_full_refresh = (
        refreshed_at
        if refresh_mode == "full"
        else (previous or {}).get("last_full_refresh", "")
    )
    return {
        "schema_version": 1,
        "ticker": ticker.upper(),
        "last_refresh_mode": refresh_mode,
        "last_refresh": refreshed_at,
        "last_full_refresh": last_full_refresh,
        "incremental_overlap_days": overlap_days if refresh_mode == "incremental" else None,
        "data_start": pd.Timestamp(df["Date"].iloc[0]).strftime("%Y-%m-%d"),
        "data_end": pd.Timestamp(df["Date"].iloc[-1]).strftime("%Y-%m-%d"),
        "row_count": len(df),
    }


def full_reconciliation_due(metadata, reconcile_days, as_of=None):
    if not metadata or not metadata.get("last_full_refresh"):
        return True
    try:
        last_full = pd.Timestamp(metadata["last_full_refresh"])
    except (TypeError, ValueError):
        return True
    now = pd.Timestamp(as_of or pd.Timestamp.now())
    if last_full.tzinfo is not None:
        last_full = last_full.tz_localize(None)
    if now.tzinfo is not None:
        now = now.tz_localize(None)
    return now - last_full >= pd.Timedelta(days=reconcile_days)


def replace_dataset_files(
    ticker,
    df,
    derive_years,
    out_dir,
    include_source=True,
    metadata=None,
):
    """Stage, validate, and atomically replace a ticker's source and slice CSVs."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    source_name = f"{safe_ticker_name(ticker)}.csv"
    replacements = []
    returned_slices = []

    with tempfile.TemporaryDirectory(prefix=".download-", dir=out_dir) as temp_dir:
        stage_dir = Path(temp_dir)
        staged_source = stage_dir / source_name
        if include_source:
            df.to_csv(staged_source, index=False)
            validate_price_frame(pd.read_csv(staged_source))
            replacements.append((staged_source, out_dir / source_name))

        for years, staged_slice, sliced in derive_slices(
            staged_source,
            df,
            derive_years,
            out_dir=stage_dir,
        ):
            validate_price_frame(pd.read_csv(staged_slice))
            destination = out_dir / staged_slice.name
            replacements.append((staged_slice, destination))
            returned_slices.append((years, destination, sliced))

        if metadata is not None:
            staged_metadata = stage_dir / download_metadata_path(
                ticker, stage_dir
            ).name
            staged_metadata.write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            replacements.append(
                (staged_metadata, download_metadata_path(ticker, out_dir))
            )

        for staged_path, destination in replacements:
            os.replace(staged_path, destination)

    return out_dir / source_name, returned_slices


def download_ticker(ticker, years, interval="1d", out_dir=None):
    """Download and atomically save one full-history ticker CSV."""
    out_dir = Path(out_dir) if out_dir else DATA_DIR
    df = fetch_ticker_data(ticker, years, interval)
    metadata = build_download_metadata(ticker, df, "full")
    csv_file, _ = replace_dataset_files(
        ticker,
        df,
        derive_years=(),
        out_dir=out_dir,
        metadata=metadata,
    )
    return csv_file, df


def refresh_ticker_files(ticker, years, derive_years, interval="1d", out_dir=None):
    """Download once, then atomically replace the full history and all slices."""
    out_dir = Path(out_dir) if out_dir else DATA_DIR
    df = fetch_ticker_data(ticker, years, interval)
    metadata = build_download_metadata(ticker, df, "full")
    csv_file, slices = replace_dataset_files(
        ticker,
        df,
        derive_years=derive_years,
        out_dir=out_dir,
        metadata=metadata,
    )
    return csv_file, df, slices


def refresh_ticker_incrementally(
    ticker,
    years,
    derive_years,
    interval="1d",
    out_dir=None,
    overlap_days=DEFAULT_INCREMENTAL_OVERLAP_DAYS,
    full_reconcile_days=DEFAULT_FULL_RECONCILE_DAYS,
):
    """Refresh recent overlapping rows, with automatic periodic full recovery."""
    if overlap_days <= 0:
        raise ValueError("overlap_days must be > 0")
    if full_reconcile_days <= 0:
        raise ValueError("full_reconcile_days must be > 0")

    out_dir = Path(out_dir) if out_dir else DATA_DIR
    source_path = out_dir / f"{safe_ticker_name(ticker)}.csv"
    previous_metadata = load_download_metadata(ticker, out_dir)
    if not source_path.exists() or full_reconciliation_due(
        previous_metadata,
        full_reconcile_days,
    ):
        reason = (
            "source file is missing"
            if not source_path.exists()
            else "full reconciliation is due or has no valid metadata"
        )
        print(f"    {ticker}: {reason}; downloading the full {years}-year history.")
        csv_file, df, slices = refresh_ticker_files(
            ticker,
            years,
            derive_years,
            interval,
            out_dir,
        )
        return csv_file, df, slices, "full"

    existing = validate_price_frame(pd.read_csv(source_path))
    existing_dates = pd.DatetimeIndex(existing["Date"])
    latest_existing = existing_dates[-1]
    start_date = latest_existing - pd.Timedelta(days=overlap_days)
    end_date = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
    recent = fetch_ticker_range(
        ticker,
        start_date,
        end_date,
        interval=interval,
    )
    recent_dates = pd.DatetimeIndex(recent["Date"])
    if recent_dates[0] > start_date + pd.Timedelta(days=7):
        raise ValueError(
            f"incremental download starts too late: requested {start_date:%Y-%m-%d}, "
            f"received {recent_dates[0]:%Y-%m-%d}"
        )
    if existing_dates.intersection(recent_dates).empty:
        raise ValueError("incremental download does not overlap the existing dataset")

    merged = (
        pd.concat([existing, recent], ignore_index=True)
        .drop_duplicates(subset=["Date"], keep="last")
        .sort_values("Date")
        .reset_index(drop=True)
    )
    merged = validate_price_frame(
        merged,
        max_staleness_days=DEFAULT_MAX_STALENESS_DAYS,
    )
    metadata = build_download_metadata(
        ticker,
        merged,
        "incremental",
        previous=previous_metadata,
        overlap_days=overlap_days,
    )
    csv_file, slices = replace_dataset_files(
        ticker,
        merged,
        derive_years=derive_years,
        out_dir=out_dir,
        metadata=metadata,
    )
    return csv_file, merged, slices, "incremental"


def print_file_summary(label, df, csv_file, indent="  "):
    first = pd.Timestamp(df["Date"].iloc[0]).strftime("%Y-%m-%d")
    last = pd.Timestamp(df["Date"].iloc[-1]).strftime("%Y-%m-%d")
    print(f"{indent}{label}: {len(df)} rows ({first} to {last}) -> {csv_file}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Download stock data for backtesting")
    parser.add_argument(
        "--years",
        type=int,
        default=DEFAULT_YEARS,
        help=f"Years of daily history to download (default: {DEFAULT_YEARS})",
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=None,
        help="Tickers to download (default: read tickers.txt)",
    )
    parser.add_argument(
        "--interval",
        default="1d",
        help="Bar interval (default: 1d)",
    )
    parser.add_argument(
        "--refresh-mode",
        choices=("full", "incremental"),
        default="full",
        help="Refresh the full history or merge a recent overlap "
        "(default: full)",
    )
    parser.add_argument(
        "--incremental-overlap-days",
        type=int,
        default=DEFAULT_INCREMENTAL_OVERLAP_DAYS,
        help="Calendar days to redownload and replace in incremental mode "
        f"(default: {DEFAULT_INCREMENTAL_OVERLAP_DAYS})",
    )
    parser.add_argument(
        "--full-reconcile-days",
        type=int,
        default=DEFAULT_FULL_RECONCILE_DAYS,
        help="Maximum days between full-history downloads in incremental mode "
        f"(default: {DEFAULT_FULL_RECONCILE_DAYS})",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Directory for the full-history and derived CSVs (default: data/). "
        "Files with matching names are overwritten.",
    )
    parser.add_argument(
        "--derive-years",
        nargs="+",
        type=int,
        default=list(DEFAULT_DERIVE_YEARS),
        help="Shorter horizons to slice from the downloaded data as "
        f"{{TICKER}}-{{N}}Y.csv, no extra downloads "
        f"(default: {' '.join(map(str, DEFAULT_DERIVE_YEARS))})",
    )
    parser.add_argument(
        "--derive-only",
        action="store_true",
        help="Skip downloading; slice existing {TICKER}.csv files "
        "in the output directory instead",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.years <= 0:
        raise ValueError("--years must be > 0")
    if any(years <= 0 for years in args.derive_years):
        raise ValueError("--derive-years values must be > 0")
    if args.incremental_overlap_days <= 0:
        raise ValueError("--incremental-overlap-days must be > 0")
    if args.full_reconcile_days <= 0:
        raise ValueError("--full-reconcile-days must be > 0")

    tickers = [t.upper() for t in args.tickers] if args.tickers else load_tickers()
    out_dir = Path(args.out_dir) if args.out_dir else DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.derive_only:
        print(f"Deriving {args.derive_years} year slices for {len(tickers)} ticker(s) from {out_dir}...")
    else:
        print(
            f"Refreshing {len(tickers)} ticker(s) in {args.refresh_mode} mode, "
            f"{args.years} year(s) of {args.interval} data..."
        )
    failures = []
    for ticker in tickers:
        try:
            if args.derive_only:
                csv_file = out_dir / f"{safe_ticker_name(ticker)}.csv"
                if not csv_file.exists():
                    raise FileNotFoundError(f"source CSV not found: {csv_file}")
                df = validate_price_frame(pd.read_csv(csv_file))
                _, slices = replace_dataset_files(
                    ticker,
                    df,
                    derive_years=args.derive_years,
                    out_dir=out_dir,
                    include_source=False,
                )
            else:
                if args.refresh_mode == "incremental":
                    csv_file, df, slices, actual_mode = refresh_ticker_incrementally(
                        ticker,
                        args.years,
                        args.derive_years,
                        args.interval,
                        out_dir,
                        overlap_days=args.incremental_overlap_days,
                        full_reconcile_days=args.full_reconcile_days,
                    )
                    print(f"    {ticker}: completed using {actual_mode} refresh.")
                else:
                    csv_file, df, slices = refresh_ticker_files(
                        ticker,
                        args.years,
                        args.derive_years,
                        args.interval,
                        out_dir,
                    )
            print_file_summary(ticker, df, csv_file)
            for years, slice_file, sliced in slices:
                print_file_summary(f"{ticker}-{years}Y", sliced, slice_file, indent="    ")
        except Exception as exc:
            failures.append(ticker)
            print(f"  {ticker}: FAILED ({exc})")

    print(f"\nDone: {len(tickers) - len(failures)} succeeded, {len(failures)} failed.")
    if failures:
        print(f"Failed tickers: {', '.join(failures)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
