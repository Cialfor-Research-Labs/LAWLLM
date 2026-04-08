#!/usr/bin/env python3
"""
query_expansion.py — Legal query expansion for hybrid retrieval.

Transforms raw user queries into enriched search queries by:
  1. Normalizing text
  2. Extracting section/act references
  3. Mapping statute abbreviations to full names
  4. Expanding layman terms with legal synonyms
  5. Building structured BM25 queries with column targeting

Usage:
    from query_expansion import build_query
    result = build_query("section 420 IPC punishment")
    # result.expanded_query  → for embedding search
    # result.bm25_query      → for FTS5 search
    # result.filters          → {section_number, act}
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Statute abbreviation → full Act name
# ---------------------------------------------------------------------------
STATUTE_MAP: Dict[str, str] = {
    "ipc": "Indian Penal Code",
    "bns": "Bharatiya Nyaya Sanhita",
    "crpc": "Code of Criminal Procedure",
    "bnss": "Bharatiya Nagarik Suraksha Sanhita",
    "cpc": "Code of Civil Procedure",
    "bsa": "Bharatiya Sakshya Adhiniyam",
    "iea": "Indian Evidence Act",
    "rera": "Real Estate (Regulation and Development) Act",
    "consumer": "Consumer Protection Act",
    "sarfaesi": "Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act",
    "ndps": "Narcotic Drugs and Psychotropic Substances Act",
    "posh": "The Sexual Harassment Of Women At Workplace (Prevention, Prohibition And Redressal) Act",
    "rti": "The Right to Information Act",
    "it act": "Information Technology Act",
    "ita": "Information Technology Act",
    "information technology act": "Information Technology Act",
    "information technology": "Information Technology Act",
    "gst": "Goods and Services Tax Act",
    "pocso": "Protection of Children from Sexual Offences Act",
    "tada": "Terrorist and Disruptive Activities (Prevention) Act",
    "uapa": "Unlawful Activities (Prevention) Act",
    "companies act": "The Companies Act",
    "transfer of property": "The Transfer Of Property Act",
    "contract act": "The Indian Contract Act",
    "motor vehicles": "The Motor Vehicles Act",
    "arbitration": "The Arbitration And Conciliation Act",
    "negotiable instruments": "The Negotiable Instruments Act",
    "partnership": "The Indian Partnership Act",
    "hindu marriage": "The Hindu Marriage Act",
    "domestic violence": "Protection of Women from Domestic Violence Act",
}

# ---------------------------------------------------------------------------
# Legal synonym expansion (max 3 per term to avoid over-expansion)
# ---------------------------------------------------------------------------
LEGAL_SYNONYMS: Dict[str, List[str]] = {
    # Criminal law
    "cheated": ["cheating", "fraud", "dishonest inducement"],
    "cheating": ["fraud", "dishonest inducement", "deception"],
    "murder": ["culpable homicide", "killing", "homicide"],
    "theft": ["stealing", "dishonest removal", "larceny", "BNS 303"],
    "stole": ["theft", "BNS 303", "dishonest removal"],
    "stolen": ["stolen property", "BNS 317", "theft", "BNS 303"],
    "robbery": ["theft", "extortion", "dacoity"],
    "assault": ["hurt", "grievous hurt", "criminal force"],
    "kidnapping": ["abduction", "wrongful confinement"],
    "rape": ["sexual assault", "sexual offence"],
    "bribe": ["corruption", "gratification", "illegal gratification"],
    "bribery": ["corruption", "gratification"],
    "forgery": ["falsification", "fabrication", "counterfeiting"],
    "defamation": ["libel", "slander", "imputation"],
    "fraud": ["cheating", "misrepresentation", "deception"],
    "dowry": ["dowry death", "cruelty", "harassment"],

    # Civil / contract
    "breach": ["violation", "contravention", "non-compliance"],
    "contract": ["agreement", "covenant"],
    "compensation": ["damages", "remedy", "restitution"],
    "refund": ["compensation", "restitution"],
    "negligence": ["rashness", "rash and negligent"],
    "defective": ["deficiency", "defect", "manufacturing defect"],
    "eviction": ["ejectment", "possession", "tenancy"],
    "property": ["immovable property", "movable property"],

    # Consumer / real estate
    "builder": ["promoter", "developer"],
    "delay": ["breach", "deficiency", "non-delivery"],
    "possession": ["occupancy", "ownership", "title"],
    "flat": ["apartment", "unit", "dwelling"],
    "phone": ["mobile", "cell phone", "movable property"],
    "laptop": ["computer", "personal computer", "movable property"],
    "refund": ["restitution", "compensation", "return"],

    # Procedural
    "bail": ["anticipatory bail", "regular bail", "interim bail"],
    "arrest": ["apprehension", "detention", "custody"],
    "sentence": ["punishment", "penalty", "imprisonment"],
    "fine": ["penalty", "monetary penalty"],
    "imprisonment": ["incarceration", "rigorous imprisonment", "simple imprisonment"],
    "appeal": ["revision", "review"],
    "fir": ["first information report", "complaint"],

    # Family law
    "divorce": ["dissolution of marriage", "matrimonial dispute"],
    "maintenance": ["alimony", "support"],
    "custody": ["guardianship", "visitation"],
    "adoption": ["guardianship", "foster"],

    # Employment / misc
    "termination": ["dismissal", "removal from service"],
    "harassment": ["sexual harassment", "workplace harassment"],
    "discrimination": ["inequality", "unfair treatment"],
    "remedy": ["relief", "compensation", "damages"],

    # Layman → legal
    "cheated online": ["cyber fraud", "online cheating"],
    "scam": ["fraud", "cheating", "misrepresentation"],
    "hit and run": ["rash driving", "causing death by negligence"],
    "drunk driving": ["driving under influence", "drunken driving"],
    "land grab": ["encroachment", "illegal possession"],
    "black money": ["money laundering", "benami"],
    "ragging": ["ragging", "criminal intimidation"],
}

# ---------------------------------------------------------------------------
# Section extraction patterns
# ---------------------------------------------------------------------------
_SECTION_PATTERNS = [
    # "section 420" / "sec 420" / "sec. 420" / "s. 420"
    re.compile(r"\b(?:section|sec\.?|s\.?)\s+(\d+[a-zA-Z]?)\b", re.IGNORECASE),
    # "420 IPC" / "302 crpc" (number followed by act abbreviation)
    re.compile(
        r"\b(\d+[a-zA-Z]?)\s+("
        + "|".join(re.escape(k) for k in STATUTE_MAP.keys())
        + r")\b",
        re.IGNORECASE,
    ),
    # "u/s 420" / "under section 420"
    re.compile(r"\bu/?s\s+(\d+[a-zA-Z]?)\b", re.IGNORECASE),
]

# Act detection pattern (standalone abbreviation not preceded by a number)
_ACT_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(STATUTE_MAP.keys(), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------
@dataclass
class ExpandedQuery:
    """Result of query expansion."""
    original_query: str
    normalized_query: str
    expanded_query: str
    bm25_query: str
    query_type: str = ""
    filters: Dict[str, Optional[str]] = field(default_factory=dict)
    expansions_added: List[str] = field(default_factory=list)

# ---------------------------------------------------------------------------
# Query Classification
# ---------------------------------------------------------------------------
def classify_query(query: str, filters: Dict[str, Optional[str]]) -> str:
    """Classify the user query into 4 distinct types for adaptive logic."""
    if filters.get("section_number"):
        return "precise"
        
    words = query.lower().split()
    
    # Check explanatory keywords
    explanatory_keywords = {"what", "how", "rights", "procedure"}
    if any(k in words for k in explanatory_keywords):
        return "explanatory"
        
    # Detect legal terms using LEGAL_SYNONYMS keys
    legal_matches = sum(1 for w in words if w in LEGAL_SYNONYMS)
    if legal_matches >= 1:
        return "legal"
        
    return "layman"


# ---------------------------------------------------------------------------
# STEP 1: Normalize
# ---------------------------------------------------------------------------
def normalize_query(query: str) -> str:
    """
    Lowercase, strip, remove excessive punctuation, collapse whitespace.
    Keeps digits, letters, and essential punctuation (. / -).
    """
    q = query.strip().lower()
    # Remove quotes, brackets, special chars (keep . / - for abbreviations)
    q = re.sub(r"[\"\'`\[\]{}()!@#$%^&*+=<>~|\\;:,?]", " ", q)
    # Collapse whitespace
    q = " ".join(q.split())
    return q


# ---------------------------------------------------------------------------
# STEP 2: Extract section references
# ---------------------------------------------------------------------------
def extract_section(query: str) -> Dict[str, Optional[str]]:
    """
    Extract section_number and act from query.

    Returns:
        {"section_number": "420" or None, "act": "Indian Penal Code" or None}
    """
    section_number: Optional[str] = None
    act: Optional[str] = None

    # Try each pattern
    for pattern in _SECTION_PATTERNS:
        m = pattern.search(query)
        if m:
            section_number = m.group(1).strip()
            # Check if pattern captured act abbreviation (2-group patterns)
            if m.lastindex and m.lastindex >= 2:
                act_abbr = m.group(2).strip().lower()
                act = STATUTE_MAP.get(act_abbr)
            break

    # If no act detected from section pattern, try standalone act detection
    if act is None:
        m = _ACT_PATTERN.search(query)
        if m:
            act_abbr = m.group(1).strip().lower()
            act = STATUTE_MAP.get(act_abbr)

    return {"section_number": section_number, "act": act}


# ---------------------------------------------------------------------------
# STEP 3: Replace statute abbreviations
# ---------------------------------------------------------------------------
def replace_statutes(query: str) -> str:
    """Replace statute abbreviations with full names in the query."""
    def _replace(match: re.Match) -> str:
        abbr = match.group(0).lower()
        return STATUTE_MAP.get(abbr, match.group(0))

    return _ACT_PATTERN.sub(_replace, query)


# ---------------------------------------------------------------------------
# STEP 4: Expand terms with legal synonyms
# ---------------------------------------------------------------------------
def expand_terms(query: str, query_type: str) -> tuple:
    """
    Expand query terms using legal synonym dictionary based on query type.

    Returns:
        (expanded_query, list_of_added_terms)
    """
    if query_type == "precise":
        return query, []
        
    words = query.lower().split()
    original_word_count = len(words)
    
    # Determine expansion limit
    if query_type == "legal":
        max_per_term = 1
        max_total = original_word_count
    elif query_type == "layman":
        max_per_term = 3
        max_total = original_word_count * 2
    elif query_type == "explanatory":
        max_per_term = 2
        max_total = original_word_count
    else:
        max_per_term = 2
        max_total = original_word_count

    existing: Set[str] = set(words)
    added: List[str] = []

    for word in words:
        synonyms = LEGAL_SYNONYMS.get(word, [])
        for syn in synonyms[:max_per_term]:
            syn_lower = syn.lower()
            # Avoid duplicates — check all words in multi-word synonyms
            if syn_lower not in existing and not any(
                s in existing for s in syn_lower.split()
            ):
                added.append(syn)
                existing.add(syn_lower)
                # Also add individual words for multi-word synonyms
                for w in syn_lower.split():
                    existing.add(w)
                    
        # Explanatory queries also append broad concepts if matching legal terms (e.g. procedure -> rules)
        if query_type == "explanatory" and word in ("procedure", "rights"):
            concept = "rules guidelines" if word == "procedure" else "entitlements protection"
            if concept not in existing:
                added.append(concept)
                existing.add(concept)

    if not added:
        return query, []

    # Deduplicate while preserving order
    seen: Set[str] = set()
    unique_added: List[str] = []
    for term in added:
        if term.lower() not in seen:
            seen.add(term.lower())
            unique_added.append(term)

    # Enforce global limit to keep original query dominant
    unique_added = unique_added[:max_total]

    expanded = query + " " + " ".join(unique_added)
    return expanded, unique_added


# ---------------------------------------------------------------------------
# STEP 5 + 6: Build structured BM25 query
# ---------------------------------------------------------------------------
def build_bm25_query(
    expanded_query: str,
    original_query: str,
    filters: Dict[str, Optional[str]],
    query_type: str,
) -> str:
    """
    Build an FTS5-compatible MATCH expression adaptively based on query_type.
    """
    base_terms = re.findall(r"[A-Za-z0-9_]+", expanded_query.lower())
    if not base_terms:
        safe = expanded_query.replace('"', "")
        return f'"{safe}"'
        
    parts: List[str] = []

    sec = filters.get("section_number")
    act = filters.get("act")
    
    if sec:
        parts.append(f'section_number:"{sec}"')
    if act:
        act_words = [w for w in act.lower().split() if w not in ("the", "of", "and")]
        if act_words:
            act_term = " ".join(act_words[:3])
            parts.append(f'title:"{act_term}"')

    # STEP 4: Adapt BM25 Strictness
    if query_type == "precise":
        # Strict: section + act only (if filtering exists), else exact original phrase
        if parts:
            return " AND ".join(parts)
        else:
            return f'"{original_query.replace(chr(34), "")}"'

    stopwords = {"the", "of", "in", "a", "an", "is", "for", "and", "or", "to",
                 "under", "what", "how", "india", "indian", "law", "act"}
    content_terms = [t for t in base_terms if not t.isdigit() and t not in stopwords]
    act_abbrs = set(STATUTE_MAP.keys())
    content_terms = [t for t in content_terms if t not in act_abbrs]

    if content_terms:
        if query_type == "legal":
            # AND-heavy query
            text_query = " AND ".join([f'"{t}"' for t in content_terms[:5]])
            
        elif query_type == "layman":
            # Allow OR expansion
            if len(content_terms) <= 2:
                text_query = " OR ".join([f'"{t}"' for t in content_terms])
            else:
                core_part = " AND ".join([f'"{t}"' for t in content_terms[:2]])
                extra_part = " OR ".join([f'"{t}"' for t in content_terms[2:6]])
                text_query = f'({core_part}) AND ({extra_part})'
                
        else: # "explanatory"
            # Broader mix
            core = content_terms[:3]
            extra = content_terms[3:7]
            if not extra:
                text_query = " AND ".join([f'"{t}"' for t in core])
            else:
                core_part = " OR ".join([f'"{t}"' for t in core])
                extra_part = " OR ".join([f'"{t}"' for t in extra])
                text_query = f'({core_part}) AND ({extra_part})'

        parts.append(f'({text_query})')

    if not parts:
        bm25_query = " AND ".join([f'"{t}"' for t in base_terms[:5]])
    else:
        bm25_query = " AND ".join(parts)

    phrase = f'"{original_query.replace(chr(34), "")}"'
    return f"{phrase} OR ({bm25_query})"


# ---------------------------------------------------------------------------
# STEP 7: Main entry point — build_query
# ---------------------------------------------------------------------------
def build_query(query: str) -> ExpandedQuery:
    """
    Full query expansion pipeline:
      1. Normalize
      2. Extract metadata
      3. Classify query dynamically
      4. Adapt terms expansion based on class
      5. Adapt BM25 based on class
    """
    normalized = normalize_query(query)
    filters = extract_section(normalized)
    
    # Classify the queries (precise, legal, layman, explanatory)
    query_type = classify_query(normalized, filters)
    
    with_statutes = replace_statutes(normalized)
    
    # STEP 5: Expand embeddings based on type
    expanded, added_terms = expand_terms(with_statutes, query_type)

    # STEP 6: BM25 adapted based on type
    bm25 = build_bm25_query(expanded, query, filters, query_type)

    return ExpandedQuery(
        original_query=query,
        normalized_query=normalized,
        expanded_query=expanded,
        bm25_query=bm25,
        query_type=query_type,
        filters=filters,
        expansions_added=added_terms,
    )


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_queries = [
        "section 420 IPC punishment",
        "breach of contract compensation india",
        "cheated in online purchase",
        "builder delay possession remedy india",
        "consumer defective product refund law",
        "420 crpc bail",
        "What is the punishment for murder?",
        "rights of arrested person",
        "RERA flat possession delay",
        "sec. 302 ipc",
        "u/s 498A IPC dowry harassment",
        "hit and run accident compensation",
    ]

    for q in test_queries:
        result = build_query(q)
        print("=" * 70)
        print(f"  ORIGINAL:  {result.original_query}")
        print(f"  NORMALIZED: {result.normalized_query}")
        print(f"  EXPANDED:   {result.expanded_query}")
        print(f"  BM25:       {result.bm25_query}")
        print(f"  FILTERS:    {result.filters}")
        if result.expansions_added:
            print(f"  ADDED:      {result.expansions_added}")
