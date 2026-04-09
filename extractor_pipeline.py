import json
import re
from typing import Any, Dict, List, Optional
from datetime import date

from case_model import CaseModel, Party, Event, Financial, Document, MetaLayer
from llama_legal_answer import call_llm
from semantic_normalizer import SemanticNormalizer

# --- STEP 1: ENTITY RESOLUTION ---
def run_entity_resolution(text: str, model_name: str) -> List[Party]:
    prompt = (
        "TASK: Identify all parties involved in the legal narrative below.\n"
        "RULES:\n"
        "1. Assign the primary user/narrator as 'P1'.\n"
        "2. Assign other parties as 'P2', 'P3', etc.\n"
        "3. Replace all personal pronouns (he, she, they, my boss, my landlord) with their P# IDs.\n"
        "4. Assign roles: 'client' (always P1), 'opponent', 'witness', 'third-party', 'authority'.\n"
        "5. Return ONLY a JSON list of objects matching: "
        "{'id': 'P#', 'name': 'string|null', 'role': 'string', 'description': 'string', 'relationship_to_client': 'string'}\n\n"
        f"NARRATIVE: {text}"
    )
    res = call_llm(model_name=model_name, prompt=prompt, temperature=0.1)
    try:
        data = _extract_json(res)
        return [Party(**p) for p in data] if isinstance(data, list) else []
    except:
        return [Party(id="P1", role="client", description="The narrator")]

# --- STEP 2: EVENT EXTRACTION ---
def run_event_extraction(text: str, parties: List[Party], model_name: str) -> List[Event]:
    parties_summary = ", ".join([f"{p.id} ({p.description})" for p in parties])
    prompt = (
        "TASK: Break the narrative into a structured sequence of discrete events.\n"
        "PARTIES INVOLVED: " + parties_summary + "\n"
        "RULES:\n"
        "1. Use ONLY the Party IDs (P1, P2...) as actors and targets.\n"
        "2. Sequence must be chronological (1, 2, 3...).\n"
        "3. Focus on actions: what happened, not why it was illegal.\n"
        "4. Certainty: Use 'certain' if the user stated it, 'uncertain' if they seem unsure, 'alleged' if it's a claim against another party.\n"
        "5. Return ONLY a JSON list of objects matching: "
        "{'sequence': int, 'actor_id': 'P#', 'action': 'string', 'target_id': 'P#|null', 'timestamp': 'string|null', 'description': 'string', 'certainty': 'string'}\n\n"
        f"NARRATIVE: {text}"
    )
    res = call_llm(model_name=model_name, prompt=prompt, temperature=0.1)
    try:
        data = _extract_json(res)
        return [Event(**e) for e in data] if isinstance(data, list) else []
    except:
        return []

# --- STEP 3: ASSET EXTRACTION (Financials & Docs) ---
def run_asset_extraction(text: str, model_name: str) -> Dict[str, Any]:
    prompt = (
        "TASK: Extract all financial amounts and documents mentioned in the text.\n"
        "RULES:\n"
        "1. Extract money amounts in INR. If mentioned in Lakhs/Crores, convert to full numbers.\n"
        "2. Identify documents: agreements, receipts, screenshots, notices, emails.\n"
        "3. Status: 'exists' (user has it), 'missing' (user reference but lacks), 'mentioned' (general reference).\n"
        "4. Return ONLY a JSON object: "
        "{'financials': [{'amount': float, 'context': 'string', 'status': 'string'}], "
        "'documents': [{'type': 'string', 'description': 'string', 'status': 'string'}]}\n\n"
        f"NARRATIVE: {text}"
    )
    res = call_llm(model_name=model_name, prompt=prompt, temperature=0.1)
    try:
        return _extract_json(res)
    except:
        return {"financials": [], "documents": []}

# --- STEP 4: META LAYER (Intent, Claims, Gaps) ---
def run_meta_extraction(text: str, model_name: str) -> MetaLayer:
    prompt = (
        "TASK: Extract intents, claims, and uncertainties from the legal narrative.\n"
        "DEFINITIONS:\n"
        "- Intent: Promises, threats, or explicit goals stated by any party (e.g., 'he threatened to fire me').\n"
        "- Claim: Subjective grievances or legal assertions made by the user (e.g., 'it was unfair').\n"
        "- Uncertainty: Contradictions or vague points.\n"
        "RULES:\n"
        "1. Do NOT interpret the law. Just capture the claims as stated.\n"
        "2. Return ONLY a JSON object: "
        "{'intents': [string], 'claims': [string], 'uncertainties': [string]}\n\n"
        f"NARRATIVE: {text}"
    )
    res = call_llm(model_name=model_name, prompt=prompt, temperature=0.1)
    try:
        data = _extract_json(res)
        return MetaLayer(**data)
    except:
        return MetaLayer()

# --- STEP 5: GAP DETECTION ---
def run_gap_detection(case: CaseModel, model_name: str) -> List[Dict[str, str]]:
    # Use a prompt to look at the current CaseModel and see what's missing
    case_summary = json.dumps(case.dict(), indent=2)
    prompt = (
        "TASK: Identify critical gaps in the Case Model below that would prevent a legal assessment.\n"
        "CRITICAL FIELDS TO CHECK:\n"
        "1. Relationship between parties (if unknown).\n"
        "2. Specific dates for key events.\n"
        "3. Exact amounts for financial loss.\n"
        "4. Presence of core documents (e.g., if a lease mentioned, is the start date or agreement known?).\n"
        "RULES:\n"
        "1. Be concise.\n"
        "2. Return ONLY a JSON list of objects: [{'field': 'string', 'question': 'The follow-up question to ask the user'}]\n"
        "3. If no gaps, return [].\n\n"
        f"CASE MODEL: {case_summary}"
    )
    res = call_llm(model_name=model_name, prompt=prompt, temperature=0.1)
    try:
        return _extract_json(res)
    except:
        return []

# --- UTILS & PIPELINE ---

def _extract_json(text: str) -> Any:
    cleaned = text.strip()
    match = re.search(r'\[.*\]|\{.*\}', cleaned, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(cleaned)


def _coerce_amount(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    raw = str(value).strip().lower()
    if not raw or raw in {"none", "null", "na", "n/a", "unknown", "not specified"}:
        return None

    multiplier = 1.0
    if "crore" in raw:
        multiplier = 10_000_000.0
    elif "lakh" in raw or "lac" in raw:
        multiplier = 100_000.0

    normalized = (
        raw.replace(",", "")
        .replace("inr", "")
        .replace("rs.", "")
        .replace("rs", "")
        .replace("₹", "")
    )
    match = re.search(r"-?\d+(?:\.\d+)?", normalized)
    if not match:
        return None
    try:
        return float(match.group()) * multiplier
    except (TypeError, ValueError):
        return None


def _sanitize_financials(raw_financials: Any) -> List[Financial]:
    if not isinstance(raw_financials, list):
        return []

    clean_items: List[Financial] = []
    for item in raw_financials:
        if not isinstance(item, dict):
            continue
        amount = _coerce_amount(item.get("amount"))
        if amount is None:
            # Skip incomplete financial rows instead of crashing validation.
            continue
        context = str(item.get("context") or "unspecified financial claim").strip()
        status = str(item.get("status") or "disputed").strip() or "disputed"
        currency = str(item.get("currency") or "INR").strip() or "INR"
        try:
            clean_items.append(
                Financial(
                    amount=amount,
                    currency=currency,
                    context=context,
                    status=status,
                )
            )
        except Exception:
            continue
    return clean_items


def _sanitize_documents(raw_documents: Any) -> List[Document]:
    if not isinstance(raw_documents, list):
        return []

    clean_items: List[Document] = []
    for item in raw_documents:
        if not isinstance(item, dict):
            continue
        doc_type = str(item.get("type") or "document").strip() or "document"
        description = str(item.get("description") or "Document referenced in user narrative").strip()
        status = str(item.get("status") or "mentioned").strip() or "mentioned"
        try:
            clean_items.append(
                Document(
                    type=doc_type,
                    description=description,
                    status=status,
                )
            )
        except Exception:
            continue
    return clean_items

def validate_case_model(case: CaseModel) -> List[str]:
    vitals = []
    # CHECK 1: Legal terminology leakage
    illegal_words = ["fraud", "illegal", "cheating", "guilty", "criminal", "justice"]
    for event in case.events:
        if any(word in event.action.lower() for word in illegal_words):
            vitals.append(f"Regressed: Legal conclusion found in event {event.sequence}")
    
    if not case.events:
        vitals.append("Error: No events extracted from narrative")
    if not case.parties:
        vitals.append("Error: No parties resolved")
    
    return vitals

def run_case_extractor_pipeline(text: str, model_name: str) -> CaseModel:
    # 1. Resolve Parties
    parties = run_entity_resolution(text, model_name)
    
    # 2. Extract Events
    events = run_event_extraction(text, parties, model_name)
    
    # FALLBACK: If no events extracted, create a synthetic one to keep the pipeline alive
    if not events:
        events = [Event(
            sequence=1,
            actor_id="P1",
            action="Narrative summary",
            description=text[:500],
            certainty="certain"
        )]
    
    # NEW: Semantic Normalization (Bridge the gap)
    normalizer = SemanticNormalizer(model_name)
    events = normalizer.normalize_events(events)
    
    # 3. Extract Assets
    assets = run_asset_extraction(text, model_name)
    if not isinstance(assets, dict):
        assets = {"financials": [], "documents": []}
    financials = _sanitize_financials(assets.get("financials", []))
    documents = _sanitize_documents(assets.get("documents", []))
    
    # 4. Meta Layer
    meta = run_meta_extraction(text, model_name)
    
    # Construct Initial Model
    case = CaseModel(
        parties=parties,
        events=events,
        financials=financials,
        documents=documents,
        meta=meta
    )
    
    # 5. Gap Detection
    case.missing_information = run_gap_detection(case, model_name)
    
    # 6. Final Validation
    case.validation_vitals = validate_case_model(case)
    
    return case
