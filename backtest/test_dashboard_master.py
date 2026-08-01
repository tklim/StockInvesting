import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

import dashboard_master


class DashboardMasterTests(unittest.TestCase):
    def test_hydrate_top_annualized_uses_best_strategy_or_buy_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            chart = tmp_path / "chart.png"
            chart.touch()
            history = tmp_path / "history.csv"
            pd.DataFrame(
                [
                    {
                        "run_id": "aapl-strategy-old",
                        "fund_label": "AAPL-3Y",
                        "adaptive_annualized_return_pct": 30,
                        "buy_hold_annualized_return_pct": 20,
                        "chart_file": chart,
                        "run_started_at": "2026-01-01",
                    },
                    {
                        "run_id": "aapl-buy-hold",
                        "fund_label": "AAPL",
                        "adaptive_annualized_return_pct": 32,
                        "buy_hold_annualized_return_pct": 35,
                        "chart_file": chart,
                        "run_started_at": "2026-02-01",
                    },
                    {
                        "run_id": "meta-strategy",
                        "fund_label": "META",
                        "adaptive_annualized_return_pct": 40,
                        "buy_hold_annualized_return_pct": 25,
                        "chart_file": chart,
                        "run_started_at": "2026-01-01",
                    },
                    {
                        "run_id": "jpm-strategy",
                        "fund_label": "JPM",
                        "adaptive_annualized_return_pct": 25,
                        "buy_hold_annualized_return_pct": 20,
                        "chart_file": chart,
                        "run_started_at": "2026-01-01",
                    },
                    {
                        "run_id": "jpm-buy-hold",
                        "fund_label": "JPM-3Y",
                        "adaptive_annualized_return_pct": 20,
                        "buy_hold_annualized_return_pct": 25,
                        "chart_file": chart,
                        "run_started_at": "2026-02-01",
                    },
                    {
                        "run_id": "tsla-buy-hold-only",
                        "fund_label": "TSLA",
                        "adaptive_annualized_return_pct": np.nan,
                        "buy_hold_annualized_return_pct": 10,
                        "chart_file": chart,
                        "run_started_at": "2026-01-01",
                    },
                ]
            ).to_csv(history, index=False)

            hydrated = dashboard_master.hydrate_top_annualized_metadata(
                [
                    {"fund_label": "AAPL"},
                    {"fund_label": "META"},
                    {"fund_label": "JPM"},
                    {"fund_label": "TSLA"},
                ],
                history,
            )

        by_ticker = {row["fund_label"]: row for row in hydrated}
        self.assertEqual(by_ticker["AAPL"]["top_annualized_return_pct"], 35)
        self.assertEqual(by_ticker["AAPL"]["top_annualized_winner"], "Buy & hold")
        self.assertEqual(
            by_ticker["AAPL"]["top_strategy_annualized_return_pct"], 32
        )
        self.assertEqual(
            by_ticker["AAPL"]["top_strategy_annualized_run_id"], "aapl-buy-hold"
        )
        self.assertEqual(
            by_ticker["AAPL"]["top_buy_hold_annualized_return_pct"], 35
        )
        self.assertEqual(by_ticker["META"]["top_annualized_return_pct"], 40)
        self.assertEqual(by_ticker["META"]["top_annualized_winner"], "Strategy")
        self.assertEqual(
            by_ticker["META"]["top_strategy_annualized_return_pct"], 40
        )
        self.assertEqual(
            by_ticker["META"]["top_buy_hold_annualized_return_pct"], 25
        )
        self.assertEqual(by_ticker["JPM"]["top_annualized_return_pct"], 25)
        self.assertEqual(by_ticker["JPM"]["top_annualized_winner"], "Buy & hold")
        self.assertEqual(
            by_ticker["JPM"]["top_strategy_annualized_run_id"], "jpm-strategy"
        )
        self.assertEqual(
            by_ticker["JPM"]["top_buy_hold_annualized_run_id"], "jpm-buy-hold"
        )
        self.assertNotIn("top_annualized_return_pct", by_ticker["TSLA"])
        self.assertNotIn(
            "top_strategy_annualized_return_pct", by_ticker["TSLA"]
        )
        self.assertEqual(
            by_ticker["TSLA"]["top_buy_hold_annualized_return_pct"], 10
        )

    def test_latest_stock_price_falls_back_to_source_csv_and_respects_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            prices = Path(tmp) / "AAPL.csv"
            pd.DataFrame(
                {
                    "Date": ["2026-07-28", "2026-07-30", "2026-07-31"],
                    "Adj Close": [100.0, 110.25, 120.0],
                }
            ).to_csv(prices, index=False)
            price, price_date = dashboard_master.latest_stock_price_from_row(
                {
                    "data_file": prices,
                    "price_column": "Adj Close",
                    "latest_data_end": "2026-07-30",
                }
            )

        self.assertEqual(price, 110.25)
        self.assertEqual(price_date, "2026-07-30")

    def test_latest_stock_price_handles_stored_missing_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            stored = dashboard_master.latest_stock_price_from_row(
                {
                    "latest_stock_price": 123.45,
                    "latest_stock_price_date": "2026-07-30",
                    "data_file": tmp_path / "missing.csv",
                }
            )
            missing = dashboard_master.latest_stock_price_from_row(
                {"data_file": tmp_path / "missing.csv", "price_column": "Adj Close"}
            )
            invalid_file = tmp_path / "invalid.csv"
            pd.DataFrame(
                {"Date": ["2026-07-30"], "Adj Close": ["not-a-number"]}
            ).to_csv(invalid_file, index=False)
            invalid = dashboard_master.latest_stock_price_from_row(
                {"data_file": invalid_file, "price_column": "Adj Close"}
            )

        self.assertEqual(stored, (123.45, "2026-07-30"))
        self.assertTrue(np.isnan(missing[0]))
        self.assertEqual(missing[1], "")
        self.assertTrue(np.isnan(invalid[0]))
        self.assertEqual(invalid[1], "")

    def test_master_dashboard_contains_sortable_metrics_and_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            results = [
                {
                    "status": "completed",
                    "fund_label": "AAPL",
                    "latest_data_end": "2026-07-30",
                    "latest_adaptive_annualized_return_pct": 59,
                    "latest_buy_hold_annualized_return_pct": 58,
                    "latest_excess_annualized_return_pct": 1,
                    "top_strategy_annualized_return_pct": 65,
                    "top_strategy_annualized_run_id": "aapl-strategy",
                    "top_strategy_annualized_data_end": "2026-07-29",
                    "top_buy_hold_annualized_return_pct": 60,
                    "top_buy_hold_annualized_run_id": "aapl-buy-hold",
                    "top_buy_hold_annualized_data_end": "2026-07-29",
                    "top_annualized_return_pct": 65,
                    "top_annualized_winner": "Strategy",
                    "top_annualized_run_id": "aapl-strategy",
                    "top_annualized_data_end": "2026-07-29",
                    "best_excess_annualized_return_pct": 8,
                    "best_excess_run_id": "aapl-best",
                    "latest_stock_price": 210.5,
                    "latest_stock_price_date": "2026-07-30",
                    "price_column": "Adj Close",
                    "ga_signal": "BUY/HOLD invested",
                },
                {
                    "status": "completed",
                    "fund_label": "META",
                    "latest_data_end": "2026-07-30",
                    "latest_adaptive_annualized_return_pct": 55,
                    "latest_buy_hold_annualized_return_pct": 40,
                    "latest_excess_annualized_return_pct": 15,
                    "top_strategy_annualized_return_pct": 68,
                    "top_strategy_annualized_run_id": "meta-strategy",
                    "top_strategy_annualized_data_end": "2026-07-29",
                    "top_buy_hold_annualized_return_pct": 70,
                    "top_buy_hold_annualized_run_id": "meta-buy-hold",
                    "top_buy_hold_annualized_data_end": "2026-07-29",
                    "top_annualized_return_pct": 70,
                    "top_annualized_winner": "Buy & hold",
                    "top_annualized_run_id": "meta-buy-hold",
                    "top_annualized_data_end": "2026-07-29",
                    "best_excess_annualized_return_pct": 20,
                    "best_excess_run_id": "meta-best",
                    "latest_stock_price": "",
                    "latest_stock_price_date": "",
                    "price_column": "Adj Close",
                    "ga_signal": "SELL/CASH",
                },
            ]
            with mock.patch.object(dashboard_master, "REPORTS_DIR", tmp_path):
                output = dashboard_master.write_master_dashboard(
                    results, tmp_path / "summary.csv", []
                )
            page = output.read_text(encoding="utf-8")

        self.assertLess(
            page.index('data-ticker="AAPL"'), page.index('data-ticker="META"')
        )
        self.assertIn('data-latest-strategy="59"', page)
        self.assertIn('data-top-strategy="65"', page)
        self.assertIn('data-top-buy-hold="60"', page)
        self.assertIn('data-top-annualized="65"', page)
        self.assertIn('data-top-excess="8"', page)
        self.assertIn('data-last-price="210.5"', page)
        self.assertIn('data-last-price=""', page)
        self.assertIn("<small>Latest strategy</small>", page)
        self.assertIn("<small>Top strategy ann.</small>", page)
        self.assertIn("<small>Top buy &amp; hold ann.</small>", page)
        self.assertIn("<small>Top annualized</small>", page)
        self.assertIn(
            "Best historical strategy annualized run aapl-strategy through 2026-07-29",
            page,
        )
        self.assertIn(
            "Best historical buy &amp; hold annualized run aapl-buy-hold through 2026-07-29",
            page,
        )
        self.assertIn("<small>Top excess</small>", page)
        self.assertIn("<small>Last price</small><strong>$210.50</strong>", page)
        self.assertIn(
            'data-sort-key="latestStrategy" aria-pressed="true"', page
        )
        self.assertIn(
            'data-sort-key="topStrategy" aria-pressed="false"', page
        )
        self.assertIn(
            'data-sort-key="topBuyHold" aria-pressed="false"', page
        )
        self.assertIn(
            'data-sort-key="topAnnualized" aria-pressed="false"', page
        )
        self.assertIn('data-sort-key="topExcess" aria-pressed="false"', page)
        self.assertIn('href="dashboard_excess_annualized.html"', page)
        self.assertIn("Excess annualized ranking", page)
        self.assertIn('data-sort-key="lastPrice" aria-pressed="false"', page)
        self.assertIn(
            "if (leftValue === null && rightValue !== null) return 1;", page
        )
        self.assertIn("row.querySelector('.rank').textContent", page)
        self.assertIn("stockDashboard.visibleColumns.v1", page)
        self.assertIn('data-column-toggle="topStrategy"', page)
        self.assertIn('data-column-toggle="topBuyHold"', page)
        self.assertIn("Reset responsive defaults", page)
        self.assertIn('href="dashboard_top_annualized_buyhold.html"', page)
        self.assertIn("Buy &amp; hold horizons", page)
        self.assertIn("window.localStorage.getItem(storageKey)", page)
        self.assertIn("window.localStorage.setItem(storageKey", page)
        self.assertIn("parsed.every((key) => columnKeys.includes(key))", page)
        self.assertIn("window.localStorage.removeItem(storageKey)", page)
        self.assertIn("window.addEventListener('resize'", page)
        self.assertIn("if (window.innerWidth > 1050)", page)
        self.assertIn("if (window.innerWidth > 650)", page)
        self.assertIn("grid-template-columns:repeat(auto-fit", page)
        self.assertIn("applySort();", page)


if __name__ == "__main__":
    unittest.main()
