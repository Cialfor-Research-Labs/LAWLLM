import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from case_model import CaseModel, Event, Financial, Party

# --- Configuration & Logging ---
logger = logging.getLogger(__name__)

# --- Models for Phase 2: Behavioral & Interpretation Layers ---

class BehavioralPrimitive(BaseModel):
    name: str = Field(..., description="Objective marker, e.g., 'money_not_paid'")
    supporting_events: List[int] = Field(default_factory=list, description="Event sequence numbers")
    description: Optional[str] = None

class LegalInterpretation(BaseModel):
    label: str = Field(..., description="The legal meaning, e.g., 'non_payment'")
    description: str = Field(..., description="A short narrative of why this fits")
    confidence: float = Field(..., ge=0.0, le=1.0)
    supporting_behaviors: List[str] = Field(default_factory=list, description="List of behavioral primitive names")
    supporting_events: List[int] = Field(default_factory=list, description="List of event sequence numbers")

class LegalBrainResponse(BaseModel):
    behavioral_primitives: List[BehavioralPrimitive] = Field(default_factory=list)
    interpretations: List[LegalInterpretation] = Field(default_factory=list)

# --- 1. Behavioral Layer (Deterministic) ---

class BehavioralDetector:
    """Objective, fact-derived behavioral markers."""
    
    def detect(self, model: CaseModel) -> List[BehavioralPrimitive]:
        markers = {}

        # --- TAG BASED DETECTION (PRIORITY) ---
        for evt in model.events:
            for tag in evt.semantic_tags:
                self._add_marker(markers, tag, [evt.sequence])

        # --- FINANCIAL STATUS DETECTION (AUGMENTED) ---
        for fin in model.financials:
            if fin.status in ["disputed", "pending"]:
                # Check if we already have a tag from an event
                if any(evt.semantic_tags for evt in model.events):
                    continue # Use tags if present
                    
                if any(kw in fin.context.lower() for kw in ["return", "refund", "deposit", "gave", "loan", "borrowed", "funds", "arrears", "outstanding", "cheque", "dishonored"]):
                    self._add_marker(markers, "money_not_returned", [e.sequence for e in model.events])
                else:
                    self._add_marker(markers, "money_not_paid", [e.sequence for e in model.events])
            if fin.status == "partially_paid":
                self._add_marker(markers, "partial_payment", [e.sequence for e in model.events])

        # --- FALLBACK KEYWORD DETECTION (LEGACY/BACKUP) ---
        for evt in model.events:
            desc = evt.description.lower()
            if not evt.semantic_tags:
                if any(kw in desc for kw in ["harassed", "abuse", "threaten"]):
                    self._add_marker(markers, "harassment", [evt.sequence])
                if any(kw in desc for kw in ["failed", "didn't", "not deliver", "broken", "defective"]):
                   self._add_marker(markers, "service_not_delivered", [evt.sequence])
                if any(kw in desc for kw in ["locked", "evict", "thrown"]):
                   self._add_marker(markers, "forced_exit", [evt.sequence])

        return list(markers.values())

    def _add_marker(self, markers: Dict[str, BehavioralPrimitive], name: str, events: List[int]):
        if name in markers:
            markers[name].supporting_events = sorted(list(set(markers[name].supporting_events + events)))
        else:
            markers[name] = BehavioralPrimitive(name=name, supporting_events=events)

# --- 2. Interpretation Layer (Probabilistic) ---

class InterpretationMapper:
    """Maps behavioral markers to legal interpretations using evidence-driven rules."""
    
    def __init__(self, llm_fn=None):
        self.llm_fn = llm_fn

    def map_behaviors(self, model: CaseModel, behaviors: List[BehavioralPrimitive]) -> List[LegalInterpretation]:
        interpretations: Dict[str, LegalInterpretation] = {}
        behavior_names = {b.name for b in behaviors}
        
        # --- Helper for temporal sequence reasoning ---
        def get_first_seq(name: str) -> int:
            b_item = next((b for b in behaviors if b.name == name), None)
            return min(b_item.supporting_events) if b_item and b_item.supporting_events else 999

        # --- Deterministic Mapping Rules with Negative Constraints ---

        # 1. Non-Payment (Temporal influence)
        if "money_not_paid" in behavior_names or "money_not_returned" in behavior_names:
            conf = 0.8  # Base
            desc = "A monetary obligation remains unfulfilled."
            
            # Boost if a promise was made PRIOR to the failure (Broken Promise signal)
            promise_seq = get_first_seq("promise_made")
            fail_seq = min(get_first_seq("money_not_paid"), get_first_seq("money_not_returned"))
            
            if promise_seq < fail_seq:
                conf += 0.1
                desc += " A clear promise to pay was violated by the subsequent failure."
            
            if "refusal_to_pay" in behavior_names:
                conf += 0.05
                desc += " Explicit refusal to pay was detected."
            
            if "followup_ignored" in behavior_names:
                conf += 0.04
                desc += " The opponent has stopped responding to communications."

            self._add_interpretation(interpretations, LegalInterpretation(
                label="non_payment",
                description=desc,
                confidence=min(0.95, conf),
                supporting_behaviors=[b for b in behavior_names if b in ["money_not_paid", "money_not_returned", "promise_made", "refusal_to_pay", "followup_ignored"]],
                supporting_events=self._get_all_events(behaviors, ["money_not_paid", "money_not_returned", "promise_made", "refusal_to_pay", "followup_ignored"])
            ))

        # 2. Breach of Contract (Negative rule: requires agreement)
        if "agreement_signal_present" in behavior_names:
            if "money_not_paid" in behavior_names or "service_not_delivered" in behavior_names or "refusal_to_pay" in behavior_names:
                self._add_interpretation(interpretations, LegalInterpretation(
                    label="breach_of_contract",
                    description="Observable violation of an agreement or contractual obligation.",
                    confidence=0.85,
                    supporting_behaviors=["agreement_signal_present", "money_not_paid", "refusal_to_pay"],
                    supporting_events=self._get_all_events(behaviors, ["agreement_signal_present", "money_not_paid", "refusal_to_pay"])
                ))
        
        # 1.5. Employment Termination
        if "employment_ended" in behavior_names:
            self._add_interpretation(interpretations, LegalInterpretation(
                label="employment_ended",
                description="Observable end of employment relationship.",
                confidence=0.9,
                supporting_behaviors=["employment_ended"],
                supporting_events=self._get_all_events(behaviors, ["employment_ended"])
            ))
            
        # 1.6 Consumer Deficiency
        if "service_not_delivered" in behavior_names or "service_failed" in behavior_names:
            self._add_interpretation(interpretations, LegalInterpretation(
                label="service_not_delivered",
                description="Failure to provide product or service as agreed.",
                confidence=0.9,
                supporting_behaviors=[b for b in behavior_names if b in ["service_not_delivered", "service_failed"]],
                supporting_events=self._get_all_events(behaviors, ["service_not_delivered", "service_failed"])
            ))

        # 1.7 Product Defect / Wrong Product
        if "product_defective" in behavior_names:
            self._add_interpretation(interpretations, LegalInterpretation(
                label="product_defective",
                description="Product is defective, wrong, or misrepresented.",
                confidence=0.9,
                supporting_behaviors=["product_defective"],
                supporting_events=self._get_all_events(behaviors, ["product_defective"])
            ))

        # 1.8 Cheque Bounce
        if "cheque_bounce" in behavior_names:
            self._add_interpretation(interpretations, LegalInterpretation(
                label="cheque_bounce",
                description="A cheque was dishonoured or bounced due to insufficient funds.",
                confidence=0.95,
                supporting_behaviors=["cheque_bounce"],
                supporting_events=self._get_all_events(behaviors, ["cheque_bounce"])
            ))

        # 1.9 Illegal/Unauthorized Charge
        if "illegal_charge" in behavior_names:
            self._add_interpretation(interpretations, LegalInterpretation(
                label="illegal_charge",
                description="Unauthorized or illegal financial charges or deductions.",
                confidence=0.9,
                supporting_behaviors=["illegal_charge"],
                supporting_events=self._get_all_events(behaviors, ["illegal_charge"])
            ))

        # 3. Illegal Dispossession (Suppress if no possession marker)
        if "possession_removed" in behavior_names or "forced_exit" in behavior_names:
             self._add_interpretation(interpretations, LegalInterpretation(
                label="illegal_dispossession",
                description="Facts support an allegation of unlawful removal from a property.",
                confidence=0.9,
                supporting_behaviors=[b for b in behavior_names if b in ["possession_removed", "forced_exit"]],
                supporting_events=self._get_all_events(behaviors, ["possession_removed", "forced_exit"])
            ))

        # 4. Fraud (Critical: No promise-only fraud, negative rules)
        # Suppress if no false statement or clear deception signal exists
        deception_signals = {"false_statement_made", "identity_misrepresented", "fraud_signal"}
        if any(sig in behavior_names for sig in deception_signals):
            if "money_not_returned" in behavior_names or "money_not_paid" in behavior_names:
                 self._add_interpretation(interpretations, LegalInterpretation(
                    label="fraud_like_behavior",
                    description="Deception (false statement) coupled with financial loss supports potential fraud.",
                    confidence=0.8,
                    supporting_behaviors=[b for b in behavior_names if b in (list(deception_signals) + ["money_not_returned"])],
                    supporting_events=self._get_all_events(behaviors, list(deception_signals) + ["money_not_returned"])
                ))
        else:
            # Broken promise alone is NOT fraud. Base confidence is near zero or suppressed.
            pass

        # 5. Unauthorized Access
        if "unauthorized_access" in behavior_names or "account_compromised" in behavior_names:
            self._add_interpretation(interpretations, LegalInterpretation(
                label="unauthorized_access",
                description="Observable patterns of unauthorized digital entry or account compromise.",
                confidence=0.9,
                supporting_behaviors=[b for b in behavior_names if b in ["unauthorized_access", "account_compromised"]],
                supporting_events=self._get_all_events(behaviors, ["unauthorized_access", "account_compromised"])
            ))

        if "possession_delayed" in behavior_names:
            self._add_interpretation(interpretations, LegalInterpretation(
                label="real_estate_delay", 
                description="Delayed possession of real estate property.", confidence=0.9, 
                supporting_behaviors=["possession_delayed"], 
                supporting_events=self._get_all_events(behaviors, ["possession_delayed"])
            ))
        
        if "overtime_work" in behavior_names:
             self._add_interpretation(interpretations, LegalInterpretation(
                label="overtime_dispute", 
                description="Claims of unpaid overtime work.", confidence=0.9, 
                supporting_behaviors=["overtime_work"], 
                supporting_events=self._get_all_events(behaviors, ["overtime_work"])
            ))

        if "maternity_leave_request" in behavior_names:
             self._add_interpretation(interpretations, LegalInterpretation(
                label="maternity_benefit", 
                description="Rights related to maternity leave benefits.", confidence=0.9, 
                supporting_behaviors=["maternity_leave_request"], 
                supporting_events=self._get_all_events(behaviors, ["maternity_leave_request"])
            ))

        if "pf_dispute" in behavior_names or "pf_not_contributed" in behavior_names:
             self._add_interpretation(interpretations, LegalInterpretation(
                label="pf_dispute", 
                description="Failure to contribute to mandatory Provident Fund accounts or discrepancies in PF records.", confidence=1.0, 
                supporting_behaviors=[b for b in behavior_names if b in ["pf_dispute", "pf_not_contributed"]], 
                supporting_events=self._get_all_events(behaviors, ["pf_dispute", "pf_not_contributed"])
            ))

        if "gratuity_dispute" in behavior_names:
             self._add_interpretation(interpretations, LegalInterpretation(
                label="gratuity_dispute", 
                description="Dispute over non-payment or calculation of statutory gratuity benefits.", confidence=1.0, 
                supporting_behaviors=["gratuity_dispute"], 
                supporting_events=self._get_all_events(behaviors, ["gratuity_dispute"])
            ))

        if "bonus_not_paid" in behavior_names:
             self._add_interpretation(interpretations, LegalInterpretation(
                label="bonus_dispute", 
                description="Dispute over non-payment of statutory or contractual bonus.", confidence=0.9, 
                supporting_behaviors=["bonus_not_paid"], 
                supporting_events=self._get_all_events(behaviors, ["bonus_not_paid"])
            ))

        if "injury_at_work" in behavior_names:
             self._add_interpretation(interpretations, LegalInterpretation(
                label="workplace_injury", 
                description="Injury or accident occurring during employment duties.", confidence=0.9, 
                supporting_behaviors=["injury_at_work"], 
                supporting_events=self._get_all_events(behaviors, ["injury_at_work"])
            ))

        if "under_payment" in behavior_names:
             self._add_interpretation(interpretations, LegalInterpretation(
                label="minimum_wage_dispute", 
                description="Payment of wages below the statutory minimum or agreed rate.", confidence=0.9, 
                supporting_behaviors=["under_payment"], 
                supporting_events=self._get_all_events(behaviors, ["under_payment"])
            ))

        # --- LLM Candidate Generation (No Confidence Boost) ---
        if self.llm_fn:
            llm_results = self._call_llm_mapper(model, behaviors)
            for hit in llm_results:
                if hit.label in interpretations:
                    # Merge ONLY the description/AI reasoning. Do NOT update confidence.
                    existing = interpretations[hit.label]
                    existing.description += f" | AI Context: {hit.description}"
                else:
                    # New interpretation from LLM. Must pass a sanity check? 
                    # If it's a new interpretation from LLM, we keep its suggested confidence 
                    # but maybe cap it low if no direct behavioral mapping exists.
                    if any(b in hit.supporting_behaviors for b in behavior_names):
                         interpretations[hit.label] = hit
                    else:
                         # Suppress LLM hallucinations not backed by our markers
                         hit.confidence = min(0.3, hit.confidence)
                         interpretations[hit.label] = hit

        if "harassment" in behavior_names or "threat_made" in behavior_names:
             self._add_interpretation(interpretations, LegalInterpretation(
                label="sexual_harassment", 
                description="Allegations of workplace harassment or inappropriate conduct.", confidence=0.9, 
                supporting_behaviors=[b for b in behavior_names if b in ["harassment", "threat_made"]], 
                supporting_events=self._get_all_events(behaviors, ["harassment", "threat_made"])
            ))

        # Handled above
        pass

        if "unauthorized_access" in behavior_names:
             self._add_interpretation(interpretations, LegalInterpretation(
                label="cyber_crime", 
                description="Unauthorized digital access or computer related offenses.", confidence=0.9, 
                supporting_behaviors=["unauthorized_access"], 
                supporting_events=self._get_all_events(behaviors, ["unauthorized_access"])
            ))

        if "breach_of_privacy_signal" in behavior_names:
             self._add_interpretation(interpretations, LegalInterpretation(
                label="privacy_breach", 
                description="Violation of individual privacy through digital or physical means.", confidence=0.95, 
                supporting_behaviors=["breach_of_privacy_signal"], 
                supporting_events=self._get_all_events(behaviors, ["breach_of_privacy_signal"])
            ))

        if "service_not_delivered" in behavior_names and any(kw in model.domain for kw in ["financial", "insurance"] if model.domain):
             self._add_interpretation(interpretations, LegalInterpretation(
                label="insurance_dispute", 
                description="Deficiency in insurance services or claim settlements.", confidence=0.9, 
                supporting_behaviors=["service_not_delivered"], 
                supporting_events=self._get_all_events(behaviors, ["service_not_delivered"])
            ))

        if "threat_made" in behavior_names and model.domain == "financial":
             self._add_interpretation(interpretations, LegalInterpretation(
                label="recovery_harassment", 
                description="Illegal harassment or threats by recovery agents.", confidence=0.9, 
                supporting_behaviors=["threat_made"], 
                supporting_events=self._get_all_events(behaviors, ["threat_made"])
            ))

        if "unauthorized_access" in behavior_names and model.domain == "financial":
             self._add_interpretation(interpretations, LegalInterpretation(
                label="unauthorized_trade", 
                description="Unauthorized transactions or trades in financial accounts.", confidence=0.9, 
                supporting_behaviors=["unauthorized_access"], 
                supporting_events=self._get_all_events(behaviors, ["unauthorized_access"])
            ))
        
        return list(interpretations.values())

    def _add_interpretation(self, interpretations: Dict[str, LegalInterpretation], item: LegalInterpretation):
        interpretations[item.label] = item

    def _get_all_events(self, behaviors: List[BehavioralPrimitive], names: List[str]) -> List[int]:
        evts = []
        for b in behaviors:
            if b.name in names:
                evts.extend(b.supporting_events)
        return sorted(list(set(evts)))

    def _call_llm_mapper(self, model: CaseModel, behaviors: List[BehavioralPrimitive]) -> List[LegalInterpretation]:
        prompt = f"""
Identify potential legal interpretations based on these OBSERVABLE BEHAVIORS:
BEHAVIORS DETECTED: {", ".join([b.name for b in behaviors])}

CASE CONTEXT:
{model.model_dump_json(indent=2)}

GUIDELINES:
- Identify 3-5 legal interpretations.
- Do NOT conclude specific statutory sections.
- For each interpretation, list the supporting behaviors and events.
- If multiple interpretations are possible, return both with appropriate confidence scores.
- Ambiguity is preferred over direct classification.
- NOTE: A broken promise alone is NOT fraud. Fraud requires misrepresentation or deception.

FORMAT:
{{
  "interpretations": [
    {{
      "label": "string",
      "description": "string",
      "confidence": float,
      "supporting_behaviors": ["string"],
      "supporting_events": [int]
    }}
  ]
}}
"""
        try:
            raw = self.llm_fn(prompt)
            data = json.loads(raw)
            return [LegalInterpretation(**item) for item in data.get("interpretations", [])]
        except Exception as e:
            logger.error(f"LLM Interpretation Mapping failed: {e}")
            return []

# --- 3. Legal Brain (Orchestration) ---

class LegalBrain:
    """Orchestrates the fact -> behavior -> interpretation pipeline."""
    
    def __init__(self, llm_fn=None):
        self.behavioral_layer = BehavioralDetector()
        self.interpretation_layer = InterpretationMapper(llm_fn)

    def detect_primitives(self, model: CaseModel) -> LegalBrainResponse:
        # Pass 1: Detective Behaviors (Objective)
        behaviors = self.behavioral_layer.detect(model)
        
        # Pass 2: Map to Legal Interpretations (Probabilistic)
        interpretations = self.interpretation_layer.map_behaviors(model, behaviors)
        
        return LegalBrainResponse(
            behavioral_primitives=behaviors,
            interpretations=interpretations
        )
