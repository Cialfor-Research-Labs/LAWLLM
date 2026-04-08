import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from case_model import CaseModel
from legal_primitives import LegalBrainResponse, LegalInterpretation, BehavioralPrimitive

# --- Configuration & Logging ---
logger = logging.getLogger(__name__)

# --- Phase 4 Models (Ranked & Scored) ---

class ApplicableLaw(BaseModel):
    law: str = Field(..., description="Act name")
    section: str = Field(..., description="Specific section")
    final_score: float = Field(..., ge=0.0, le=1.0)
    rank: int = Field(default=0)
    confidence_level: str = Field(default="low", description="high, medium, low")
    based_on_interpretations: List[str] = Field(default_factory=list)
    based_on_behaviors: List[str] = Field(default_factory=list)
    has_confirmed_signal: bool = False
    reasoning: str = Field(..., description="Explain the scoring factors clearly")

class UncertaintyResponse(BaseModel):
    is_uncertain: bool = False
    top_tags: List[str] = Field(default_factory=list)
    confidence: List[float] = Field(default_factory=list)
    missing_signals: List[str] = Field(default_factory=list)

class LawEngineResponse(BaseModel):
    applicable_laws: List[ApplicableLaw] = Field(default_factory=list)
    uncertainty: Optional[UncertaintyResponse] = None

# --- The Mapping Registry (Layer 1) ---

LAW_REGISTRY = {
    "non_payment": [
        {
            "act": "Indian Contract Act, 1872", "section": "Sec 73", 
            "domain": "general", "relationship": "any", 
            "base_score": 0.9, "required_behaviors": ["money_not_paid"]
        },
        {
            "act": "Payment of Wages Act, 1936", "section": "Sec 3", 
            "domain": "employment", "relationship": "employer-employee", 
            "base_score": 0.99, "required_behaviors": ["money_not_paid"]
        },
        {
            "act": "Industrial Disputes Act, 1947", "section": "Sec 33C", 
            "domain": "employment", "relationship": "employer-employee", 
            "base_score": 0.95, "required_behaviors": ["money_not_paid"]
        }
    ],
    "breach_of_contract": [
        {
            "act": "Indian Contract Act, 1872", "section": "Sec 37", 
            "domain": "civil", "relationship": "any", 
            "base_score": 0.9, "required_behaviors": ["agreement_signal_present"]
        },
        {
            "act": "Specific Relief Act, 1963", "section": "Sec 10", 
            "domain": "civil", "relationship": "any", 
            "base_score": 0.8, "required_behaviors": ["agreement_signal_present"]
        }
    ],
    "unauthorized_access": [
        {
            "act": "Information Technology Act, 2000", "section": "Sec 43", 
            "domain": "cyber", "relationship": "any", 
            "base_score": 0.95, "required_behaviors": ["unauthorized_access"]
        },
        {
            "act": "Information Technology Act, 2000", "section": "Sec 66", 
            "domain": "cyber", "relationship": "any", 
            "base_score": 0.9, "required_behaviors": ["unauthorized_access", "account_compromised"]
        }
    ],
    "employment_ended": [
        {
            "act": "Industrial Disputes Act, 1947", "section": "Sec 2A", 
            "domain": "employment", "relationship": "employer-employee", 
            "base_score": 0.95, "required_behaviors": ["employment_ended"]
        }
    ],
    "money_not_returned": [
        {
            "act": "Negotiable Instruments Act, 1881", "section": "Sec 138", 
            "domain": "financial", "relationship": "any", 
            "base_score": 0.95, "required_behaviors": ["money_not_returned"]
        }
    ],
    "gratuity_dispute": [
        {
            "act": "Payment of Gratuity Act, 1972", "section": "Sec 4", 
            "domain": "employment", "relationship": "employer-employee", 
            "base_score": 0.98, "required_behaviors": ["gratuity_dispute"]
        }
    ],
    "pf_dispute": [
        {
            "act": "Employees' Provident Funds and Miscellaneous Provisions Act, 1952", "section": "Sec 6", 
            "domain": "employment", "relationship": "employer-employee", 
            "base_score": 0.99, "required_behaviors": ["pf_dispute"]
        }
    ],
    "sexual_harassment": [
        {
            "act": "Sexual Harassment of Women at Workplace Act, 2013", "section": "Sec 9", 
            "domain": "employment", "relationship": "employer-employee", 
            "base_score": 0.98, "required_behaviors": ["harassment"]
        },
        {
            "act": "Sexual Harassment of Women at Workplace Act, 2013", "section": "Sec 9", 
            "domain": "employment", "relationship": "employer-employee", 
            "base_score": 0.95, "required_behaviors": ["threat_made"]
        }
    ],
    "service_not_delivered": [
        {
            "act": "Consumer Protection Act, 2019", "section": "Sec 2(11)", 
            "domain": "consumer", "relationship": "any", 
            "base_score": 0.98, "required_behaviors": ["service_not_delivered"]
        }
    ],
    "cheque_bounce": [
        {
            "act": "Negotiable Instruments Act, 1881", "section": "Sec 138", 
            "domain": "financial", "relationship": "any", 
            "base_score": 0.99, "required_behaviors": ["cheque_bounce"]
        }
    ],
    "product_defective": [
        {
            "act": "Consumer Protection Act, 2019", "section": "Sec 2(10)", 
            "domain": "consumer", "relationship": "any", 
            "base_score": 0.98, "required_behaviors": ["product_defective"]
        }
    ],
    "illegal_dispossession": [
        {
            "act": "Specific Relief Act, 1963", "section": "Sec 6", 
            "domain": "property", "relationship": "any", 
            "base_score": 0.98, "required_behaviors": ["possession_removed", "forced_exit"]
        },
        {
            "act": "Transfer of Property Act, 1882", "section": "Sec 105", 
            "domain": "property", "relationship": "landlord-tenant", 
            "base_score": 0.8, "required_behaviors": ["possession_removed"]
        }
    ],
    "illegal_charge": [
        {
            "act": "Consumer Protection Act, 2019", "section": "Sec 2(47)", 
            "domain": "consumer", "relationship": "any", 
            "base_score": 0.95, "required_behaviors": ["fraud_signal"]
        }
    ],
    "data_privacy_threat": [
        {
            "act": "Information Technology Act, 2000", "section": "Sec 66E", 
             "domain": "cyber", "relationship": "any", 
             "base_score": 0.98, "required_behaviors": ["data_privacy_threat"]
        }
    ],
    "overtime_dispute": [
        {
            "act": "Factories Act, 1948", "section": "Sec 59", 
            "domain": "employment", "relationship": "employer-employee", 
            "base_score": 0.95, "required_behaviors": ["overtime_work"]
        }
    ],
    "maternity_benefit": [
        {
            "act": "Maternity Benefit Act, 1961", "section": "Sec 5", 
            "domain": "employment", "relationship": "employer-employee", 
            "base_score": 0.98, "required_behaviors": ["maternity_leave_request"]
        }
    ],
    "provident_fund": [], # Handled by pf_dispute above
    "bonus_dispute": [
        {
            "act": "Payment of Bonus Act, 1965", "section": "Sec 8", 
            "domain": "employment", "relationship": "employer-employee", 
            "base_score": 0.9, "required_behaviors": ["bonus_not_paid"]
        }
    ],
    "workplace_injury": [
        {
            "act": "Employees' Compensation Act, 1923", "section": "Sec 3", 
            "domain": "employment", "relationship": "employer-employee", 
            "base_score": 0.98, "required_behaviors": ["injury_at_work"]
        }
    ],
    "real_estate_delay": [
        {
            "act": "RERA, 2016", "section": "Sec 18", 
            "domain": "property", "relationship": "any", 
            "base_score": 0.98, "required_behaviors": ["possession_delayed"]
        }
    ],
    "minimum_wage_dispute": [
        {
            "act": "Minimum Wages Act, 1948", "section": "Sec 12", 
            "domain": "employment", "relationship": "employer-employee", 
            "base_score": 0.95, "required_behaviors": ["under_payment"]
        }
    ],
    "fraud_like_behavior": [
        {
            "act": "Bharatiya Nyaya Sanhita, 2023", "section": "Sec 318", 
            "domain": "criminal", "relationship": "any", 
            "base_score": 0.9, "required_behaviors": ["fraud_signal", "money_not_returned"],
            "requires_deception": True
        },
        {
            "act": "Information Technology Act, 2000", "section": "Sec 66D", 
            "domain": "cyber", "relationship": "any", 
            "base_score": 0.98, "required_behaviors": ["fraud_signal", "money_not_paid"]
        }
    ],
    "privacy_breach": [
        {
            "act": "Information Technology Act, 2000", "section": "Sec 66E", 
             "domain": "cyber", "relationship": "any", 
             "base_score": 0.98, "required_behaviors": ["data_privacy_threat"]
        }
    ],
    "cyber_crime": [
        {
            "act": "Information Technology Act, 2000", "section": "Sec 43", 
            "domain": "cyber", "relationship": "any", 
            "base_score": 0.95, "required_behaviors": ["unauthorized_access"]
        },
        {
             "act": "Information Technology Act, 2000", "section": "Sec 43A", 
             "domain": "cyber", "relationship": "any", 
             "base_score": 0.98, "required_behaviors": ["account_compromised"]
        }
    ],
    "insurance_dispute": [
        {
            "act": "Consumer Protection Act, 2019", "section": "Sec 2(11)", 
            "domain": "consumer", "relationship": "any", 
            "base_score": 0.95, "required_behaviors": ["service_not_delivered"]
        }
    ],
    "recovery_harassment": [
        {
            "act": "Bharatiya Nyaya Sanhita, 2023", "section": "Sec 308", 
             "domain": "criminal", "relationship": "any", 
             "base_score": 0.9, "required_behaviors": ["harassment"]
        }
    ],
    "unauthorized_trade": [
        {
            "act": "Consumer Protection Act, 2019", "section": "Sec 2(47)", 
            "domain": "consumer", "relationship": "any", 
            "base_score": 0.95, "required_behaviors": ["money_not_paid", "unauthorized_access"]
        }
    ]
}

# --- The Ranking Engine Logic ---

class LawEngine:
    """Orchestrates Law ranking, filtering, and scoring (Phase 4)."""

    def __init__(self, llm_fn=None):
        self.llm_fn = llm_fn

    def map_laws(
        self,
        model: CaseModel,
        brain_output: LegalBrainResponse,
        confirmed_tags: Optional[List[str]] = None,
        confirmed_tag_confidence: Optional[Dict[str, float]] = None,
        contradiction_penalty: float = 1.0,
    ) -> LawEngineResponse:
        results = []
        is_modern_regime = self._is_post_bns(model)
        confirmed_tag_confidence = confirmed_tag_confidence or {}
        
        # 1. Component Extraction
        detected_behaviors = [b.name for b in brain_output.behavioral_primitives if b.name]
        if confirmed_tags:
            detected_behaviors = list(set(detected_behaviors + confirmed_tags))
        detected_behaviors = [b for b in detected_behaviors if b] # Double check for None/empty
        
        # Merge interpretations from brain and confirmed tags
        active_interpretations = list(brain_output.interpretations)
        if confirmed_tags:
            for ct in confirmed_tags:
                # Add a synthetic interpretation if not already present
                if not any(i.label == ct for i in active_interpretations):
                    active_interpretations.append(
                        LegalInterpretation(label=ct, confidence=1.0, description=f"User confirmed: {ct}")
                    )

        for interp in active_interpretations:
            if interp.label not in LAW_REGISTRY: continue
            
            for entry in LAW_REGISTRY[interp.label]:
                # A. Temporal Regime Filter
                if entry.get("legacy") and is_modern_regime: continue
                if not entry.get("legacy") and "Bharatiya" in entry["act"] and not is_modern_regime: continue
                if not entry.get("legacy") and "Indian Penal" in entry["act"] and is_modern_regime: continue

                # B. Calculate Factors
                base_score = entry["base_score"]
                interp_conf = interp.confidence
                behavior_score = self._calculate_behavior_match_score(detected_behaviors, entry["required_behaviors"])
                context_score = self._calculate_context_match_score(model, entry, brain_output)
                sanity_factor = self._calculate_legal_sanity_factor(model, entry, brain_output)
                
                # C. Final Formula
                spec_weight = self._calculate_specialization_weight(entry, results)
                
                # PHASE 6.5: User confirmation weighting (2.0 * user_confidence)
                confirmation_boost = 1.0
                matched_confirmed_tags = []
                if confirmed_tags:
                    matched_confirmed_tags = [ct for ct in confirmed_tags if ct in entry["required_behaviors"]]
                if matched_confirmed_tags:
                    best_user_confidence = max(confirmed_tag_confidence.get(ct, 1.0) for ct in matched_confirmed_tags)
                    confirmation_boost = max(0.2, 2.0 * best_user_confidence)
                
                final_score = min(
                    1.0,
                    base_score
                    * interp_conf
                    * behavior_score
                    * context_score
                    * sanity_factor
                    * spec_weight
                    * confirmation_boost
                    * contradiction_penalty
                )
                
                if final_score >= 0.4:
                    res = ApplicableLaw(
                        law=entry["act"],
                        section=entry["section"],
                        final_score=round(final_score, 3),
                        confidence_level=self._get_conf_level(final_score),
                        based_on_interpretations=[interp.label],
                        has_confirmed_signal=(confirmation_boost > 1.0),
                        based_on_behaviors=list(set(detected_behaviors) & set(entry["required_behaviors"])),
                        reasoning=self._generate_reasoning_trace(
                            base_score, interp_conf, behavior_score, context_score, sanity_factor, entry, model
                        )
                    )
                    results.append(res)

        # 2. Thresholding & Deduction
        final_list = self._rank_and_filter(results)
        
        # 3. TASK 1: Uncertainty Detection
        uncertainty = self._analyze_uncertainty(final_list, detected_behaviors)
        
        return LawEngineResponse(applicable_laws=final_list, uncertainty=uncertainty)

    def _analyze_uncertainty(self, results: List[ApplicableLaw], behaviors: List[str]) -> UncertaintyResponse:
        if not results:
            return UncertaintyResponse(is_uncertain=True, missing_signals=["legal_context"])
            
        top_1 = results[0].final_score
        is_uncertain = False
        
        # Rule 1: Low Confidence (< 0.7)
        if top_1 < 0.7:
            is_uncertain = True
            
        # Rule 2: Close Competition (Gap < 0.15 between Top-1 and Top-2)
        if len(results) > 1:
            gap = top_1 - results[1].final_score
            if gap < 0.15:
                is_uncertain = True
                
        if not is_uncertain:
            return UncertaintyResponse(is_uncertain=False)
            
        # Extract signal requirements (Task 2)
        from signal_registry import get_signals_for_tag
        missing_signals = []
        for b in behaviors:
            signals = get_signals_for_tag(b)
            for s in signals:
                if s.signal_name not in missing_signals:
                    missing_signals.append(s.signal_name)
                    
        return UncertaintyResponse(
            is_uncertain=True,
            top_tags=behaviors[:3],
            confidence=[r.final_score for r in results[:3]],
            missing_signals=missing_signals[:2] # Max 1-2 signals per Task 3
        )

    def _calculate_behavior_match_score(self, detected: List[str], required: List[str]) -> float:
        if not required: return 1.0
        
        # --- ALIASING (Normalize tags for matching) ---
        ALIASES = {
            "money_not_returned": ["money_not_paid", "money_not_returned", "partial_payment"],
            "money_not_paid": ["money_not_paid", "money_not_returned", "partial_payment"],
            "cheque_bounce": ["cheque_bounce", "money_not_returned"],
            "service_not_delivered": ["service_not_delivered", "service_failed", "product_defective"],
            "product_defective": ["product_defective", "service_failed"]
        }
        
        # Map detected tags to their alias groups
        detected_normalized = set()
        for d in detected:
            detected_normalized.add(d)
            for canonical, group in ALIASES.items():
                if d in group:
                    detected_normalized.add(canonical)
        
        matches = len(detected_normalized & set(required))
        total = len(required)
        
        if matches == total: return 1.0
        if matches > 0: return 0.8
        return 0.0

    def _calculate_context_match_score(self, model: CaseModel, entry: Dict, brain: LegalBrainResponse) -> float:
        score = 0.6 # Neutral base
        
        # 1. Domain Match/Penalty
        is_domain_match = entry["domain"] == model.domain
        is_general_act = entry["domain"] == "general"
        
        # Check if any specialized domain act is already triggered
        has_domain_act = any(l["domain"] == model.domain for l in LAW_REGISTRY.get("non_payment", [])) # Heuristic
        
        if is_domain_match:
            score = 1.0
            score *= 1.5 # Substantial Domain Bonus
        elif is_general_act:
            score = 0.8
            # Only penalize if the case has a specific domain and it's not a generic dispute
            if model.domain and model.domain != "general":
                score *= 0.5 # Generic Statute Penalty
        elif model.domain is not None and model.domain != "general":
            score = 0.4 # Less aggressive mismatch penalty
        else:
            score = 1.0 # Neutral if no domain known
                
        # 2. Relationship match
        rel_factor = 1.0
        if entry["relationship"] != "any":
            if model.detected_relationship == entry["relationship"]:
                rel_factor = 1.0
            elif model.detected_relationship is not None:
                rel_factor = 0.3
            else:
                rel_factor = 0.8
                
        return score * rel_factor

    def _calculate_specialization_weight(self, entry: Dict, current_results: List[ApplicableLaw]) -> float:
        """Boosts domain-specific acts and penalizes general acts ONLY IF specific ones exist."""
        SPECIALIZED_ACTS = [
            "Payment of Wages Act", "Payment of Gratuity Act", "Industrial Disputes Act",
            "Maternity Benefit Act", "Factories Act", "Minimum Wages Act", "POSH Act",
            "RERA", "Negotiable Instruments Act", "Consumer Protection Act", "IT Act",
            "Information Technology Act", "Sexual Harassment of Women"
        ]
        GENERAL_ACTS = ["Indian Contract Act", "Specific Relief Act", "Transfer of Property Act"]
        
        act_name = entry["act"]
        
        # 1. Specialized Act Boost (Absolute)
        if any(spec in act_name for spec in SPECIALIZED_ACTS):
            return 1.8
            
        # 2. General Act Penalty (Conditional on finding a specialized act first)
        if any(gen in act_name for gen in GENERAL_ACTS):
            # Check if any specialized act is present in current_results with a decent score
            has_specialized_candidate = any(
                any(spec in res.law for spec in SPECIALIZED_ACTS) and res.final_score > 0.4
                for res in current_results
            )
            if has_specialized_candidate:
                return 0.4 
            
        return 1.0

    def _calculate_legal_sanity_factor(self, model: CaseModel, entry: Dict, brain: LegalBrainResponse) -> float:
        # Prevent over-criminalization
        is_criminal = entry["domain"] == "criminal" or "BNS" in entry["act"] or "IPC" in entry["act"]
        has_deception = any(b.name in ["false_statement_made", "identity_misrepresented"] for b in brain.behavioral_primitives)
        
        if is_criminal:
            if not has_deception:
                return 0.5 # Penalize criminal law for civil debt
            else:
                return 1.0 # Allow if deception exists
                
        # Weak evidence penalty
        if len(model.events) < 2:
            return 0.6
            
        return 1.0

    def _get_conf_level(self, score: float) -> str:
        if score >= 0.75: return "high"
        if score >= 0.5: return "medium"
        return "low"

    def _rank_and_filter(self, results: List[ApplicableLaw]) -> List[ApplicableLaw]:
        # 1. Sort by confirmation, then score, then by registrar's base_score to break ties
        results.sort(key=lambda x: (not x.has_confirmed_signal, -x.final_score, -self._get_base_score_for_act(x.law)), reverse=False)
        
        # 2. Limit to top 4
        ranked = results[:4]
        
        # 3. Assign rank numbers
        for i, res in enumerate(ranked):
            res.rank = i + 1
            
        return ranked

    def _get_base_score_for_act(self, act: str) -> float:
        """Helper to fetch base_score for tie-breaking."""
        for entries in LAW_REGISTRY.values():
            for entry in entries:
                if entry["act"] == act:
                    return entry.get("base_score", 0.0)
        return 0.0

    def _generate_reasoning_trace(self, base, interp, beh, ctx, sanity, entry, model) -> str:
        factors = []
        if beh == 1.0: factors.append("Full behavioral evidence")
        elif beh > 0: factors.append("Partial behavioral evidence")
        
        if ctx > 0.8: factors.append(f"Strong context match ({model.domain or 'general'})")
        
        if sanity < 1.0:
            if entry["domain"] == "criminal": factors.append("Criminal law reduced due to lack of strong deception markers")
            else: factors.append("Score adjusted for evidence density")
            
        return f"Ranked based on: {', '.join(factors)}. Formula trace: Base({base}) x Interp({interp}) x Evidence({beh}) x Context({round(ctx, 2)}) x Sanity({sanity})."

    def _is_post_bns(self, model: CaseModel) -> bool:
        transition_date = datetime(2024, 7, 1)
        for evt in model.events:
            if evt.timestamp:
                try:
                    evt_dt = datetime.fromisoformat(evt.timestamp.split('T')[0])
                    if evt_dt < transition_date: return False
                except: pass
        return True 
