from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class Party(BaseModel):
    id: str = Field(..., description="Unique party ID like P1, P2...")
    name: Optional[str] = None
    role: str = Field(default="unknown", description="Role: client, opponent, witness, third-party")
    description: Optional[str] = None
    relationship_to_client: Optional[str] = None

class Event(BaseModel):
    sequence: int = Field(..., description="Order of the event in time")
    actor_id: str = Field(..., description="ID of the party who performed the action")
    action: str = Field(..., description="The action performed (verb-phrase)")
    target_id: Optional[str] = None
    timestamp: Optional[str] = None
    location: Optional[str] = None
    description: str = Field(..., description="Lossless narrative of what happened in this specific event")
    certainty: str = Field(default="certain", description="certain, uncertain, alleged")
    event_type: str = Field(default="action", description="action, state, threat, outcome")
    semantic_tags: List[str] = Field(default_factory=list, description="Canonical behavior tags like 'money_not_paid', 'cheque_bounce'")

class Financial(BaseModel):
    amount: float
    currency: str = "INR"
    context: str = Field(..., description="What the money was for (e.g., 'unpaid salary', 'security deposit')")
    status: str = Field(default="disputed", description="pending, paid, disputed, partially_paid")

class Document(BaseModel):
    type: str = Field(..., description="agreement, receipt, notice, screenshot, email")
    description: str
    status: str = Field(default="mentioned", description="exists, missing, mentioned, verified")
    
class MetaLayer(BaseModel):
    intents: List[str] = Field(default_factory=list, description="Explicitly stated promises, threats, or goals")
    claims: List[str] = Field(default_factory=list, description="Opinions, grievances, or legal claims made by the user")
    uncertainties: List[str] = Field(default_factory=list, description="Ambiguous points or contradictions needing clarification")

class CaseModel(BaseModel):
    parties: List[Party] = Field(default_factory=list)
    events: List[Event] = Field(default_factory=list)
    financials: List[Financial] = Field(default_factory=list)
    documents: List[Document] = Field(default_factory=list)
    meta: MetaLayer = Field(default_factory=MetaLayer)
    domain: Optional[str] = Field(None, description="E.g., 'cyber', 'employment', 'property', 'financial'")
    detected_relationship: Optional[str] = Field(None, description="E.g., 'employer-employee', 'landlord-tenant'")
    missing_information: List[Dict[str, str]] = Field(default_factory=list, description="Detected gaps like missing dates, amounts, or relationships")
    validation_vitals: List[str] = Field(default_factory=list, description="Internal validation notes (e.g., 'Zero events found')")

    def is_valid(self) -> bool:
        """Mandatory validation layer check."""
        if not self.events: return False
        if not self.parties: return False
        return True
