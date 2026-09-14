import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import dashboard_stock_selection as selection


class StockSelectionDashboardTests(unittest.TestCase):
    def write_prices(self, directory, ticker, start, end, annual_growth, shock=None):
        dates = pd.date_range(start, end, freq="BMS")
        years = np.arange(len(dates)) / 12.0
        prices = 100.0 * np.power(1.0 + annual_growth, years)
        if shock is not None:
            index, factor = shock
            prices[index:] *= factor
        pd.DataFrame({"Date": dates, "Adj Close": prices}).to_csv(
            Path(directory) / f"{ticker}.csv", index=False
        )

    def metadata(self, rows):
        frame = pd.DataFrame(rows, columns=["ticker", "role", "industry_group"])
        return frame.set_index("ticker", drop=False)

    def build_fixture(self, directory, include_short=False, stale=False):
        specs = {
            "AAA": (0.18, "Technology"),
            "BBB": (0.15, "Technology"),
            "CCC": (0.12, "Technology"),
            "DDD": (0.08, "Industrial"),
            "SPY": (0.07, "Benchmark"),
            "QQQ": (0.09, "Benchmark"),
        }
        rows = []
        tickers = list(specs)
        for ticker, (growth, group) in specs.items():
            role = "benchmark" if ticker in {"SPY", "QQQ"} else "candidate"
            end = "2026-08-01"
            if stale and ticker == "DDD":
                end = "2026-06-01"
            self.write_prices(directory, ticker, "2004-01-01", end, growth)
            rows.append((ticker, role, group))
        if include_short:
            tickers.insert(4, "SNDK")
            self.write_prices(directory, "SNDK", "2025-01-01", "2026-08-01", 2.0)
            rows.append(("SNDK", "candidate", "Technology"))
        return tickers, self.metadata(rows)

    def test_ticker_parser_supports_comments_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tickers.txt"
            path.write_text("# list\naaa\nBBB # inline\n", encoding="utf-8")
            self.assertEqual(selection.load_ticker_universe(path), ["AAA", "BBB"])
            path.write_text("AAA\nAAA\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate ticker"):
                selection.load_ticker_universe(path)

    def test_cli_supports_current_through_three_year_ago_snapshots(self):
        self.assertEqual(selection.parse_args([]).years_ago, (0, 1, 2, 3, 4, 5))
        self.assertEqual(selection.parse_args([]).group_cap, 3)
        self.assertEqual(selection.parse_args(["--years-ago", "2", "3"]).years_ago, [2, 3])

    def test_metadata_requires_exact_universe_and_valid_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "groups.csv"
            path.write_text(
                "ticker,role,industry_group\nAAA,candidate,Tech\nSPY,wrong,Benchmark\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Invalid metadata roles"):
                selection.load_selection_metadata(path, ["AAA", "SPY"])
            path.write_text(
                "ticker,role,industry_group\nAAA,candidate,Tech\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Metadata/universe mismatch"):
                selection.load_selection_metadata(path, ["AAA", "SPY"])

    def test_short_history_and_benchmarks_cannot_enter_shortlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            tickers, metadata = self.build_fixture(tmp, include_short=True)
            prices = selection.load_price_universe(tickers, tmp)
            rows, _ = selection.compute_selection_scores(
                tickers, metadata, prices, shortlist_size=10, group_cap=2
            )

        sndk = rows.set_index("ticker").loc["SNDK"]
        self.assertEqual(sndk["eligibility"], "ineligible")
        self.assertIn("Under 4.95 years", sndk["exclusion_reason"])
        self.assertFalse(bool(sndk["shortlisted"]))
        self.assertNotIn("SPY", rows["ticker"].tolist())
        self.assertNotIn("QQQ", rows["ticker"].tolist())

    def test_benchmark_reference_rows_are_scored_but_never_ranked_or_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tickers, metadata = self.build_fixture(tmp)
            prices = selection.load_price_universe(tickers, tmp)
            snapshots, _ = selection.build_selection_snapshots(
                tickers, metadata, prices, years_ago=(0,)
            )
        snapshot = snapshots[0]
        candidates = snapshot["rows"]
        benchmarks = snapshot["benchmark_rows"].set_index("ticker")
        self.assertNotIn("SPY", candidates["ticker"].tolist())
        self.assertNotIn("QQQ", candidates["ticker"].tolist())
        self.assertEqual(set(benchmarks.index), {"SPY", "QQQ"})
        self.assertTrue(benchmarks["score"].notna().all())
        self.assertTrue(benchmarks["cagr_5y_pct"].notna().all())
        self.assertTrue(benchmarks["max_drawdown_5y_pct"].notna().all())
        self.assertTrue(benchmarks["raw_rank"].isna().all())
        self.assertFalse(benchmarks["shortlisted"].any())
        self.assertTrue(benchmarks["display_rank"].notna().all())
        self.assertTrue(snapshot["rows"]["display_rank"].notna().all())
        self.assertTrue(
            benchmarks["shortlist_reason"].str.contains("ranked for comparison; never selected").all()
        )

    def test_score_components_sum_and_group_cap_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            tickers, metadata = self.build_fixture(tmp)
            prices = selection.load_price_universe(tickers, tmp)
            rows, _ = selection.compute_selection_scores(
                tickers, metadata, prices, shortlist_size=4, group_cap=2
            )
            second, _ = selection.compute_selection_scores(
                tickers, metadata, prices, shortlist_size=4, group_cap=2
            )

        scored = rows.dropna(subset=["score"])
        components = scored[
            [
                "return_score",
                "persistence_score",
                "risk_score",
                "benchmark_score",
                "confidence_score",
            ]
        ].sum(axis=1)
        np.testing.assert_allclose(scored["score"], components)
        self.assertTrue(scored["score"].between(0, 100).all())
        selected = rows[rows["shortlisted"]]
        self.assertLessEqual(
            int((selected["industry_group"] == "Technology").sum()), 2
        )
        capped = rows[rows["shortlist_reason"].str.contains("Industry cap", na=False)]
        self.assertFalse(capped.empty)
        self.assertEqual(rows["ticker"].tolist(), second["ticker"].tolist())
        np.testing.assert_allclose(
            rows["score"].fillna(-1), second["score"].fillna(-1)
        )

    def test_timing_overlay_cannot_change_score_or_rank(self):
        with tempfile.TemporaryDirectory() as tmp:
            tickers, metadata = self.build_fixture(tmp)
            prices = selection.load_price_universe(tickers, tmp)
            first, _ = selection.compute_selection_scores(
                tickers,
                metadata,
                prices,
                timing_overlay={"AAA": {"timing_signal": "BUY"}},
            )
            second, _ = selection.compute_selection_scores(
                tickers,
                metadata,
                prices,
                timing_overlay={"AAA": {"timing_signal": "SELL/CASH"}},
            )

        self.assertEqual(first["ticker"].tolist(), second["ticker"].tolist())
        np.testing.assert_allclose(
            first["score"].fillna(-1), second["score"].fillna(-1)
        )
        self.assertNotEqual(
            first.set_index("ticker").loc["AAA", "timing_signal"],
            second.set_index("ticker").loc["AAA", "timing_signal"],
        )

    def test_stale_history_is_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            tickers, metadata = self.build_fixture(tmp, stale=True)
            prices = selection.load_price_universe(tickers, tmp)
            rows, _ = selection.compute_selection_scores(tickers, metadata, prices)

        ddd = rows.set_index("ticker").loc["DDD"]
        self.assertEqual(ddd["eligibility"], "ineligible")
        self.assertIn("stale", ddd["exclusion_reason"].lower())

    def test_missing_ten_year_return_uses_neutral_percentile(self):
        with tempfile.TemporaryDirectory() as tmp:
            tickers, metadata = self.build_fixture(tmp)
            self.write_prices(tmp, "DDD", "2017-08-01", "2026-08-01", 0.11)
            prices = selection.load_price_universe(tickers, tmp)
            rows, _ = selection.compute_selection_scores(tickers, metadata, prices)

        ddd = rows.set_index("ticker").loc["DDD"]
        self.assertEqual(ddd["eligibility"], "eligible")
        self.assertTrue(pd.isna(ddd["cagr_10y_pct"]))
        expected = (
            selection._percentile(
                rows.dropna(subset=["cagr_3y_pct"]).set_index("ticker")["cagr_3y_pct"]
            )["DDD"]
            * 5
            + selection._percentile(
                rows.dropna(subset=["cagr_5y_pct"]).set_index("ticker")["cagr_5y_pct"]
            )["DDD"]
            * 10
            + 5.0
        )
        self.assertAlmostEqual(ddd["return_score"], expected)

    def test_aligned_benchmark_uses_candidate_dates(self):
        values = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2020-01-01", "2021-01-01", "2022-01-01"]),
                "Price": [100.0, 110.0, 242.0],
            }
        )
        item = {"values": values}
        annualized = selection._aligned_annualized(
            item, pd.Timestamp("2020-06-01"), pd.Timestamp("2022-01-01")
        )
        expected = ((242.0 / 110.0) ** (1.0 / (365 / 365.25)) - 1.0) * 100.0
        self.assertAlmostEqual(annualized, expected, places=6)

    def test_drawdown_details_marks_peak_trough_and_recovery_dates(self):
        values = pd.DataFrame(
            {
                "Date": pd.to_datetime(
                    ["2022-01-03", "2022-02-01", "2022-03-01", "2022-04-01"]
                ),
                "Price": [100.0, 120.0, 90.0, 121.0],
            }
        )
        details = selection._drawdown_details(values)

        self.assertAlmostEqual(details["max_drawdown_5y_pct"], 25.0)
        self.assertEqual(details["max_drawdown_peak_date"], "2022-02-01")
        self.assertEqual(details["max_drawdown_trough_date"], "2022-03-01")
        self.assertEqual(details["max_drawdown_recovery_date"], "2022-04-01")
        self.assertEqual(details["max_drawdown_duration_days"], 28)
        self.assertEqual(details["max_drawdown_recovery_duration_days"], 31)
        self.assertIn(("2022-02-01", 0.0), details["drawdown_points"])
        self.assertIn(("2022-03-01", -25.0), details["drawdown_points"])

    def test_point_in_time_snapshots_use_common_anchor_and_historical_timing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tickers, metadata = self.build_fixture(tmp)
            prices = selection.load_price_universe(tickers, tmp)
            snapshots, latest = selection.build_selection_snapshots(
                tickers,
                metadata,
                prices,
                years_ago=(0, 1, 2, 3),
                current_timing_overlay={"AAA": {"timing_signal": "BUY"}},
            )

        current, historical, two_year, three_year = snapshots
        self.assertEqual(latest.strftime("%Y-%m-%d"), "2026-07-01")
        self.assertEqual(current["as_of_date"].strftime("%Y-%m-%d"), "2026-07-01")
        self.assertEqual(historical["as_of_date"].strftime("%Y-%m-%d"), "2025-07-01")
        self.assertEqual(two_year["as_of_date"].strftime("%Y-%m-%d"), "2024-07-01")
        self.assertEqual(three_year["as_of_date"].strftime("%Y-%m-%d"), "2023-06-01")
        self.assertTrue((historical["rows"]["data_end"] <= "2025-07-01").all())
        self.assertEqual(
            historical["rows"].set_index("ticker").loc["AAA", "timing_signal"],
            "Unavailable (historical selection replay)",
        )
        self.assertEqual(
            historical["rows"]["years_ago"].drop_duplicates().tolist(), [1]
        )
        self.assertTrue((two_year["rows"]["data_end"] <= "2024-07-01").all())
        self.assertTrue((three_year["rows"]["data_end"] <= "2023-06-01").all())
        direct_current, _ = selection.compute_selection_scores(
            tickers,
            metadata,
            prices,
            timing_overlay={"AAA": {"timing_signal": "BUY"}},
            as_of_date=current["as_of_date"],
        )
        np.testing.assert_allclose(
            current["rows"].sort_values("ticker")["score"].fillna(-1),
            direct_current.sort_values("ticker")["score"].fillna(-1),
        )
        direct_rows, _ = selection.compute_selection_scores(
            tickers,
            metadata,
            {ticker: selection.price_item_as_of(item, historical["as_of_date"]) for ticker, item in prices.items()},
            timing_overlay=selection.historical_timing_overlay(tickers),
            as_of_date=historical["as_of_date"],
        )
        np.testing.assert_allclose(
            historical["rows"].sort_values("ticker")["score"].fillna(-1),
            direct_rows.sort_values("ticker")["score"].fillna(-1),
        )

    def test_render_has_provenance_components_and_local_gate_storage(self):
        rows = pd.DataFrame(
            [
                {
                    "ticker": "AAA",
                    "industry_group": "Technology",
                    "eligibility": "eligible",
                    "shortlisted": True,
                    "shortlist_rank": 1,
                    "raw_rank": 1,
                    "score": 75.0,
                    "return_score": 20.0,
                    "persistence_score": 18.0,
                    "risk_score": 17.0,
                    "benchmark_score": 12.0,
                    "confidence_score": 8.0,
                    "cagr_3y_pct": 15.0,
                    "cagr_5y_pct": 14.0,
                    "cagr_10y_pct": np.nan,
                    "max_drawdown_5y_pct": 30.0,
                    "max_drawdown_peak_date": "2023-02-01",
                    "max_drawdown_trough_date": "2023-09-01",
                    "max_drawdown_recovery_date": "2024-01-01",
                    "max_drawdown_duration_days": 212,
                    "max_drawdown_recovery_duration_days": 122,
                    "drawdown_points": [
                        ("2023-01-01", 0.0),
                        ("2023-02-01", 0.0),
                        ("2023-09-01", -30.0),
                        ("2024-01-01", 0.0),
                    ],
                    "volatility_5y_pct": 25.0,
                    "history_years": 8.0,
                    "persistence_panels": 9,
                    "primary_benchmark": "SPY",
                    "primary_beat_rate_pct": 70.0,
                    "secondary_benchmark": "QQQ",
                    "secondary_beat_rate_pct": 60.0,
                    "risk_warning": "Lower historical risk",
                    "timing_signal": "BUY",
                    "timing_data_end": "2026-08-01",
                    "shortlist_reason": "Selected",
                    "coverage": "Medium",
                }
            ]
        )
        historical_rows = rows.copy()
        historical_rows["timing_signal"] = "Unavailable (historical selection replay)"
        historical_rows["timing_data_end"] = ""
        with tempfile.TemporaryDirectory() as tmp:
            output = selection.render_selection_dashboard(
                rows,
                Path(tmp) / "dashboard.html",
                Path(tmp) / "tickers.txt",
                Path(tmp) / "groups.csv",
                Path(tmp),
                pd.Timestamp("2026-08-01"),
                snapshots=[
                    {
                        "id": "current",
                        "label": "Current",
                        "years_ago": 0,
                        "as_of_date": pd.Timestamp("2026-08-01"),
                        "rows": rows,
                    },
                    {
                        "id": "1y-ago",
                        "label": "1Y ago",
                        "years_ago": 1,
                        "as_of_date": pd.Timestamp("2025-08-01"),
                        "rows": historical_rows,
                    },
                ],
            )
            page = output.read_text(encoding="utf-8")

        self.assertIn("Return</small><b>20.0/25", page)
        self.assertIn('href="dashboard_stock_selection_backtest.html"', page)
        self.assertIn("Timing overlay", page)
        self.assertIn("not scored", page)
        self.assertIn("stockSelection.fundamentals.v2", page)
        self.assertIn("Reset fundamentals checks", page)
        self.assertIn("Research support only", page)
        self.assertIn("5Y drawdown timeline", page)
        self.assertIn("Peak Feb 2023", page)
        self.assertIn("Trough Sep 2023", page)
        self.assertIn("Drawdown duration 212 days (7.0 mo)", page)
        self.assertIn("Recovery duration 122 days (4.0 mo)", page)
        self.assertIn('class="dd-trough"', page)
        self.assertIn('id="candidateRanking-current"', page)
        self.assertIn('id="candidateRanking-1y-ago"', page)
        self.assertIn('<tr class="selected-row"', page)
        self.assertIn('.candidate-ranking tbody tr.selected-row td{background:var(--selected-row)}', page)
        self.assertIn(':root[data-theme=dark]', page)
        self.assertIn('data-theme-toggle', page)
        self.assertIn('stockSelection.theme.v1', page)
        self.assertIn("prefers-color-scheme:dark", page)
        self.assertIn("Switch to light mode", page)
        self.assertIn('data-gate="current|AAA|quality"', page)
        self.assertIn('data-gate="1y-ago|AAA|quality"', page)
        self.assertIn('data-snapshot="current"', page)
        self.assertIn('data-snapshot="1y-ago"', page)
        self.assertIn('data-sort-key="rank">Rank', page)
        self.assertNotIn("Raw rank", page)
        self.assertIn('data-sort-key="score"', page)
        self.assertIn("const sortTable", page)
        self.assertIn("selectSnapshot", page)
        self.assertIn("aria-sort", page)
        self.assertIn("Selection status:", page)
        self.assertIn("Score (0–100):", page)
        self.assertLess(
            page.index("<h2>Complete candidate ranking</h2>"),
            page.index("<h2>Diversified shortlist</h2>"),
        )
        self.assertIn("adaptive timing overlay does not affect the score or rank", page)
        self.assertNotRegex(page, r"(?i)>\s*nan\s*<")
        self.assertNotIn("Infinity", page)
        self.assertIn("@media(min-width:1500px)", page)
        self.assertIn("@media(min-width:2100px)", page)


if __name__ == "__main__":
    unittest.main()
