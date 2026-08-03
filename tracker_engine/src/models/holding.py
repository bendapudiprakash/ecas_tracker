"""
Security Holding Domain Dataclass
"""

from dataclasses import dataclass, field
from typing import Dict, Any
from tracker_engine.src.models.security import SecurityIdentity


@dataclass
class SecurityHolding:
    identity: SecurityIdentity
    quantity: float
    price: float
    market_value: float
    cost_basis: float = 0.0
    realized_gain: float = 0.0
    unrealized_gain: float = 0.0
    unrealized_pct: float = 0.0
    total_gain: float = 0.0
    pan: str = ""
    investor_name: str = ""
    statement_period: str = ""

    def __post_init__(self):
        if self.market_value <= 0.0 and self.quantity > 0.0 and self.price > 0.0:
            self.market_value = round(self.quantity * self.price, 2)
        if self.cost_basis > 0.0:
            self.unrealized_gain = round(self.market_value - self.cost_basis, 2)
            self.unrealized_pct = round((self.unrealized_gain / self.cost_basis) * 100.0, 2)
        self.total_gain = round(self.unrealized_gain + self.realized_gain, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_class": self.identity.asset_class,
            "isin": self.identity.isin,
            "security_name": self.identity.security_name,
            "dp_id": self.identity.dp_id,
            "depository": self.identity.depository,
            "quantity": self.quantity,
            "price": self.price,
            "value": self.market_value,
            "cost_basis": self.cost_basis,
            "realized_gain": self.realized_gain,
            "unrealized_gain": self.unrealized_gain,
            "unrealized_pct": self.unrealized_pct,
            "total_gain": self.total_gain,
            "pan": self.pan,
            "investor_name": self.investor_name,
            "statement_period": self.statement_period,
        }
