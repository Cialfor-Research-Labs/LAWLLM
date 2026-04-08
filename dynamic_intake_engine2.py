import json
from typing import Dict, Any, List

from context_builder import build_context_pack, load_acts_chunk_lookup, run_retrieval
from llama_legal_answer import call_ollama


class FactStore:
    def __init__(self):
        self.data: Dict[str, Any] = {}

    def update(self, key: str, value: Any):
        if value:
            self.data[key] = value

    def update_many(self, values: Dict[str, Any]):
        for k, v in values.items():
            self.update(k, v)


def build_retrieval(query: str):
    args = type("Args", (), {
        "q": query,
        "corpus": "all",
        "top_k": 5,
        "dense_k": 100,
        "bm25_k": 100,
        "dense_weight": 0.6,
        "bm25_weight": 0.4,
        "rerank": False,
        "max_context_chars": 14000
    })()

    results = run_retrieval(args)
    acts_lookup = load_acts_chunk_lookup("JSON_acts")

    pack = build_context_pack(
        query=query,
        results=results,
        acts_lookup=acts_lookup,
        max_chars=14000
    )

    return pack


def build_prompt(query: str, context_blocks: List[Dict]) -> str:
    context_text = "\n\n".join([
        f"{c.get('title')} - Section {c.get('section_number')}\n{(c.get('texts', {}) or {}).get('chunk_text', '')}"
        for c in context_blocks
    ])

    return f"""
You are an AI Legal Assistant trained to help users understand Indian law.

STRICT RULES:
- Use ONLY the provided context
- Do NOT hallucinate laws or sections
- If insufficient data, say so clearly

FORMAT:
Issue:
Relevant Law / Sections:
Explanation:
Conclusion:

-----------------------------------

USER QUERY:
{query}

LEGAL CONTEXT:
{context_text}

-----------------------------------

Generate a complete legal answer.
"""


def handle_query(user_input: str, llm_model="llama3.1", timeout=300):
    fact_store = FactStore()
    fact_store.update("query", user_input)

    pack = build_retrieval(user_input)

    prompt = build_prompt(
        user_input,
        pack.get("context_blocks", [])
    )

    answer = call_ollama(
        model=llm_model,
        prompt=prompt,
        timeout_sec=timeout
    )

    return {
        "text": answer
    }