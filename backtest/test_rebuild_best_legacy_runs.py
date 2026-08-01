import tempfile
import unittest
from pathlib import Path

import pandas as pd

import final_backtest_from_summary as final_report
import rebuild_best_legacy_runs as rebuild
from walk_forward_replay import (
    assert_metrics_match,
    load_replay_artifacts,
    load_recorded_schedule,
    load_schedule_from_tuning_history_with_metadata,
)


SCRIPT_DIR = Path(__file__).resolve().parent


def schedule_row(**overrides):
    row = {
        "run_id": "run-1",
        "window_sequence": 1,
        "train_start": "2024-01-01",
        "train_end": "2025-01-01",
        "test_start": "2025-01-01",
        "test_end": "2025-03-31",
        "test_end_exclusive": "2025-04-01",
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
    row.update(overrides)
    return row


class SelectiveLegacyRebuildTests(unittest.TestCase):
    def test_applied_window_history_has_priority(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            windows = base / "windows.csv"
            tuning = base / "tuning.csv"
            pd.DataFrame([schedule_row(short_ema=7)]).to_csv(windows, index=False)
            pd.DataFrame(
                [
                    schedule_row(
                        short_ema=31,
                        best=True,
                        pop_size=4,
                        generations=2,
                        mutation_rate=0.01,
                        crossover_rate=0.6,
                    )
                ]
            ).to_csv(tuning, index=False)
            schedule, source = load_recorded_schedule(
                windows,
                tuning,
                "run-1",
                {"reuse_tuned_params": True},
            )
        self.assertEqual(source, "window_history")
        self.assertEqual(int(schedule.iloc[0]["short_ema"]), 7)

    def test_tuning_tie_uses_original_grid_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tuning = Path(temp_dir) / "tuning.csv"
            later = schedule_row(
                short_ema=31,
                best=True,
                score=10,
                pop_size=4,
                generations=2,
                mutation_rate=0.05,
                crossover_rate=0.6,
            )
            first = schedule_row(
                short_ema=11,
                best=True,
                score=10,
                pop_size=4,
                generations=2,
                mutation_rate=0.01,
                crossover_rate=0.6,
            )
            pd.DataFrame([later, first]).to_csv(tuning, index=False)
            schedule = load_schedule_from_tuning_history_with_metadata(
                tuning,
                "run-1",
                {
                    "reuse_tuned_params": True,
                    "pop_ranges": "4",
                    "gen_ranges": "2",
                    "mutation_rates": "0.01,0.05",
                    "crossover_rates": "0.6",
                },
            )
        self.assertEqual(len(schedule), 1)
        self.assertEqual(int(schedule.iloc[0]["short_ema"]), 11)

    def test_latest_command_preserves_configuration_and_lineage(self):
        row = pd.Series(
            {
                "ticker": "TEST",
                "selected_source_run_id": "legacy-1",
                "rebuild_batch_id": "batch-1",
                "input_snapshot_file": "C:/tmp/TEST.csv",
                "lookback_years": 3,
                "offset_months": 6,
                "initial_capital": 12000,
                "price_column": "Adj Close",
                "strategy_profile": "generic",
                "profile_override_preset": "default",
                "ga_search_preset": "grid",
                "pop_ranges": "4,6",
                "gen_ranges": "2,3",
                "ga_seed": "42",
                "mutation_rates": "0.01,0.05",
                "crossover_rates": "0.6,0.8",
                "reuse_tuned_params": True,
                "short_ema_min": 2,
                "short_ema_max": 60,
                "long_ema_min": 30,
                "long_ema_max": 300,
                "rsi_oversold_min": 10,
                "rsi_oversold_max": 40,
                "rsi_overbought_min": 60,
                "rsi_overbought_max": 90,
                "stop_loss_min": 8,
                "stop_loss_max": 15,
                "cooldown_min": 0,
                "cooldown_max": 3,
            }
        )
        command = rebuild.build_latest_command(row, "python")
        joined = " ".join(command)
        self.assertIn("--rebuild-source-run-id legacy-1", joined)
        self.assertIn("--rebuild-batch-id batch-1", joined)
        self.assertIn("--rebuild-mode latest_data", joined)
        self.assertIn("--lookback-years 3", joined)
        self.assertIn("--offset-months 6", joined)
        self.assertIn("--pop_ranges 4 6", joined)
        self.assertIn("--gen_ranges 2 3", joined)
        self.assertIn("--ga-seed 42", joined)
        self.assertIn("--reuse-tuned-params", command)

    def test_frozen_input_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "TEST.csv"
            path.write_text("Date,Adj Close\n2026-01-01,1\n", encoding="utf-8")
            row = pd.Series(
                {
                    "input_snapshot_file": str(path),
                    "input_snapshot_sha256": "wrong",
                }
            )
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                rebuild.verify_frozen_input(row)

    def test_csv_status_frames_allow_mixed_type_updates(self):
        frame = pd.DataFrame(
            {
                "status": [float("nan")],
                "count": pd.Series([""], dtype="str"),
            }
        )
        mutable = rebuild.mutable_frame(frame)
        mutable.loc[0, "status"] = "exact_replay"
        mutable.loc[0, "count"] = 8
        self.assertEqual(mutable.loc[0, "status"], "exact_replay")
        self.assertEqual(mutable.loc[0, "count"], 8)

    def test_exact_history_update_adds_numeric_metadata_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "history.csv"
            pd.DataFrame(
                [{"run_id": "legacy-1", "replay_status": ""}]
            ).to_csv(history_path, index=False)
            rebuild.update_exact_history(
                "legacy-1",
                "ZZTEST",
                {
                    "replay_schema_version": 1,
                    "schedule_window_count": 8,
                    "source_snapshot_file": "outputs/snapshot.csv",
                },
                history_path,
            )
            updated = pd.read_csv(history_path)
        self.assertEqual(updated.iloc[0]["replay_status"], "exact_replay")
        self.assertEqual(int(updated.iloc[0]["replay_schema_version"]), 1)
        self.assertEqual(int(updated.iloc[0]["schedule_window_count"]), 8)

    def test_batch_lock_rejects_concurrent_resume(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "manifest.csv"
            manifest.write_text("ticker\nTEST\n", encoding="utf-8")
            with rebuild.batch_lock(manifest):
                with self.assertRaisesRegex(RuntimeError, "already active"):
                    with rebuild.batch_lock(manifest):
                        pass

    def test_live_v_and_jnj_artifacts_are_complete(self):
        history = final_report.normalize_run_history(
            pd.read_csv(
                SCRIPT_DIR / "outputs" / "tunings" / "backtest_run_history.csv",
                low_memory=False,
            )
        )
        winners = final_report.select_best_run_rows(history, top_funds=0)
        by_ticker = {
            row["canonical_fund_label"]: row
            for _, row in winners.iterrows()
        }

        v = by_ticker["V"]
        v_metadata = final_report.artifact_metadata_for_row(v, "V")
        self.assertIsNotNone(v_metadata)
        _, v_schedule, _, _ = load_replay_artifacts(
            v_metadata,
            final_report.REPO_ROOT,
        )
        self.assertEqual(len(v_schedule), 4)

        jnj = by_ticker["JNJ"]
        jnj_metadata = final_report.artifact_metadata_for_row(jnj, "JNJ")
        self.assertIsNotNone(jnj_metadata)
        _, jnj_schedule, _, _ = load_replay_artifacts(
            jnj_metadata,
            final_report.REPO_ROOT,
        )
        self.assertEqual(len(jnj_schedule), 8)

    def test_near_match_beyond_metric_tolerance_is_rejected(self):
        actual = {
            "adaptive_return": 10.0,
            "buy_hold_return": 8.0,
            "excess_return": 2.0,
            "adaptive_annualized_return": 5.0011,
            "buy_hold_annualized_return": 4.0,
            "excess_annualized_return": 1.0011,
        }
        expected = {
            "source_adaptive_return_pct": 10.0,
            "source_buy_hold_return_pct": 8.0,
            "source_excess_return_pct": 2.0,
            "source_adaptive_annualized_return_pct": 5.0,
            "source_buy_hold_annualized_return_pct": 4.0,
            "source_excess_annualized_return_pct": 1.0,
        }
        with self.assertRaisesRegex(ValueError, "do not match"):
            assert_metrics_match(actual, expected)


if __name__ == "__main__":
    unittest.main()
