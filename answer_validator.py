import re
from typing import Dict, List, Tuple

from legal_router import DOMAIN_SOURCE_HINTS

DOMAIN_CONTAMINATION_TERMS: Dict[str, List[str]] = {
    "consumer": ["court fee", "magistrate", "crpc", "bnss", "central excise", "customs act", "gst"],
    "property": ["industrial disputes act", "court fee"],
    "contract": ["magistrate", "crpc", "bnss"],
    "labour": ["transfer of property act", "rera"],
}

REQUIRED_HEADINGS = [
    "FACTS",
    "LEGAL ISSUE",
    "GROUNDS",
    "Analysis",
    "PRAYER",
    "LIMITS/UNCERTAINTY",
]

LEGACY_REQUIRED_HEADINGS = [
    "Facts Summary",
    "Legal Issue",
    "Applicable Law",
    "Analysis",
    "Practical Next Steps",
    "Limits/Uncertainty",
]

BEDROCK_LAWS = {
    "consumer protection act",
    "bhartiya nyay sanhita",
    "indian penal code",
    "criminal procedure code",
    "bhartiya nagrik suraksha sanhita",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _extract_allowed_laws(pack: Dict) -> Dict[str, set]:
    allowed: Dict[str, set] = {}
    for block in pack.get("context_blocks", []):
        title = _norm(block.get("title") or "")
        section = _norm(str(block.get("section_number") or ""))
        if not title:
            continue
        if title not in allowed:
            allowed[title] = set()
        if section:
            allowed[title].add(section)
    return allowed


def _split_sections(answer: str) -> List[str]:
    parts = re.split(
        r"(?m)^(?:#{1,6}\s*)?"
        r"(FACTS|LEGAL ISSUE|GROUNDS|ANALYSIS|PRAYER|LIMITS/UNCERTAINTY|"
        r"Facts Summary|Legal Issue|Applicable Law|Analysis|Practical Next Steps|Limits/Uncertainty)"
        r"\s*:?\s*$",
        answer,
    )
    # re.split with capture returns [prefix, heading, body, heading, body...]
    return parts


def _rebuild_answer_with_applicable_law(answer: str, new_applicable_body: str) -> str:
    parts = _split_sections(answer)
    if len(parts) < 3:
        return answer

    rebuilt: List[str] = [parts[0]]
    i = 1
    while i < len(parts) - 1:
        heading = parts[i]
        body = parts[i + 1]
        if heading in {"Applicable Law", "GROUNDS"}:
            body = "\n" + new_applicable_body.strip() + "\n"
        rebuilt.append(f"{heading}\n{body}")
        i += 2
    return "\n".join(x.strip("\n") for x in rebuilt if x is not None).strip()


def validate_applicable_law_section(answer: str, pack: Dict, domain: str) -> Tuple[str, Dict]:
    if not answer:
        return answer, {"applied": False, "reason": "empty_answer"}

    allowed = _extract_allowed_laws(pack)
    if not allowed:
        return answer, {"applied": False, "reason": "no_allowed_laws"}

    parts = _split_sections(answer)
    if len(parts) < 3:
        return answer, {"applied": False, "reason": "unstructured_answer"}

    applicable_body = ""
    i = 1
    while i < len(parts) - 1:
        heading = parts[i]
        body = parts[i + 1]
        if heading in {"Applicable Law", "GROUNDS"}:
            applicable_body = body
            break
        i += 2

    if not applicable_body.strip():
        return answer, {"applied": False, "reason": "missing_applicable_law"}

    lines = [ln.strip() for ln in applicable_body.splitlines() if ln.strip()]
    valid_lines: List[str] = []
    rejected_lines: List[str] = []
    context_based: List[str] = []
    priors_based: List[str] = []
    unverified: List[str] = []

    domain_hints = DOMAIN_SOURCE_HINTS.get(domain, [])
    enforce_domain = domain not in ("", "auto", "general")

    for line in lines:
        if not line.startswith("-"):
            rejected_lines.append(line)
            unverified.append(line)
            continue

        payload = line.lstrip("-").strip()
        parts = [p.strip() for p in payload.split("|")]
        if len(parts) < 2:
            rejected_lines.append(line)
            unverified.append(line)
            continue

        act = _norm(parts[0])
        section_part = _norm(parts[1])
        section_match = re.search(r"(?:section|sec\.?)\s+([a-z0-9().-]+)", section_part, re.IGNORECASE)
        section = section_match.group(1).lower() if section_match else ""

        # title must be one of retrieved authorities OR be a bedrock statute.
        is_bedrock = any(bedrock in act for bedrock in BEDROCK_LAWS)
        if act not in allowed and not is_bedrock:
            rejected_lines.append(line)
            unverified.append(line)
            continue

        # if section is present and act is retrieved context-bound, enforce section match.
        if section and (not is_bedrock) and allowed.get(act) and section not in allowed[act]:
            rejected_lines.append(line)
            unverified.append(line)
            continue

        # relevance gate: if domain is known, authority should align with domain hints.
        # bedrock statutes bypass this strict hint match.
        if enforce_domain and domain_hints:
            if (not is_bedrock) and (not any(hint in act for hint in domain_hints)):
                rejected_lines.append(line)
                unverified.append(line)
                continue

        valid_lines.append(line)
        if act in allowed:
            context_based.append(line)
        elif is_bedrock:
            priors_based.append(line)

    if not valid_lines:
        fallback = "- No specific statutory provision identified with high confidence from retrieved context."
        sanitized = _rebuild_answer_with_applicable_law(answer, fallback)
        return sanitized, {
            "applied": True,
            "valid_law_lines": 0,
            "rejected_law_lines": len(rejected_lines),
            "fallback_used": True,
            "source_confidence": {
                "context_based": context_based,
                "priors_based": priors_based,
                "unverified": unverified,
            },
        }

    sanitized = _rebuild_answer_with_applicable_law(answer, "\n".join(valid_lines))
    return sanitized, {
        "applied": True,
        "valid_law_lines": len(valid_lines),
        "rejected_law_lines": len(rejected_lines),
        "fallback_used": False,
        "source_confidence": {
            "context_based": context_based,
            "priors_based": priors_based,
            "unverified": unverified,
        },
    }


def detect_domain_contamination(answer: str, domain: str) -> Dict:
    if not answer or domain not in DOMAIN_CONTAMINATION_TERMS:
        return {"applied": False, "contaminated": False, "terms": []}

    text = answer.lower()
    hits = [term for term in DOMAIN_CONTAMINATION_TERMS[domain] if term in text]
    return {
        "applied": True,
        "contaminated": len(hits) > 0,
        "terms": hits,
    }


def validate_output_structure(answer: str) -> Dict:
    if not answer:
        return {
            "applied": True,
            "valid": False,
            "missing_headings": REQUIRED_HEADINGS,
            "has_raw_citation_markers": False,
        }
    lower = answer.lower()
    missing_current = [h for h in REQUIRED_HEADINGS if h.lower() not in lower]
    missing_legacy = [h for h in LEGACY_REQUIRED_HEADINGS if h.lower() not in lower]
    valid_schema = len(missing_current) == 0 or len(missing_legacy) == 0
    missing = [] if valid_schema else missing_current
    has_raw_citations = bool(re.search(r"\[c\d+\]", answer, flags=re.IGNORECASE))
    return {
        "applied": True,
        "valid": valid_schema and not has_raw_citations,
        "missing_headings": missing,
        "has_raw_citation_markers": has_raw_citations,
    }


def detect_era_mismatch(answer: str, pack: Dict, domain: str) -> Dict:
    if not answer:
        return {"applied": False, "mismatch": False}

    text = answer.lower()
    if domain != "consumer":
        return {"applied": True, "mismatch": False, "reason": "not_consumer_domain"}

    # If retrieved context contains CPA 2019 and answer references 1986, flag.
    titles = " ".join([str(b.get("title") or "").lower() for b in pack.get("context_blocks", [])])
    has_cpa_context = "consumer protection act" in titles
    mentions_1986 = "consumer protection act, 1986" in text or "consumer protection act 1986" in text
    mentions_2019 = "consumer protection act, 2019" in text or "consumer protection act 2019" in text

    mismatch = has_cpa_context and mentions_1986 and not mentions_2019
    return {
        "applied": True,
        "mismatch": mismatch,
        "has_cpa_context": has_cpa_context,
        "mentions_1986": mentions_1986,
        "mentions_2019": mentions_2019,
    }


def validate_grounding(answer: str, pack: Dict) -> Dict:
    if not answer:
        return {"applied": True, "valid": False, "reason": "empty_answer", "invalid_sections": []}

    allowed_sections = {
        str(block.get("section_number") or "").strip().lower()
        for block in pack.get("context_blocks", [])
        if str(block.get("section_number") or "").strip()
    }
    found_sections = {
        match.lower()
        for match in re.findall(r"\bSection(?:s)?\s+(\d+[A-Za-z]?)", answer, flags=re.IGNORECASE)
    }
    invalid_sections = sorted(sec for sec in found_sections if sec not in allowed_sections)

    return {
        "applied": True,
        "valid": len(invalid_sections) == 0,
        "invalid_sections": invalid_sections,
        "allowed_sections": sorted(allowed_sections),
    }
