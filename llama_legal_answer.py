import argparse
import os
import re
from typing import Optional, List, Dict, Any

from context_builder import build_context_pack, load_acts_chunk_lookup, run_retrieval
from bedrock_client import call_bedrock_chat, DEFAULT_BEDROCK_MODEL_ID

OUT_DIR = "llama_outputs"

# AWS Bedrock configuration
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)

# Global placeholders
_model = None
_tokenizer = None


def get_model_and_tokenizer(model_name: str):
    """Bypassed local loading to use remote API."""
    return None, None


def safe_filename(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in text).strip("_")
    return (cleaned[:80] or "query").strip("_")


def build_llm_prompt(query: str, context: str, history: List[Dict[str, str]] = None, tokenizer=None) -> Dict[str, Any]:
    """
    Build structured messages for the LLM, separating the system prompt.
    """
    system_message = (
        "You are a senior Indian legal AI assistant providing structured legal analysis.\n\n"
        "You MUST follow these rules:\n"
        "0. Answer in Indian legal context only. Use Indian statutes, Indian courts, and Indian legal terminology.\n"
        "0.1 Do not refuse with generic statements like 'I can't give legal advice'; provide general legal information and procedural next steps instead.\n"
        "1. Answer ONLY using the provided context blocks and any Known Legal Signals provided.\n"
        "2. DO NOT invent laws, sections, courts, or facts not present in the context.\n"
        "3. If a relevant statute or judgement is present in the context, you MUST name it explicitly with section numbers.\n"
        "4. Do NOT mention context-block markers like [C1], [C2], etc. in the final answer.\n"
        "5. Instead of block markers, cite the authority by name and section number or sub-section.\n"
        "6. Only say \"No relevant legal provision found in the database.\" when the context is genuinely unrelated.\n"
        "7. Prefer current law names exactly as they appear in the context.\n"
        "8. Keep headings and body text on separate lines.\n"
        "9. Do not output stray markdown markers or incomplete fragments.\n"
        "10. Use only the authorities listed in the retrieved authorities list.\n"
        "11. Do not cite any section number that is not present in the retrieved authorities list.\n"
        "12. Be confident and direct. Do NOT hedge with 'maybe', 'it depends completely', or 'I'm not sure'.\n"
        "13. If assumptions are needed due to missing facts, state them explicitly but still provide the legal position.\n\n"
        "Return the answer in exactly this FIRAC structure:\n\n"
        "Part 1 - Facts and Legal Issue:\n"
        "- Briefly restate the key facts from the query\n"
        "- Identify the core legal issue(s)\n\n"
        "Part 2 - Applicable Law:\n"
        "- List every relevant Act, exact section number, and judgement found in the retrieved authorities\n"
        "- For each law, briefly state how it applies to the facts\n"
        "- List relevant judgements separately if any are present in context\n"
        "- Do not add any authority not present in context or Known Legal Signals\n\n"
        "Part 3 - Analysis:\n"
        "- Apply the law to the facts step by step\n"
        "- Identify strengths and weaknesses of the legal position\n"
        "- Note any conditions or prerequisites that must be met\n\n"
        "Part 4 - Remedies and Next Steps:\n"
        "1. <specific immediate action>\n"
        "2. <specific procedural step>\n"
        "3. <specific authority/forum to approach>\n"
        "- Be practical, procedural, and lawyer-like\n"
        "- Include timelines and deadlines where applicable\n\n"
        "Part 5 - Limits:\n"
        "<Short paragraph explaining forum, jurisdiction, fact, and evidence limits where relevant.>\n\n"
        "Part 6 - Disclaimer:\n"
        "For information only. Consult a professional."
    )

    messages = []
    
    # Add history (excluding the current query)
    if history:
        # Keep last 10 turns to avoid context overflow
        for turn in history[-10:]:
            messages.append({"role": turn["role"], "content": turn["content"]})

    # Add current query with context
    user_message = (
        f"Question: {query}\n\n"
        "Do not output context block IDs.\n"
        "If both statutes and judgements are provided, mention both when relevant.\n"
        "Use only the retrieved authorities listed below when naming sections.\n\n"
        f"Relevant Legal Context:\n{context}"
    )
    messages.append({"role": "user", "content": user_message})

    # Return structured dict instead of string
    return {
        "system": system_message,
        "messages": messages
    }


def call_llm(
    model_name: Optional[str] = None,
    prompt: Any = "",
    timeout_sec: int = 300,
    model: Optional[str] = None,
    max_tokens: int = 1000,
    temperature: float = 0.2,
    top_p: float = 0.9,
) -> str:
    """Calls AWS Bedrock for text generation. 
    Can accept a raw prompt string or a structured message dict/list.
    Dynamic max_tokens: Legal Query (1,000) vs Document Generation (4,000).
    """
    selected_model = model_name or model or BEDROCK_MODEL_ID
    _ = timeout_sec  # Timeout is configured in bedrock client env vars.

    system_prompt = None
    messages = []

    if isinstance(prompt, dict) and "messages" in prompt:
        system_prompt = prompt.get("system")
        messages = prompt.get("messages", [])
    elif isinstance(prompt, list):
        messages = prompt
    else:
        # String fallback
        messages = [{"role": "user", "content": str(prompt)}]

    return call_bedrock_chat(
        messages=messages,
        system_prompt=system_prompt,
        model_id=selected_model,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
    )

def rewrite_query(user_query: str, model_name: str, timeout_sec: int = 15) -> str:
    """Uses LLM to rewrite a layman query into a dense legal query."""
    prompt = (
        "Convert the following user query into a precise legal search query for INDIA only.\n"
        "Focus on Indian legal terms, relevant Indian Acts, and user intent.\n"
        "Do NOT include foreign laws or jurisdictions (e.g., US, UK, EU, GDPR, CFAA).\n"
        "Do NOT include section numbers unless explicitly present in user query.\n"
        "Return plain search keywords only (no markdown, no bullets, no quotes).\n\n"
        f"User Query: {user_query}\n\n"
        "Output ONLY the improved legal query."
    )
    result = call_llm(model_name, prompt, timeout_sec)
    if result.startswith("[ERROR]"):
        return user_query  # Fallback to original
    cleaned = result.strip().replace("**", "").replace("\"", "")
    lower = cleaned.lower()
    foreign_markers = ["u.s.", "united states", "cfaa", "gdpr", "wiretap act", "ecpa", "eu law", "uk law"]
    if any(tok in lower for tok in foreign_markers):
        return user_query
    return cleaned or user_query


def _query_terms(text: str) -> set[str]:
    stopwords = {
        "the", "and", "for", "with", "from", "that", "this", "what", "when", "where",
        "which", "your", "have", "has", "had", "been", "into", "them", "they", "their",
        "about", "would", "could", "should", "not", "returning", "return", "doing", "do",
        "my", "our", "his", "her", "its", "you", "are", "was", "were", "will",
    }
    return {tok for tok in re.findall(r"[a-z0-9]{3,}", (text or "").lower()) if tok not in stopwords}

def llm_rerank(user_query: str, results: List[Dict], model_name: str, timeout_sec: int = 20) -> List[Dict]:
    """Uses LLM to select the top 3 most relevant retrieved results."""
    if not results:
        return []
    
    chunks_text = ""
    for idx, r in enumerate(results):
        txt = r.get("chunk_text", "")
        title = r.get("title", "")
        sec = r.get("section_number", "")
        chunks_text += f"[Block {idx}] {title} Sec {sec}\n{txt[:500]}...\n\n"
        
    prompt = (
        f"User Query: {user_query}\n\n"
        f"Below are retrieved legal texts:\n\n{chunks_text}\n"
        f"Select the 3 most relevant blocks for answering the query. "
        f"PRIORITIZE statutes (like Bhartiya Nyay Sanhita/BNS) over judgements for legal grounding. "
        f"Output ONLY a comma-separated list of the block numbers (e.g. 0, 2, 4) and nothing else."
    )
    
    response = call_llm(model_name, prompt, timeout_sec)
    
    selected_indices = []
    import re
    matches = re.findall(r'\d+', response)
    for m in matches:
        idx = int(m)
        if idx < len(results) and idx not in selected_indices:
            selected_indices.append(idx)
            
    if not selected_indices:
        selected_indices = list(range(min(3, len(results))))

    selected = [results[i] for i in selected_indices[:3]]

    available_corpora = {r.get("corpus") for r in results if r.get("corpus")}
    selected_corpora = {r.get("corpus") for r in selected if r.get("corpus")}

    if "judgements" in available_corpora and "judgements" not in selected_corpora:
        query_terms = _query_terms(user_query)
        best_judgement = None
        for candidate in results:
            if candidate.get("corpus") != "judgements":
                continue
            candidate_terms = _query_terms(
                " ".join(
                    [
                        str(candidate.get("title") or ""),
                        str(candidate.get("chunk_text") or ""),
                    ]
                )
            )
            if len(query_terms & candidate_terms) >= 2:
                best_judgement = candidate
                break
        if best_judgement is not None:
            if len(selected) >= 3:
                selected[-1] = best_judgement
            else:
                selected.append(best_judgement)

    if "acts" in available_corpora and "acts" not in {r.get("corpus") for r in selected}:
        best_act = next((r for r in results if r.get("corpus") == "acts"), None)
        if best_act is not None:
            if len(selected) >= 3:
                selected[0] = best_act
            else:
                selected.append(best_act)

    deduped = []
    seen_keys = set()
    for item in selected:
        key = (item.get("corpus"), item.get("chunk_id"), item.get("title"), item.get("section_number"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(item)

    return deduped[:3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--q", required=True)
    parser.add_argument("--llm-model", default=BEDROCK_MODEL_ID)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    results = run_retrieval(args)
    acts_lookup = load_acts_chunk_lookup("JSON_acts")

    pack = build_context_pack(
        query=args.q,
        results=results,
        acts_lookup=acts_lookup,
        max_chars=45000,
    )

    context_text = "\n\n".join([
        f"{c.get('title')} - Section {c.get('section_number')}\n{(c.get('texts', {}) or {}).get('chunk_text', '')}"
        for c in pack.get("context_blocks", [])
    ])

    _, tokenizer = get_model_and_tokenizer(args.llm_model)
    prompt = build_llm_prompt(args.q, context_text, tokenizer=tokenizer)
    answer = call_llm(args.llm_model, prompt, args.timeout)

    print("\n===== ANSWER =====\n")
    print(answer)


if __name__ == "__main__":
    main()
