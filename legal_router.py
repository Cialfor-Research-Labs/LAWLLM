import re
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class IssueRoute:
    domain: str
    confidence: float
    matched_terms: List[str]
    sub_domain: str
    exclude_terms: List[str]
    must_have_terms: List[str]


DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "property": [
        "landlord", "tenant", "rent", "evict", "eviction", "lease", "property",
        "possession", "flat", "apartment", "premises", "ownership",
    ],
    "consumer": [
        "consumer", "defective", "refund", "warranty", "service deficiency",
        "ecommerce", "e-commerce", "product liability", "seller", "marketplace",
        "hospital", "medical negligence", "overcharge", "overcharging", "billing",
        "builder delay", "delayed possession",
    ],
    "criminal": [
        "fir", "police", "arrest", "bail", "murder", "assault", "cheating",
        "theft", "forgery", "criminal", "offence", "offense",
        "cyber", "online fraud", "phishing", "otp", "hacking", "hacked",
        "data breach", "identity theft", "ransomware", "fake profile",
    ],
    "labour": [
        "salary", "wages", "termination", "dismissal", "employee", "employer",
        "industrial dispute", "gratuity", "pf", "provident fund", "workman",
    ],
    "contract": [
        "contract", "agreement", "breach", "specific performance", "damages",
        "indemnity", "arbitration", "consideration",
    ],
}


DOMAIN_SOURCE_HINTS: Dict[str, List[str]] = {
    "property": [
        "transfer of property act",
        "specific relief act",
        "real estate (regulation and development) act",
        "code of civil procedure",
    ],
    "consumer": [
        "consumer protection act",
    ],
    "criminal": [
        "bhartiya nyay sanhita",
        "bhartiya nagrik suraksha sanhita",
        "bhartiya sakshya adhiniyam",
        "information technology act",
        "it act",
        "indian penal code",
        "criminal procedure code",
        "indian evidence act",
        "state vs",
        "v. state",
        "union of india",
    ],
    "labour": [
        "industrial disputes act",
    ],
    "contract": [
        "specific relief act",
        "negotiable instruments act",
        "companies act",
    ],
}

DOMAIN_NEGATIVE_HINTS: Dict[str, List[str]] = {
    "consumer": [
        "insolvency and bankruptcy code",
        "indian penal code",
        "bhartiya nyay sanhita",
        "criminal procedure code",
        "bhartiya nagrik suraksha sanhita",
        "consumer protection act, 1986",
        "consumer protection act 1986",
        "central excise",
        "customs act",
        "gst",
    ],
    "property": [
        "insolvency and bankruptcy code",
        "industrial disputes act",
    ],
    "contract": [
        "indian penal code",
        "bhartiya nyay sanhita",
        "criminal procedure code",
        "bhartiya nagrik suraksha sanhita",
    ],
    "criminal": [
        "indian penal code",
        "criminal procedure code",
        "indian evidence act",
    ],
    "labour": [
        "transfer of property act",
        "consumer protection act",
    ],
}

DOMAIN_SUBDOMAIN: Dict[str, str] = {
    "consumer": "consumer_dispute",
    "property": "property_dispute",
    "criminal": "criminal_complaint",
    "labour": "employment_dispute",
    "contract": "contract_dispute",
    "general": "general_legal",
}

DOMAIN_PRIORS: Dict[str, str] = {
    "consumer": "Always consider Section 35 (filing), Section 38 (procedure), and Section 39 (reliefs) of Consumer Protection Act, 2019, where relevant.",
    "criminal": "Always apply current criminal framework: BNS, BNSS, and BSA. Avoid legacy IPC/CrPC framing unless explicitly required.",
    "property": "Prioritize possession, notice, tenancy, and civil remedy pathways before extraordinary relief.",
    "labour": "Prioritize unpaid dues, termination legality, and statutory labour remedy forums.",
    "contract": "Prioritize breach analysis, notice, damages, and specific performance where applicable.",
}

SUBDOMAIN_PRIORS: Dict[str, str] = {
    "consumer_ecommerce_dispute": (
        "Prioritize refund/replacement/repair pathway first, then compensation. "
        "Use Consumer Protection Act, 2019 and Consumer Protection (E-Commerce) Rules where relevant."
    ),
    "consumer_healthcare_dispute": (
        "Prioritize deficiency in service and billing transparency analysis for healthcare services. "
        "Do not drift into court-fee or criminal procedure unless user facts explicitly invoke police/crime."
    ),
    "consumer_real_estate_dispute": (
        "Prioritize delayed-possession/refund/interest framework under CPA 2019 and RERA where relevant."
    ),
    "consumer_dispute": (
        "Prioritize Section 35 (filing), Section 38 (procedure), and Section 39 (reliefs) under CPA 2019."
    ),
}

DOMAIN_MUST_HAVE_TERMS: Dict[str, List[str]] = {
    "consumer": ["consumer", "refund", "defect", "deficiency", "unfair trade practice", "seller", "service"],
    "property": ["property", "tenant", "landlord", "eviction", "possession", "lease"],
    "criminal": [
        "fir", "police", "offence", "offense", "arrest", "bail", "cheating", "theft", "stole", "robbery",
        "cyber", "phishing", "otp", "hacking", "online fraud", "identity theft",
    ],
    "labour": ["employee", "employer", "wages", "termination", "industrial dispute"],
    "contract": ["contract", "agreement", "breach", "damages", "specific performance"],
}

DOMAIN_ALLOWED_SOURCE_HINTS: Dict[str, List[str]] = {
    "consumer": [
        "consumer protection act",
        "real estate (regulation and development) act",
        "rera",
        "hospital",
        "medical",
        "e-commerce",
        "ecommerce",
        "consumer protection (e-commerce) rules",
        "clinical establishments",
    ],
    "property": [
        "transfer of property act",
        "specific relief act",
        "real estate (regulation and development) act",
        "rera",
    ],
    "criminal": [
        "bhartiya nyay sanhita",
        "bhartiya nagrik suraksha sanhita",
        "bhartiya sakshya adhiniyam",
        "information technology act",
        "it act",
        "indian penal code",
        "criminal procedure code",
        "indian evidence act",
        "state vs",
        "v. state",
        "union of india",
    ],
    "labour": [
        "industrial disputes act",
        "gratuity",
        "wages",
    ],
    "contract": [
        "specific relief act",
        "indian contract",
        "negotiable instruments act",
    ],
}

INJURY_SIGNALS = [
    "injury",
    "injured",
    "hospitalization",
    "hospitalised",
    "hospitalized",
    "burn",
    "fracture",
    "death",
    "medical treatment",
    "bodily harm",
    "property damage",
]

HEALTHCARE_SIGNALS = [
    "hospital",
    "doctor",
    "medical",
    "clinic",
    "treatment",
    "billing",
    "overcharging",
]

ECOMMERCE_SIGNALS = [
    "online",
    "e-commerce",
    "ecommerce",
    "marketplace",
    "seller",
    "order",
    "delivered",
]


def _term_hits(query: str, terms: List[str]) -> List[str]:
    q = query.lower()
    hits: List[str] = []
    for term in terms:
        pattern = r"\b" + re.escape(term.lower()) + r"\b"
        if re.search(pattern, q):
            hits.append(term)
    return hits


def classify_legal_issue(query: str) -> IssueRoute:
    best_domain = "general"
    best_hits: List[str] = []

    for domain, terms in DOMAIN_KEYWORDS.items():
        hits = _term_hits(query, terms)
        if len(hits) > len(best_hits):
            best_domain = domain
            best_hits = hits

    if not best_hits:
        return IssueRoute(
            domain="general",
            confidence=0.0,
            matched_terms=[],
            sub_domain=DOMAIN_SUBDOMAIN["general"],
            exclude_terms=[],
            must_have_terms=[],
        )

    confidence = min(0.95, 0.45 + (0.12 * len(best_hits)))
    return IssueRoute(
        domain=best_domain,
        confidence=confidence,
        matched_terms=best_hits,
        sub_domain=DOMAIN_SUBDOMAIN.get(best_domain, "general_legal"),
        exclude_terms=list(DOMAIN_NEGATIVE_HINTS.get(best_domain, [])),
        must_have_terms=list(DOMAIN_MUST_HAVE_TERMS.get(best_domain, [])),
    )


def build_intent_route(query: str, forced_domain: str = "") -> Dict:
    route = classify_legal_issue(query)
    domain = forced_domain if forced_domain and forced_domain != "auto" else route.domain
    q = (query or "").lower()

    sub_domain = DOMAIN_SUBDOMAIN.get(domain, route.sub_domain)
    allowed_source_hints = list(DOMAIN_ALLOWED_SOURCE_HINTS.get(domain, []))
    exclude_terms = list(DOMAIN_NEGATIVE_HINTS.get(domain, route.exclude_terms))

    # Domain-lock for healthcare consumer queries to avoid "court fee"/tax bleed.
    if domain == "consumer" and any(sig in q for sig in HEALTHCARE_SIGNALS):
        sub_domain = "consumer_healthcare_dispute"
        allowed_source_hints.extend(
            [
                "consumer protection act",
                "medical",
                "hospital",
                "clinical establishments",
                "unfair trade practice",
                "deficiency",
            ]
        )
        exclude_terms.extend(
            [
                "court fees act",
                "magistrate",
                "central excise",
                "customs act",
            ]
        )

    # Domain-lock for ecommerce consumer queries with remedy-first authorities.
    if domain == "consumer" and any(sig in q for sig in ECOMMERCE_SIGNALS):
        sub_domain = "consumer_ecommerce_dispute"
        allowed_source_hints.extend(
            [
                "consumer protection act",
                "consumer protection (e-commerce) rules",
                "refund",
                "replacement",
                "defect",
            ]
        )

    if domain == "consumer" and any(x in q for x in ["builder", "possession", "flat", "apartment", "rera"]):
        sub_domain = "consumer_real_estate_dispute"

    # De-duplicate while preserving order.
    allowed_source_hints = list(dict.fromkeys([x for x in allowed_source_hints if x]))
    exclude_terms = list(dict.fromkeys([x for x in exclude_terms if x]))

    return {
        "domain": domain,
        "sub_domain": sub_domain,
        "priors": SUBDOMAIN_PRIORS.get(sub_domain, DOMAIN_PRIORS.get(domain, "")),
        "statute_regime": get_statute_regime(),
        "confidence": route.confidence,
        "matched_terms": route.matched_terms,
        "exclude_terms": exclude_terms,
        "must_have_terms": list(DOMAIN_MUST_HAVE_TERMS.get(domain, route.must_have_terms)),
        "allowed_source_hints": allowed_source_hints,
        "strict_domain_filter": domain != "general",
        "injury_signal": query_has_injury_signal(query),
    }


def query_has_injury_signal(query: str) -> bool:
    q = (query or "").lower()
    return any(sig in q for sig in INJURY_SIGNALS)


def entity_override(query: str, current_domain: str) -> str:
    q = (query or "").lower()
    if any(k in q for k in ["landlord", "tenant", "rent", "lease"]):
        return "property"
    if any(k in q for k in ["employer", "salary", "termination"]):
        return "labour"
    return current_domain


def get_statute_regime() -> str:
    return "modern"  # always BNS/BNSS/BSA


def score_result_for_domain(result: Dict, domain: str) -> float:
    if domain == "general":
        return 1.0

    title = (result.get("title") or "").lower()
    doc_id = (result.get("document_id") or "").lower()
    context_path = (result.get("context_path") or "").lower()
    chunk_text = (result.get("chunk_text") or "").lower()
    combined = f"{title} {doc_id} {context_path} {chunk_text}"

    score = 0.0
    for hint in DOMAIN_SOURCE_HINTS.get(domain, []):
        if hint in combined:
            score += 1.0

    for kw in DOMAIN_KEYWORDS.get(domain, []):
        if re.search(r"\b" + re.escape(kw.lower()) + r"\b", combined):
            score += 0.2

    for hint in DOMAIN_NEGATIVE_HINTS.get(domain, []):
        if hint in combined:
            score -= 1.25

    # Strong negative for labour bleed into other domains.
    if domain != "labour" and "industrial disputes act" in combined:
        score -= 1.5

    return score


def domain_filter(results: List[Dict], domain: str, min_keep: int, confidence: float = 0.0) -> Tuple[List[Dict], bool]:
    if domain == "general" or not results:
        return results, False

    scored: List[Tuple[float, Dict]] = [(score_result_for_domain(r, domain), r) for r in results]
    kept = [item for score, item in scored if score > 0]

    # Avoid over-filtering on weak matches.
    if len(kept) < min_keep:
        return results, False

    # On confident classification, prioritize statute-first retrieval for civil/statutory domains.
    if confidence >= 0.55 and domain in {"consumer", "property", "contract", "labour"}:
        kept.sort(
            key=lambda r: (
                1 if r.get("corpus") == "acts" else 0,
                score_result_for_domain(r, domain),
                r.get("hybrid_score", 0.0),
            ),
            reverse=True,
        )
    else:
        kept.sort(key=lambda r: (score_result_for_domain(r, domain), r.get("hybrid_score", 0.0)), reverse=True)
    return kept, True
