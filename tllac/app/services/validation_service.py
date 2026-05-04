"""
Validation Service
===================
Enforces strict Indian Legal context before generating any response.

Steps:
  1. Check whether the query relates to Indian law (keyword heuristic).
  2. Attempt to match the query against keys in trained_data.json.
  3. Return (is_valid, fallback_message, matched_data).
"""

from typing import Dict, Optional, Tuple, List
import re
import logging

logger = logging.getLogger("tllac.services.validation")

# ──────────────────────────────────────────────
# Step 1 — Indian Legal Context Detection
# ──────────────────────────────────────────────
_INDIAN_LEGAL_KEYWORDS: List[str] = [
    # General legal terms
    "legal", "law", "act", "section", "article", "clause", "statute",
    "regulation", "ordinance", "amendment", "bill",
    # India-specific
    "india", "indian", "bharat",
    # Courts
    "supreme court", "high court", "district court", "sessions court",
    "tribunal", "nclat", "ncdrc", "nclt", "cci",
    # Major codes & acts
    "ipc", "crpc", "cpc", "bns", "bnss", "bsa",
    "constitution", "fundamental rights", "directive principles",
    "contract", "property", "possession", "tort",
    "criminal", "civil", "family", "divorce", "maintenance",
    "arbitration", "mediation", "bail", "fir", "chargesheet",
    "writ", "habeas corpus", "mandamus", "certiorari",
    # Specific acts
    "limitation act", "transfer of property", "indian penal code",
    "evidence act", "negotiable instruments", "companies act",
    "consumer protection", "right to information", "rti",
    "dpdp", "data protection", "it act", "cyber", "pocso",
    "dowry", "domestic violence", "sc/st", "obc", "reservation",
    "land acquisition", "eminent domain", "gst", "income tax",
    "insolvency", "bankruptcy", "labour", "labor", "epf", "esi",
    "motor vehicles", "environmental", "ngt",
    # AI & emerging
    "ai regulation", "ai regulations", "meity",
]


def is_indian_legal_query(query: str) -> bool:
    """Return True if the query appears to relate to Indian law."""
    q_lower = query.lower()
    return any(kw in q_lower for kw in _INDIAN_LEGAL_KEYWORDS)


# ──────────────────────────────────────────────
# Step 2 — Trained Data Matching
# ──────────────────────────────────────────────
def get_matched_data(query: str, data: Dict) -> Optional[Dict]:
    """
    Return the best matching entry from trained_data.json.

    Matching strategy:
      1. Exact key match in query text.
      2. Partial keyword overlap (≥ 60% of key words present).
    """
    q_lower = query.lower()

    # Pass 1 — direct substring match
    for key, value in data.items():
        if key.lower() in q_lower:
            return {**value, "matched_key": key}

    # Pass 2 — fuzzy word overlap
    q_words = set(re.findall(r"\w+", q_lower))
    best_match = None
    best_score = 0.0

    for key, value in data.items():
        key_words = set(re.findall(r"\w+", key.lower()))
        if not key_words:
            continue
        overlap = len(q_words & key_words) / len(key_words)
        if overlap > best_score and overlap >= 0.6:
            best_score = overlap
            best_match = {**value, "matched_key": key}

    return best_match


def is_in_trained_data(query: str, data: Dict) -> bool:
    """Check whether any trained data key matches the query."""
    return get_matched_data(query, data) is not None


# ──────────────────────────────────────────────
# Step 3 — Orchestrated Validation
# ──────────────────────────────────────────────
def validate_query(
    query: str, trained_data: Dict
) -> Tuple[bool, str, Optional[Dict]]:
    """
    Run the full validation pipeline.

    Returns:
        (is_valid, fallback_message, matched_data)
    """
    # Rule 1 — Must be an Indian legal query
    if not is_indian_legal_query(query):
        logger.info("Query rejected — not Indian legal context.")
        return (False, "This is out of context", None)

    # Rule 2 — Must have matching trained data
    matched = get_matched_data(query, trained_data)
    if matched is None:
        logger.info("Query accepted as Indian legal but no trained data match.")
        return (False, "This is not in my trained data", None)

    logger.info("Query matched trained topic: %s", matched.get("matched_key"))
    return (True, "", matched)
