"""
Security Identity & Asset Category Domain Rules
"""

from dataclasses import dataclass
from typing import Optional, Union, Tuple


def get_canonical_asset_class(isin: str, raw_class: str, name: str) -> str:
    """Normalize asset category using canonical ISIN and security name rules."""
    isin_u = (isin or "").strip().upper()
    name_u = (name or "").strip().upper()
    raw_u = (raw_class or "").strip().upper()

    if isin_u == "INE494B04019" or "PREFERENCE" in name_u:
        return "Preference Shares (P)"
    if (
        isin_u.startswith("IN0020")
        or "GOVT OF INDIA" in name_u
        or "SGB" in name_u
        or "SOVEREIGN GOLD" in name_u
    ):
        return "Government Securities (G)"
    if isin_u.startswith("NPS_") or "PENSION" in name_u or "NPS" in name_u:
        return "National Pension System (N)"
    if isin_u == "INE103C07132" or "BONDS" in raw_u or "CORPORATE BONDS" in name_u:
        return "Corporate Bonds (C)"
    if "ALTERNATE" in raw_u or "AIF" in raw_u:
        return "Alternate Investment Fund (A)"
    if isin_u.startswith("INF") or "MUTUAL" in raw_u:
        return "Mutual Funds (M)"
    if isin_u.startswith("INE") or "EQUITIES" in raw_u:
        return "Equities (E)"

    return raw_class or "Other"


@dataclass(frozen=True)
class SecurityIdentity:
    isin: str
    security_name: str
    dp_id: str = ""
    depository: str = ""
    asset_class: str = ""

    def __post_init__(self):
        clean_isin = (self.isin or "").strip().upper()
        clean_name = (self.security_name or "").strip().upper()
        clean_dp = (self.dp_id or "").strip()
        clean_ac = get_canonical_asset_class(clean_isin, self.asset_class, clean_name)
        
        # Override frozen attributes via object.__setattr__
        object.__setattr__(self, "isin", clean_isin)
        object.__setattr__(self, "security_name", clean_name)
        object.__setattr__(self, "dp_id", clean_dp)
        object.__setattr__(self, "asset_class", clean_ac)

    def get_unique_key(self) -> Union[str, Tuple[str, str]]:
        """
        Primary identity key resolution fallback chain:
        1. Clean ISIN if valid and not UNKNOWN
        2. (ISIN, Security Name) fallback
        """
        if self.isin and self.isin != "UNKNOWN":
            return self.isin
        return (self.isin, self.security_name)
