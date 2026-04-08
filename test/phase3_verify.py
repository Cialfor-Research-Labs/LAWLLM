import asyncio
import json
from case_model import CaseModel, Party, Event, Financial
from legal_primitives import LegalBrain
from law_engine import LawEngine

async def test_phase3():
    # Test Case 1: Salary Unpaid (Employment Context)
    print("\n--- Test 1: Salary Unpaid (Employment) ---")
    case1 = CaseModel(
        parties=[
            Party(id="P1", name="User", role="client"),
            Party(id="P2", name="Company X", role="opponent", relationship_to_client="employer")
        ],
        events=[
            Event(sequence=1, actor_id="P1", action="worked for 3 months", description="I worked for the company from Jan to March."),
            Event(sequence=2, actor_id="P2", action="did not pay", description="They failed to credit my salary for March.")
        ],
        financials=[
            Financial(amount=50000, context="unpaid salary", status="disputed")
        ]
    )
    
    brain = LegalBrain() # No LLM for deterministic part
    brain_resp = brain.detect_primitives(case1)
    
    # Manual domain injection for testing
    case1.domain = "employment"
    case1.detected_relationship = "employer-employee"
    
    engine = LawEngine()
    laws_resp = engine.map_laws(case1, brain_resp)
    
    print(f"Behaviors: {[b.name for b in brain_resp.behavioral_primitives]}")
    print(f"Interpretations: {[i.label for i in brain_resp.interpretations]}")
    print("Applicable Laws:")
    for l in laws_resp.applicable_laws:
        print(f"- {l.law} ({l.section}) [Conf: {l.confidence:.2f}]")
        print(f"  Reasoning: {l.reasoning}")

    # Test Case 2: Account Hacked (Cyber Context)
    print("\n--- Test 2: Account Hacked (Cyber) ---")
    case2 = CaseModel(
        parties=[
            Party(id="P1", name="User", role="client"),
            Party(id="P2", name="Unknown", role="opponent")
        ],
        events=[
            Event(sequence=1, actor_id="P2", action="logged in without permission", description="Someone hacked my email account."),
            Event(sequence=2, actor_id="P2", action="transferred money", description="The hacker transferred 10,000 INR.")
        ],
        financials=[Financial(amount=10000, context="hacker transfer", status="disputed")]
    )
    case2.domain = "cyber"
    
    brain_resp2 = brain.detect_primitives(case2)
    laws_resp2 = engine.map_laws(case2, brain_resp2)
    
    print("Applicable Laws:")
    for l in laws_resp2.applicable_laws:
        print(f"- {l.law} ({l.section}) [Conf: {l.confidence:.2f}]")

if __name__ == "__main__":
    asyncio.run(test_phase3())
