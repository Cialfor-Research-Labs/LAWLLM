from types import SimpleNamespace
from typing import Dict, List, Tuple

from context_builder import run_retrieval
from hybrid_retrieval import rerank_results
from legal_router import query_has_injury_signal

SPECIFICITY_KEYWORDS = ["section", "shall", "liable", "compensation", "refund"]


def _safe_key(item: Dict) -> str:
    chunk_id = item.get("chunk_id")
    if chunk_id:
        return str(chunk_id)
    return f"{item.get('corpus')}::{item.get('source_json')}::{item.get('chunk_index')}"


def _consumer_remedy_tier_bonus(item: Dict, has_injury_signal: bool) -> float:
    text = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("context_path") or ""),
            str(item.get("chunk_text") or ""),
            str(item.get("section_number") or ""),
        ]
    ).lower()

    # Tier 1: primary consumer remedies (default path for most complaints)
    tier1 = [
        "refund",
        "replacement",
        "repair",
        "defect",
        "deficiency",
        "unfair trade practice",
        "e-commerce rules",
        "ecommerce rules",
        "section 39",
    ]
    # Tier 2: compensation/interest
    tier2 = ["compensation", "interest", "mental agony", "damages"]

    score = 0.0
    if any(k in text for k in tier1):
        score += 0.16
    elif any(k in text for k in tier2):
        score += 0.08

    # Tier 3 (product liability: sections 82-87) should be deprioritized unless injury is present.
    product_liability_sections = {"82", "83", "84", "85", "86", "87"}
    section = str(item.get("section_number") or "").strip()
    if section in product_liability_sections and not has_injury_signal:
        score -= 0.28

    # Additional de-prioritization for explicit product-liability framing without injury facts.
    if not has_injury_signal and "product liability" in text:
        score -= 0.12

    return score


def _specificity_bonus(item: Dict) -> float:
    text = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("context_path") or ""),
            str(item.get("chunk_text") or ""),
        ]
    ).lower()
    return 0.05 if any(k in text for k in SPECIFICITY_KEYWORDS) else -0.05


def build_sub_questions(query: str, domain: str) -> List[Tuple[str, str]]:
    generic = [
        ("issue", f"Identify the core legal issue in: {query}"),
        ("rule", f"What are the applicable statutory provisions for: {query}"),
        ("remedy", f"What are the legal remedies, forum, and jurisdiction for: {query}"),
    ]

    domain_specific: Dict[str, List[Tuple[str, str]]] = {
        "consumer": [
            ("issue", f"Under Consumer Protection Act 2019, what is the issue in: {query}"),
            ("rule", f"Under Consumer Protection Act 2019, identify defect/deficiency or unfair trade practice provisions for: {query}"),
            ("remedy", f"Prioritize routine remedies first (refund/replacement/repair) and then compensation under Section 39 for: {query}"),
            ("forum", f"Identify filing forum, limitation period, and e-Daakhil pathway for: {query}"),
        ],
        "property": [
            ("issue", f"Identify tenancy/eviction or possession issue in: {query}"),
            ("rule", f"Find applicable property/civil procedure provisions for: {query}"),
            ("remedy", f"Find legal remedies and forum in property disputes for: {query}"),
        ],
        "contract": [
            ("issue", f"Identify contract breach issue in: {query}"),
            ("rule", f"Find applicable contract/specific performance provisions for: {query}"),
            ("remedy", f"Find contract remedies including damages/specific performance for: {query}"),
        ],
        "labour": [
            ("issue", f"Identify the labour/employment dispute issue in: {query}"),
            ("rule", f"Find applicable labour law provisions for: {query}"),
            ("remedy", f"Find labour dispute remedies and forum for: {query}"),
        ],
        "criminal": [
            ("issue", f"Identify potential criminal offence issue in: {query}"),
            ("rule", f"Find applicable BNS/CrPC provisions for: {query}"),
            ("remedy", f"Find immediate legal steps and process for criminal complaints in: {query}"),
        ],
    }

    return domain_specific.get(domain, generic)


def _build_args(base_args: SimpleNamespace, query: str, domain: str, top_k: int) -> SimpleNamespace:
    return SimpleNamespace(
        q=query,
        corpus=base_args.corpus,
        legal_domain=domain,
        top_k=top_k,
        dense_k=base_args.dense_k,
        bm25_k=base_args.bm25_k,
        dense_weight=base_args.dense_weight,
        bm25_weight=base_args.bm25_weight,
        rerank=False,  # collect broad candidates first, rerank once after merge
        rerank_model=base_args.rerank_model,
        rerank_top_n=base_args.rerank_top_n,
        rerank_batch_size=base_args.rerank_batch_size,
        max_context_chars=base_args.max_context_chars,
    )


def run_subquestion_retrieval(
    base_args: SimpleNamespace,
    resolved_domain: str,
    per_query_top_k: int,
) -> Tuple[List[Dict], Dict]:
    sub_questions = build_sub_questions(base_args.q, resolved_domain)
    has_injury_signal = query_has_injury_signal(base_args.q)
    merged: Dict[str, Dict] = {}

    for tag, sq in sub_questions:
        sq_args = _build_args(
            base_args=base_args,
            query=sq,
            domain=resolved_domain if resolved_domain else "auto",
            top_k=per_query_top_k,
        )
        results = run_retrieval(sq_args)
        for item in results:
            key = _safe_key(item)
            base_score = float(item.get("final_score", item.get("hybrid_score", 0.0)))
            if key not in merged:
                merged[key] = dict(item)
                merged[key]["_subq_tags"] = {tag}
                merged[key]["_subq_score"] = base_score
            else:
                merged[key]["_subq_tags"].add(tag)
                merged[key]["_subq_score"] = max(float(merged[key]["_subq_score"]), base_score)

    combined = list(merged.values())
    for item in combined:
        coverage = len(item.get("_subq_tags", []))
        bonus = 0.06 * max(0, coverage - 1)
        base_score = float(item.get("_subq_score", item.get("hybrid_score", 0.0)))

        # Statute > judgment priority for civil/statutory tracks.
        statute_priority_bonus = 0.0
        if resolved_domain in {"consumer", "property", "contract", "labour"}:
            statute_priority_bonus = 0.12 if item.get("corpus") == "acts" else -0.04

        remedy_bonus = 0.0
        if resolved_domain == "consumer":
            remedy_bonus = _consumer_remedy_tier_bonus(item, has_injury_signal=has_injury_signal)

        specificity = _specificity_bonus(item)
        item["hybrid_score"] = base_score + bonus + statute_priority_bonus + remedy_bonus + specificity
        item["final_score"] = item["hybrid_score"]

    combined.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)

    # Optional final rerank on merged candidates, using the original user query.
    if base_args.rerank and combined:
        combined = rerank_results(
            query=base_args.q,
            results=combined,
            top_k=base_args.top_k,
            rerank_top_n=max(base_args.rerank_top_n, base_args.top_k),
            rerank_model=base_args.rerank_model,
            rerank_batch_size=base_args.rerank_batch_size,
        )
    else:
        combined = combined[: base_args.top_k]

    meta = {
        "used": True,
        "sub_questions": [{"tag": tag, "query": q} for tag, q in sub_questions],
        "candidate_count": len(merged),
        "selected_count": len(combined),
    }
    return combined, meta
