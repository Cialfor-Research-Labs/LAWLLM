import json
import os
import re
from typing import Dict, List, Tuple

from llama_legal_answer import call_llm

_INDIAN_ACT_TITLES_CACHE: set = set()

FOREIGN_OR_NON_TARGET_RED_FLAGS = [
    "magistrates' courts act",
    "magistrates courts act",
    "uk ",
    "united kingdom",
    "england",
    "wales",
    "u.s.",
    "united states",
]


def _load_master_indian_acts(json_dir: str = "JSON_acts") -> set:
    global _INDIAN_ACT_TITLES_CACHE
    if _INDIAN_ACT_TITLES_CACHE:
        return _INDIAN_ACT_TITLES_CACHE

    titles = set()
    if os.path.isdir(json_dir):
        for name in os.listdir(json_dir):
            if not name.endswith(".json"):
                continue
            titles.add(name.replace(".json", "").strip().lower())
    _INDIAN_ACT_TITLES_CACHE = titles
    return titles


def _passes_geography_guardrail(item: Dict, domain: str, master_titles: set) -> bool:
    title = str(item.get("title") or "").lower()
    context_path = str(item.get("context_path") or "").lower()
    source = str(item.get("source_json") or "").lower()
    chunk = str(item.get("chunk_text") or "").lower()
    combined = f"{title} {context_path} {source} {chunk}"

    if any(flag in combined for flag in FOREIGN_OR_NON_TARGET_RED_FLAGS):
        return False

    # For acts corpus, title/source should align with known Indian acts list.
    if item.get("corpus") == "acts" and master_titles:
        source_ok = any(t in source for t in master_titles)
        title_ok = any(t in title for t in master_titles)
        # Keep if either title or source matches known act names.
        if not (source_ok or title_ok):
            return False

    # Consumer-domain hard rejection of court-fee procedural bleed.
    if domain == "consumer":
        bleed_terms = ["court fee", "court fees", "magistrate", "process-fee"]
        if any(term in combined for term in bleed_terms):
            return False

    return True


def _extract_json(raw: str) -> Dict:
    text = (raw or "").strip()
    if not text:
        return {}
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return {}
    return {}


def llm_relevance_judge(
    query: str,
    domain: str,
    results: List[Dict],
    llm_model: str,
    timeout_sec: int,
    top_n: int = 5,
) -> Tuple[List[Dict], Dict]:
    if not results:
        return results, {"applied": False, "reason": "no_results"}

    master_titles = _load_master_indian_acts()
    prefiltered = [r for r in results if _passes_geography_guardrail(r, domain=domain, master_titles=master_titles)]
    if len(prefiltered) >= max(3, min(top_n, len(results))):
        results = prefiltered

    top = results[:top_n]
    lines = []
    for i, item in enumerate(top, start=1):
        snippet = (item.get("chunk_text") or "").replace("\n", " ")
        if len(snippet) > 260:
            snippet = snippet[:260] + "..."
        lines.append(
            f'{{"id": {i}, "source": "{item.get("source_json")}", "title": "{item.get("title")}", "context": "{item.get("context_path")}", "text": "{snippet}"}}'
        )

    prompt = (
        "You are a strict legal retrieval judge.\n"
        f"User query: {query}\n"
        f"Target domain: {domain}\n"
        "From the candidate chunks below, keep only chunks directly relevant to the user issue.\n"
        "Reject off-domain procedural/tax/criminal noise unless explicitly asked.\n"
        'Return ONLY JSON: {"keep_ids":[...]} where ids are from the list.\n\n'
        "Candidates:\n" + "\n".join(lines)
    )

    try:
        raw = call_llm(
model=llm_model, prompt=prompt, timeout_sec=timeout_sec)
        parsed = _extract_json(raw)
        keep_ids = [int(x) for x in parsed.get("keep_ids", []) if isinstance(x, int) or (isinstance(x, str) and x.isdigit())]
        keep_ids = [k for k in keep_ids if 1 <= k <= len(top)]
        if not keep_ids:
            return results, {"applied": True, "kept": len(results), "reason": "empty_keep_ids"}

        kept_top = [top[i - 1] for i in keep_ids]
        kept_keys = {id(x) for x in kept_top}
        tail = [r for r in results[top_n:] if id(r) not in kept_keys]
        merged = kept_top + tail
        return merged, {"applied": True, "kept_top": len(kept_top), "top_n": top_n, "prefiltered": len(prefiltered)}
    except Exception as exc:
        return results, {"applied": True, "reason": f"judge_failed:{exc}", "prefiltered": len(prefiltered)}
