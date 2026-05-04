"""
Scope validation for the new TLLAC chat flow.

This service intentionally does not perform trained-data or RAG lookups.
It only gates whether a query appears to belong to Indian legal context.
"""

from typing import List, Tuple
import logging

logger = logging.getLogger("tllac.services.validation")

_INDIAN_LEGAL_KEYWORDS: List[str] = [
    "legal",
    "law",
    "act",
    "section",
    "article",
    "statute",
    "regulation",
    "india",
    "indian",
    "bharat",
    "supreme court",
    "high court",
    "district court",
    "tribunal",
    "ipc",
    "crpc",
    "cpc",
    "bns",
    "bnss",
    "bsa",
    "constitution",
    "fundamental rights",
    "contract",
    "property",
    "possession",
    "criminal",
    "civil",
    "family",
    "divorce",
    "maintenance",
    "arbitration",
    "mediation",
    "bail",
    "fir",
    "chargesheet",
    "writ",
    "habeas corpus",
    "mandamus",
    "certiorari",
    "limitation act",
    "transfer of property",
    "consumer protection",
    "rti",
    "dpdp",
    "it act",
    "cyber",
    "gst",
    "income tax",
    "insolvency",
    "bankruptcy",
    "labour",
    "labor",
    "motor accident",
    "mact",
]


def is_indian_legal_query(query: str) -> bool:
    """Return True if the query appears to relate to Indian law."""
    q_lower = (query or "").lower()
    return any(keyword in q_lower for keyword in _INDIAN_LEGAL_KEYWORDS)


def validate_query(query: str) -> Tuple[bool, str]:
    """
    Validate only the Indian legal scope.

    Returns:
        (is_valid, fallback_message)
    """
    if not is_indian_legal_query(query):
        logger.info("Query rejected: not Indian legal context.")
        return (False, "This is out of context")
    return (True, "")
