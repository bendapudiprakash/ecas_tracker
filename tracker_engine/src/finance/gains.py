"""
Gain & Loss Calculation Engine
"""

from typing import Dict, Any, Tuple


class GainCalculator:
    @staticmethod
    def calculate_holding_gains(
        market_value: float,
        cost_basis: float,
        realized_gain: float = 0.0
    ) -> Tuple[float, float, float]:
        """
        Calculates (unrealized_gain, unrealized_pct, total_gain) for a holding.
        """
        cost = max(0.0, cost_basis)
        unrealized = round(market_value - cost, 2)
        unrealized_pct = round((unrealized / cost * 100.0), 2) if cost > 0 else 0.0
        total_gain = round(unrealized + realized_gain, 2)
        return (unrealized, unrealized_pct, total_gain)

    @staticmethod
    def calculate_category_summary(
        holdings_metrics: list
    ) -> Dict[str, Dict[str, float]]:
        """
        Aggregates holding-level gain metrics into category-wise summaries.
        """
        summary = {}
        for h in holdings_metrics:
            ac = h.identity.asset_class if hasattr(h, 'identity') else h.get("asset_class", "Other")
            if ac not in summary:
                summary[ac] = {
                    "curr_value": 0.0,
                    "cost_basis": 0.0,
                    "realized_gain": 0.0,
                    "unrealized_gain": 0.0,
                    "total_gain": 0.0,
                }
            
            val = getattr(h, 'market_value', 0.0) if hasattr(h, 'market_value') else h.get("value", 0.0)
            cost = getattr(h, 'cost_basis', 0.0) if hasattr(h, 'cost_basis') else h.get("cost_basis", 0.0)
            real = getattr(h, 'realized_gain', 0.0) if hasattr(h, 'realized_gain') else h.get("realized_gain", 0.0)
            unreal = getattr(h, 'unrealized_gain', 0.0) if hasattr(h, 'unrealized_gain') else h.get("unrealized_gain", 0.0)

            summary[ac]["curr_value"] += val
            summary[ac]["cost_basis"] += cost
            summary[ac]["realized_gain"] += real
            summary[ac]["unrealized_gain"] += unreal
            summary[ac]["total_gain"] += (real + unreal)

        for ac, stats in summary.items():
            c = stats["cost_basis"]
            u = stats["unrealized_gain"]
            stats["unrealized_pct"] = round((u / c * 100.0), 2) if c > 0 else 0.0

        return summary
