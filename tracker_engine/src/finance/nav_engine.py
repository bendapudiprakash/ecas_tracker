"""
Zerodha Console Unitized Performance NAV Engine
"""

from typing import List


class ZerodhaNavEngine:
    @staticmethod
    def calculate_nav(current_valuation: float, cumulative_net_injected: float) -> float:
        """
        Calculates Capital-Weighted Zerodha Console Style NAV (Base 100.0).
        """
        if cumulative_net_injected > 0:
            return round(100.0 * (current_valuation / cumulative_net_injected), 2)
        return 100.0
