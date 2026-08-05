"""Tests for the data-vintage fingerprint.

Derived slice files (MSFT-3Y.csv etc.) roll forward silently: same filename,
same fund_slice_label, often the same data_end, but a different start date and
row count. Three separate A/B comparisons were invalidated that way. The
fingerprint has to change whenever the traded series changes, and stay stable
when nothing meaningful has.
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent


def frame(start="2024-01-01", periods=10, offset=0.0):
    dates = pd.bdate_range(start, periods=periods)
    dates.name = "Date"
    return pd.DataFrame({"NAV": [100.0 + i + offset for i in range(periods)]}, index=dates)


class DataFingerprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "fingerprint_test_backtester", SCRIPT_DIR / "backtest_stocks.py"
        )
        cls.bt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bt)

    def fp(self, f):
        return self.bt.compute_data_fingerprint(f)

    def test_identical_data_gives_identical_fingerprint(self):
        self.assertEqual(self.fp(frame()), self.fp(frame()))

    def test_rolling_the_window_forward_changes_the_fingerprint(self):
        # The exact failure that invalidated the MSFT-3Y comparison: the slice
        # rolled 3 days forward, so the row count and start date moved while
        # the end date stayed put.
        original = frame(start="2023-07-31", periods=754)
        rolled = frame(start="2023-08-03", periods=751)
        self.assertNotEqual(self.fp(original), self.fp(rolled))

    def test_appending_a_bar_changes_the_fingerprint(self):
        self.assertNotEqual(self.fp(frame(periods=10)), self.fp(frame(periods=11)))

    def test_changing_a_single_price_changes_the_fingerprint(self):
        a = frame()
        b = frame()
        b.iloc[5, b.columns.get_loc("NAV")] = 999.0
        self.assertNotEqual(self.fp(a), self.fp(b))

    def test_works_with_date_column_instead_of_index(self):
        indexed = frame()
        columned = indexed.reset_index()
        self.assertEqual(self.fp(indexed), self.fp(columned))

    def test_insignificant_float_noise_does_not_change_it(self):
        # Guards the fingerprint against float repr drift across pandas/numpy
        # versions; a re-serialized file must not look like new data.
        a = frame()
        b = frame()
        b["NAV"] = b["NAV"] + 1e-15
        self.assertEqual(self.fp(a), self.fp(b))

    def test_file_hash_detects_byte_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "slice.csv"
            frame().to_csv(path)
            first = self.bt.compute_file_sha256(path)
            self.assertEqual(first, self.bt.compute_file_sha256(path))
            frame(periods=11).to_csv(path)
            self.assertNotEqual(first, self.bt.compute_file_sha256(path))


if __name__ == "__main__":
    unittest.main()
