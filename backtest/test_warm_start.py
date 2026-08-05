"""Tests for the GA warm start (H-014).

Warm starting seeds part of each walk-forward window's GA population with the
previous window's winner. The properties that matter: the elite really is
inherited unchanged, the population still contains genuinely random members so
the search can escape a stale answer, every individual is legal for the GA's
gene space and fitness constraints, and turning the option off reproduces
today's behaviour exactly.
"""
import importlib.util
import unittest
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent

# Distinguishes "argument not supplied" from an explicit None, which is itself
# one of the cases under test.
_UNSET = object()


def base_gene_space():
    # Mirrors genetic_optimize_params: stepped genes use an exclusive upper
    # edge (max + 1), continuous genes are inclusive.
    return [
        {"low": 2, "high": 61, "step": 1},      # short_ema
        {"low": 30, "high": 301, "step": 1},    # long_ema
        {"low": 8, "high": 15},                 # stop_loss
        {"low": 0, "high": 4, "step": 1},       # cooldown
        {"low": 2.5, "high": 4.0},              # drawdown_exit_pct
        {"low": 1.0, "high": 3.0},              # reentry_rebound_pct
        {"low": 10, "high": 41, "step": 1},     # rsi_oversold
        {"low": 60, "high": 91, "step": 1},     # rsi_overbought
    ]


def base_params(**overrides):
    params = {
        "short_ema": 45,
        "long_ema": 114,
        "stop_loss": 13.26,
        "cooldown": 2,
        "drawdown_exit_pct": 3.43,
        "reentry_rebound_pct": 1.94,
        "rsi_oversold": 30,
        "rsi_overbought": 66,
        "take_profit_pct": 12.5,
        "exposure_multiplier": 1.0,
    }
    params.update(overrides)
    return params


class WarmStartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "warm_start_test_backtester", SCRIPT_DIR / "backtest_stocks.py"
        )
        cls.bt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bt)

    def build(self, pop_size=10, fraction=0.5, params=_UNSET, gene_space=None,
              take_profit=False, exposure=False, seed=7):
        np.random.seed(seed)
        return self.bt.build_warm_start_population(
            base_params() if params is _UNSET else params,
            gene_space if gene_space is not None else base_gene_space(),
            pop_size,
            fraction,
            take_profit,
            exposure,
            1.0,
        )

    def test_elite_is_inherited_unchanged(self):
        population = self.build()
        self.assertEqual(
            population[0],
            [45.0, 114.0, 13.26, 2.0, 3.43, 1.94, 30.0, 66.0],
        )

    def test_population_size_and_seeded_fraction(self):
        population = self.build(pop_size=10, fraction=0.5)
        self.assertEqual(len(population), 10)
        # Half inherited (1 elite + 4 jittered), half random.
        near_elite = [
            row for row in population
            if abs(row[0] - 45.0) <= 12 and abs(row[1] - 114.0) <= 40
        ]
        self.assertGreaterEqual(len(near_elite), 5)

    def test_always_keeps_at_least_one_random_individual(self):
        # Even at fraction 1.0 the search must be able to escape the old answer.
        population = self.build(pop_size=6, fraction=1.0)
        self.assertEqual(len(population), 6)
        inherited = population[:5]
        self.assertEqual(len(inherited), 5)
        distinct = {tuple(row) for row in population}
        self.assertGreater(len(distinct), 1)

    def test_jittered_individuals_differ_from_elite(self):
        population = self.build(pop_size=12, fraction=0.5)
        jittered = population[1:6]
        self.assertTrue(
            any(row != population[0] for row in jittered),
            "warm-start copies collapsed onto the elite",
        )

    def test_every_gene_stays_inside_its_space(self):
        gene_space = base_gene_space()
        population = self.build(pop_size=25, fraction=0.6, gene_space=gene_space)
        for row in population:
            for value, spec in zip(row, gene_space):
                step = spec.get("step")
                highest = spec["high"] - (step if step else 0)
                self.assertGreaterEqual(value, spec["low"])
                self.assertLessEqual(value, highest)
                if step:
                    self.assertAlmostEqual(value, round(value))

    def test_fitness_constraints_are_repaired(self):
        # fitness_func rejects these outright with -inf, so seeded individuals
        # must never violate them.
        gene_space = base_gene_space()
        population = self.build(pop_size=30, fraction=0.7, gene_space=gene_space)
        for row in population[:21]:  # the inherited portion
            self.assertGreaterEqual(
                row[1] - row[0], self.bt.GA_MIN_EMA_SEPARATION,
                f"EMA separation violated: {row[:2]}",
            )
            self.assertLess(row[6], row[7], f"RSI guards inverted: {row[6:8]}")

    def test_optional_genes_are_appended_in_order(self):
        gene_space = base_gene_space() + [
            {"low": 0.0, "high": 20.0},   # take_profit_pct
            {"low": 0.5, "high": 1.0},    # exposure_multiplier
        ]
        population = self.build(
            pop_size=4, fraction=0.5, gene_space=gene_space,
            take_profit=True, exposure=True,
        )
        self.assertEqual(len(population[0]), 10)
        self.assertAlmostEqual(population[0][8], 12.5)
        self.assertAlmostEqual(population[0][9], 1.0)

    def test_disabled_when_nothing_to_inherit(self):
        # First window of a run: no previous winner, so pygad keeps its own
        # random initialization and behaviour is unchanged.
        self.assertIsNone(self.build(params=None))
        self.assertIsNone(self.build(params={}))

    def test_malformed_previous_params_fall_back_safely(self):
        self.assertIsNone(self.build(params={"short_ema": 5}))

    def test_reproducible_for_a_given_seed(self):
        self.assertEqual(self.build(seed=123), self.build(seed=123))
        self.assertNotEqual(self.build(seed=123), self.build(seed=456))

    def test_snap_gene_to_space_respects_exclusive_upper_edge(self):
        stepped = {"low": 2, "high": 61, "step": 1}
        self.assertEqual(self.bt.snap_gene_to_space(999, stepped), 60.0)
        self.assertEqual(self.bt.snap_gene_to_space(-5, stepped), 2.0)
        self.assertEqual(self.bt.snap_gene_to_space(7.4, stepped), 7.0)
        continuous = {"low": 2.5, "high": 4.0}
        self.assertEqual(self.bt.snap_gene_to_space(9.0, continuous), 4.0)
        self.assertAlmostEqual(self.bt.snap_gene_to_space(3.3, continuous), 3.3)

    def test_repair_falls_back_to_elite_values(self):
        gene_space = base_gene_space()
        elite = [45.0, 114.0, 13.26, 2.0, 3.43, 1.94, 30.0, 66.0]
        broken = [60.0, 61.0, 13.26, 2.0, 3.43, 1.94, 70.0, 20.0]
        repaired = self.bt.repair_gene_vector(broken, elite, gene_space)
        self.assertEqual(repaired[0], 45.0)
        self.assertEqual(repaired[1], 114.0)
        self.assertEqual(repaired[6], 30.0)
        self.assertEqual(repaired[7], 66.0)


if __name__ == "__main__":
    unittest.main()
