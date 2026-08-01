import tempfile
import unittest
from pathlib import Path

import pandas as pd

import dashboard_by_excess_annualized as dashboard


class ExcessHorizonDashboardTests(unittest.TestCase):
    def _history(self, tmp_path):
        chart = tmp_path / "chart.png"
        chart.touch()
        end = pd.Timestamp("2026-01-01")

        def row(ticker, source_years, scored_years, excess, started):
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
                "excess_annualized_return_pct": excess,
                "adaptive_annualized_return_pct": excess + 10,
                "buy_hold_annualized_return_pct": 10,
                "adaptive_return_pct": 20,
                "max_dd_pct": -12,
                "lookback_years": 2,
                "offset_months": 12,
                "strategy_profile": "generic",
            }

        rows = [
            row("AAPL", 5, 2, 4, "2026-01-01"),
            row("AAPL", 5, 2, 4, "2026-02-01"),  # newest tie wins
            row("AAPL", 5, 1, 0, "2026-03-01"),
            row("META", 20, 6, 7, "2026-01-01"),
            row("MSFT", 10, 1, 3, "2026-01-01"),
            row("GOOGL", 4, 2, 2, "2026-01-01"),
            row("TSLA", 3, 3, 1, "2026-01-01"),
            row("V", 12, 5, -1, "2026-01-01"),
        ]
        history = tmp_path / "history.csv"
        pd.DataFrame(rows).to_csv(history, index=False)
        return history

    def test_source_tabs_and_dynamic_run_year_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            rankings, considered = dashboard.load_excess_horizon_rankings(
                self._history(Path(tmp))
            )

        self.assertEqual(considered, 8)
        self.assertEqual(rankings["20y"]["views"]["all"].iloc[0]["_ticker"], "META")
        self.assertEqual(rankings["10y"]["views"]["all"].iloc[0]["_ticker"], "MSFT")
        self.assertEqual(rankings["5y"]["views"]["all"].iloc[0]["_ticker"], "AAPL")
        self.assertEqual(rankings["4y"]["views"]["all"].iloc[0]["_ticker"], "GOOGL")
        self.assertEqual(rankings["3y"]["views"]["all"].iloc[0]["_ticker"], "TSLA")
        self.assertEqual(rankings["other"]["views"]["all"].iloc[0]["_ticker"], "V")
        self.assertIn("6y", rankings["20y"]["run_buckets"])
        self.assertIn("5y", rankings["other"]["run_buckets"])

    def test_intersection_prefers_nonzero_and_newest_tie(self):
        with tempfile.TemporaryDirectory() as tmp:
            rankings, _ = dashboard.load_excess_horizon_rankings(self._history(Path(tmp)))

        aapl = rankings["5y"]["views"]["2y"].iloc[0]
        self.assertEqual(aapl["_excess"], 4)
        self.assertEqual(str(aapl["run_started_at"]), "2026-02-01")
        mixed_aapl = rankings["mixed"]["views"]["all"]
        mixed_aapl = mixed_aapl[mixed_aapl["_ticker"] == "AAPL"].iloc[0]
        self.assertEqual(mixed_aapl["_excess"], 4)

    def test_grouped_html_has_accessible_tabs_charts_and_hash_navigation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            history = self._history(tmp_path)
            rankings, considered = dashboard.load_excess_horizon_rankings(history)
            output = dashboard.render_excess_horizon_dashboard(
                rankings, tmp_path / "dashboard.html", history, considered
            )
            page = output.read_text(encoding="utf-8")

        for key, label, _ in dashboard.SOURCE_HORIZONS:
            self.assertIn(f'data-source="{key}"', page)
            self.assertIn(f'id="source-panel-{key}"', page)
            self.assertIn(label, page)
        self.assertIn('role="tablist"', page)
        self.assertIn('data-run="6y"', page)
        self.assertIn("Source years <b>20.0Y</b>", page)
        self.assertIn("Run years <b>6.0Y</b>", page)
        self.assertIn('class="ranking-grid"', page)
        self.assertIn('class="chart-button"', page)
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
            rankings, considered = dashboard.load_excess_horizon_rankings(history)
            page = dashboard.render_excess_horizon_dashboard(
                rankings, tmp_path / "dashboard.html", history, considered
            ).read_text(encoding="utf-8")

        panel = page.split('id="source-panel-10y"', 1)[1].split("</section>", 1)[0]
        self.assertIn("No valid completed runs match", panel)


if __name__ == "__main__":
    unittest.main()
