from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# --- 3.1 UserMessage ---
class UserMessage(BaseModel):
    conversation_id: str
    message_id: str
    text: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# --- 3.2 ExpandedIntent ---
class Parties(BaseModel):
    user_role: Optional[str] = None # consumer|employee|tenant|other
    opposite_party_type: Optional[str] = None # seller|employer|landlord|manufacturer|other
    opposite_party_name: Optional[str] = None

class Timeline(BaseModel):
    incident_date: Optional[str] = None # YYYY-MM-DD
    complaint_date: Optional[str] = None

class Money(BaseModel):
    claim_amount_inr: Optional[float] = None
    price_paid_inr: Optional[float] = None

class Harm(BaseModel):
    physical_injury: str = "unknown" # yes|no|unknown
    property_damage: str = "unknown"
    mental_agony: str = "unknown"

class ProductOrService(BaseModel):
    type: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None

class ExpandedIntent(BaseModel):
    case_summary: str
    primary_issue: str
    secondary_issues: List[str] = []
    legal_domains_guess: List[str] = []
    facts: Dict[str, Any] = {} # Can be structured using sub-models below if needed
    # We'll use a more flexible facts dict to store the nested models
    missing_information: List[str] = []
    risk_flags: List[str] = []
    confidence: float = 0.0

# --- 3.3 IssueExpansion ---
class Issue(BaseModel):
    issue_id: str
    label: str
    category: str
    description: str
    relevance_score: float

class IssueExpansion(BaseModel):
    issues: List[Issue]
    overall_severity: str # low|medium|high
    needs_deep_reasoning: bool = True

# --- 3.4 DomainRoutingDecision ---
class DomainRoutingDecision(BaseModel):
    domains_selected: List[str]
    primary_domain: str
    secondary_domains: List[str] = []
    justification: str

# --- 3.5 QuestionPlan ---
class Question(BaseModel):
    field_id: str
    question_text: str
    priority: int

class QuestionPlan(BaseModel):
    questions: List[Question]
    stop_condition: str # enough_for_reasoning|user_refuses|max_turns_reached

# --- 3.7 RetrievalResult ---
class Snippet(BaseModel):
    snippet_id: str
    source_type: str # statute|case|article
    source_name: str
    section_or_citation: str
    text: str
    relevance_score: float
    url: Optional[str] = None

class RetrievalResult(BaseModel):
    domain: str
    queries_used: List[str]
    snippets: List[Snippet]

# --- 3.8 ReasoningPlan ---
class ReasoningPlan(BaseModel):
    issue_map: Dict[str, Any]
    recommended_actions: List[str]
    remedies: List[str]
    evidence_needed: List[str]
    tone: str = "firm_formal"
    priority_level: str = "medium"

# --- 3.9 Draft ---
class Ground(BaseModel):
    legal_basis: str
    snippet_ids: List[str]

class Citation(BaseModel):
    snippet_id: str
    source_name: str
    section_or_citation: str

class Draft(BaseModel):
    facts: str
    issues: List[str]
    grounds: List[Ground]
    analysis: str
    prayer: str
    additional_remedies: List[str] = []
    citations: List[Citation] = []
    domains_covered: List[str]
    confidence: float = 0.0

# --- 3.10 ValidationResult ---
class ValidationResult(BaseModel):
    is_valid: bool
    missing_domains: List[str] = []
    missing_sections: List[str] = []
    coverage: Dict[str, bool]
    issues_found: List[str] = []
    auto_fixes_applied: List[str] = []

# --- 3.6 ConversationState ---
class ConversationState(BaseModel):
    conversation_id: str
    status: str # INIT|EXPANDED|ISSUES_IDENTIFIED|ASKING|FACTS_COLLECTED|RETRIEVING|REASONING|DRAFTING|VALIDATING|READY
    expanded_intent: Optional[ExpandedIntent] = None
    issues: Optional[IssueExpansion] = None
    domain_routing: Optional[DomainRoutingDecision] = None
    asked_fields: List[str] = []
    answered_fields: Dict[str, Any] = {}
    retrieval_context: Dict[str, List[Snippet]] = {}
    reasoning_plan: Optional[ReasoningPlan] = None
    draft: Optional[Draft] = None
    validation: Optional[ValidationResult] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
