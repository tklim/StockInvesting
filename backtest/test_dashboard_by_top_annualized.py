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
                comparison_data_dir=tmp_path,
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
        self.assertEqual(page.count('class="consolidated-chart"'), 7)
        self.assertEqual(page.count('class="ranking-table"'), len(dashboard.BUY_HOLD_HORIZONS))
        self.assertIn("Local-price normalized growth", page)
        self.assertIn("not a strategy result", page)
        self.assertIn("Compact table", page)
        self.assertIn("Buy &amp; hold ann.", page)
        self.assertIn("table.querySelectorAll('.table-sort')", page)
        self.assertIn('id="themeToggle"', page)
        self.assertIn("body.dark", page)
        self.assertIn("buyhold-theme", page)

    def test_mixed_summary_uses_scored_years_and_links_to_horizon_chart(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history = self._history(tmp_path)
            rankings, considered = dashboard.load_buy_hold_horizon_rankings(
                history, derived_horizons=()
            )
            rows = rankings["mixed"]["rows"]
            aapl = rows[rows["_ticker"] == "AAPL"].index[0]
            rows.loc[aapl, "backtest_start"] = "2022-01-01"
            output = dashboard.render_buy_hold_horizon_dashboard(
                rankings, tmp_path / "dashboard.html", history, considered,
                comparison_data_dir=tmp_path,
            )
            page = output.read_text(encoding="utf-8")

        mixed = page.split('id="panel-mixed"', 1)[1].split("</section>", 1)[0]
        self.assertIn("Source years <b>4.0Y</b>", mixed)
        self.assertIn("Scored years <b>4.0Y</b>", mixed)
        self.assertIn('href="#5y"', mixed)
        self.assertIn('class="simple-chart"', mixed)
        self.assertIn("window.addEventListener('hashchange'", page)

    def test_negative_buy_hold_headline_uses_negative_tone(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history = self._history(tmp_path)
            rankings, considered = dashboard.load_buy_hold_horizon_rankings(
                history, derived_horizons=()
            )
            rows = rankings["3y"]["rows"].copy()
            rows["_top"] = rows["_top"].astype(float)
            rows.loc[:, "_top"] = -2.24
            rankings["3y"]["rows"] = rows
            output = dashboard.render_buy_hold_horizon_dashboard(
                rankings, tmp_path / "dashboard.html", history, considered,
                comparison_data_dir=tmp_path,
            )
            page = output.read_text(encoding="utf-8")

        panel = page.split('id="panel-3y"', 1)[1].split("</section>", 1)[0]
        self.assertIn('class="headline neg"', panel)
        self.assertIn('.headline.neg strong{color:var(--neg)}', page)

    def test_consolidated_chart_normalizes_returns_and_marks_20y_start_variance(self):
        def series(ticker, dates, prices):
            return {
                "ticker": ticker,
                "data_file": f"{ticker}.csv",
                "price_column": "Adj Close",
                "data_start": dates[0].strftime("%Y-%m-%d"),
                "data_end": dates[-1].strftime("%Y-%m-%d"),
                "source_years": (dates[-1] - dates[0]).days / 365.25,
                "values": pd.DataFrame({"Date": dates, "Price": prices}),
            }

        common_dates = pd.to_datetime(["2023-01-01", "2024-01-01", "2025-01-01"])
        short_dates = pd.to_datetime(["2016-01-01", "2021-01-01", "2025-01-01"])
        chart = dashboard.consolidated_buy_hold_svg(
            [
                series("AAPL", common_dates, [100.0, 125.0, 150.0]),
                series("SHORT", short_dates, [100.0, 110.0, 120.0]),
            ],
            years=20,
        )

        self.assertEqual(chart.count("<polyline"), 2)
        self.assertIn("AAPL</b> $15,000 · +50.00%", chart)
        self.assertIn("SHORT</b> $12,000 · +20.00%", chart)
        self.assertIn("start dates vary", chart)
        self.assertIn("2016-01-01", chart)
        self.assertIn("2025-01-01", chart)

    def test_consolidated_loader_excludes_invalid_and_short_non_twenty_year_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            long_dates = pd.date_range("2013-01-01", "2026-01-01", freq="BMS")
            short_dates = pd.date_range("2023-01-01", "2026-01-01", freq="BMS")
            pd.DataFrame({"Date": long_dates, "Adj Close": range(100, 100 + len(long_dates))}).to_csv(data_dir / "AAPL.csv", index=False)
            pd.DataFrame({"Date": long_dates, "Adj Close": range(100, 100 + len(long_dates))}).to_csv(data_dir / "AAPL-3Y.csv", index=False)
            pd.DataFrame({"Date": short_dates, "Adj Close": range(100, 100 + len(short_dates))}).to_csv(data_dir / "SHORT.csv", index=False)
            pd.DataFrame({"Date": long_dates, "Volume": 1}).to_csv(data_dir / "NO_PRICE.csv", index=False)
            pd.DataFrame({"Adj Close": [100, 110]}).to_csv(data_dir / "NO_DATE.csv", index=False)

            ten_year = dashboard.load_local_buy_hold_price_series(data_dir, years=10)
            twenty_year = dashboard.load_local_buy_hold_price_series(data_dir, years=20)

        self.assertEqual([item["ticker"] for item in ten_year], ["AAPL"])
        self.assertEqual({item["ticker"] for item in twenty_year}, {"AAPL", "SHORT"})

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

    def test_default_horizons_replace_history_with_derived_rows(self):
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

        self.assertEqual(
            [call.kwargs["years"] for call in build_rows.call_args_list],
            [20, 10, 5, 4, 3, 2, 1],
        )
        for key in dashboard.DEFAULT_DERIVED_BUY_HOLD_HORIZONS:
            rows = rankings[key]["rows"]
            self.assertEqual(rows["_ticker"].tolist(), ["META", "MSFT", "AAPL"])
            self.assertTrue(rows["_data_derived"].all())
            self.assertTrue(rankings[key]["fully_derived"])
            self.assertEqual(rankings[key]["historical_count"], 0)
            self.assertEqual(rankings[key]["derived_count"], 3)

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


class TopHorizonDashboardTests(unittest.TestCase):
    """Two-axis (Source years x Run years) dashboard for --basis best."""

    def _history(self, tmp_path):
        chart = tmp_path / "chart.png"
        chart.touch()
        end = pd.Timestamp("2026-01-01")

        def row(ticker, source_years, scored_years, adaptive, buy_hold, started):
            source_start = end - pd.DateOffset(years=source_years)
            scored_start = end - pd.DateOffset(years=scored_years)
            return {
                "run_id": f"{ticker}-{source_years}-{scored_years}-{started}",
                "fund_label": ticker,
                "fund_slice_label": f"{ticker}-{source_years}Y",
                "run_status": "completed",
                "run_started_at": started,
                "data_start": source_start.strftime("%Y-%m-%d"),
                "data_end": end.strftime("%Y-%m-%d"),
                "backtest_start": scored_start.strftime("%Y-%m-%d"),
                "backtest_end": end.strftime("%Y-%m-%d"),
                "chart_file": chart,
                "adaptive_annualized_return_pct": adaptive,
                "buy_hold_annualized_return_pct": buy_hold,
                "excess_annualized_return_pct": adaptive - buy_hold,
                "max_dd_pct": -12,
                "lookback_years": 2,
                "offset_months": 12,
                "strategy_profile": "generic",
            }

        rows = [
            row("AAPL", 5, 2, 25, 10, "2026-01-01"),  # strategy side
            row("AAPL", 5, 1, 0, 30, "2026-02-01"),  # buy-hold wins overall
            row("META", 20, 6, 8, 35, "2026-01-01"),  # buy-hold, 6y bucket
            row("MSFT", 10, 1, 40, 12, "2026-01-01"),  # strategy, 1y bucket
            row("GOOGL", 4, 2, 15, 5, "2026-01-01"),
            row("TSLA", 3, 3, -2, 1, "2026-01-01"),
            row("V", 12, 5, 6, 4, "2026-01-01"),  # 12y -> "other"
        ]
        history = tmp_path / "history.csv"
        pd.DataFrame(rows).to_csv(history, index=False)
        return history

    def test_source_tabs_and_dynamic_run_year_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            rankings, considered = dashboard.load_top_annualized_horizon_rankings(
                self._history(Path(tmp)), "best"
            )

        self.assertEqual(considered, 7)
        self.assertEqual(rankings["20y"]["views"]["all"].iloc[0]["_ticker"], "META")
        self.assertEqual(rankings["10y"]["views"]["all"].iloc[0]["_ticker"], "MSFT")
        self.assertEqual(rankings["5y"]["views"]["all"].iloc[0]["_ticker"], "AAPL")
        self.assertEqual(rankings["4y"]["views"]["all"].iloc[0]["_ticker"], "GOOGL")
        self.assertEqual(rankings["3y"]["views"]["all"].iloc[0]["_ticker"], "TSLA")
        self.assertEqual(rankings["other"]["views"]["all"].iloc[0]["_ticker"], "V")
        self.assertIn("6y", rankings["20y"]["run_buckets"])
        self.assertIn("1y", rankings["10y"]["run_buckets"])

    def test_top_semantics_and_winner_badge(self):
        with tempfile.TemporaryDirectory() as tmp:
            rankings, _ = dashboard.load_top_annualized_horizon_rankings(
                self._history(Path(tmp)), "best"
            )

        aapl = rankings["5y"]["views"]["all"].iloc[0]
        self.assertEqual(aapl["_top"], 30)
        self.assertEqual(aapl["_winner"], dashboard.BUY_HOLD_LABEL)
        meta = rankings["20y"]["views"]["all"].iloc[0]
        self.assertEqual(meta["_top"], 35)
        self.assertEqual(meta["_winner"], dashboard.BUY_HOLD_LABEL)
        msft = rankings["10y"]["views"]["all"].iloc[0]
        self.assertEqual(msft["_top"], 40)
        self.assertEqual(msft["_winner"], dashboard.STRATEGY_LABEL)

    def test_grouped_html_has_accessible_tabs_charts_hash_and_badge(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history = self._history(tmp_path)
            rankings, considered = dashboard.load_top_annualized_horizon_rankings(history, "best")
            output = dashboard.render_top_annualized_horizon_dashboard(
                rankings, tmp_path / "dashboard.html", history, considered, "best"
            )
            page = output.read_text(encoding="utf-8")

        for key, label, _ in dashboard.TOP_SOURCE_HORIZONS:
            self.assertIn(f'data-source="{key}"', page)
            self.assertIn(f'id="source-panel-{key}"', page)
            self.assertIn(label, page)
        self.assertIn('role="tablist"', page)
        self.assertIn('data-run="6y"', page)
        self.assertIn("Source years <b>20.0Y</b>", page)
        self.assertIn("Run years <b>6.0Y</b>", page)
        self.assertIn('class="ranking-grid"', page)
        self.assertIn('class="chart-button"', page)
        self.assertIn('class="badge strategy"', page)
        self.assertIn('class="badge market"', page)
        self.assertIn("ArrowLeft", page)
        self.assertIn("hashFor(source,run)", page)
        self.assertIn(".empty{", page)
        self.assertIn('class="master-link" href="dashboard.html"', page)

    def test_empty_source_horizon_renders_an_empty_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history = self._history(tmp_path)
            frame = pd.read_csv(history)
            frame = frame[frame["fund_label"] != "MSFT"]
            frame.to_csv(history, index=False)
            rankings, considered = dashboard.load_top_annualized_horizon_rankings(history, "best")
            page = dashboard.render_top_annualized_horizon_dashboard(
                rankings, tmp_path / "dashboard.html", history, considered, "best"
            ).read_text(encoding="utf-8")

        panel = page.split('id="source-panel-10y"', 1)[1].split("</section>", 1)[0]
        self.assertIn("No valid completed runs match", panel)

    def test_top_funds_applied_per_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            rankings, _ = dashboard.load_top_annualized_horizon_rankings(
                self._history(Path(tmp)), "best", top_funds=2
            )

        for group in rankings.values():
            for view in group["views"].values():
                self.assertLessEqual(len(view), 2)

    def test_main_routes_best_to_grouped_renderer_but_not_per_slice(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history = self._history(tmp_path)
            with mock.patch.object(
                dashboard, "load_top_annualized_horizon_rankings"
            ) as load_rank, mock.patch.object(
                dashboard, "render_top_annualized_horizon_dashboard", return_value=tmp_path / "x.html"
            ), mock.patch.object(dashboard, "render_pdf"), mock.patch.object(dashboard, "render_html") as render_flat:
                load_rank.return_value = ({"dummy": {}}, 7)
                with mock.patch(
                    "sys.argv",
                    ["dashboard_by_top_annualized.py", "--history-file", str(history)],
                ):
                    dashboard.main()
        load_rank.assert_called_once()
        render_flat.assert_not_called()


if __name__ == "__main__":
    unittest.main()
