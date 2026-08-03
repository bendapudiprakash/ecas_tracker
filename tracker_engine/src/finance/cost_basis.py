"""
Cost Basis & Lot Accounting Engine
"""

from collections import defaultdict
from typing import Dict, List, Any, Tuple
from tracker_engine.src.models.security import SecurityIdentity


class CostBasisCalculator:
    def __init__(self):
        self._running_cost: Dict[Any, float] = defaultdict(float)
        self._running_realized: Dict[Any, float] = defaultdict(float)
        self._first_seen_period: Dict[Any, str] = {}

    def get_cost_basis(self, key: Any) -> float:
        return max(0.0, self._running_cost.get(key, 0.0))

    def get_realized_gain(self, key: Any) -> float:
        return self._running_realized.get(key, 0.0)

    def process_monthly_transition(
        self,
        period: str,
        prev_holdings: Dict[Any, Dict[str, Any]],
        curr_holdings: Dict[Any, Dict[str, Any]]
    ):
        """
        Processes month-over-month quantity and valuation changes for all securities.
        """
        all_keys = set(prev_holdings.keys()) | set(curr_holdings.keys())

        for key in all_keys:
            p = prev_holdings.get(key)
            c = curr_holdings.get(key)

            if p and c:
                qp, qc = p.get("quantity", 0.0), c.get("quantity", 0.0)
                vp, vc = p.get("value", 0.0), c.get("value", 0.0)

                # Prioritize explicit Total Cost extracted directly from PDF table
                if c.get("total_cost", 0.0) > 0.0:
                    self._running_cost[key] = c["total_cost"]
                elif qp > 0 and qc > 0:
                    if qc > qp:
                        # Purchase / Addition of units
                        inflow = vc * (1.0 - (qp / qc))
                        self._running_cost[key] += inflow
                    elif qc < qp:
                        # Partial / Full Redemption of units
                        frac_sold = (qp - qc) / qp
                        cost_sold = self._running_cost[key] * frac_sold
                        proceeds = vp * frac_sold
                        realized = proceeds - cost_sold
                        self._running_realized[key] += realized
                        self._running_cost[key] -= cost_sold
            elif not p and c:
                # Brand new position added
                vc = c.get("value", 0.0)
                tc = c.get("total_cost", 0.0)
                self._running_cost[key] += (tc if tc > 0.0 else vc)
                if key not in self._first_seen_period:
                    self._first_seen_period[key] = period
            elif p and not c:
                # Position fully exited / closed
                vp = p.get("value", 0.0)
                cost_sold = self._running_cost[key]
                realized = vp - cost_sold
                self._running_realized[key] += realized
                self._running_cost[key] = 0.0
