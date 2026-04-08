import json
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from jurisdiction_validator import consumer_forum_by_amount
from llama_legal_answer import call_llm
from statutory_checks import consumer_limitation, money_recovery_limitation


class IncidentCandidate(BaseModel):
    type: str
    confidence: float

class Entities(BaseModel):
    platform: List[str] = Field(default_factory=list)
    financial_institution: List[str] = Field(default_factory=list)
    person: List[str] = Field(default_factory=list)
    device: List[str] = Field(default_factory=list)

class Loss(BaseModel):
    financial: Optional[float] = None
    access: Optional[bool] = None
    reputation: Optional[bool] = None

class Timeline(BaseModel):
    incident_date: Optional[str] = None
    reported: bool = False

class Evidence(BaseModel):
    available: bool = False
    type: List[str] = Field(default_factory=list)

class FactExtraction(BaseModel):
    incident_type_candidates: List[IncidentCandidate] = Field(default_factory=list)
    entities: Entities = Field(default_factory=Entities)
    actions: List[str] = Field(default_factory=list)
    loss: Loss = Field(default_factory=Loss)
    timeline: Timeline = Field(default_factory=Timeline)
    evidence: Evidence = Field(default_factory=Evidence)
    
    # Keeping some existing meta-fields if needed by existing code
    legal_domain: str = Field(default="general")
    cause_summary: str = Field(default="")
    follow_up_question: Optional[str] = None


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def _to_iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def _extract_json_object(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Empty LLM response")

    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _parse_amount_inr(text: str) -> Optional[float]:
    q = (text or "").lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lakhs|lac|lacs|crore|crores)\b", q)
    if m:
        n = float(m.group(1))
        unit = m.group(2)
        if "crore" in unit:
            return n * 10_000_000
        return n * 100_000
    m2 = re.search(r"\b(?:rs\.?|inr)?\s*(\d{4,12})\b", q)
    if m2:
        return float(m2.group(1))
    return None


def _parse_date_from_query(text: str) -> Optional[date]:
    q = (text or "").strip()
    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", q)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except Exception:
            pass

    m2 = re.search(
        r"\b(0?[1-9]|[12]\d|3[01])\s+"
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+"
        r"(20\d{2})\b",
        q,
        flags=re.IGNORECASE,
    )
    if m2:
        try:
            return datetime.strptime(f"{m2.group(1)} {m2.group(2)} {m2.group(3)}", "%d %b %Y").date()
        except Exception:
            try:
                return datetime.strptime(f"{m2.group(1)} {m2.group(2)} {m2.group(3)}", "%d %B %Y").date()
            except Exception:
                pass

    m3 = re.search(r"\b(20\d{2})\b", q)
    if m3:
        return date(int(m3.group(1)), 1, 1)
    return None


def _heuristic_domain(text: str) -> str:
    q = (text or "").lower()
    if any(k in q for k in ["hacked", "access", "platform", "online", "fraud", "scam", "cyber"]):
        return "it_act"
    if any(k in q for k in ["defect", "defective", "refund", "seller", "consumer", "hospital", "builder", "rera"]):
        return "consumer"
    if any(k in q for k in ["landlord", "tenant", "evict", "possession", "lease", "property"]):
        return "property"
    if any(k in q for k in ["fir", "arrest", "bail", "cheat", "theft", "forgery", "police", "criminal"]):
        return "criminal"
    if any(k in q for k in ["salary", "wages", "termination", "employee", "employer", "gratuity"]):
        return "labour"
    if any(k in q for k in ["contract", "agreement", "breach", "damages"]):
        return "contract"
    return "general"


def enforce_minimum_facts(query: str, facts: FactExtraction) -> FactExtraction:
    q = (query or "").lower()

    if not facts.cause_summary:
        facts.cause_summary = query.strip()

    return facts


def heuristic_extract_facts(query: str, today: date) -> FactExtraction:
    domain = _heuristic_domain(query)
    incident_date = _parse_date_from_query(query)
    financial_loss = _parse_amount_inr(query)
    
    return FactExtraction(
        incident_type_candidates=[IncidentCandidate(type=domain if domain != "it_act" else "online_fraud", confidence=0.5)],
        legal_domain=domain,
        cause_summary=query.strip(),
        timeline=Timeline(incident_date=incident_date.isoformat() if incident_date else None),
        loss=Loss(financial=financial_loss)
    )


def _build_prompt(user_query: str, today: date) -> str:
    schema_json = {
        "incident_type_candidates": [
            {"type": "account_hacking|online_fraud|identity_theft|data_breach|harassment|consumer_dispute|wage_dispute|... ", "confidence": 0.0-1.0}
        ],
        "entities": {
            "platform": ["string"],
            "financial_institution": ["string"],
            "person": ["string"],
            "device": ["string"]
        },
        "actions": ["string"],
        "loss": {
            "financial": "number|null",
            "access": "boolean|null",
            "reputation": "boolean|null"
        },
        "timeline": {
            "incident_date": "YYYY-MM-DD|null",
            "reported": "boolean"
        },
        "evidence": {
            "available": "boolean",
            "type": ["string"]
        },
        "legal_domain": "it_act|consumer|property|criminal|contract|labour|general",
        "cause_summary": "string"
    }
    return (
        "You are a professional legal fact extraction engine for Indian law intake, specializing in IT Act and General Civil/Criminal matters.\n"
        f"Today is {today.isoformat()} (YYYY-MM-DD).\n"
        "Return ONLY valid JSON matching the schema.\n\n"
        "Rules:\n"
        "1) Map types to: account_hacking, online_fraud, identity_theft, data_breach, harassment, consumer_dispute, wage_dispute, property_dispute, etc.\n"
        "2) entities: Identify specific platforms (Instagram, GPay, etc.), banks, or devices mentioned.\n"
        "3) actions: List the core actions described (e.g., 'unauthorized access', 'transferred money').\n"
        "4) loss: Be precise about financial loss (in INR), loss of access, and reputation damage.\n"
        "5) timeline: Extract the date if mentioned. Assume reported=false unless user says they filed a complaint/FIR.\n"
        "6) evidence: Set available=true if user mentions screenshots, recordings, or bank statements.\n"
        "7) Provide confidence scores for incident types.\n"
        "8) Never invent facts. Use null or empty lists when unknown.\n\n"
        f"Schema:\n{json.dumps(schema_json, ensure_ascii=False, indent=2)}\n\n"
        f"User text:\n{user_query}"
    )


def _derive_and_normalize(facts: FactExtraction, today: date) -> FactExtraction:
    # Minimal normalization for now
    return facts


def extract_facts(query: str, llm_model: str, llm_timeout_sec: int, today: Optional[date] = None) -> FactExtraction:
    today = today or date.today()
    prompt = _build_prompt(query, today=today)
    try:
        raw = call_llm(
model=llm_model, prompt=prompt, timeout_sec=llm_timeout_sec)
        parsed = _extract_json_object(raw)
        facts = FactExtraction(**parsed)
        facts = enforce_minimum_facts(query=query, facts=facts)
        return _derive_and_normalize(facts, today=today)
    except Exception:
        return heuristic_extract_facts(query=query, today=today)
