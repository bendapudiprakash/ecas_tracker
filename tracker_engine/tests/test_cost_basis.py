import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tracker_engine.src.finance.cost_basis import CostBasisCalculator


class TestCostBasisCalculator(unittest.TestCase):
    def setUp(self):
        self.calc = CostBasisCalculator()

    def test_initial_purchase(self):
        prev = {}
        curr = {"INE123A01011": {"quantity": 100.0, "price": 10.0, "value": 1000.0}}
        self.calc.process_monthly_transition("JAN 2024", prev, curr)
        self.assertEqual(self.calc.get_cost_basis("INE123A01011"), 1000.0)
        self.assertEqual(self.calc.get_realized_gain("INE123A01011"), 0.0)

    def test_additional_purchase(self):
        prev = {"INE123A01011": {"quantity": 100.0, "price": 10.0, "value": 1000.0}}
        curr = {"INE123A01011": {"quantity": 200.0, "price": 15.0, "value": 3000.0}}
        self.calc.process_monthly_transition("JAN 2024", {}, prev)
        self.calc.process_monthly_transition("FEB 2024", prev, curr)
        # Inflow = 3000 * (1 - 100/200) = 1500
        # Total Cost Basis = 1000 + 1500 = 2500
        self.assertEqual(self.calc.get_cost_basis("INE123A01011"), 2500.0)

    def test_partial_redemption(self):
        prev = {"INE123A01011": {"quantity": 100.0, "price": 10.0, "value": 1000.0}}
        curr = {"INE123A01011": {"quantity": 50.0, "price": 20.0, "value": 1000.0}}
        self.calc.process_monthly_transition("JAN 2024", {}, prev)
        self.calc.process_monthly_transition("FEB 2024", prev, curr)
        # Fraction sold = 50/100 = 0.5
        # Cost sold = 1000 * 0.5 = 500
        # Remaining Cost Basis = 1000 - 500 = 500
        # Proceeds = 1000 * 0.5 = 500
        # Realized Gain = 500 - 500 = 0
        self.assertEqual(self.calc.get_cost_basis("INE123A01011"), 500.0)
        self.assertEqual(self.calc.get_realized_gain("INE123A01011"), 0.0)


if __name__ == "__main__":
    unittest.main()
