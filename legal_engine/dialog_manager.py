from typing import Optional
from legal_engine.models import ConversationState, QuestionPlan
from legal_engine.orchestrator import LegalEngineOrchestrator

class DialogManager:
    def __init__(self, orchestrator: LegalEngineOrchestrator):
        self.orchestrator = orchestrator

    def handle_user_input(self, conversation_id: str, text: str) -> str:
        """
        Unified method to handle user input and return either questions or final output.
        """
        state, action = self.orchestrator.handle_message(conversation_id, text)
        
        if isinstance(action, QuestionPlan):
            # Render questions (limit to 3 as per request)
            questions = action.questions[:3]
            response = ("I need a few more details to provide a complete legal strategy:\n\n" + 
                       "\n".join([f"{i+1}. {q.question_text}" for i, q in enumerate(questions)]))
            return response
        
        if state.status == "FACTS_COLLECTED":
            # Proceed to final output generation (Phase 3 & 4)
            print("Generating final legal draft...")
            state, draft = self.orchestrator.process_final_output(conversation_id)
            
            if draft:
                return self._format_draft(draft)
            
        return "I'm processing your case. Please provide more details."

    def _format_draft(self, draft) -> str:
        """
        Format the Draft model into a beautiful markdown response.
        """
        sections = []
        sections.append("# Legal Analysis & Strategy\n")
        sections.append("## Facts\n" + draft.facts)
        
        sections.append("\n## Legal Issues Identified")
        for i in draft.issues:
            sections.append(f"- {i}")
            
        sections.append("\n## Legal Grounds")
        for g in draft.grounds:
            sections.append(f"### {g.legal_basis}")
            # Snippet IDs could be mapped to actual citations if needed
            
        sections.append("\n## Analysis\n" + draft.analysis)
        sections.append("\n## Prayer / Recommended Actions\n" + draft.prayer)
        
        if draft.additional_remedies:
            sections.append("\n## Additional Remedies")
            for r in draft.additional_remedies:
                sections.append(f"- {r}")
                
        if draft.citations:
            sections.append("\n## Citations")
            for c in draft.citations:
                sections.append(f"- {c.source_name} | {c.section_or_citation}")
        
        return "\n".join(sections)
