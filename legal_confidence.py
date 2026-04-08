"""
Legal Confidence & Quality Engine — Phase 3

Provides:
- Confidence scoring (retrieval + heuristic signal)
- Citation extraction from context blocks
- Answer validation (contradiction/weakness check)
- Refinement prompt builder (dual-generation pass 2)
- Mode-aware output styling qualifiers
"""

import re
from typing import Any, Dict, List


# =====================================================
# STEP 1: CONFIDENCE SCORING
# =====================================================

def compute_confidence(
    retrieved_chunks: List[Dict[str, Any]],
    heuristic_matches: List[Dict[str, Any]],
    retrieval_mode: str,
) -> float:
    """Compute a 0.0–1.0 confidence score for the response.

    Factors:
    - Retrieval strength (60% weight): average dense score of top chunks
    - Heuristic match strength (30% weight): did we match known legal patterns?
    - Mode penalty (10%): fallback mode reduces confidence
    """
    score = 0.0

    # --- Retrieval strength (up to 0.60) ---
    if retrieved_chunks:
        chunk_scores = []
        for c in retrieved_chunks:
            s = c.get("scores", {}) if isinstance(c.get("scores"), dict) else {}
            raw = (
                s.get("final_score")
                or s.get("dense_score")
                or c.get("final_score")
                or c.get("dense_score")
                or c.get("hybrid_score")
                or 0.0
            )
            chunk_scores.append(float(raw or 0.0))
        if chunk_scores:
            avg = sum(chunk_scores) / len(chunk_scores)
            # Boost if we have many chunks with decent scores
            count_bonus = min(len(chunk_scores) / 5.0, 1.0) * 0.1
            score += min(avg + count_bonus, 1.0) * 0.60

    # --- Heuristic match strength (up to 0.30) ---
    if heuristic_matches:
        # More matches = higher confidence in legal direction
        match_strength = min(len(heuristic_matches) / 3.0, 1.0)
        score += match_strength * 0.30

    # --- Mode penalty ---
    if retrieval_mode == "fallback":
        score -= 0.15
    if not retrieved_chunks:
        score -= 0.10

    return round(max(0.0, min(score, 1.0)), 2)


def confidence_label(score: float) -> str:
    """Human-readable confidence label."""
    if score >= 0.75:
        return "high"
    elif score >= 0.45:
        return "medium"
    elif score >= 0.20:
        return "low"
    else:
        return "very_low"


# =====================================================
# STEP 2: CITATION EXTRACTION
# =====================================================

def extract_citations(context_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract structured citation data from context blocks for prompt injection."""
    citations: List[Dict[str, Any]] = []
    seen: set = set()

    for block in context_blocks:
        title = str(block.get("title") or "").strip()
        section = str(block.get("section_number") or "").strip()
        corpus = str(block.get("corpus") or "").strip()
        texts = block.get("texts", {}) or {}
        chunk_text = str(texts.get("chunk_text") or "").strip()
        court = str(texts.get("court") or "").strip()
        date = str(texts.get("date") or "").strip()

        if not title:
            continue

        # Deduplicate by title+section
        key = f"{title}|{section}"
        if key in seen:
            continue
        seen.add(key)

        citation = {
            "source": title,
            "section": section or None,
            "corpus": corpus,
            "text_preview": chunk_text[:200] if chunk_text else "",
        }
        if court:
            citation["court"] = court
        if date:
            citation["date"] = date

        citations.append(citation)

    return citations[:8]


def format_citations_for_prompt(citations: List[Dict[str, Any]]) -> str:
    """Format citations into a text block for injection into LLM prompt."""
    if not citations:
        return ""

    lines = ["Available Citations (use these for grounding your answer):"]
    for i, cite in enumerate(citations, 1):
        source = cite.get("source", "Unknown")
        section = cite.get("section")
        corpus = cite.get("corpus", "")
        court = cite.get("court", "")

        ref = f"  [{i}] {source}"
        if section:
            ref += f", Section {section}"
        if corpus:
            ref += f" ({corpus})"
        if court:
            ref += f" — {court}"
        lines.append(ref)

        preview = cite.get("text_preview", "")
        if preview:
            lines.append(f"      Excerpt: {preview[:150]}...")

    return "\n".join(lines)


# =====================================================
# STEP 3: ANSWER VALIDATION (CONTRADICTION CHECK)
# =====================================================

# Red flags that indicate a weak / hedging / non-committal answer
_WEAK_ANSWER_PATTERNS = [
    "i am not sure",
    "i'm not sure",
    "it depends completely",
    "i cannot determine",
    "i can't determine",
    "no specific law applies",
    "there is no law",
    "i don't have enough information to",
    "i need more information",
    "unfortunately, i cannot",
    "i'm unable to provide",
    "i am unable to provide",
    "this is outside my scope",
    "please consult a lawyer for",
]

# Patterns that suggest the model is refusing
_REFUSAL_PATTERNS = [
    "i can't give legal advice",
    "i cannot give legal advice",
    "i'm not a lawyer",
    "i am not a lawyer",
    "cannot provide legal advice",
    "not qualified to",
]

# Patterns that suggest hallucination (inventing details)
_HALLUCINATION_FLAGS = [
    r"Section\s+\d{4,}",               # Section numbers > 999 are suspicious
    r"Article\s+\d{4,}",               # Article numbers > 999
    r"\bAct,?\s+\d{4}\b.*\bAct,?\s+\d{4}\b.*\bAct,?\s+\d{4}\b.*\bAct,?\s+\d{4}\b",  # 4+ Acts in one sentence — spam
]


def validate_answer(answer: str) -> Dict[str, Any]:
    """Validate an LLM answer for weakness, refusal, and basic hallucination signals.

    Returns:
        {
            "valid": bool,
            "issues": ["issue description", ...],
            "needs_refinement": bool
        }
    """
    text = (answer or "").strip()
    lower = text.lower()
    issues: List[str] = []

    if len(text) < 50:
        issues.append("answer_too_short")

    # Check for weak hedging
    for pattern in _WEAK_ANSWER_PATTERNS:
        if pattern in lower:
            issues.append(f"weak_answer:{pattern}")
            break

    # Check for refusal
    for pattern in _REFUSAL_PATTERNS:
        if pattern in lower:
            issues.append(f"refusal:{pattern}")
            break

    # Check for hallucination signals
    for pattern in _HALLUCINATION_FLAGS:
        if re.search(pattern, text, re.IGNORECASE):
            issues.append(f"possible_hallucination:{pattern[:30]}")
            break

    # Check if the answer actually contains legal content
    legal_markers = ["section", "act", "court", "law", "legal", "statute", "remedy", "file", "complaint", "notice"]
    has_legal_content = any(marker in lower for marker in legal_markers)
    if not has_legal_content and len(text) > 100:
        issues.append("no_legal_content")

    valid = len(issues) == 0
    needs_refinement = len(issues) > 0 and not any("refusal" in i for i in issues)

    return {
        "valid": valid,
        "issues": issues,
        "needs_refinement": needs_refinement,
    }


# =====================================================
# STEP 4: REFINEMENT PROMPT (DUAL-GENERATION PASS 2)
# =====================================================

def build_refinement_prompt(draft_answer: str, user_query: str, legal_priors: str = "") -> str:
    """Build a refinement prompt for dual-generation (pass 2).

    Takes the draft answer and asks the LLM to improve it with:
    - Missing legal references
    - Logical gap fixes
    - Better structure
    - Clearer next steps
    """
    priors_block = f"\nKnown Legal Signals:\n{legal_priors}\n" if legal_priors else ""

    return (
        "You are a senior Indian legal expert reviewing a junior lawyer's draft answer.\n\n"
        "Improve the following legal answer by:\n"
        "1. Adding any missing Indian legal references (Acts, Sections, Judgements)\n"
        "2. Fixing logical gaps or unclear reasoning\n"
        "3. Ensuring practical, actionable next steps are included\n"
        "4. Making the answer structured and confident\n"
        "5. Removing any hedging language ('maybe', 'it depends completely', 'I'm not sure')\n"
        "6. Ensuring all cited laws are real Indian laws\n\n"
        "Do NOT refuse or say 'I can't give legal advice'.\n"
        "Do NOT remove existing correct content — only improve and add.\n"
        f"{priors_block}\n"
        f"Original User Query:\n{user_query}\n\n"
        f"Draft Answer to Improve:\n{draft_answer}\n\n"
        "Return the improved answer in this FIRAC structure:\n"
        "Part 1 - Facts and Legal Issue:\n"
        "Part 2 - Applicable Law:\n"
        "Part 3 - Analysis:\n"
        "Part 4 - Remedies and Next Steps:\n"
        "Part 5 - Limits:\n"
        "Part 6 - Disclaimer:\n"
        "For information only. Consult a professional.\n"
    )


def build_confidence_rewrite_prompt(draft_answer: str) -> str:
    """When the draft is weak/hedging, ask for a confident rewrite."""
    return (
        "The following legal answer contains hedging or uncertain language.\n"
        "Rewrite it clearly and confidently.\n"
        "State the legal position directly.\n"
        "If assumptions are needed, state them explicitly but do not hedge.\n"
        "Keep the same structure.\n\n"
        f"Answer to rewrite:\n{draft_answer}\n"
    )


# =====================================================
# STEP 5: MODE-AWARE OUTPUT STYLING
# =====================================================

_HIGH_CONFIDENCE_PREFIX = ""  # No prefix needed for high confidence
_MEDIUM_CONFIDENCE_PREFIX = ""  # Clean — no visible prefix
_LOW_CONFIDENCE_PREFIX = (
    "*Based on the available information and applicable Indian legal provisions, "
    "the following legal position applies. Additional facts may affect this analysis.*\n\n"
)
_VERY_LOW_CONFIDENCE_PREFIX = (
    "*This is a preliminary legal overview based on limited information. "
    "The applicable laws and remedies may vary based on specific facts, jurisdiction, "
    "and the complete factual matrix. Please consult a qualified legal professional.*\n\n"
)


def apply_confidence_styling(
    answer: str,
    confidence_score: float,
    retrieval_mode: str,
) -> str:
    """Apply mode-aware and confidence-aware styling to the final answer.

    - High confidence + normal mode: clean output, strong citations
    - Medium confidence: no change
    - Low confidence: add soft qualifier prefix
    - Very low / fallback: add stronger qualifier
    """
    label = confidence_label(confidence_score)

    if label == "very_low":
        prefix = _VERY_LOW_CONFIDENCE_PREFIX
    elif label == "low" or retrieval_mode == "fallback":
        prefix = _LOW_CONFIDENCE_PREFIX
    else:
        prefix = ""

    if prefix and not answer.startswith("*Based") and not answer.startswith("*This is"):
        return prefix + answer

    return answer


# =====================================================
# STEP 6: NEXT-ACTION VALIDATOR
# =====================================================

_NEXT_STEP_MARKERS = [
    "send legal notice",
    "file complaint",
    "file fir",
    "approach",
    "consult",
    "lodge",
    "apply for",
    "file a",
    "next step",
    "file case",
    "file suit",
    "report to",
    "seek",
]


def has_actionable_next_steps(answer: str) -> bool:
    """Check if the answer contains actionable next steps."""
    lower = (answer or "").lower()
    return any(marker in lower for marker in _NEXT_STEP_MARKERS)


def build_next_steps_supplement(user_query: str, legal_priors: str = "") -> str:
    """Generate a prompt to add next steps if the answer is missing them."""
    priors_block = f"\n{legal_priors}\n" if legal_priors else ""
    return (
        "The following legal answer is missing concrete next steps.\n"
        "Add a 'Next Steps' section with 3-5 specific, actionable steps "
        "the person should take to resolve their legal issue.\n"
        "Include specific authorities to approach, documents to prepare, "
        "and timelines where applicable.\n\n"
        f"Original query: {user_query}\n"
        f"{priors_block}"
    )
