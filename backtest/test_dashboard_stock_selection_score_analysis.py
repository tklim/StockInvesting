import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import dashboard_stock_selection_score_analysis as analysis


class ScoreAnalysisTests(unittest.TestCase):
    def test_weight_grid_is_deterministic_and_sums_to_one_hundred(self):
        first = analysis.generate_weight_grid(5)
        second = analysis.generate_weight_grid(5)
        self.assertEqual(first, second)
        self.assertIn(analysis.BASELINE_WEIGHTS, first)
        self.assertTrue(all(sum(weights) == 100 for weights in first))

    def test_rank_and_select_applies_industry_cap(self):
        rows = []
        for index, ticker in enumerate(("AAA", "BBB", "CCC", "DDD", "EEE")):
            rows.append(
                {
                    "ticker": ticker,
                    "industry_group": "Tech" if index < 4 else "Health",
                    "eligibility": "eligible",
                    "score": 90 - index,
                    "return_score": 25 - index,
                    "persistence_score": 25 - index,
                    "risk_score": 25 - index,
                    "benchmark_score": 15 - index,
                    "confidence_score": 10,
                }
            )
        selected = analysis._rank_and_select(
            pd.DataFrame(rows), analysis.BASELINE_WEIGHTS, shortlist_size=4, group_cap=3
        )
        self.assertEqual(selected, ["AAA", "BBB", "CCC", "EEE"])

    def test_nested_analysis_uses_only_one_year_holds_and_does_not_promote_partial_universe(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "SPY", "QQQ"]
            groups = ["Tech", "Tech", "Tech", "Industrial", "Health", "Finance", "Benchmark", "Benchmark"]
            growth = [0.16, 0.14, 0.12, 0.10, 0.08, 0.06, 0.07, 0.09]
            dates = pd.date_range("1998-01-02", "2026-08-03", freq="BMS")
            for ticker, rate in zip(tickers, growth):
                years = np.arange(len(dates)) / 12.0
                prices = 100.0 * np.power(1.0 + rate, years)
                pd.DataFrame({"Date": dates, "Adj Close": prices}).to_csv(
                    directory / f"{ticker}.csv", index=False
                )
            (directory / "tickers.txt").write_text("\n".join(tickers), encoding="utf-8")
            pd.DataFrame(
                {
                    "ticker": tickers,
                    "role": ["benchmark" if ticker in {"SPY", "QQQ"} else "candidate" for ticker in tickers],
                    "industry_group": groups,
                }
            ).to_csv(directory / "selection_groups.csv", index=False)
            pd.DataFrame(
                columns=[
                    "ticker", "role", "industry_group", "valid_from", "valid_to",
                    "membership_source", "membership_quality",
                ]
            ).to_csv(directory / "selection_universe_history.csv", index=False)
            args = analysis.parse_args(
                [
                    "--tickers-file", str(directory / "tickers.txt"),
                    "--metadata-file", str(directory / "selection_groups.csv"),
                    "--data-dir", str(directory),
                    "--universe-history-file", str(directory / "selection_universe_history.csv"),
                    "--walk-forward-years", "5",
                    "--minimum-training-cohorts", "2",
                    "--weight-step", "10",
                    "--shortlist-size", "4",
                    "--group-cap", "3",
                    "--bootstrap-iterations", "100",
                ]
            )
            result = analysis.build_score_analysis(args)

        self.assertFalse(result["promotion_passed"])
        self.assertEqual(set(result["cohorts"]["holding_years"]), {1})
        self.assertTrue((result["cohorts"]["validity_status"] == "exploratory").all())
        self.assertGreaterEqual(
            len(result["cohorts"][result["cohorts"]["model"] == "nested_optimized"]),
            2,
        )


if __name__ == "__main__":
    unittest.main()
