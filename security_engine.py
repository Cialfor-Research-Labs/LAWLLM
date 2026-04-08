import re
from typing import Optional, Tuple, List

# ---------------------------------------------------------------------------
# Strict Configuration
# ---------------------------------------------------------------------------

ALLOWED_ACTS = ["BNS", "BNSS", "The Information Technology Act, 2000", "Contract Act"]

# ---------------------------------------------------------------------------
# Mandated Functions
# ---------------------------------------------------------------------------

def is_valid_query(query: str) -> bool:
    """Pre-LLM filter for prompt injection and jailbreak patterns."""
    blocked_patterns = [
        "ignore previous instructions",
        "act as",
        "pretend to be",
        "system prompt",
        "jailbreak"
    ]

    query_lower = query.lower()
    for pattern in blocked_patterns:
        if pattern in query_lower:
            return False

    return True

def is_legal_query(query: str) -> bool:
    """Strict routing: Determine if query is in legal domain."""
    # Simple version as requested (upgrade later if needed)
    legal_keywords = [
        "section", "act", "law", "legal", "contract", "notice",
        "harassment", "fake", "profile", "social media", "money", 
        "threat", "victim", "report", "misuse", "crime", "police",
        "complaint", "court", "judge", "rights", "illegal", "punish",
        "advice", "advocate", "lawyer", "justice", "penalty", "extortion",
        "fraud", "cyber", "online", "defamation", "identity", "theft",
        "consumer", "faulty", "defective", "damage", "injury", "blast",
        "refund", "warranty", "service", "purchase", "product", "liability",
        "safety", "harm", "sue", "compensation", "damages"
    ]
    
    query_lower = query.lower()
    return any(word in query_lower for word in legal_keywords)

def validate_output(response: str, allowed_sections: List[str]) -> bool:
    """Verifies that cited sections in the response are present in the retrieved context."""
    import re
    
    # 🚫 Hard rejection for legacy acts like IPC as requested
    if "IPC" in response.upper():
        return False

    # Find all "Section X" patterns
    sections_found = re.findall(r"Section\s+\d+", response, re.IGNORECASE)

    for sec in sections_found:
        # Check if the section name (case-insensitive) is in our allowed list
        sec_clean = re.sub(r"\s+", " ", sec).strip().lower()
        if not any(sec_clean in allowed.lower() for allowed in allowed_sections):
            return False

    return True

# ---------------------------------------------------------------------------
# Sanitization Helper
# ---------------------------------------------------------------------------

def sanitize_user_input(text: str) -> str:
    """Light sanitization to remove brackets and hidden directives."""
    # Remove text in brackets
    cleaned = re.sub(r"\[.*?\]", "", text)
    return cleaned.strip()
