import json
from fact_extractor import FactExtraction, IncidentCandidate, Entities, Loss, Timeline, Evidence
from legal_interview import detect_issues, classify_severity, generate_firac_analysis, REQUIRED_FACTS

def test_it_act_logic():
    print("--- Verifying IT Act Logic Integration ---")

    # 1. Severity Classification
    it_issues = ["account_hacking", "online_fraud", "identity_theft", "data_breach", "harassment_cyber"]
    for issue in it_issues:
        severity = classify_severity(issue, "general", {})
        print(f"Issue: {issue}, Severity: {severity}")
        assert severity == "high"
    print("✅ Severity Classification for IT Act matters is correct (High).")

    # 2. Required Facts
    for issue in it_issues:
        req = REQUIRED_FACTS.get(issue)
        print(f"Issue: {issue}, Required Facts: {req}")
        assert req is not None
        assert len(req) > 0
    print("✅ Required Facts for IT Act matters are defined.")

    # 3. FIRAC Structure Verification (Mock LLM would be needed for full run)
    print("\n[Manual Note] FIRAC analysis will be triggered for these issues because severity is HIGH.")

def test_fact_extraction_schema():
    print("\n--- Verifying Fact Extraction Schema ---")
    
    # Test Pydantic model
    try:
        data = {
            "incident_type_candidates": [{"type": "account_hacking", "confidence": 0.8}],
            "entities": {"platform": ["Instagram"]},
            "actions": ["Unauthorized login"],
            "loss": {"access": True},
            "timeline": {"incident_date": "2024-04-01", "reported": False},
            "evidence": {"available": False, "type": []}
        }
        facts = FactExtraction(**data)
        print("✅ FactExtraction Pydantic model initialized correctly.")
    except Exception as e:
        print(f"❌ FactExtraction model failed: {e}")
        raise

if __name__ == "__main__":
    test_it_act_logic()
    test_fact_extraction_schema()
    print("\n🏆 Verification Successful!")
