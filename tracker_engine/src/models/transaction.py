"""
Trade Transaction Domain Dataclass & Enum
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any
from tracker_engine.src.models.security import SecurityIdentity


class TransactionType(Enum):
    PURCHASE = "PURCHASE"
    SIP = "SIP"
    REDEMPTION = "REDEMPTION"
    SWITCH_IN = "SWITCH_IN"
    SWITCH_OUT = "SWITCH_OUT"
    DIVIDEND_REINVEST = "DIVIDEND_REINVEST"
    DEMAT_CREDIT = "DEMAT_CREDIT"
    DEMAT_DEBIT = "DEMAT_DEBIT"
    OTHER = "OTHER"


@dataclass
class TradeTransaction:
    transaction_date: str
    statement_period: str
    identity: SecurityIdentity
    transaction_type: str
    amount: float
    units: float = 0.0
    price_nav: float = 0.0
    description: str = ""
    pan: str = ""
    investor_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transaction_date": self.transaction_date,
            "statement_period": self.statement_period,
            "asset_class": self.identity.asset_class,
            "isin": self.identity.isin,
            "security_name": self.identity.security_name,
            "transaction_type": self.transaction_type,
            "amount": self.amount,
            "units": self.units,
            "price_nav": self.price_nav,
            "description": self.description,
            "pan": self.pan,
            "investor_name": self.investor_name,
        }
