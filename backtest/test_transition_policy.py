"""Tests for the offset-month transition handling.

The scenarios pin down the boundary behavior directly: a position carried
across a walk-forward window boundary with parameters that changed at the
switch. Policy "none" documents the current phantom-exit behavior; policy
"grandfather" must keep the old exit rules until the carried position closes.
"""
import importlib.util
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from walk_forward_replay import (
    advance_carry_exit_params,
    evaluate_parameter_window,
    extract_carry_exit_params,
)

SCRIPT_DIR = Path(__file__).resolve().parent


def make_windows(lookback_prices, test_prices):
    total = len(lookback_prices) + len(test_prices)
    dates = pd.bdate_range("2024-01-01", periods=total)
    dates.name = "Date"
    lookback = pd.DataFrame(
        {"NAV": list(lookback_prices)}, index=dates[: len(lookback_prices)]
    )
    test = pd.DataFrame(
        {"NAV": list(test_prices)}, index=dates[len(lookback_prices):]
    )
    return lookback, test


def carried_state(entry_price, peak_price=None, shares=100.0):
    return {
        "position": 1.0,
        "shares": shares,
        "cash": 0.0,
        "entry_price": entry_price,
        "peak_price": peak_price if peak_price is not None else entry_price,
        "cash_low_watermark": 0.0,
        "cooldown_counter": 0,
    }


def window_params(**overrides):
    params = {
        "short_ema": 5,
        "long_ema": 50,
        "stop_loss": 25.0,
        "use_take_profit": False,
        "take_profit_pct": 50.0,
        "cooldown": 0,
        "drawdown_exit_pct": 30.0,
        "reentry_rebound_pct": 2.0,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "exposure_multiplier": 1.0,
    }
    params.update(overrides)
    return params


class TransitionPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        module_path = SCRIPT_DIR / "backtest_stocks.py"
        spec = importlib.util.spec_from_file_location(
            "transition_test_backtester", module_path
        )
        cls.bt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bt)

    def evaluate(self, lookback, test, params, carry_state, carry_exit_params):
        return evaluate_parameter_window(
            lookback,
            test,
            params,
            10000.0,
            carry_state,
            self.bt.backtest_enhanced_dual_ema,
            "generic",
            self.bt.DEFAULT_RSI_PERIOD,
            carry_exit_params=carry_exit_params,
        )

    def test_tighter_stop_loss_fires_phantom_exit_under_policy_none(self):
        # Carried position is down 6% with no market movement inside the new
        # window; the new window's tighter 4% stop fires on the very first bar.
        lookback, test = make_windows([100.0] * 100, [94.0] * 30)
        new_params = window_params(stop_loss=4.0)
        result = self.evaluate(lookback, test, new_params, carried_state(100.0), None)
        trades = result[3]
        self.assertGreaterEqual(len(trades), 1)
        self.assertEqual(trades[0][0], "STOP_LOSS")
        self.assertEqual(trades[0][1], test.index[0])

    def test_grandfather_keeps_old_stop_loss_for_carried_position(self):
        lookback, test = make_windows([100.0] * 100, [94.0] * 30)
        new_params = window_params(stop_loss=4.0)
        old_exit = extract_carry_exit_params(window_params(stop_loss=8.0))
        result = self.evaluate(
            lookback, test, new_params, carried_state(100.0), old_exit
        )
        trades = result[3]
        final_state = result[9]
        self.assertEqual(trades, [])
        self.assertGreater(final_state["position"], 0)
        self.assertTrue(final_state["carried_position_open"])

    def test_new_take_profit_fires_phantom_exit_under_policy_none(self):
        # Carried position is up 6%; the previous window had no take-profit,
        # the new one takes profit at 4%.
        lookback, test = make_windows([100.0] * 100, [106.0] * 30)
        new_params = window_params(use_take_profit=True, take_profit_pct=4.0)
        result = self.evaluate(lookback, test, new_params, carried_state(100.0), None)
        trades = result[3]
        self.assertGreaterEqual(len(trades), 1)
        self.assertEqual(trades[0][0], "TAKE_PROFIT")
        self.assertEqual(trades[0][1], test.index[0])

    def test_grandfather_keeps_old_take_profit_rules(self):
        lookback, test = make_windows([100.0] * 100, [106.0] * 30)
        new_params = window_params(use_take_profit=True, take_profit_pct=4.0)
        old_exit = extract_carry_exit_params(window_params(use_take_profit=False))
        result = self.evaluate(
            lookback, test, new_params, carried_state(100.0), old_exit
        )
        self.assertEqual(result[3], [])
        self.assertTrue(result[9]["carried_position_open"])

    def test_tighter_drawdown_exit_fires_phantom_sell_under_policy_none(self):
        # Carried peak is 110, price sits at 100 (-9.1% from peak, flat market).
        # Old drawdown exit 20% tolerated it; the new 3% exits immediately.
        lookback_prices = np.linspace(104.0, 100.5, 100)
        lookback, test = make_windows(lookback_prices, [100.0] * 30)
        new_params = window_params(drawdown_exit_pct=3.0)
        state = carried_state(100.0, peak_price=110.0)
        result = self.evaluate(lookback, test, new_params, state, None)
        trades = result[3]
        self.assertGreaterEqual(len(trades), 1)
        self.assertEqual(trades[0][0], "SELL")
        self.assertEqual(trades[0][1], test.index[0])

    def test_grandfather_keeps_old_drawdown_exit(self):
        lookback_prices = np.linspace(104.0, 100.5, 100)
        lookback, test = make_windows(lookback_prices, [100.0] * 30)
        new_params = window_params(drawdown_exit_pct=3.0)
        old_exit = extract_carry_exit_params(window_params(drawdown_exit_pct=20.0))
        state = carried_state(100.0, peak_price=110.0)
        result = self.evaluate(lookback, test, new_params, state, old_exit)
        self.assertEqual(result[3], [])
        self.assertTrue(result[9]["carried_position_open"])

    def test_grandfathered_params_persist_across_surviving_windows(self):
        # The carried position survives two consecutive windows; the exit
        # params of the window that opened it must persist, not refresh.
        lookback, test = make_windows([100.0] * 100, [94.0] * 30)
        old_exit = extract_carry_exit_params(window_params(stop_loss=8.0))
        window2_params = window_params(stop_loss=4.0)
        result = self.evaluate(
            lookback, test, window2_params, carried_state(100.0), old_exit
        )
        carry_state = result[9]
        active = advance_carry_exit_params(old_exit, carry_state, window2_params)
        self.assertIs(active, old_exit)

        # Window 3: yet another harsh param set; still no exit under the
        # original 8% stop while the loss stays at 6%.
        lookback3, test3 = make_windows([94.0] * 100, [94.0] * 30)
        window3_params = window_params(stop_loss=3.0)
        result3 = self.evaluate(lookback3, test3, window3_params, carry_state, active)
        self.assertEqual(result3[3], [])
        self.assertTrue(result3[9]["carried_position_open"])

    def test_grandfathered_stop_still_fires_on_real_breach(self):
        # Grandfathering must not disable exits: once the loss breaches the
        # OLD 8% stop, the carried position is closed and the flag clears.
        lookback, test = make_windows([100.0] * 100, [90.0] * 30)
        new_params = window_params(stop_loss=4.0)
        old_exit = extract_carry_exit_params(window_params(stop_loss=8.0))
        result = self.evaluate(
            lookback, test, new_params, carried_state(100.0), old_exit
        )
        trades = result[3]
        final_state = result[9]
        self.assertGreaterEqual(len(trades), 1)
        self.assertEqual(trades[0][0], "STOP_LOSS")
        self.assertFalse(final_state["carried_position_open"])
        self.assertIsNone(
            advance_carry_exit_params(old_exit, final_state, new_params)
        )

    def test_advance_carry_exit_params_branches(self):
        params = window_params(stop_loss=7.0)
        # Flat -> nothing to grandfather.
        self.assertIsNone(advance_carry_exit_params(None, {"position": 0.0}, params))
        self.assertIsNone(advance_carry_exit_params(None, None, params))
        # Position opened inside the window -> that window's params take over.
        state = {"position": 1.0, "carried_position_open": False}
        adopted = advance_carry_exit_params(None, state, params)
        self.assertEqual(adopted["stop_loss_pct"], 7.0)
        self.assertEqual(adopted["short_ema"], params["short_ema"])
        # Carried position still open -> keep the existing exit params.
        held = {"stop_loss_pct": 9.9}
        state = {"position": 1.0, "carried_position_open": True}
        self.assertIs(advance_carry_exit_params(held, state, params), held)

    def test_classify_phantom_exit_thresholds(self):
        old = window_params(stop_loss=8.0, drawdown_exit_pct=20.0)
        new = window_params(stop_loss=4.0, drawdown_exit_pct=3.0)
        # -6% loss: fires at the new 4% stop, not at the old 8% -> phantom.
        self.assertTrue(
            self.bt.classify_phantom_exit("STOP_LOSS", 94.0, 100.0, 100.0, old, new)
        )
        # -10% loss breaches both stops -> a real exit, not a phantom.
        self.assertFalse(
            self.bt.classify_phantom_exit("STOP_LOSS", 90.0, 100.0, 100.0, old, new)
        )
        # -9.1% off the peak: inside the old 20% tolerance -> phantom SELL.
        self.assertTrue(
            self.bt.classify_phantom_exit("SELL", 100.0, 100.0, 110.0, old, new)
        )
        # First window has no previous params -> never phantom.
        self.assertFalse(
            self.bt.classify_phantom_exit("STOP_LOSS", 94.0, 100.0, 100.0, None, new)
        )


if __name__ == "__main__":
    unittest.main()
