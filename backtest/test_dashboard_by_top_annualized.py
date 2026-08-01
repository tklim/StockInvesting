import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

import dashboard_by_top_annualized as dashboard


class BuyHoldHorizonDashboardTests(unittest.TestCase):
    def _history(self, tmp_path):
        chart = tmp_path / "chart.png"
        chart.touch()
        prices = tmp_path / "prices.csv"
        dates = pd.date_range("2005-01-01", "2026-01-01", freq="YS")
        pd.DataFrame(
            {
                "Date": dates,
                "Adj Close": [100 + index * 10 for index in range(len(dates))],
            }
        ).to_csv(prices, index=False)

        def row(ticker, years, buy_hold, started):
            end = pd.Timestamp("2026-01-01")
            start = end - pd.DateOffset(years=years)
            return {
                "run_id": f"{ticker}-{years}Y",
                "fund_label": ticker,
                "fund_slice_label": f"{ticker}-{years}Y",
                "run_status": "completed",
                "run_started_at": started,
                "data_file": prices,
                "source_snapshot_file": prices,
                "price_column": "Adj Close",
                "data_start": start.strftime("%Y-%m-%d"),
                "data_end": end.strftime("%Y-%m-%d"),
                "backtest_start": start.strftime("%Y-%m-%d"),
                "backtest_end": end.strftime("%Y-%m-%d"),
                "adaptive_annualized_return_pct": buy_hold - 1,
                "buy_hold_annualized_return_pct": buy_hold,
                "excess_annualized_return_pct": -1,
                "chart_file": chart,
                "lookback_years": 1,
                "offset_months": 12,
                "strategy_profile": "generic",
            }

        rows = [
            row("AAPL", 20, 20, "2026-01-01"),
            row("AAPL", 5, 30, "2026-02-01"),
            row("META", 10, 25, "2026-01-01"),
            row("GOOGL", 4, 18, "2026-01-01"),
            row("TSLA", 3, 15, "2026-01-01"),
        ]
        history = tmp_path / "history.csv"
        pd.DataFrame(rows).to_csv(history, index=False)
        return history

    def test_rankings_are_grouped_by_source_span(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = self._history(Path(tmp))
            rankings, considered = dashboard.load_buy_hold_horizon_rankings(
                history, derived_horizons=()
            )

        self.assertEqual(considered, 5)
        self.assertEqual(rankings["mixed"]["rows"].iloc[0]["_ticker"], "AAPL")
        self.assertEqual(rankings["mixed"]["rows"].iloc[0]["_top"], 30)
        self.assertEqual(rankings["20y"]["rows"].iloc[0]["_top"], 20)
        self.assertEqual(rankings["10y"]["rows"].iloc[0]["_ticker"], "META")
        self.assertEqual(rankings["5y"]["rows"].iloc[0]["_top"], 30)
        self.assertEqual(rankings["4y"]["rows"].iloc[0]["_ticker"], "GOOGL")
        self.assertEqual(rankings["3y"]["rows"].iloc[0]["_ticker"], "TSLA")

    def test_grouped_dashboard_has_tabs_and_simple_charts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history = self._history(tmp_path)
            rankings, considered = dashboard.load_buy_hold_horizon_rankings(
                history, derived_horizons=()
            )
            output = dashboard.render_buy_hold_horizon_dashboard(
                rankings,
                tmp_path / "dashboard.html",
                history,
                considered,
            )
            page = output.read_text(encoding="utf-8")

        for key, label, _ in dashboard.BUY_HOLD_HORIZONS:
            self.assertIn(f'data-group="{key}"', page)
            self.assertIn(f'id="panel-{key}"', page)
            self.assertIn(label, page)
        self.assertIn("Mixed highest (4)", page)
        self.assertIn("20 years (1)", page)
        self.assertIn("10 years (1)", page)
        self.assertIn('class="simple-chart"', page)
        self.assertIn("Buy and hold growth", page)
        self.assertIn("role=\"tablist\"", page)
        self.assertIn("ArrowLeft", page)
        self.assertIn("history.replaceState", page)
        self.assertIn('class="back-link" href="dashboard.html"', page)

    def test_simple_chart_shows_investment_return_and_raw_price_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            prices = Path(tmp) / "META.csv"
            pd.DataFrame(
                {
                    "Date": ["2020-01-01", "2021-01-01"],
                    "Adj Close": [100.0, 150.0],
                    "Close": [110.0, 165.0],
                }
            ).to_csv(prices, index=False)
            chart = dashboard.simple_buy_hold_svg(
                {
                    "data_file": prices,
                    "price_column": "Adj Close",
                    "backtest_start": "2020-01-01",
                    "backtest_end": "2021-01-01",
                }
            )

        self.assertIn("2020-01-01", chart)
        self.assertIn("2021-01-01", chart)
        self.assertIn("$10,000 · 0.00%", chart)
        self.assertIn("$15,000 · +50.00%", chart)
        self.assertIn("Raw stock price", chart)
        self.assertIn("$110.00", chart)
        self.assertIn("$165.00", chart)

    def test_data_derived_ten_year_rows_use_full_price_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            dates = pd.date_range("2014-01-01", "2026-01-01", freq="BMS")
            pd.DataFrame(
                {"Date": dates, "Adj Close": range(100, 100 + len(dates))}
            ).to_csv(data_dir / "AAPL.csv", index=False)
            # A slice name must not be mistaken for a full history.
            pd.DataFrame(
                {"Date": dates[-36:], "Adj Close": range(100, 136)}
            ).to_csv(data_dir / "AAPL-3Y.csv", index=False)
            pd.DataFrame(
                {"Date": dates[-48:], "Adj Close": range(100, 148)}
            ).to_csv(data_dir / "SHORT.csv", index=False)
            pd.DataFrame({"Price": [100, 101]}).to_csv(
                data_dir / "NO_DATE.csv", index=False
            )
            pd.DataFrame({"Date": dates[:2], "Volume": [10, 11]}).to_csv(
                data_dir / "NO_PRICE.csv", index=False
            )
            pd.DataFrame(columns=["Date", "Adj Close"]).to_csv(
                data_dir / "EMPTY.csv", index=False
            )

            derived = dashboard.build_data_derived_buy_hold_rows(data_dir, years=10)

        self.assertEqual(derived["_ticker"].tolist(), ["AAPL"])
        row = derived.iloc[0]
        self.assertTrue(row["_data_derived"])
        self.assertEqual(row["price_column"], "Adj Close")
        self.assertGreater(row["_top"], 0)
        self.assertGreaterEqual(row["_source_years"], 9.95)

    def test_twenty_year_rows_use_all_available_history_when_shorter(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            long_dates = pd.date_range("2000-01-01", "2026-01-01", freq="BMS")
            short_dates = pd.date_range("2014-01-01", "2026-01-01", freq="BMS")
            pd.DataFrame(
                {"Date": long_dates, "Adj Close": range(100, 100 + len(long_dates))}
            ).to_csv(data_dir / "LONG.csv", index=False)
            pd.DataFrame(
                {"Date": short_dates, "Adj Close": range(100, 100 + len(short_dates))}
            ).to_csv(data_dir / "SHORT.csv", index=False)

            derived = dashboard.build_data_derived_buy_hold_rows(data_dir, years=20)

        by_ticker = derived.set_index("_ticker")
        self.assertEqual(set(by_ticker.index), {"LONG", "SHORT"})
        self.assertGreaterEqual(by_ticker.loc["LONG", "_source_years"], 19.95)
        self.assertGreaterEqual(by_ticker.loc["SHORT", "_source_years"], 11.95)
        self.assertLess(by_ticker.loc["SHORT", "_source_years"], 20)
        self.assertEqual(
            by_ticker.loc["SHORT", "data_start"],
            short_dates[0].strftime("%Y-%m-%d"),
        )
        self.assertEqual(
            by_ticker.loc["SHORT", "backtest_start"],
            by_ticker.loc["SHORT", "data_start"],
        )

    def test_default_ten_year_horizon_replaces_history_with_derived_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history = self._history(tmp_path)
            derived = pd.DataFrame(
                [
                    {"_ticker": "META", "_top": 99.0, "_data_derived": True},
                    {"_ticker": "MSFT", "_top": 35.0, "_data_derived": True},
                    {"_ticker": "AAPL", "_top": 30.0, "_data_derived": True},
                ]
            )
            with mock.patch.object(
                dashboard, "build_data_derived_buy_hold_rows", return_value=derived
            ) as build_rows:
                rankings, _ = dashboard.load_buy_hold_horizon_rankings(
                    history
                )

        build_rows.assert_called_once_with(years=10)
        rows = rankings["10y"]["rows"]
        self.assertEqual(rows["_ticker"].tolist(), ["META", "MSFT", "AAPL"])
        self.assertEqual(rows["_ticker"].nunique(), 3)
        meta = rows[rows["_ticker"] == "META"].iloc[0]
        self.assertEqual(meta["_top"], 99)
        self.assertTrue(meta["_data_derived"])
        self.assertTrue(rankings["10y"]["fully_derived"])
        self.assertEqual(rankings["10y"]["historical_count"], 0)
        self.assertEqual(rankings["10y"]["derived_count"], 3)

    def test_top_funds_applies_after_fully_derived_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = self._history(Path(tmp))
            derived = pd.DataFrame(
                [
                    {"_ticker": "META", "_top": 99.0, "_data_derived": True},
                    {"_ticker": "MSFT", "_top": 35.0, "_data_derived": True},
                    {"_ticker": "AAPL", "_top": 30.0, "_data_derived": True},
                ]
            )
            with mock.patch.object(
                dashboard, "build_data_derived_buy_hold_rows", return_value=derived
            ):
                rankings, _ = dashboard.load_buy_hold_horizon_rankings(
                    history, top_funds=2, derived_horizons=("10y",)
                )

        self.assertEqual(
            rankings["10y"]["rows"]["_ticker"].tolist(), ["META", "MSFT"]
        )
        self.assertEqual(rankings["10y"]["derived_count"], 2)

    def test_fully_derived_provenance_and_matching_windows_are_rendered(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history = self._history(tmp_path)
            prices = tmp_path / "prices.csv"
            derived = pd.DataFrame(
                [
                    {
                        "fund_label": "AAPL",
                        "fund_slice_label": "AAPL",
                        "data_file": prices,
                        "price_column": "Adj Close",
                        "data_start": "2016-01-01",
                        "data_end": "2026-01-01",
                        "backtest_start": "2016-01-01",
                        "backtest_end": "2026-01-01",
                        "_ticker": "AAPL",
                        "_row_label": "AAPL",
                        "_top": 30.0,
                        "_buy_hold": 30.0,
                        "_adaptive": float("nan"),
                        "_winner": dashboard.BUY_HOLD_LABEL,
                        "_source_years": 10.0,
                        "_data_derived": True,
                    }
                ]
            )
            with mock.patch.object(
                dashboard, "build_data_derived_buy_hold_rows", return_value=derived
            ):
                rankings, considered = dashboard.load_buy_hold_horizon_rankings(
                    history, derived_horizons=("10y",)
                )
            output = dashboard.render_buy_hold_horizon_dashboard(
                rankings, tmp_path / "dashboard.html", history, considered
            )
            page = output.read_text(encoding="utf-8")

        panel = page.split('id="panel-10y"', 1)[1].split("</section>", 1)[0]
        self.assertNotIn("Winning run <b>", panel)
        self.assertIn("Derived from local price data", panel)
        self.assertIn("Source years <b>10.0Y</b>", panel)
        self.assertIn("Scored years <b>10.0Y</b>", panel)
        self.assertIn("same consistent window", panel)
        self.assertIn("1 eligible local source file(s)", panel)

    def test_selected_three_year_horizon_replaces_historical_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = self._history(Path(tmp))
            derived = pd.DataFrame(
                [
                    {"_ticker": "TSLA", "_top": 40.0, "_data_derived": True},
                    {"_ticker": "AAPL", "_top": 30.0, "_data_derived": True},
                ]
            )
            with mock.patch.object(
                dashboard, "build_data_derived_buy_hold_rows", return_value=derived
            ):
                rankings, _ = dashboard.load_buy_hold_horizon_rankings(
                    history, derived_horizons=("3y",)
                )

        rows = rankings["3y"]["rows"]
        self.assertEqual(rows["_ticker"].tolist(), ["TSLA", "AAPL"])
        self.assertEqual(rows.iloc[0]["_top"], 40)
        self.assertTrue(rows["_data_derived"].all())
        self.assertEqual(rankings["3y"]["historical_count"], 0)

    def test_preferred_and_compatibility_cli_options_match(self):
        parsed = []
        for option in (
            "--derive-buyhold-horizons",
            "--derive-missing-horizons",
        ):
            with mock.patch(
                "sys.argv",
                ["dashboard_by_top_annualized.py", option, "3y", "5y"],
            ):
                parsed.append(dashboard.parse_args().derive_buyhold_horizons)

        self.assertEqual(parsed[0], ["3y", "5y"])
        self.assertEqual(parsed[0], parsed[1])


if __name__ == "__main__":
    unittest.main()
