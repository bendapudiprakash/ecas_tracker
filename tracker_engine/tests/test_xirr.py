import unittest
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tracker_engine.src.finance.returns import XirrSolver, TwrrSolver


class TestReturnsSolvers(unittest.TestCase):
    def test_xirr_positive_return(self):
        cfs = [
            (datetime.date(2020, 1, 1), -10000.0),
            (datetime.date(2021, 1, 1), 11000.0),
        ]
        xrate = XirrSolver.calculate_xirr(cfs)
        self.assertAlmostEqual(xrate, 10.0, delta=0.5)

    def test_twrr(self):
        r = TwrrSolver.calculate_period_twrr(100.0, 110.0, 0.0, 10.0)
        self.assertEqual(round(r * 100.0, 2), 10.0)


if __name__ == "__main__":
    unittest.main()
