import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import dashboard_stock_selection_backtest as backtest


class StockSelectionBacktestTests(unittest.TestCase):
    def write_prices(self, directory, ticker, annual_growth):
        dates = pd.date_range("2004-01-01", "2026-08-01", freq="BMS")
        years = np.arange(len(dates)) / 12.0
        prices = 100.0 * np.power(1.0 + annual_growth, years)
        pd.DataFrame({"Date": dates, "Adj Close": prices}).to_csv(
            Path(directory) / f"{ticker}.csv", index=False
        )

    def fixture(self, directory):
        specs = {
            "AAA": (0.18, "Technology"),
            "BBB": (0.15, "Technology"),
            "CCC": (0.12, "Industrial"),
            "DDD": (0.08, "Industrial"),
            "SPY": (0.07, "Benchmark"),
            "QQQ": (0.09, "Benchmark"),
        }
        tickers_path = Path(directory) / "tickers.txt"
        metadata_path = Path(directory) / "groups.csv"
        tickers_path.write_text("\n".join(specs) + "\n", encoding="utf-8")
        rows = []
        for ticker, (growth, group) in specs.items():
            self.write_prices(directory, ticker, growth)
            rows.append((ticker, "benchmark" if ticker in {"SPY", "QQQ"} else "candidate", group))
        pd.DataFrame(rows, columns=["ticker", "role", "industry_group"]).to_csv(
            metadata_path, index=False
        )
        return tickers_path, metadata_path

    def test_cli_defaults_to_one_two_and_three_year_comparisons(self):
        args = backtest.parse_args([])
        self.assertEqual(args.years_ago, (1, 2, 3))
        self.assertEqual(args.holding_years, (1,))
        self.assertEqual(args.execution_lag_sessions, 1)
        self.assertEqual(args.one_way_cost_bps, 10.0)
        self.assertEqual(args.random_portfolios, 5000)
        self.assertEqual(args.group_cap, 3)
        self.assertEqual(backtest.parse_args(["--years-ago", "2"]).years_ago, [2])

    def test_build_and_render_compare_historical_shortlists(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tickers_path, metadata_path = self.fixture(tmp_path)
            result = backtest.build_selection_backtest(
                tickers_file=tickers_path,
                metadata_file=metadata_path,
                data_dir=tmp_path,
                years_ago=(1, 2, 3),
                holding_years=(1,),
                walk_forward_years=3,
                random_portfolios=50,
                shortlist_size=4,
                group_cap=2,
            )
            html_path = backtest.render_selection_backtest(result, tmp_path / "report.html")
            csv_path = backtest.write_backtest_csv(result["export"], tmp_path / "report.csv")
            page = html_path.read_text(encoding="utf-8")
            exported = pd.read_csv(csv_path)

        self.assertEqual(
            [(report["years_ago"], report["review_years_ago"]) for report in result["reports"]],
            [(1, 0), (2, 1), (3, 2)],
        )
        self.assertGreater(len(result["export"]), 12)
        self.assertEqual(set(exported["years_ago"].dropna().astype(int)), {1, 2, 3})
        self.assertEqual(set(exported["review_years_ago"].dropna().astype(int)), {0, 1, 2})
        review_end_dates = {0: "2026-07-01", 1: "2025-07-01", 2: "2024-07-01"}
        for report in result["reports"]:
            self.assertEqual(len(report["historical_tickers"]), 4)
            self.assertEqual(len(report["review_tickers"]), 4)
            self.assertTrue(
                report["holdings"]["end_date"].eq(
                    review_end_dates[report["review_years_ago"]]
                ).all()
            )
            self.assertTrue(
                report["holdings"]["start_date"].lt(report["holdings"]["end_date"]).all()
            )
            self.assertTrue(np.isfinite(report["historical_portfolio_return_pct"]))
            self.assertTrue(np.isfinite(report["review_portfolio_return_pct"]))
        self.assertIn("1Y-ago selection held to Current", page)
        self.assertIn("2Y-ago selection held to 1Y ago", page)
        self.assertIn("3Y-ago selection held to 2Y ago", page)
        self.assertIn("Current top-10 hindsight", page)
        self.assertIn("Annual walk-forward evidence", page)
        self.assertIn("Annually refreshed top 10", page)
        self.assertIn("Predeclared model ablations", page)
        self.assertIn("Exploratory", page)
        self.assertIn("Random-portfolio percentile", page)
        self.assertIn("Benchmark excess vs SPY", page)
        self.assertIn("Benchmark excess vs QQQ", page)
        self.assertIn("Score predictive correlation", page)
        self.assertIn("Contribution concentration", page)
        self.assertIn("Cumulative NAV", page)
        self.assertIn("Outside current top 10", page)
        self.assertIn('class="outside-note"', page)
        self.assertIn("price-derived paper portfolios", page)
        self.assertNotRegex(page, r"(?i)>\s*nan\s*<")
        self.assertNotIn("Infinity", page)
        self.assertEqual(set(result["model_evaluation"]["model"]), set(backtest.MODEL_NAMES))
        self.assertFalse(result["model_evaluation"]["promotion_passed"].any())
        self.assertIn("baseline retained", result["promotion_decision"])

    def test_rejects_holding_periods_longer_than_one_year(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tickers_path, metadata_path = self.fixture(tmp_path)
            with self.assertRaisesRegex(ValueError, "exactly a one-year holding horizon"):
                backtest.build_selection_backtest(
                    tickers_file=tickers_path,
                    metadata_file=metadata_path,
                    data_dir=tmp_path,
                    years_ago=(1,),
                    holding_years=(3,),
                    walk_forward_years=3,
                    random_portfolios=5,
                    shortlist_size=4,
                    group_cap=2,
                )

    def test_next_session_costs_and_nav_reconcile(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tickers_path, _ = self.fixture(tmp_path)
            tickers = [ticker for ticker in tickers_path.read_text().splitlines() if ticker]
            prices = backtest.selection.load_price_universe(tickers, tmp_path)
            calendar = backtest._benchmark_calendar(prices, "SPY")
            portfolio = backtest.build_portfolio(
                "fixture",
                "selected",
                ["AAA", "BBB"],
                prices,
                calendar,
                pd.Timestamp("2025-07-01"),
                pd.Timestamp("2026-07-01"),
                execution_lag_sessions=1,
                one_way_cost_bps=10.0,
            )

        self.assertEqual(portfolio["entry_date"].strftime("%Y-%m-%d"), "2025-08-01")
        self.assertEqual(portfolio["exit_date"].strftime("%Y-%m-%d"), "2026-07-01")
        holding_mean = portfolio["holdings"]["net_return_pct"].mean()
        self.assertAlmostEqual(portfolio["metrics"]["total_return_pct"], holding_mean, places=10)
        self.assertAlmostEqual(
            portfolio["nav"]["nav"].iloc[-1], 1.0 + holding_mean / 100.0, places=10
        )

    def test_zero_lag_zero_cost_reproduces_original_endpoint_return(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tickers_path, _ = self.fixture(tmp_path)
            tickers = tickers_path.read_text().splitlines()
            prices = backtest.selection.load_price_universe(tickers, tmp_path)
            calendar = backtest._benchmark_calendar(prices, "SPY")
            portfolio = backtest.build_portfolio(
                "compatibility",
                "selected",
                ["AAA", "BBB"],
                prices,
                calendar,
                pd.Timestamp("2025-07-01"),
                pd.Timestamp("2026-07-01"),
                execution_lag_sessions=0,
                one_way_cost_bps=0.0,
            )
            original = backtest.holding_returns(
                ["AAA", "BBB"], prices, "2025-07-01", "2026-07-01"
            )

        self.assertAlmostEqual(
            portfolio["metrics"]["total_return_pct"],
            original["holding_return_pct"].mean(),
            places=10,
        )

    def test_verified_universe_retains_removed_ticker_at_historical_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tickers_path, metadata_path = self.fixture(tmp_path)
            self.write_prices(tmp_path, "EEE", 0.20)
            history_path = tmp_path / "selection_universe_history.csv"
            rows = []
            metadata = pd.read_csv(metadata_path)
            for row in metadata.itertuples():
                rows.append(
                    (row.ticker, row.role, row.industry_group, "2004-01-01", "", "fixture", "verified")
                )
            rows.append(
                ("EEE", "candidate", "Healthcare", "2004-01-01", "2025-01-01", "fixture", "verified")
            )
            pd.DataFrame(
                rows,
                columns=[
                    "ticker", "role", "industry_group", "valid_from", "valid_to",
                    "membership_source", "membership_quality",
                ],
            ).to_csv(history_path, index=False)
            result = backtest.build_selection_backtest(
                tickers_file=tickers_path,
                metadata_file=metadata_path,
                data_dir=tmp_path,
                universe_history_file=history_path,
                years_ago=(2,),
                holding_years=(1,),
                walk_forward_years=2,
                random_portfolios=0,
                shortlist_size=4,
                group_cap=2,
            )

        self.assertIn("EEE", set(result["snapshots"][2]["rows"]["ticker"]))
        self.assertNotIn("EEE", set(result["snapshots"][0]["rows"]["ticker"]))
        self.assertEqual(result["snapshots"][2]["validity_status"], "validated")

    def test_random_control_is_deterministic(self):
        eligible = pd.DataFrame(
            {
                "ticker": ["A", "B", "C", "D"],
                "industry_group": ["G1", "G1", "G2", "G2"],
            }
        )
        returns = pd.DataFrame(
            {"ticker": ["A", "B", "C", "D"], "net_return_pct": [1.0, 2.0, 3.0, 4.0]}
        )
        first = backtest._random_percentile(eligible, returns, 2.5, 1, 2, 100, 42)
        second = backtest._random_percentile(eligible, returns, 2.5, 1, 2, 100, 42)
        self.assertEqual(first, second)

    def test_post_anchor_price_changes_do_not_change_historical_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tickers_path, metadata_path = self.fixture(tmp_path)
            common = dict(
                tickers_file=tickers_path,
                metadata_file=metadata_path,
                data_dir=tmp_path,
                years_ago=(1,),
                holding_years=(1,),
                walk_forward_years=1,
                execution_lag_sessions=0,
                one_way_cost_bps=0,
                random_portfolios=0,
                shortlist_size=4,
                group_cap=2,
            )
            first = backtest.build_selection_backtest(**common)
            historical_anchor = first["snapshots"][1]["as_of_date"]
            path = tmp_path / "AAA.csv"
            frame = pd.read_csv(path)
            mask = pd.to_datetime(frame["Date"]) > historical_anchor
            frame.loc[mask, "Adj Close"] *= 100.0
            frame.to_csv(path, index=False)
            second = backtest.build_selection_backtest(**common)

        left = first["snapshots"][1]["rows"].set_index("ticker")
        right = second["snapshots"][1]["rows"].set_index("ticker")
        pd.testing.assert_series_equal(left["score"], right["score"])
        pd.testing.assert_series_equal(left["shortlisted"], right["shortlisted"])

    def test_stale_portfolio_price_is_not_silently_forward_filled(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tickers_path, _ = self.fixture(tmp_path)
            tickers = tickers_path.read_text().splitlines()
            prices = backtest.selection.load_price_universe(tickers, tmp_path)
            prices["AAA"]["values"] = prices["AAA"]["values"].iloc[:-4].copy()
            calendar = backtest._benchmark_calendar(prices, "SPY")
            with self.assertRaisesRegex(ValueError, "stale/missing portfolio price"):
                backtest.build_portfolio(
                    "stale",
                    "selected",
                    ["AAA", "BBB"],
                    prices,
                    calendar,
                    pd.Timestamp("2026-01-01"),
                    pd.Timestamp("2026-07-01"),
                    execution_lag_sessions=0,
                    one_way_cost_bps=0,
                )


if __name__ == "__main__":
    unittest.main()
