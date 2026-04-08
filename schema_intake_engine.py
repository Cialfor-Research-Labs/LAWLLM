import json
import os
import re
from typing import Any, Dict, List, Optional

from llama_legal_answer import call_llm


DEFAULT_SCHEMA_FILE = "legal_case_schemas.json"


def load_schema_registry(path: str = DEFAULT_SCHEMA_FILE) -> Dict[str, Dict[str, Any]]:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Schema file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    schemas = payload.get("schemas", [])
    registry: Dict[str, Dict[str, Any]] = {}
    for s in schemas:
        case_type = str(s.get("case_type", "")).strip()
        required_fields = s.get("required_fields", [])
        if not case_type or not isinstance(required_fields, list):
            continue
        registry[case_type] = {
            "case_type": case_type,
            "required_fields": required_fields,
        }
    if not registry:
        raise ValueError("No valid schemas found in schema file")
    return registry


class FactStore:
    def __init__(self) -> None:
        self.data: Dict[str, Dict[str, Any]] = {} # {"key": {"value": ..., "confidence": ...}}
        self._asked: set[str] = set()

    def update(self, key: str, value: Any, confidence: float = 1.0) -> None:
        if value is None:
            return
        if isinstance(value, str) and not value.strip():
            return
        current = self.data.get(key, {"value": None, "confidence": 0.0})
        if confidence >= current.get("confidence", 0.0):
            self.data[key] = {"value": value, "confidence": confidence}

    def update_many(self, values: Dict[str, Any], confidence: float = 1.0) -> None:
        for k, v in (values or {}).items():
            if isinstance(v, dict) and "value" in v and "confidence" in v:
                self.update(k, v["value"], v["confidence"])
            else:
                self.update(k, v, confidence)

    def get(self, key: str) -> Any:
        field = self.data.get(key)
        return field.get("value") if field else None

    def get_confidence(self, key: str) -> float:
        field = self.data.get(key)
        return field.get("confidence", 0.0) if field else 0.0

    def missing_fields(self, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        # A field is missing if it's not in data OR its confidence is low (< 0.7)
        return [
            field for field in schema["required_fields"] 
            if field["key"] not in self.data or self.data[field["key"]].get("confidence", 0.0) < 0.7
        ]

    def mark_asked(self, field_key: str) -> None:
        self._asked.add(field_key)

    def asked(self, field_key: str) -> bool:
        return field_key in self._asked

    def to_flat_dict(self) -> Dict[str, Any]:
        return {k: v.get("value") for k, v in self.data.items() if v.get("value") is not None}

    def to_json(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, indent=2)


def _extract_json_object(raw: str) -> Dict[str, Any]:
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


def classify_case(
    user_input: str,
    schemas: Dict[str, Dict[str, Any]],
    llm_model: str,
    llm_timeout_sec: int,
) -> str:
    case_types = list(schemas.keys())
    if not case_types:
        return "general"

    prompt = (
        "You are a case-type classifier.\n"
        "Select exactly one case_type from this allowed list:\n"
        f"{json.dumps(case_types, ensure_ascii=False)}\n\n"
        "Return JSON only: {\"case_type\":\"<one_allowed_value>\"}\n\n"
        f"User input:\n{user_input}"
    )

    try:
        raw = call_llm(model=llm_model, prompt=prompt, timeout_sec=llm_timeout_sec)
        parsed = _extract_json_object(raw)
        case_type = str(parsed.get("case_type", "")).strip()
        if case_type in schemas:
            return case_type
    except Exception:
        pass

    # Fallback classifier uses schema text only (no hardcoded business logic).
    q = user_input.lower()
    best_case = case_types[0]
    best_score = -1
    for case_type, schema in schemas.items():
        score = 0
        score += q.count(case_type.lower().replace("_", " "))
        for field in schema.get("required_fields", []):
            key = str(field.get("key", "")).lower().replace("_", " ")
            question = str(field.get("question", "")).lower()
            for token in set((key + " " + question).split()):
                if len(token) >= 4 and token in q:
                    score += 1
        if score > best_score:
            best_case = case_type
            best_score = score
    return best_case


def extract_facts(user_input: str, schema: Dict[str, Any], llm_model: str, llm_timeout_sec: int) -> Dict[str, Any]:
    required = [f["key"] for f in schema.get("required_fields", []) if f.get("key")]
    prompt = (
        "You extract structured facts from user text.\n"
        "Return JSON only.\n"
        f"Allowed keys: {json.dumps(required, ensure_ascii=False)}\n"
        "For unknown fields, omit the key.\n\n"
        f"User input:\n{user_input}"
    )
    try:
        raw = call_llm(model=llm_model, prompt=prompt, timeout_sec=llm_timeout_sec)
        parsed = _extract_json_object(raw)
        out: Dict[str, Dict[str, Any]] = {}
        for k in required:
            if k in parsed and parsed[k] is not None and str(parsed[k]).strip() != "":
                # LLM extracted facts from schema intake get a high confidence by default
                out[k] = {"value": parsed[k], "confidence": 0.9}
        return out
    except Exception:
        return _fallback_extract_facts(user_input=user_input, schema=schema)


def _fallback_extract_facts(user_input: str, schema: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    text = (user_input or "").strip()
    lower = text.lower()

    for field in schema.get("required_fields", []):
        key = str(field.get("key", "")).strip()
        question = str(field.get("question", "")).strip().lower()
        if not key:
            continue

        # Generic yes/no extraction.
        if "do you have" in question or question.startswith("is there"):
            if any(x in lower for x in ["yes", "i have", "available", "present"]):
                out[key] = {"value": "yes", "confidence": 0.7}
                continue
            if any(x in lower for x in ["no", "not", "don't", "dont", "none"]):
                out[key] = {"value": "no", "confidence": 0.7}
                continue

        # Keyword-overlap extraction from schema text itself (no case hardcoding).
        key_tokens = [t for t in re.split(r"[_\s\-]+", key.lower()) if len(t) >= 4]
        q_tokens = [t for t in re.split(r"\W+", question) if len(t) >= 4]
        tokens = set(key_tokens + q_tokens)
        if any(tok in lower for tok in tokens):
            out[key] = {"value": text, "confidence": 0.5}

    return out


def generate_questions(missing_fields: List[Dict[str, Any]], fact_store: FactStore) -> List[str]:
    questions: List[str] = []
    for field in missing_fields:
        key = str(field.get("key", "")).strip()
        question = str(field.get("question", "")).strip()
        if not key or not question:
            continue
        if fact_store.asked(key):
            continue
        questions.append(question)
        fact_store.mark_asked(key)
    return questions


def format_question_block(questions: List[str], fact_store: Optional[FactStore] = None) -> str:
    if not questions:
        return "Please share any additional details you have."
    lines = ["To proceed, please share these details:"]
    for i, q in enumerate(questions, start=1):
        # We don't have a specific mapping for confirmation questions in schema mode yet,
        # but we could add it here if needed.
        lines.append(f"{i}. {q}")
    return "\n".join(lines)


def generate_output(
    fact_store: FactStore,
    schema: Dict[str, Any],
    llm_model: str,
    llm_timeout_sec: int,
) -> str:
    prompt = (
        "You are a legal reasoning assistant.\n"
        "Generate output in this exact structure with headings:\n"
        "FACTS\nLEGAL ISSUE\nGROUNDS\nANALYSIS\nSTRATEGY\nPRAYER\n\n"
        "If unsure about exact sections, use Act-level references without guessing section numbers.\n"
        f"Case type: {schema.get('case_type')}\n"
        f"Known facts JSON:\n{fact_store.to_json()}" # LLM can see confidence now
    )
    try:
        return call_llm(model=llm_model, prompt=prompt, timeout_sec=llm_timeout_sec).strip()
    except Exception:
        case_type = schema.get("case_type", "unknown_case")
        facts_text = json.dumps(fact_store.data, ensure_ascii=False, indent=2)
        return (
            "FACTS\n"
            f"{facts_text}\n\n"
            "LEGAL ISSUE\n"
            f"The primary legal issue under case type '{case_type}' requires formal legal analysis.\n\n"
            "GROUNDS\n"
            "Applicable statutory and factual grounds should be mapped to the collected facts.\n\n"
            "ANALYSIS\n"
            "Based on available facts, the matter appears legally actionable subject to documentary verification.\n\n"
            "STRATEGY\n"
            "Proceed with notice/complaint preparation and preserve all evidence.\n\n"
            "PRAYER\n"
            "Seek statutory relief and compensation appropriate to the documented facts."
        )


def handle_input(
    user_input: str,
    fact_store: FactStore,
    schemas: Dict[str, Dict[str, Any]],
    llm_model: str,
    llm_timeout_sec: int,
) -> Dict[str, Any]:
    if not fact_store.get("case_type"):
        case_type = classify_case(
            user_input=user_input,
            schemas=schemas,
            llm_model=llm_model,
            llm_timeout_sec=llm_timeout_sec,
        )
        fact_store.update("case_type", case_type)

    case_type = fact_store.get("case_type")
    schema = schemas[case_type]

    extracted = extract_facts(
        user_input=user_input,
        schema=schema,
        llm_model=llm_model,
        llm_timeout_sec=llm_timeout_sec,
    )
    fact_store.update_many(extracted)

    missing = fact_store.missing_fields(schema)
    if missing:
        questions = generate_questions(missing, fact_store)
        return {
            "mode": "question",
            "case_type": case_type,
            "missing_fields": [f["key"] for f in missing],
            "questions": questions,
            "text": format_question_block(questions, fact_store),
        }

    output = generate_output(
        fact_store=fact_store,
        schema=schema,
        llm_model=llm_model,
        llm_timeout_sec=llm_timeout_sec,
    )
    return {
        "mode": "answer",
        "case_type": case_type,
        "missing_fields": [],
        "questions": [],
        "text": output,
    }
