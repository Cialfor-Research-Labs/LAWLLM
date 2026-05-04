"""
Validation service for the trained Indian legal chat backend.

This module:
1. Detects whether a query appears to be about Indian law.
2. Matches the query against the local trained dataset.
3. Returns one-line fallbacks when the query is out of scope or unmatched.
"""

from typing import Dict, Iterable, List, Optional, Tuple
import logging
import re

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
    "constitution",
    "fundamental rights",
    "contract",
    "property",
    "possession",
    "criminal",
    "civil",
    "divorce",
    "maintenance",
    "bail",
    "writ",
    "limitation act",
    "transfer of property",
    "consumer protection",
    "rti",
    "dpdp",
    "it act",
    "cyber",
    "gst",
    "labour",
    "labor",
    "motor accident",
    "mact",
    "adverse possession",
]

_TOPIC_ALIASES: Dict[str, List[str]] = {
    "adverse possession": ["adverse possession", "hostile possession", "limitation act"],
    "contract law": ["contract law", "contract", "agreement", "offer", "acceptance", "breach of contract"],
    "ai regulations": ["ai regulation", "ai regulations", "artificial intelligence", "dpdp", "meity"],
    "property disputes": ["property dispute", "property", "title suit", "partition suit", "encroachment"],
    "fundamental rights": ["fundamental rights", "article 14", "article 19", "article 21", "article 32"],
    "ipc offences": ["ipc", "indian penal code", "bns", "section 420", "section 302", "section 376", "498a", "120b"],
    "bail": ["bail", "anticipatory bail", "default bail", "section 436", "section 437", "section 438"],
    "consumer protection": ["consumer protection", "consumer complaint", "deficiency in service", "e-daakhil"],
    "divorce law": ["divorce", "mutual consent divorce", "custody", "maintenance", "section 125 crpc"],
    "right to information": ["rti", "right to information", "information commission"],
    "gst": ["gst", "input tax credit", "gstr", "gst council"],
    "cyber crime": ["cyber crime", "online fraud", "identity theft", "it act", "section 66"],
    "labour law": ["labour law", "labor law", "wages", "gratuity", "maternity benefit", "epf", "esi"],
    "writ jurisdiction": ["writ", "habeas corpus", "mandamus", "certiorari", "quo warranto", "article 226"],
    "motor accident claims": ["motor accident", "mact", "third-party insurance", "pranay sethi"],
}

_LOW_SIGNAL_TOKENS = {
    "act",
    "and",
    "article",
    "about",
    "court",
    "explain",
    "for",
    "in",
    "india",
    "indian",
    "law",
    "legal",
    "mention",
    "of",
    "on",
    "rights",
    "section",
    "tell",
    "the",
    "to",
    "what",
    "which",
}


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _iter_section_terms(query: str) -> Iterable[str]:
    for number in re.findall(r"\b\d+[a-z]?\b", query.lower()):
        yield number
        yield f"section {number}"


def _build_search_corpus(key: str, value: Dict) -> str:
    parts: List[str] = [key, value.get("title", ""), value.get("summary", ""), value.get("law", "")]
    parts.extend(value.get("points", []) or [])
    parts.extend(value.get("case_references", []) or [])
    practical_notes = value.get("practical_notes", "")
    if practical_notes:
        parts.append(practical_notes)
    parts.extend(_TOPIC_ALIASES.get(key, []))
    return " ".join(part for part in parts if part)


def is_indian_legal_query(query: str) -> bool:
    """Return True if the query appears to relate to Indian law."""
    q_lower = query.lower()
    return any(keyword in q_lower for keyword in _INDIAN_LEGAL_KEYWORDS)


def get_matched_data(query: str, data: Dict) -> Optional[Dict]:
    """
    Return the best matching entry from trained_data.json.

    The matcher considers:
    - direct key and alias hits
    - overlap against the dataset entry's title, summary, law, points, and cases
    - section-number mentions like "IPC 420" or "Section 438"
    """
    q_lower = query.lower().strip()
    q_words = set(_tokenize(q_lower))
    if not q_words:
        return None

    best_match: Optional[Dict] = None
    best_score = 0.0

    for key, value in data.items():
        key_lower = key.lower()
        title_lower = str(value.get("title", "")).lower()
        corpus = _build_search_corpus(key, value).lower()
        corpus_words = set(_tokenize(corpus))

        score = 0.0
        has_targeted_hit = False

        if key_lower in q_lower:
            score += 8.0
            has_targeted_hit = True
        if title_lower and title_lower in q_lower:
            score += 6.0
            has_targeted_hit = True

        for alias in _TOPIC_ALIASES.get(key, []):
            if alias in q_lower:
                score += 4.0
                has_targeted_hit = True

        overlap_words = q_words & corpus_words
        meaningful_overlap = {
            word for word in overlap_words
            if word not in _LOW_SIGNAL_TOKENS
        }
        score += len(overlap_words) * 1.25

        for section_term in _iter_section_terms(q_lower):
            if section_term in corpus:
                score += 5.0
                has_targeted_hit = True

        if not has_targeted_hit and len(meaningful_overlap) < 2:
            continue

        if score > best_score:
            best_score = score
            best_match = {
                **value,
                "matched_key": key,
                "_match_score": round(score, 3),
            }

    if best_score < 2.5:
        return None
    return best_match


def is_in_trained_data(query: str, data: Dict) -> bool:
    """Check whether any trained data entry matches the query."""
    return get_matched_data(query, data) is not None


def validate_query(query: str, trained_data: Dict) -> Tuple[bool, str, Optional[Dict]]:
    """
    Run the full validation pipeline.

    Returns:
        (is_valid, fallback_message, matched_data)
    """
    if not is_indian_legal_query(query):
        logger.info("Query rejected: not Indian legal context.")
        return (False, "This is out of context", None)

    matched = get_matched_data(query, trained_data)
    if matched is None:
        logger.info("Query accepted as Indian legal but not present in trained data.")
        return (False, "This is not in my trained data", None)

    logger.info(
        "Query matched trained topic '%s' with score %s.",
        matched.get("matched_key"),
        matched.get("_match_score"),
    )
    return (True, "", matched)
