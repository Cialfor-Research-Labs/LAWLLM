import asyncio
import json
from case_model import CaseModel, Party, Event, Financial
from legal_primitives import LegalBrain
from law_engine import LawEngine

async def test_phase4():
    engine = LawEngine()
    brain = LegalBrain()

    # Test 1: Salary Unpaid (Employment, No Deception)
    print("\n--- Test 1: Salary Unpaid (Employment) ---")
    case1 = CaseModel(
        parties=[Party(id="P1", role="client"), Party(id="P2", role="opponent", relationship_to_client="employer")],
        events=[
            Event(sequence=1, actor_id="P1", action="worked", description="I worked for the company."),
            Event(sequence=2, actor_id="P1", action="fired", description="They terminated me."),
            Event(sequence=3, actor_id="P2", action="did not pay", description="They did not pay my salary.")
        ],
        financials=[Financial(amount=50000, context="salary", status="disputed")],
        domain="employment",
        detected_relationship="employer-employee"
    )
    brain_resp1 = brain.detect_primitives(case1)
    laws_resp1 = engine.map_laws(case1, brain_resp1)
    for l in laws_resp1.applicable_laws:
        print(f"Rank {l.rank}: {l.law} ({l.section}) | Conf: {l.confidence_level} | Score: {l.final_score}")

    # Test 2: Loan Unpaid (Civil, No Deception)
    print("\n--- Test 2: Loan Unpaid (Civil, No Deception) ---")
    case2 = CaseModel(
        parties=[Party(id="P1", role="client"), Party(id="P2", role="opponent")],
        events=[
            Event(sequence=1, actor_id="P2", action="borrowed money", description="He borrowed 1L from me."),
            Event(sequence=2, actor_id="P2", action="did not return", description="He is not returning the money.")
        ],
        financials=[Financial(amount=100000, context="loan", status="disputed")],
        domain="financial"
    )
    brain_resp2 = brain.detect_primitives(case2)
    laws_resp2 = engine.map_laws(case2, brain_resp2)
    for l in laws_resp2.applicable_laws:
        print(f"Rank {l.rank}: {l.law} ({l.section}) | Conf: {l.confidence_level} | Score: {l.final_score}")

    # Test 3: Cyber Fraud (Cyber + Deception)
    print("\n--- Test 3: Cyber Fraud (Cyber + Deception) ---")
    case3 = CaseModel(
        parties=[Party(id="P1", role="client"), Party(id="P2", role="opponent")],
        events=[
            Event(sequence=1, actor_id="P2", action="lied about profile", description="He made a false statement about his identity."),
            Event(sequence=2, actor_id="P2", action="hacked account", description="He accessed my account."),
            Event(sequence=3, actor_id="P2", action="took money", description="He transferred money out.")
        ],
        financials=[Financial(amount=5000, context="stolen money", status="disputed")],
        domain="cyber"
    )
    brain_resp3 = brain.detect_primitives(case3)
    print(f"Behaviors: {[b.name for b in brain_resp3.behavioral_primitives]}")
    print(f"Interpretations: {[i.label for i in brain_resp3.interpretations]}")
    laws_resp3 = engine.map_laws(case3, brain_resp3)
    for l in laws_resp3.applicable_laws:
        print(f"Rank {l.rank}: {l.law} ({l.section}) | Conf: {l.confidence_level} | Score: {l.final_score}")

if __name__ == "__main__":
    asyncio.run(test_phase4())
