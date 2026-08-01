import tempfile
import unittest
import json
from pathlib import Path
from unittest import mock

import pandas as pd

import download_data


def sample_history(end=None):
    end = pd.Timestamp(end or pd.Timestamp.today()).normalize()
    dates = pd.bdate_range(end - pd.DateOffset(years=21), end)
    values = pd.Series(range(len(dates)), index=dates, dtype=float)
    frame = pd.DataFrame(
        {
            "Open": values + 1,
            "High": values + 2,
            "Low": values,
            "Close": values + 1,
            "Adj Close": values + 1,
            "Volume": 1000,
        },
        index=dates,
    )
    frame.index.name = "Date"
    return frame


class DownloadDataTests(unittest.TestCase):
    def test_default_download_writes_20_year_source_and_four_slices(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with mock.patch.object(
                download_data.yf,
                "download",
                return_value=sample_history(),
            ) as yahoo_download:
                download_data.main(
                    ["--tickers", "NVDA", "--out-dir", str(output_dir)]
                )

            self.assertEqual(yahoo_download.call_count, 1)
            request = yahoo_download.call_args.kwargs
            self.assertEqual(
                pd.Timestamp(request["end"]) - pd.DateOffset(years=20),
                pd.Timestamp(request["start"]),
            )

            source_path = output_dir / "NVDA.csv"
            self.assertTrue(source_path.exists())
            source = pd.read_csv(source_path, parse_dates=["Date"])
            source_end = source["Date"].max()
            metadata = download_data.load_download_metadata("NVDA", output_dir)
            self.assertEqual(metadata["last_refresh_mode"], "full")
            self.assertEqual(metadata["row_count"], len(source))

            for years in (10, 5, 4, 3):
                slice_path = output_dir / f"NVDA-{years}Y.csv"
                self.assertTrue(slice_path.exists())
                sliced = pd.read_csv(slice_path, parse_dates=["Date"])
                cutoff = source_end - pd.DateOffset(years=years)
                expected = source[source["Date"] >= cutoff]
                self.assertEqual(sliced["Date"].min(), expected["Date"].min())
                self.assertEqual(sliced["Date"].max(), source_end)
                self.assertEqual(len(sliced), len(expected))

    def test_incremental_refresh_replaces_overlap_and_appends_new_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            existing_raw = sample_history(pd.Timestamp.today() - pd.Timedelta(days=2))
            existing = download_data.validate_price_frame(existing_raw)
            existing.to_csv(output_dir / "NVDA.csv", index=False)
            full_metadata = download_data.build_download_metadata(
                "NVDA",
                existing,
                "full",
            )
            download_data.download_metadata_path(
                "NVDA", output_dir
            ).write_text(json.dumps(full_metadata), encoding="utf-8")

            latest_existing = existing["Date"].iloc[-1]
            requested_start = latest_existing - pd.Timedelta(days=90)
            recent = sample_history().reset_index()
            recent = recent[recent["Date"] >= requested_start].copy()
            overlap_date = recent["Date"].iloc[0]
            recent.loc[recent["Date"] == overlap_date, "Adj Close"] = 999999.0
            recent = recent.set_index("Date")

            with mock.patch.object(
                download_data.yf,
                "download",
                return_value=recent,
            ) as yahoo_download:
                csv_file, merged, slices, actual_mode = (
                    download_data.refresh_ticker_incrementally(
                        "NVDA",
                        20,
                        (5, 4, 3),
                        out_dir=output_dir,
                    )
                )

            self.assertEqual(actual_mode, "incremental")
            self.assertEqual(
                pd.Timestamp(yahoo_download.call_args.kwargs["start"]),
                requested_start.normalize(),
            )
            self.assertEqual(merged["Date"].iloc[-1], recent.index[-1])
            replaced = merged.loc[merged["Date"] == overlap_date, "Adj Close"]
            self.assertEqual(replaced.iloc[0], 999999.0)
            self.assertTrue(csv_file.exists())
            self.assertEqual(len(slices), 3)
            metadata = download_data.load_download_metadata("NVDA", output_dir)
            self.assertEqual(metadata["last_refresh_mode"], "incremental")
            self.assertEqual(metadata["last_full_refresh"], full_metadata["last_full_refresh"])
            self.assertEqual(metadata["incremental_overlap_days"], 90)

    def test_incremental_mode_runs_periodic_full_reconciliation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            existing = download_data.validate_price_frame(sample_history())
            existing.to_csv(output_dir / "NVDA.csv", index=False)
            old_full = (
                pd.Timestamp.now() - pd.Timedelta(days=31)
            ).isoformat()
            metadata = download_data.build_download_metadata(
                "NVDA",
                existing,
                "full",
            )
            metadata["last_full_refresh"] = old_full
            download_data.download_metadata_path(
                "NVDA", output_dir
            ).write_text(json.dumps(metadata), encoding="utf-8")

            with mock.patch.object(
                download_data.yf,
                "download",
                return_value=sample_history(),
            ) as yahoo_download:
                _, _, _, actual_mode = download_data.refresh_ticker_incrementally(
                    "NVDA",
                    20,
                    (5, 4, 3),
                    out_dir=output_dir,
                )

            self.assertEqual(actual_mode, "full")
            request = yahoo_download.call_args.kwargs
            self.assertEqual(
                pd.Timestamp(request["end"]) - pd.DateOffset(years=20),
                pd.Timestamp(request["start"]),
            )
            refreshed = download_data.load_download_metadata("NVDA", output_dir)
            self.assertEqual(refreshed["last_refresh_mode"], "full")
            self.assertNotEqual(refreshed["last_full_refresh"], old_full)

    def test_invalid_downloads_are_retried_without_replacing_existing_files(self):
        good = sample_history()
        invalid_frames = {
            "empty": good.iloc[0:0],
            "duplicate": pd.concat([good, good.iloc[[-1]]]),
            "unsorted": good.iloc[::-1],
            "missing": good.drop(columns=["Volume"]),
            "stale": sample_history(pd.Timestamp.today() - pd.Timedelta(days=10)),
        }
        for label, invalid in invalid_frames.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir)
                existing_source = output_dir / "NVDA.csv"
                existing_slice = output_dir / "NVDA-5Y.csv"
                existing_source.write_text("existing source", encoding="utf-8")
                existing_slice.write_text("existing slice", encoding="utf-8")

                with mock.patch.object(
                    download_data.yf,
                    "download",
                    return_value=invalid,
                ) as yahoo_download, mock.patch.object(
                    download_data.time,
                    "sleep",
                ) as retry_sleep:
                    with self.assertRaisesRegex(RuntimeError, "3 attempts"):
                        download_data.refresh_ticker_files(
                            "NVDA",
                            20,
                            (5, 4, 3),
                            out_dir=output_dir,
                        )

                self.assertEqual(yahoo_download.call_count, 3)
                self.assertEqual(retry_sleep.call_count, 2)
                self.assertEqual(
                    existing_source.read_text(encoding="utf-8"),
                    "existing source",
                )
                self.assertEqual(
                    existing_slice.read_text(encoding="utf-8"),
                    "existing slice",
                )

    def test_transient_failure_retries_then_replaces_complete_dataset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            (output_dir / "NVDA.csv").write_text("old", encoding="utf-8")
            with mock.patch.object(
                download_data.yf,
                "download",
                side_effect=[ConnectionError("temporary"), sample_history()],
            ) as yahoo_download, mock.patch.object(
                download_data.time,
                "sleep",
            ) as retry_sleep:
                download_data.refresh_ticker_files(
                    "NVDA",
                    20,
                    (5, 4, 3),
                    out_dir=output_dir,
                )

            self.assertEqual(yahoo_download.call_count, 2)
            retry_sleep.assert_called_once_with(2)
            source = pd.read_csv(output_dir / "NVDA.csv")
            self.assertGreater(len(source), 5000)
            for years in (5, 4, 3):
                self.assertTrue((output_dir / f"NVDA-{years}Y.csv").exists())

    def test_custom_years_and_derived_horizons_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with mock.patch.object(
                download_data.yf,
                "download",
                return_value=sample_history(),
            ) as yahoo_download:
                download_data.main(
                    [
                        "--tickers",
                        "NVDA",
                        "--out-dir",
                        str(output_dir),
                        "--years",
                        "10",
                        "--derive-years",
                        "5",
                        "3",
                    ]
                )

            request = yahoo_download.call_args.kwargs
            self.assertEqual(
                pd.Timestamp(request["end"]) - pd.DateOffset(years=10),
                pd.Timestamp(request["start"]),
            )
            self.assertTrue((output_dir / "NVDA-5Y.csv").exists())
            self.assertTrue((output_dir / "NVDA-3Y.csv").exists())
            self.assertFalse((output_dir / "NVDA-4Y.csv").exists())

    def test_derive_only_uses_existing_source_without_downloading(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            source = sample_history().reset_index()
            source.to_csv(output_dir / "NVDA.csv", index=False)

            with mock.patch.object(download_data.yf, "download") as yahoo_download:
                download_data.main(
                    [
                        "--tickers",
                        "NVDA",
                        "--out-dir",
                        str(output_dir),
                        "--derive-only",
                    ]
                )

            yahoo_download.assert_not_called()
            for years in (10, 5, 4, 3):
                self.assertTrue((output_dir / f"NVDA-{years}Y.csv").exists())


if __name__ == "__main__":
    unittest.main()
