"""
XIRR & TWRR Financial Solvers
"""

import datetime
from typing import List, Tuple


class XirrSolver:
    @staticmethod
    def calculate_xirr(cashflows: List[Tuple[datetime.date, float]]) -> float:
        """
        Calculates Extended Internal Rate of Return (XIRR) for a series of (date, amount) tuples.
        Amounts are negative for cash invested, positive for current market value.
        """
        if not cashflows or len(cashflows) < 2:
            return 0.0

        # Ensure sorted by date
        sorted_cfs = sorted(cashflows, key=lambda x: x[0])
        d0 = sorted_cfs[0][0]

        def npv(r: float) -> float:
            if r <= -0.999:
                return 1e15
            total = 0.0
            for d, cf in sorted_cfs:
                dt = (d - d0).days / 365.25
                total += cf / ((1.0 + r) ** dt)
            return total

        low, high = -0.5, 2.5
        f_low, f_high = npv(low), npv(high)
        if f_low * f_high > 0:
            return 0.0

        for _ in range(50):
            mid = (low + high) / 2.0
            f_mid = npv(mid)
            if f_low * f_mid <= 0:
                high = mid
                f_high = f_mid
            else:
                low = mid
                f_low = f_mid

        return round(mid * 100.0, 2)


class TwrrSolver:
    @staticmethod
    def calculate_period_twrr(
        v_prev: float,
        v_curr: float,
        net_inflow: float,
        appreciation: float
    ) -> float:
        """
        Calculates Modified Dietz period return rate.
        """
        denom = v_prev + max(0.0, 0.5 * net_inflow)
        if denom <= 0:
            return 0.0
        r_dietz = appreciation / denom
        return max(-0.25, min(0.25, r_dietz))
