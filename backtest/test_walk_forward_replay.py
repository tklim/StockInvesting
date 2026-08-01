import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

import final_backtest_from_summary as final_report
from walk_forward_replay import (
    METRIC_TOLERANCE_PCT,
    assert_metrics_match,
    load_replay_artifacts,
    load_schedule_from_tuning_history,
    normalize_schedule,
    replay_parameter_schedule,
    save_replay_artifacts,
)


SCRIPT_DIR = Path(__file__).resolve().parent
V_RUN_ID = "20260726185629_V-4Y_57209da0"


class WalkForwardReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        module_path = SCRIPT_DIR / "backtest_stocks.py"
        spec = importlib.util.spec_from_file_location("replay_test_backtester", module_path)
        cls.bt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bt)

    def test_v_winner_replays_exactly(self):
        source = pd.read_csv(SCRIPT_DIR / "data" / "V.csv")
        source["Date"] = pd.to_datetime(source["Date"])
        source = source[
            (source["Date"] >= "2022-07-25")
            & (source["Date"] <= "2026-07-24")
        ].copy()
        source["NAV"] = pd.to_numeric(source["Adj Close"])
        source = source.set_index("Date")
        schedule = load_schedule_from_tuning_history(
            SCRIPT_DIR / "outputs" / "tunings" / "backtest_tuning_history.csv",
            V_RUN_ID,
        )
        result = replay_parameter_schedule(
            source,
            schedule,
            10000,
            "generic",
            self.bt.backtest_enhanced_dual_ema,
            self.bt.calculate_index_strategy_metrics,
            self.bt.DEFAULT_RSI_PERIOD,
        )
        self.assertEqual(result["window_count"], 4)
        self.assertEqual(len(result["adaptive_df"]), 251)
        self.assertEqual(result["trade_count"], 21)
        self.assertAlmostEqual(
            result["metrics"]["adaptive_return"],
            2.4706156255273526,
            delta=METRIC_TOLERANCE_PCT,
        )
        self.assertAlmostEqual(
            result["metrics"]["excess_annualized_return"],
            2.0548608360872134,
            delta=METRIC_TOLERANCE_PCT,
        )

    def test_schedule_rejects_duplicate_windows_and_gaps(self):
        valid = pd.DataFrame(
            [
                {
                    "window_sequence": 1,
                    "train_start": "2024-01-01",
                    "train_end": "2025-01-01",
                    "test_start": "2025-01-01",
                    "test_end": "2025-04-01",
                    "test_end_exclusive": "2025-04-01",
                    "short_ema": 5,
                    "long_ema": 50,
                    "stop_loss": 10,
                    "cooldown": 1,
                    "drawdown_exit_pct": 3,
                    "reentry_rebound_pct": 2,
                    "rsi_oversold": 20,
                    "rsi_overbought": 80,
                    "exposure_multiplier": 1,
                },
                {
                    "window_sequence": 2,
                    "train_start": "2024-04-01",
                    "train_end": "2025-04-01",
                    "test_start": "2025-04-01",
                    "test_end": "2025-07-01",
                    "test_end_exclusive": "2025-07-01",
                    "short_ema": 8,
                    "long_ema": 80,
                    "stop_loss": 9,
                    "cooldown": 2,
                    "drawdown_exit_pct": 3,
                    "reentry_rebound_pct": 2,
                    "rsi_oversold": 25,
                    "rsi_overbought": 75,
                    "exposure_multiplier": 1,
                },
            ]
        )
        self.assertEqual(len(normalize_schedule(valid)), 2)
        duplicate = valid.copy()
        duplicate.loc[1, "window_sequence"] = 1
        with self.assertRaisesRegex(ValueError, "duplicate"):
            normalize_schedule(duplicate)
        gap = valid.copy()
        gap.loc[1, ["train_end", "test_start"]] = "2025-04-02"
        with self.assertRaisesRegex(ValueError, "gap or overlap"):
            normalize_schedule(gap)

    def test_snapshot_hash_is_enforced(self):
        schedule = load_schedule_from_tuning_history(
            SCRIPT_DIR / "outputs" / "tunings" / "backtest_tuning_history.csv",
            V_RUN_ID,
        )
        source = pd.read_csv(SCRIPT_DIR / "data" / "V.csv").head(10)
        source["NAV"] = source["Adj Close"]
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            metadata = save_replay_artifacts(
                source, schedule, base, "V", "hash-test"
            )
            load_replay_artifacts(metadata, base)
            snapshot = base / metadata["source_snapshot_file"]
            snapshot.write_text(
                snapshot.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                load_replay_artifacts(metadata, base)

    def test_metric_match_accepts_bounded_legacy_drift(self):
        expected = {
            "source_adaptive_return_pct": 10.0,
            "source_buy_hold_return_pct": 5.0,
            "source_excess_return_pct": 5.0,
            "source_adaptive_annualized_return_pct": 4.0,
            "source_buy_hold_annualized_return_pct": 2.0,
            "source_excess_annualized_return_pct": 2.0,
        }
        actual = {
            "adaptive_return": 10.00005,
            "buy_hold_return": 5.00005,
            "excess_return": 5.00005,
            "adaptive_annualized_return": 4.00005,
            "buy_hold_annualized_return": 2.00005,
            "excess_annualized_return": 2.00005,
        }
        assert_metrics_match(actual, expected)

        actual["excess_return"] = 5.002
        with self.assertRaisesRegex(ValueError, "excess_return"):
            assert_metrics_match(actual, expected)

    def test_incremental_provenance_is_not_exact_replay_eligible(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            candidate = output_dir / "NVDA.csv"
            candidate.write_text("Date,Adj Close\n2026-01-01,1\n", encoding="utf-8")
            metadata_path = output_dir / "NVDA.download-meta.json"
            metadata_path.write_text(
                json.dumps(
                    {
                        "ticker": "NVDA",
                        "last_refresh_mode": "incremental",
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(
                final_report.is_incrementally_merged_candidate(candidate, "NVDA")
            )

            snapshot = output_dir / "source_snapshot.csv"
            snapshot.write_text(candidate.read_text(encoding="utf-8"), encoding="utf-8")
            self.assertFalse(
                final_report.is_incrementally_merged_candidate(snapshot, "NVDA")
            )

            metadata_path.write_text(
                json.dumps(
                    {
                        "ticker": "NVDA",
                        "last_refresh_mode": "full",
                    }
                ),
                encoding="utf-8",
            )
            self.assertFalse(
                final_report.is_incrementally_merged_candidate(candidate, "NVDA")
            )

            metadata_path.write_text("{invalid", encoding="utf-8")
            self.assertTrue(
                final_report.is_incrementally_merged_candidate(candidate, "NVDA")
            )

    def test_csv_ga_seed_is_normalized_before_numpy_or_pygad(self):
        self.assertEqual(self.bt.normalize_ga_seed("42"), 42)
        self.assertEqual(self.bt.normalize_ga_seed("42.0"), 42)
        self.assertEqual(self.bt.normalize_ga_seed(42), 42)
        self.assertIsNone(self.bt.normalize_ga_seed("deterministic"))
        self.assertIsNone(self.bt.normalize_ga_seed(""))
        with self.assertRaisesRegex(ValueError, "must be an integer"):
            self.bt.normalize_ga_seed("42.5")
        with self.assertRaisesRegex(ValueError, "Invalid GA seed"):
            self.bt.normalize_ga_seed("seed")

    def test_adaptive_continuation_adds_boundary_window(self):
        schedule = pd.DataFrame(
            [
                {
                    "window_sequence": 1,
                    "train_start": "2024-01-01",
                    "train_end": "2025-01-01",
                    "test_start": "2025-01-01",
                    "test_end": "2025-03-31",
                    "test_end_exclusive": "2025-04-01",
                    "offset_months": 3,
                    "short_ema": 5,
                    "long_ema": 50,
                    "stop_loss": 10,
                    "cooldown": 1,
                    "drawdown_exit_pct": 3,
                    "reentry_rebound_pct": 2,
                    "rsi_oversold": 20,
                    "rsi_overbought": 80,
                    "rsi_period": 14,
                    "exposure_multiplier": 1,
                }
            ]
        )
        dates = pd.bdate_range("2024-01-01", "2025-04-04")
        data = pd.DataFrame({"NAV": range(len(dates))}, index=dates)
        row = {
            "lookback_years": 1,
            "offset_months": 3,
            "pop_ranges": "4",
            "gen_ranges": "2",
            "ga_seed": "deterministic",
        }
        params = {
            "short_ema": 6,
            "long_ema": 60,
            "stop_loss": 9,
            "cooldown": 2,
            "drawdown_exit_pct": 3,
            "reentry_rebound_pct": 2,
            "rsi_oversold": 25,
            "rsi_overbought": 75,
            "rsi_period": 14,
            "exposure_multiplier": 1,
        }
        with mock.patch.object(
            final_report.bt,
            "tune_ga_hyperparams",
            return_value=((4, 2, 0.01, 0.8), params),
        ) as tune_mock:
            continued, count = final_report.build_adaptive_continuation_schedule(
                schedule, data, row, 10000, "generic"
            )
        self.assertIsNone(tune_mock.call_args.kwargs["ga_seed_value"])
        self.assertEqual(count, 1)
        self.assertEqual(len(continued), 2)
        self.assertEqual(continued.iloc[-1]["test_start"], pd.Timestamp("2025-04-01"))

        row["ga_seed"] = "42"
        with mock.patch.object(
            final_report.bt,
            "tune_ga_hyperparams",
            return_value=((4, 2, 0.01, 0.8), params),
        ) as tune_mock:
            final_report.build_adaptive_continuation_schedule(
                schedule, data, row, 10000, "generic"
            )
        self.assertEqual(tune_mock.call_args.kwargs["ga_seed_value"], 42)


if __name__ == "__main__":
    unittest.main()
