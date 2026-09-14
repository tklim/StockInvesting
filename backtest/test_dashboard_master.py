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
                    "latest_max_dd_pct": 36.88,
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
                    "latest_max_dd_pct": 20.5,
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
        self.assertIn('data-top-excess="8"', page)
        self.assertIn('data-max-drawdown="36.88"', page)
        self.assertIn('data-last-price="210.5"', page)
        self.assertIn('data-last-price=""', page)
        # Column labels live in a single sticky header row, not in every row.
        self.assertIn(
            'data-column="latestStrategy">Latest strategy <i class="info"', page
        )
        self.assertIn(
            "archived winning walk-forward schedule is reproduced, then adaptively continued",
            page,
        )
        self.assertIn('<span data-column="topStrategy">Strategy ann.', page)
        self.assertIn('<span data-column="topBuyHold">B&amp;H ann.', page)
        self.assertIn(
            'data-column="maxDrawdown">Drawdown <i class="info"', page
        )
        self.assertIn(
            "Maximum peak-to-trough decline in strategy NAV during the latest replay",
            page,
        )
        self.assertIn(
            "Best historical strategy annualized run aapl-strategy through 2026-07-29",
            page,
        )
        self.assertIn(
            "Best historical buy &amp; hold annualized run aapl-buy-hold through 2026-07-29",
            page,
        )
        # The combined top-annualized figure renders as a winner badge on the
        # winning column: AAPL's strategy won, META's buy & hold won.
        aapl_row = page[page.index('data-ticker="AAPL"'):page.index('data-ticker="META"')]
        meta_row = page[page.index('data-ticker="META"'):]
        self.assertIn('+65.00%<span class="win"', aapl_row)
        self.assertIn('+70.00%<span class="win"', meta_row)
        self.assertNotIn('data-column="topAnnualized"', page)
        # Drawdown reads as a loss; positive returns are tinted green.
        self.assertIn('<span class="val neg">−36.88%</span>', page)
        self.assertIn('<span class="val pos">+59.00%</span>', page)
        self.assertIn('<span class="val">$210.50</span>', page)
        # Signal renders as a compact status chip beside the ticker.
        self.assertIn('<span class="chip buy"><span class="dot"></span>BUY</span>', page)
        self.assertIn('<span class="chip cash"><span class="dot"></span>CASH</span>', page)
        self.assertIn(
            'data-sort-key="latestStrategy" aria-pressed="true"', page
        )
        self.assertIn(
            'data-sort-key="topStrategy" aria-pressed="false"', page
        )
        self.assertIn(
            'data-sort-key="topBuyHold" aria-pressed="false"', page
        )
        self.assertIn('data-sort-key="topExcess" aria-pressed="false"', page)
        self.assertNotIn('data-sort-key="topAnnualized"', page)
        self.assertIn('href="dashboard_excess_annualized.html"', page)
        self.assertIn("Excess annualized ranking", page)
        self.assertIn('data-sort-key="lastPrice" aria-pressed="false"', page)
        self.assertIn('data-sort-key="maxDrawdown" aria-pressed="false"', page)
        self.assertIn(
            "if (leftValue === null && rightValue !== null) return 1;", page
        )
        self.assertIn("row.querySelector('.rank').textContent", page)
        self.assertIn("stockDashboard.visibleColumns.v2", page)
        self.assertIn('data-column-toggle="topStrategy"', page)
        self.assertIn('data-column-toggle="topBuyHold"', page)
        self.assertIn('data-column-toggle="maxDrawdown"', page)
        self.assertIn("'topExcess','maxDrawdown','lastPrice'", page)
        self.assertIn("Reset responsive defaults", page)
        self.assertIn('href="dashboard_top_annualized_buyhold.html"', page)
        self.assertIn("Buy &amp; hold horizons", page)
        self.assertIn('href="dashboard_stock_selection.html"', page)
        self.assertIn("Long-term stock selection", page)
        self.assertIn(
            'href="https://stock-investing-avpuzw7i0-tklims-projects.vercel.app/"',
            page,
        )
        self.assertIn('>Company Research ↗</a>', page)
        self.assertIn('rel="noopener noreferrer"', page)
        self.assertIn("window.localStorage.getItem(storageKey)", page)
        self.assertIn("window.localStorage.setItem(storageKey", page)
        self.assertIn("parsed.every((key) => columnKeys.includes(key))", page)
        self.assertIn("window.localStorage.removeItem(storageKey)", page)
        self.assertIn("window.addEventListener('resize'", page)
        self.assertIn("if (window.innerWidth > 1050)", page)
        self.assertIn("if (window.innerWidth > 650)", page)
        self.assertIn("grid-template-columns:repeat(auto-fit", page)
        self.assertIn("applySort();", page)
        # Drawdown sorts best-first (smallest loss) by default.
        self.assertIn("defaultDirections = {maxDrawdown: 'asc'}", page)
        self.assertIn("direction = defaultDirections[sortKey] || 'desc';", page)
        # Sorting by a hidden column reveals it.
        self.assertIn("if (!visibleColumns.has(sortKey))", page)
        # The active sort column is highlighted in header and rows.
        self.assertIn("cell.classList.toggle('sorted', cell.dataset.column === sortKey)", page)
        # Dark mode: token overrides, persisted toggle, and pre-paint init.
        self.assertIn('[data-theme="dark"]', page)
        self.assertIn("stockDashboard.theme.v1", page)
        self.assertIn('id="themeToggle"', page)
        self.assertIn("prefers-color-scheme: dark", page)
        # Mobile defaults keep at least two metric columns visible.
        self.assertIn("return ['latestStrategy','topExcess'];", page)

    def test_fund_dashboard_links_to_buy_hold_ranking(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            row = {
                "fund_label": "NVDA",
                "data_file": "NVDA.csv",
                "latest_data_end": "2026-07-31",
                "ga_signal": "SELL/CASH",
            }
            with mock.patch.object(dashboard_master, "FUND_REPORTS_DIR", tmp_path):
                output = dashboard_master.write_fund_dashboard(
                    row, tmp_path / "summary.csv"
                )
            page = output.read_text(encoding="utf-8")

        self.assertIn(
            '<a href="../dashboard_top_annualized_buyhold.html">'
            "Top buy &amp; hold</a>",
            page,
        )
        self.assertIn(
            '<a href="../dashboard_stock_selection.html">Stock selection</a>',
            page,
        )
        self.assertNotIn('Open full screen', page)
        self.assertIn('dialog{display:grid;grid-template-rows:auto minmax(0,1fr)}', page)
        self.assertIn('#viewerImage{display:block;max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain}', page)

    def test_selection_dashboard_still_refreshes_without_run_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            expected_html = tmp_path / "selection.html"
            expected_csv = tmp_path / "selection.csv"
            with (
                mock.patch.object(dashboard_master, "HISTORY_FILE", tmp_path / "missing.csv"),
                mock.patch.object(
                    dashboard_master.selection_dashboard,
                    "build_selection_dashboard",
                    return_value={"html": expected_html, "csv": expected_csv},
                ) as build_selection,
            ):
                generated, warnings = dashboard_master.refresh_companion_dashboards(
                    tmp_path / "summary.csv"
                )

        build_selection.assert_called_once_with(
            summary_file=str(tmp_path / "summary.csv")
        )
        self.assertEqual(generated["selection"], expected_html)
        self.assertEqual(generated["selection_csv"], expected_csv)
        self.assertTrue(any("Run history not found" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
