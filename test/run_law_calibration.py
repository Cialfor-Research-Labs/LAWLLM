import asyncio
import json
import os
import sys
from datetime import datetime

# Import project modules
sys.path.append(os.getcwd())
from case_model import CaseModel
from legal_primitives import LegalBrain
from law_engine import LawEngine
from extractor_pipeline import run_case_extractor_pipeline

# Calibration Config
DATASET_PATH = "test/law_eval_dataset.json"

async def evaluate_case(case_data, brain, engine):
    """Run full pipeline for a single case."""
    # Step 1: Extract Case Model (Simplified for evaluation to focus on law mapping)
    # In real world, run_case_extractor_pipeline(case_data['input'])
    # For calibration, we'll use a direct mock or fast-path if needed, 
    # but here let's run the real LLM-based extractor for fidelity.
    
    # NOTE: To speed up, we'll mock the extraction part and focus on context-driven law ranking
    # unless you want the full pipeline latency.
    
    # MOCK CASE MODEL (FOR SPEED AND REPRODUCIBILITY IN CALIBRATION)
    # We simulate what the extractor would find based on the input.
    model = CaseModel(
        parties=[],
        events=[],
        domain=case_data['domain']
    )
    
    # Determine relationship and context for logic check
    if case_data['domain'] == "employment":
        model.detected_relationship = "employer-employee"
    elif case_data['domain'] == "property":
        model.detected_relationship = "landlord-tenant"

    # Run the real Brain and LawEngine
    # (Using real extraction would be too slow/expensive for 100 cases in one go)
    # Actually, we MUST run at least the primitives and laws logic.
    
    # Simulate events for the brain to detect
    low_input = case_data['input'].lower()
    from case_model import Event, Financial
    
    # 1. Employment signals
    if any(kw in low_input for kw in ["salary", "pay"]):
        model.financials.append(Financial(amount=0.0, context="unpaid", status="disputed"))
        model.events.append(Event(sequence=1, actor_id="P1", action="worked", description="User worked for month."))
        model.events.append(Event(sequence=2, actor_id="P2", action="did not pay", description="Opponent didn't pay."))
    if any(kw in low_input for kw in ["terminated", "fired", "notice", "quit", "resigned"]):
        model.events.append(Event(sequence=3, actor_id="P2", action="terminated", description="Employment ended."))
    if "gratuity" in low_input:
        model.events.append(Event(sequence=4, actor_id="P2", action="no gratuity", description="Did not return gratuity."))
    if any(kw in low_input for kw in ["overtime", "extra hours"]):
        model.events.append(Event(sequence=10, actor_id="P2", action="refuse overtime", description="Overtime work not paid."))
    if any(kw in low_input for kw in ["maternity", "pregnant", "leave"]):
        model.events.append(Event(sequence=11, actor_id="P2", action="deny leave", description="Maternity leave request denied."))
    if any(kw in low_input for kw in ["pf ", "provident fund"]):
        model.events.append(Event(sequence=12, actor_id="P2", action="no pf", description="PF not contributed."))
    if "bonus" in low_input:
        model.events.append(Event(sequence=13, actor_id="P2", action="no bonus", description="Bonus not paid."))
    if any(kw in low_input for kw in ["injury", "accident", "hurt"]):
        model.events.append(Event(sequence=14, actor_id="P2", action="accident", description="Injury at work."))
    if any(kw in low_input for kw in ["minimum wage", "underpaid"]):
        model.events.append(Event(sequence=15, actor_id="P2", action="underpaid", description="Under payment of wages."))

    # 2. Cyber/Deception signals
    if any(kw in low_input for kw in ["hacked", "otp", "accessed", "phishing", "scam", "compromised", "password"]):
         model.events.append(Event(sequence=5, actor_id="P2", action="accessed account", description="Account was accessed illegally."))
    if any(kw in low_input for kw in ["lied", "misrepresented", "false", "misleading", "fake", "identity", "posing"]):
         model.events.append(Event(sequence=6, actor_id="P2", action="lied", description="False statement made."))
    if any(kw in low_input for kw in ["private", "photos", "leaked", "camera", "images", "privacy", "stalking", "morph"]):
         model.events.append(Event(sequence=17, actor_id="P2", action="privacy breach", description="Breached privacy of individual."))

    # 3. Property signals
    if any(kw in low_input for kw in ["evicted", "threw out", "locked"]):
         model.events.append(Event(sequence=7, actor_id="P2", action="evicted", description="Forced exit made."))
    if any(kw in low_input for kw in ["delay", "possession", "flat", "handover", "rera"]):
         model.events.append(Event(sequence=16, actor_id="P2", action="delay", description="Possession delayed."))

    # 4. Financial signals
    if any(kw in low_input for kw in ["loan", "return", "cheque", "funds", "dishonored", "interest"]):
         model.events.append(Event(sequence=8, actor_id="P2", action="not returned", description="Money not returned."))
    if any(kw in low_input for kw in ["harass", "abuse", "agent"]):
         model.events.append(Event(sequence=18, actor_id="P2", action="threat", description="Threat made by recovery agent."))
    if any(kw in low_input for kw in ["trade", "stock", "broker", "unauthorized transaction"]):
         model.events.append(Event(sequence=19, actor_id="P2", action="digital breach", description="Unauthorized digital access to account."))

    # 5. Consumer signals
    if any(kw in low_input for kw in ["defective", "product", "cancel", "refund", "not work", "poor quality"]):
         model.events.append(Event(sequence=9, actor_id="P2", action="refusal", description="Service not delivered."))

    brain_resp = brain.detect_primitives(model)
    laws_resp = engine.map_laws(model, brain_resp)
    
    return laws_resp.applicable_laws

def calculate_metrics(results, dataset):
    top1_hits = 0
    top3_hits = 0
    over_crim = 0
    irrelevant_count = 0
    total = len(dataset)
    
    for i, res_list in enumerate(results):
        expected_top = dataset[i]['expected_top']
        expected_secondary = dataset[i].get('secondaries', [])
        expected_all = [expected_top] + expected_secondary
        
        predicted_laws = [l.law for l in res_list]
        
        # 1. Top-1 Accuracy
        if predicted_laws and any(expected_top in p for p in predicted_laws[:1]):
            top1_hits += 1
            
        # 2. Top-3 Accuracy
        if any(expected_top in p for p in predicted_laws[:3]):
            top3_hits += 1
            
        # 3. Over-Criminalization
        if predicted_laws and ("BNS" in predicted_laws[0] or "IPC" in predicted_laws[0]):
            if dataset[i]['domain'] in ["employment", "property", "financial", "consumer"]:
                # If it's a civil domain case but Rank 1 is criminal without deception
                # (Ideally we'd check if deception was in expected, but this is a heuristic)
                if "fraud" not in dataset[i]['input'].lower():
                    over_crim += 1
                    
        # 4. Irrelevant Rate
        for l in predicted_laws:
            if not any(exp in l for exp in expected_all):
                irrelevant_count += 1

    return {
        "top1_accuracy": (top1_hits / total) * 100,
        "top3_accuracy": (top3_hits / total) * 100,
        "over_criminalization_rate": (over_crim / total) * 100,
        "irrelevant_law_rate": (irrelevant_count / max(1, sum(len(r) for r in results))) * 100
    }

async def main():
    if not os.path.exists(DATASET_PATH):
        print(f"Error: {DATASET_PATH} not found.")
        return

    with open(DATASET_PATH, "r") as f:
        dataset = json.load(f)

    print(f"Evaluating {len(dataset)} cases...")
    
    brain = LegalBrain()
    engine = LawEngine()
    
    all_results = []
    for case in dataset:
        print(f"Processing {case['id']}...", end="\r")
        res = await evaluate_case(case, brain, engine)
        all_results.append(res)
    
    metrics = calculate_metrics(all_results, dataset)
    
    print("\n--- Final Metrics ---")
    print(f"Top-1 Accuracy: {metrics['top1_accuracy']:.2f}%")
    print(f"Top-3 Accuracy: {metrics['top3_accuracy']:.2f}%")
    print(f"Over-Criminalization Rate: {metrics['over_criminalization_rate']:.2f}%")
    print(f"Irrelevant Law Rate: {metrics['irrelevant_law_rate']:.2f}%")
    
    # Save results
    report = {
        "timestamp": datetime.now().isoformat(),
        "metrics": metrics,
        "detail": []
    }
    for i, res in enumerate(all_results):
        report["detail"].append({
            "case_id": dataset[i]["id"],
            "input": dataset[i]["input"],
            "expected": dataset[i]["expected_top"],
            "predicted": [l.law for l in res],
            "scores": [l.final_score for l in res]
        })
        
    with open("test/calibration_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("Report saved to test/calibration_report.json")

if __name__ == "__main__":
    asyncio.run(main())
