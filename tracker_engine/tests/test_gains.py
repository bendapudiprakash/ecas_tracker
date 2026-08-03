import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tracker_engine.src.finance.gains import GainCalculator


class TestGainCalculator(unittest.TestCase):
    def test_holding_gains_profit(self):
        unreal, pct, tot = GainCalculator.calculate_holding_gains(1500.0, 1000.0, 100.0)
        self.assertEqual(unreal, 500.0)
        self.assertEqual(pct, 50.0)
        self.assertEqual(tot, 600.0)

    def test_holding_gains_loss(self):
        unreal, pct, tot = GainCalculator.calculate_holding_gains(800.0, 1000.0, -50.0)
        self.assertEqual(unreal, -200.0)
        self.assertEqual(pct, -20.0)
        self.assertEqual(tot, -250.0)


if __name__ == "__main__":
    unittest.main()
