import asyncio
import json
from typing import List
from case_model import CaseModel
from extractor_pipeline import run_case_extractor_pipeline
from legal_primitives import LegalBrain

async def run_test(query: str, test_id: str):
    print(f"\n--- Running Test {test_id}: {query} ---")
    
    # Phase 1: Case Model Extraction
    # Note: run_case_extractor_pipeline is synchronous in recent implementation
    case_model = run_case_extractor_pipeline(query, "mistral.ministral-3-14b-instruct") # Using default model
    
    # Phase 2: Legal Brain (Detection)
    from bedrock_client import call_bedrock_chat
    def llm_wrapper(prompt: str) -> str:
        return call_bedrock_chat(
            messages=[{"role": "user", "content": prompt}],
            model_id="mistral.ministral-3-14b-instruct"
        )
        
    brain = LegalBrain(llm_fn=llm_wrapper)
    result = brain.detect_primitives(case_model)
    
    print("\n[PHASE 1: Structured Facts]")
    print(case_model.model_dump_json(indent=2))
    
    print("\n[BEHAVIORAL PRIMITIVES]")
    for b in result.behavioral_primitives:
        print(f"- {b.name} (Events: {b.supporting_events})")
        
    print("\n[INTERPRETATION PRIMITIVES]")
    for i in result.interpretations:
        print(f"- {i.label} (Conf: {i.confidence:.2f})")
        print(f"  Description: {i.description}")
        print(f"  Behaviors: {i.supporting_behaviors}")
        print(f"  Events: {i.supporting_events}")

async def main():
    tests = [
        "I gave him 50,000. He promised to return but didn’t.",
        "I paid advance but service was not delivered.",
        "Someone accessed my account and transferred money.",
        "He said he will pay later but stopped responding.",
        "This is fraud. He cheated me."
    ]
    
    for i, t in enumerate(tests, 1):
        await run_test(t, str(i))

if __name__ == "__main__":
    asyncio.run(main())
