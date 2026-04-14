import argparse
import json
import os
import re
from datetime import datetime
from typing import Dict, List, Tuple

from hybrid_retrieval import CORPORA, hybrid_search, rerank_results
from legal_router import classify_legal_issue, domain_filter

OUT_DIR = "context_builder_outputs"


def safe_filename(text: str) -> str:
    t = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_")
    return t[:80] if t else "query"


def load_acts_chunk_lookup(json_dir: str = "JSON_acts") -> Dict[str, Dict]:
    lookup: Dict[str, Dict] = {}
    if not os.path.isdir(json_dir):
        return lookup

    for name in sorted(os.listdir(json_dir)):
        if not name.endswith(".json") or name.startswith("."):
            continue
        path = os.path.join(json_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        for chunk in data.get("chunks", []):
            cid = chunk.get("chunk_id")
            if not cid:
                continue
            lookup[cid] = {
                "parent_text": chunk.get("parent_text"),
                "full_section_text": chunk.get("full_section_text"),
                "context_path": chunk.get("context_path"),
                "section_title": chunk.get("section_title"),
                "section_number": chunk.get("section_number"),
                "title": chunk.get("title"),
                "source_file": chunk.get("source_file"),
            }
    return lookup


def trim(text: str, n: int) -> str:
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[: n - 3].rstrip() + "..."


def _looks_like_hash(value: str) -> bool:
    token = str(value or "").strip().lower()
    return bool(re.fullmatch(r"[a-f0-9]{24,64}", token))


def _normalize_hint_list(values: List[str]) -> List[str]:
    return [str(v).strip().lower() for v in values if str(v).strip()]


def _apply_section_diversity(results: List[Dict], top_k: int, max_per_section: int = 2) -> List[Dict]:
    if not results:
        return results
    section_counts: Dict[Tuple[str, str, str], int] = {}
    diversified: List[Dict] = []
    overflow: List[Dict] = []

    for item in results:
        key = (
            str(item.get("corpus") or ""),
            str(item.get("document_id") or item.get("title") or ""),
            str(item.get("section_number") or item.get("context_path") or ""),
        )
        current = section_counts.get(key, 0)
        if current < max_per_section:
            section_counts[key] = current + 1
            diversified.append(item)
        else:
            overflow.append(item)

    if len(diversified) < top_k:
        diversified.extend(overflow[: max(0, top_k - len(diversified))])
    return diversified[:top_k]


def _apply_law_focus(
    results: List[Dict],
    relevant_laws: List[str],
    preferred_laws: List[str],
    disallowed_law_hints: List[str],
) -> List[Dict]:
    if not results:
        return results

    relevant_laws = _normalize_hint_list(relevant_laws)
    preferred_laws = _normalize_hint_list(preferred_laws)
    disallowed_law_hints = _normalize_hint_list(disallowed_law_hints)

    for item in results:
        hay = " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("document_id") or ""),
                str(item.get("context_path") or ""),
                str(item.get("chunk_text") or ""),
                str(item.get("court") or ""),
            ]
        ).lower()

        base = float(item.get("final_score", item.get("hybrid_score", 0.0)) or 0.0)
        multiplier = 1.0

        if preferred_laws and any(hint in hay for hint in preferred_laws):
            multiplier *= 1.4
        if relevant_laws and not any(hint in hay for hint in relevant_laws):
            multiplier *= 0.65
        if disallowed_law_hints and any(hint in hay for hint in disallowed_law_hints):
            multiplier *= 0.1

        item["final_score"] = base * multiplier
        item["hybrid_score"] = base * multiplier

    results.sort(key=lambda x: x.get("final_score", x.get("hybrid_score", 0.0)), reverse=True)
    return results


def run_retrieval(args: argparse.Namespace) -> List[Dict]:
    route = classify_legal_issue(args.q)
    requested_domain = getattr(args, "legal_domain", "auto")
    domain = route.domain if requested_domain in (None, "", "auto") else requested_domain

    rerank_top_n = int(getattr(args, "rerank_top_n", args.top_k) or args.top_k)
    candidate_k = max(args.top_k, rerank_top_n) if args.rerank else args.top_k
    act_filter_arg = getattr(args, "act_filter", None)
    section_filter_arg = getattr(args, "section_filter", None)
    era_filter_arg = getattr(args, "era_filter", None)

    results = []
    if args.corpus == "all" or args.corpus == "acts":
        cfg = CORPORA["acts"]
        domain_filter_arg = getattr(args, "domain_filter", None)
        res_acts = hybrid_search(
            cfg,
            query=args.q,
            top_k=candidate_k,
            dense_k=args.dense_k,
            bm25_k=args.bm25_k,
            dense_weight=args.dense_weight,
            bm25_weight=args.bm25_weight,
            domain_filter=domain_filter_arg,
            act_filter=act_filter_arg,
            section_filter=section_filter_arg,
            era_filter=era_filter_arg,
        )
        results.extend(res_acts)
    
    if args.corpus == "all" or args.corpus == "judgements":
        cfg = CORPORA["judgements"]
        res_judgements = hybrid_search(
            cfg,
            query=args.q,
            top_k=candidate_k,
            dense_k=args.dense_k,
            bm25_k=args.bm25_k,
            dense_weight=args.dense_weight,
            bm25_weight=args.bm25_weight,
            domain_filter=None, # domain_filter usually for acts
            act_filter=None,
            section_filter=None,
            era_filter=era_filter_arg,
        )
        results.extend(res_judgements)

    # Implement Quota-Based Interleaving for "all" search
    if args.corpus == "all":
        acts = [r for r in results if r.get("corpus") == "acts"]
        judgements = [r for r in results if r.get("corpus") == "judgements"]
        
        # Sort each separately
        acts.sort(key=lambda x: x.get("hybrid_score", 0), reverse=True)
        judgements.sort(key=lambda x: x.get("hybrid_score", 0), reverse=True)
        
        # Keep at least a small quota from each (if they pass a threshold, here 0.3)
        final_list = []
        quota = min(candidate_k // 3, 5) # Keep at least 5 from each if they pass
        
        final_list.extend(acts[:quota])
        final_list.extend(judgements[:quota])
        
        # Fill the rest from the combined pool
        remaining = sorted(acts[quota:] + judgements[quota:], key=lambda x: x.get("hybrid_score", 0), reverse=True)
        final_list.extend(remaining[:candidate_k - len(final_list)])
        
        results = final_list
    else:
        # Normal sort and truncate for single corpus
        results.sort(key=lambda x: x.get("hybrid_score", 0), reverse=True)
        results = results[:candidate_k]

    intent = getattr(args, "intent_route", None) or {}
    exclude_terms = [t.lower() for t in intent.get("exclude_terms", []) if t]
    must_have_terms = [t.lower() for t in intent.get("must_have_terms", []) if t]
    allowed_source_hints = [t.lower() for t in intent.get("allowed_source_hints", []) if t]
    strict_domain_filter = bool(intent.get("strict_domain_filter", False))

    if exclude_terms and results:
        filtered = []
        for item in results:
            hay = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("context_path") or ""),
                    str(item.get("chunk_text") or ""),
                ]
            ).lower()
            if any(term in hay for term in exclude_terms):
                continue
            filtered.append(item)
        # keep fallback behavior if hard filter over-prunes
        if len(filtered) >= max(3, args.top_k // 2):
            results = filtered

    if must_have_terms and results:
        prioritized = []
        others = []
        for item in results:
            hay = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("context_path") or ""),
                    str(item.get("chunk_text") or ""),
                ]
            ).lower()
            if any(term in hay for term in must_have_terms):
                prioritized.append(item)
            else:
                others.append(item)
        if prioritized:
            results = prioritized + others

    if strict_domain_filter and allowed_source_hints and results:
        strict = []
        for item in results:
            hay = " ".join(
                [
                    str(item.get("source_json") or ""),
                    str(item.get("title") or ""),
                    str(item.get("context_path") or ""),
                    str(item.get("chunk_text") or ""),
                ]
            ).lower()
            if any(h in hay for h in allowed_source_hints):
                strict.append(item)
        if len(strict) >= max(3, args.top_k // 2):
            results = strict

    if args.rerank:
        results = rerank_results(
            query=args.q,
            results=results,
            top_k=args.top_k,
            rerank_top_n=args.rerank_top_n,
            rerank_model=args.rerank_model,
            rerank_batch_size=args.rerank_batch_size,
        )
    else:
        results = results[: args.top_k]

    # Keep section-level diversity in the final shortlist.
    results = _apply_section_diversity(results, top_k=args.top_k, max_per_section=2)

    results = _apply_law_focus(
        results,
        relevant_laws=getattr(args, "relevant_laws", []) or [],
        preferred_laws=getattr(args, "preferred_laws", []) or [],
        disallowed_law_hints=getattr(args, "disallowed_law_hints", []) or [],
    )

    # Statute-vs-judgment weighting for civil/statutory domains.
    if domain in {"consumer", "property", "contract", "labour"} and results:
        tenant_keywords = {"tenant", "renter", "landlord", "eviction", "lease", "rent"}
        is_tenant_query = any(k in args.q.lower() for k in tenant_keywords)
        
        for item in results:
            base = float(item.get("final_score", item.get("hybrid_score", 0.0)))
            title = (item.get("title") or "").lower()
            doc_id = (item.get("document_id") or "").lower()
            
            boost = 1.0
            # Boost Transfer of Property Act for tenancy queries
            if is_tenant_query and ("transfer of property" in doc_id or "transfer of property" in title):
                boost = 1.5
            # Penalize clearly irrelevant acts for tenancy
            elif is_tenant_query and ("companies act" in doc_id or "companies act" in title):
                boost = 0.1
            
            final_item_score = base * boost
            item["final_score"] = final_item_score
            item["hybrid_score"] = final_item_score
            
        results.sort(key=lambda x: x.get("final_score", x.get("hybrid_score", 0.0)), reverse=True)

    min_keep = max(3, args.top_k // 2)
    scoped_results, applied = domain_filter(
        results,
        domain=domain,
        min_keep=min_keep,
        confidence=route.confidence,
    )
    scoped_results = scoped_results[: args.top_k]

    # Lightweight trace for API/CLI callers that inspect items.
    for item in scoped_results:
        item["issue_domain"] = domain
        item["issue_domain_confidence"] = route.confidence
        item["issue_domain_filter_applied"] = applied

    return scoped_results


def build_context_pack(query: str, results: List[Dict], acts_lookup: Dict[str, Dict], max_chars: int) -> Dict:
    citations = []
    blocks = []
    total = 0

    for i, item in enumerate(results, start=1):
        cite_id = f"C{i}"
        chunk_id = item.get("chunk_id")
        extra = acts_lookup.get(chunk_id, {}) if item.get("corpus") == "acts" else {}

        chunk_text = item.get("chunk_text", "")
        parent_text = extra.get("parent_text") or ""
        section_text = extra.get("full_section_text") or ""

        # Clean up titles with corpus-aware rules.
        raw_title = extra.get("title") or item.get("title")
        doc_id = item.get("document_id")

        corpus = str(item.get("corpus") or "").strip().lower()

        # For judgements, always prefer the retrieved case name.
        # Avoid showing hash-like document IDs as authority names.
        if corpus == "judgements":
            if raw_title:
                display_title = raw_title
            elif doc_id and not _looks_like_hash(doc_id):
                display_title = doc_id
            else:
                display_title = "Judgement (title unavailable)"
        else:
            # For acts, keep existing cleanup behavior.
            if doc_id and (not raw_title or len(raw_title) > 60 or "The following provisions" in raw_title):
                display_title = doc_id
            else:
                display_title = raw_title or "Legal Document"

        block = {
            "citation_id": cite_id,
            "corpus": item.get("corpus"),
            "document_id": doc_id,
            "title": display_title,
            "section_number": extra.get("section_number") or item.get("section_number"),
            "section_title": extra.get("section_title") or item.get("section_title"),
            "context_path": extra.get("context_path") or item.get("context_path"),
            "source_file": extra.get("source_file") or item.get("source_json"),
            "chunk_id": chunk_id,
            "scores": {
                "final_score": item.get("final_score", item.get("hybrid_score")),
                "hybrid_score": item.get("hybrid_score"),
                "dense_score": item.get("dense_score"),
                "bm25_score": item.get("bm25_score"),
                "rerank_score": item.get("rerank_score"),
            },
            "texts": {
                "chunk_text": trim(chunk_text, 1200),
                "parent_text": trim(parent_text, 450),
                "section_text": trim(section_text, 1200),
                "court": item.get("court"),
                "bench": item.get("bench"),
                "date": item.get("date"),
                "chunk_type": item.get("chunk_type") or extra.get("unit_type"),
            },
        }

        block_str = json.dumps(block, ensure_ascii=False)
        if total + len(block_str) > max_chars:
            break

        total += len(block_str)
        blocks.append(block)

        citations.append(
            {
                "citation_id": cite_id,
                "title": block["title"],
                "section_number": block["section_number"],
                "context_path": block["context_path"],
                "source_file": block["source_file"],
                "chunk_id": block["chunk_id"],
            }
        )

    instructions = (
        "Use only the cited context blocks. "
        "If conflict exists, prioritize statutory text over secondary interpretation. "
        "Do not introduce legal authorities not present in these context blocks."
    )

    prompt_context_lines = [
        f"User Query: {query}",
        "",
        "Context Blocks:",
    ]

    for b in blocks:
        prompt_context_lines.append(f"[{b['citation_id']}] Source: {b['corpus'].upper()} | Ref: {b['document_id']} | Title: {b['title']}")
        prompt_context_lines.append(f"Content: {b['texts']['chunk_text']}")
        if b['texts'].get('court'):
            prompt_context_lines.append(f"Court: {b['texts']['court']} | Date: {b['texts']['date']}")
        if b['texts'].get('bench'):
            prompt_context_lines.append(f"Bench: {b['texts']['bench']}")
        if b["texts"]["parent_text"]:
            prompt_context_lines.append(f"Context: {b['texts']['parent_text']}")
        prompt_context_lines.append("")

    prompt_context = "\n".join(prompt_context_lines).strip()

    return {
        "query": query,
        "instructions_for_llm": instructions,
        "context_blocks": blocks,
        "citations": citations,
        "prompt_context": prompt_context,
    }


def save_outputs(pack: Dict, query: str) -> Tuple[str, str]:
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = safe_filename(query)

    json_path = os.path.join(OUT_DIR, f"{stamp}_{slug}.json")
    txt_path = os.path.join(OUT_DIR, f"{stamp}_{slug}.txt")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=2)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(pack["prompt_context"])

    return json_path, txt_path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build LLM-ready context packs from hybrid retrieval")
    p.add_argument("--q", required=True)
    p.add_argument("--corpus", choices=["acts", "judgements", "all"], default="all")
    p.add_argument("--top-k", type=int, default=12)
    p.add_argument("--dense-k", type=int, default=100)
    p.add_argument("--bm25-k", type=int, default=100)
    p.add_argument("--dense-weight", type=float, default=0.6)
    p.add_argument("--bm25-weight", type=float, default=0.4)
    p.add_argument("--rerank", action="store_true")
    p.add_argument("--rerank-model", default="BAAI/bge-reranker-base")
    p.add_argument("--rerank-top-n", type=int, default=50)
    p.add_argument("--rerank-batch-size", type=int, default=16)
    p.add_argument("--act-filter", default=None)
    p.add_argument("--section-filter", default=None)
    p.add_argument("--era-filter", default=None)
    p.add_argument("--max-context-chars", type=int, default=45000)
    p.add_argument(
        "--legal-domain",
        choices=["auto", "general", "property", "consumer", "criminal", "labour", "contract"],
        default="auto",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    results = run_retrieval(args)
    acts_lookup = load_acts_chunk_lookup("JSON_acts")
    pack = build_context_pack(
        query=args.q,
        results=results,
        acts_lookup=acts_lookup,
        max_chars=args.max_context_chars,
    )

    json_path, txt_path = save_outputs(pack, args.q)

    print(f"Retrieved: {len(results)} results")
    print(f"Context blocks used: {len(pack['context_blocks'])}")
    print(f"Saved JSON: {json_path}")
    print(f"Saved prompt text: {txt_path}")


if __name__ == "__main__":
    main()
