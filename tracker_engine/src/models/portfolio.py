"""
Portfolio & Snapshot Aggregate Domain Dataclasses
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from tracker_engine.src.models.holding import SecurityHolding


@dataclass
class AssetClassMetrics:
    asset_class: str
    prev_value: float = 0.0
    curr_value: float = 0.0
    cost_basis: float = 0.0
    net_capital_inflow: float = 0.0
    realized_gain: float = 0.0
    unrealized_gain: float = 0.0
    unrealized_pct: float = 0.0
    annualized_xirr: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_class": self.asset_class,
            "prev_value": self.prev_value,
            "curr_value": self.curr_value,
            "cost_basis": self.cost_basis,
            "net_capital_inflow": self.net_capital_inflow,
            "realized_gain": self.realized_gain,
            "unrealized_gain": self.unrealized_gain,
            "unrealized_pct": self.unrealized_pct,
            "annualized_xirr": self.annualized_xirr,
        }


@dataclass
class MonthlySnapshot:
    statement_period: str
    portfolio_value: float
    holdings: List[SecurityHolding] = field(default_factory=list)
    pan: str = ""
    investor_name: str = ""
    cas_id: str = ""


@dataclass
class PortfolioMetrics:
    start_period: str
    latest_period: str
    latest_valuation: float
    starting_valuation: float
    total_fresh_deposits: float
    total_capital_withdrawn: float
    net_capital_injected: float
    reinvested_sales_proceeds: float
    gross_capital_deployed: float
    unrealized_market_gain: float
    total_realized_gain: float
    portfolio_xirr: float
    capital_weighted_nav: float
    twrr_index: float
    asset_class_metrics: Dict[str, AssetClassMetrics] = field(default_factory=dict)
