"""Financial invariants and source reconciliation; run with unittest discovery."""

import copy
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from visualizer.strategy_analysis import (
    SimulationConfig, drawdown_episodes, equity_curve, expectancy_stats,
    load_strategies, max_loss_streak, monthly_table, position_size, simulate_risk,
)


class FormulaTests(unittest.TestCase):
    def test_expectancy_includes_breakevens_and_absolute_losses(self):
        stats = expectancy_stats([100, -50, 0, 150, -100])
        self.assertEqual(stats["win_rate"], 0.4)
        self.assertEqual(stats["loss_rate"], 0.4)
        self.assertEqual(stats["avg_loss"], 75)
        self.assertEqual(stats["expectancy"], 20)
        self.assertTrue(stats["expectancy_positive"])

    def test_one_sided_and_flat_samples(self):
        for sample, expected in [([10, 20], 15), ([-10, -20], -15), ([0, 0], 0)]:
            with self.subTest(sample=sample):
                stats = expectancy_stats(sample)
                self.assertEqual(stats["expectancy"], expected)
                self.assertEqual(stats["expectancy_positive"], expected > 0)
        for sample in ([], [np.nan], [np.inf]):
            with self.assertRaises(ValueError):
                expectancy_stats(sample)

    def test_initial_loss_counts_and_returns_use_account_capital(self):
        curve = equity_curve([-20, 50, -26], 100)
        np.testing.assert_allclose(curve.equity, [100, 80, 130, 104])
        np.testing.assert_allclose(curve.cumulative_return, [0, -0.2, 0.3, 0.04])
        np.testing.assert_allclose(curve.drawdown_fraction, [0, -0.2, 0, -0.2])

    def test_streak_resets_at_breakeven(self):
        self.assertEqual(max_loss_streak([-1, -2, 0, -1, -2, -3, 1]), 3)

    def test_position_sizing_rounds_down_and_includes_costs(self):
        result = position_size(100000, 0.01, 100, 90, lot_size=25, cost_per_unit=1)
        self.assertEqual(result["units"], 75)
        self.assertEqual(result["estimated_risk"], 825)
        self.assertLessEqual(result["estimated_risk"], result["risk_budget"])
        self.assertEqual(position_size(1000, 0.01, 100, 90, lot_size=25)["units"], 0)
        with self.assertRaises(ValueError):
            position_size(10000, 0.01, 100, 100)

    def test_simulation_absorbing_barriers_and_timeouts(self):
        config = SimulationConfig(target_return=0.1, max_drawdown=0.1, horizon_trades=10, paths=100)
        self.assertEqual(simulate_risk([1], 0.1, config)["success_probability"], 1)
        self.assertEqual(simulate_risk([-1], 0.1, config)["drawdown_breach_probability"], 1)
        self.assertEqual(simulate_risk([0], 0.1, config)["timeout_probability"], 1)
        self.assertEqual(simulate_risk([-100], 0.1, config)["drawdown_breach_probability"], 1)
        self.assertEqual(simulate_risk([-1, 1], 0.1, config, win_rate=1)["success_probability"], 1)
        self.assertEqual(simulate_risk([-1, 1], 0.1, config, win_rate=0)["drawdown_breach_probability"], 1)

    def test_simulation_is_reproducible_and_exhaustive(self):
        config = SimulationConfig(paths=300)
        a = simulate_risk([-1.1, -0.5, 0, 1, 3], 0.01, config)
        self.assertEqual(a, simulate_risk([-1.1, -0.5, 0, 1, 3], 0.01, config))
        self.assertAlmostEqual(sum(a[k] for k in ("success_probability", "drawdown_breach_probability", "timeout_probability")), 1)
        with self.assertRaises(ValueError):
            simulate_risk([1, np.nan], 0.01, config)
        with self.assertRaises(ValueError):
            simulate_risk([0, 1], 0.01, config, win_rate=0.9)


class ReportIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw_dir = Path(__file__).resolve().parents[1] / "data/raw/strategy_report"
        if not raw_dir.is_dir() or not any(raw_dir.iterdir()):
            raise unittest.SkipTest("Local raw strategy reports are unavailable")
        cls.strategies = load_strategies(raw_dir)

    def test_all_source_totals_and_expectancy_reconcile(self):
        for name, data in self.strategies.items():
            with self.subTest(strategy=name):
                self.assertTrue(data.checks.passed.all(), data.checks.to_string())
                self.assertAlmostEqual(expectancy_stats(data.trades.net_pnl)["expectancy"], data.trades.net_pnl.mean())
                self.assertAlmostEqual(data.daily.net_pnl.sum(), data.trades.net_pnl.sum())
                self.assertAlmostEqual(monthly_table(data).net_pnl.sum(), data.trades.net_pnl.sum())
                self.assertFalse(data.trades.status.eq("OPEN").any())

    def test_trailing_stops_do_not_replace_initial_risk(self):
        data = self.strategies.get("timeseries_trend_v3")
        if data is None:
            self.skipTest("Example strategy unavailable")
        example = data.trades.loc[data.trades.id.eq("bab3a883")]
        if example.empty:
            self.skipTest("Original example trade unavailable")
        trade = example.iloc[0]
        self.assertGreater(trade.stoploss, trade.entry_price)
        self.assertLess(trade.initial_stop, trade.entry_price)
        self.assertGreater(trade.initial_risk, 0)

    def test_pre_entry_equity_has_no_future_pnl(self):
        for data in self.strategies.values():
            for _, trade in data.trades.loc[data.trades.chronology_valid].iterrows():
                expected = data.initial_cash + data.trades.loc[data.trades.exit_time.lt(trade.timestamp), "net_pnl"].sum()
                self.assertAlmostEqual(trade.equity_before_entry, expected)

    def test_invalid_chronology_remains_visible_and_has_unknown_percentage_risk(self):
        for data in self.strategies.values():
            bad = data.trades.loc[~data.trades.chronology_valid]
            self.assertTrue(bad.risk_fraction.isna().all())
            self.assertTrue(bad.holding_minutes.isna().all())
            self.assertTrue(bad.net_pnl.notna().all())

    def test_drawdown_episode_includes_initial_peak_and_unrecovered_tail(self):
        data = copy.copy(next(iter(self.strategies.values())))
        initial = data.initial_cash
        dates = pd.date_range("2026-01-01", periods=4)
        data.daily = pd.DataFrame({"equity": np.array([0.9, 1.0, 1.2, 1.1]) * initial}, index=dates)
        episodes = drawdown_episodes(data).sort_values("peak_date")
        self.assertEqual(len(episodes), 2)
        self.assertEqual(episodes.iloc[0].peak_date, pd.Timestamp("2025-12-31"))
        self.assertEqual(episodes.iloc[0].duration_days, 2)
        self.assertTrue(episodes.iloc[0].recovered)
        self.assertFalse(episodes.iloc[1].recovered)
        self.assertTrue(pd.isna(episodes.iloc[1].recovery_date))


if __name__ == "__main__":
    unittest.main()
