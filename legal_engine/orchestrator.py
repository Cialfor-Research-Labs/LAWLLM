import uuid
from datetime import datetime
from typing import Optional, Tuple, Any

from legal_engine.models import (
    UserMessage, ConversationState, ExpandedIntent, 
    IssueExpansion, DomainRoutingDecision, QuestionPlan,
    Draft, ReasoningPlan, ValidationResult
)
from legal_engine.state_manager import load_state, save_state
from legal_engine.intent_expansion import expand_intent
from legal_engine.issue_expansion import expand_issues
from legal_engine.domain_router import route_domains
from legal_engine.question_planner import plan_questions

from legal_engine.retrieval_service import retrieve_multi_domain
from legal_engine.reasoning_planner import plan_reasoning
from legal_engine.drafting_engine import draft_output
from legal_engine.validator import validate_draft

class LegalEngineOrchestrator:
    def __init__(self, model: str = "llama3.1:8b"):
        self.model = model

    def handle_message(self, conversation_id: str, text: str) -> Tuple[ConversationState, Any]:
        """
        Main entry point for handling a user message.
        Returns the updated state and the next action (QuestionPlan or Draft).
        """
        # 1. Load or Initialize State
        state = load_state(conversation_id)
        if not state:
            state = ConversationState(
                conversation_id=conversation_id,
                status="INIT",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

        # 2. Update status and history
        state.updated_at = datetime.utcnow()
        user_msg = UserMessage(
            conversation_id=conversation_id,
            message_id=str(uuid.uuid4()),
            text=text
        )
        # We could store messages in state.history if we added it to models.py
        
        # 3. Step 1: Intent Expansion (Broad understanding)
        if state.status in ["INIT", "ASKING"]:
            print(f"Expanding intent for: {text[:50]}...")
            # For multi-turn, we might want to append new text to existing context
            # Simplification: treat 'text' as the current combined view or new delta
            new_intent = expand_intent(text, model=self.model)
            
            if not state.expanded_intent:
                state.expanded_intent = new_intent
            else:
                # Merge logic: overwrite for now
                state.expanded_intent = new_intent
            
            state.status = "EXPANDED"

        # 4. Step 2: Legal Issue Expansion (Multi-angle detection)
        if state.expanded_intent:
            print("Expanding legal issues...")
            state.issues = expand_issues(state.expanded_intent, model=self.model)
            state.status = "ISSUES_IDENTIFIED"

        # 5. Step 3: Domain Routing
        if state.issues:
            print("Routing domains...")
            state.domain_routing = route_domains(state.issues)

        # 6. Step 4: Question Planning
        print("Planning questions...")
        q_plan = plan_questions(state, model=self.model)
        
        # 7. Check stop condition
        if q_plan.stop_condition == "enough_for_reasoning" or not q_plan.questions:
            print("Sufficient facts collected. Transitioning to FACTS_COLLECTED...")
            state.status = "FACTS_COLLECTED"
            save_state(state)
            return state, None
        else:
            state.status = "ASKING"
            # Update asked_fields
            for q in q_plan.questions:
                if q.field_id not in state.asked_fields:
                    state.asked_fields.append(q.field_id)
            
            save_state(state)
            return state, q_plan

    def process_final_output(self, conversation_id: str) -> Tuple[ConversationState, Draft]:
        """
        Phase 3 & 4 logic: Retrieval -> Reasoning -> Drafting -> Validation
        """
        state = load_state(conversation_id)
        if not state or state.status != "FACTS_COLLECTED":
            # If not in FACTS_COLLECTED, we cannot process final output
            return state, None
            
        # 1. Multi-domain Retrieval
        print("Running multi-domain retrieval...")
        state.status = "RETRIEVING"
        state.retrieval_context = {} # Optional: clear old context
        results = retrieve_multi_domain(
            state.expanded_intent, state.issues, state.domain_routing, state.answered_fields
        )
        for r in results:
            state.retrieval_context[r.domain] = r.snippets
        
        # 2. Reasoning Plan
        print("Generating reasoning plan...")
        state.status = "REASONING"
        state.reasoning_plan = plan_reasoning(
            state.expanded_intent, state.issues, results, state.answered_fields, model=self.model
        )
        
        # 3. Drafting
        print("Drafting final output...")
        state.status = "DRAFTING"
        state.draft = draft_output(
            state.expanded_intent, state.reasoning_plan, results, model=self.model
        )
        
        # 4. Validation
        print("Validating draft...")
        state.status = "VALIDATING"
        state.validation = validate_draft(
            state.draft, state.issues, state.domain_routing, model=self.model
        )
        
        state.status = "READY"
        state.updated_at = datetime.utcnow()
        save_state(state)
        return state, state.draft

