import sys
import os
import json
import time
from typing import List, Dict, Any

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from extractor_pipeline import run_case_extractor_pipeline
from legal_primitives import LegalBrain
from law_engine import LawEngine
from case_model import CaseModel

# Config
DATASET_PATH = "test/law_eval_dataset.json"
OUTPUT_REPORT = "test/full_system_evaluation_report.json"
MODEL_NAME = "mistral.ministral-3-14b-instruct" # Fast & Balanced for extraction

def select_test_cases(limit_per_domain=8):
    with open(DATASET_PATH, 'r') as f:
        all_cases = json.load(f)
    
    selected = []
    counts = {}
    for case in all_cases:
        domain = case['domain']
        counts[domain] = counts.get(domain, 0)
        if counts[domain] < limit_per_domain:
            selected.append(case)
            counts[domain] += 1
    return selected

def run_evaluation():
    test_cases = select_test_cases(8)
    print(f"Selected {len(test_cases)} cases for evaluation.")
    
    brain = LegalBrain()
    engine = LawEngine()
    
    results = []
    
    for idx, case in enumerate(test_cases):
        print(f"[{idx+1}/{len(test_cases)}] Processing {case['id']}: {case['input'][:50]}...")
        start_time = time.time()
        
        try:
            # PHASE 1: Extraction
            case_model = run_case_extractor_pipeline(case['input'], MODEL_NAME)
            
            # PHASE 2: Primitives
            brain_resp = brain.detect_primitives(case_model)
            
            # PHASE 3: Mapping & Ranking
            laws_resp = engine.map_laws(case_model, brain_resp)
            
            # Capture Trace
            trace = {
                "case_id": case['id'],
                "input": case['input'],
                "expected_top": case['expected_top'],
                "phase1_facts": {
                    "events": [e.dict() for e in case_model.events],
                    "parties": [p.dict() for p in case_model.parties],
                    "financials": [f.dict() for f in case_model.financials]
                },
                "phase2_primitives": {
                    "behaviors": [b.name for b in brain_resp.behavioral_primitives],
                    "interpretations": [
                        {"label": i.label, "conf": i.confidence} 
                        for i in brain_resp.interpretations
                    ]
                },
                "phase3_ranked_laws": [
                    {
                        "law": l.law,
                        "section": l.section,
                        "score": l.final_score,
                        "rank": l.rank,
                        "reasoning": l.reasoning
                    }
                    for l in laws_resp.applicable_laws
                ]
            }
            
            # Scoring
            top_laws = [l.law for l in laws_resp.applicable_laws]
            predicted_top = top_laws[0] if top_laws else None
            
            trace["is_top1_correct"] = (predicted_top == case['expected_top'])
            trace["is_top3_correct"] = (case['expected_top'] in top_laws[:3])
            
            # Special Check: Over-criminalization
            has_criminal = any(
                "Bharatiya Nyaya Sanhita" in l.law or "Indian Penal Code" in l.law 
                for l in laws_resp.applicable_laws
            )
            # Incorrect if criminal law suggested for a non-criminal expected law (heuristic)
            trace["over_criminalized"] = has_criminal and "Bharatiya" not in case['expected_top'] and "Indian Penal" not in case['expected_top']
            
            # Irrelevant Laws: laws with score < 0.5 that are not the top law
            trace["irrelevant_laws"] = [l.law for l in laws_resp.applicable_laws if l.final_score < 0.6]

            results.append(trace)
            
        except Exception as e:
            print(f"Error processing {case['id']}: {str(e)}")
            results.append({
                "case_id": case['id'],
                "error": str(e)
            })
            
        elapsed = time.time() - start_time
        print(f"   Done in {elapsed:.1f}s. Result: {'CORRECT' if trace.get('is_top1_correct') else 'WRONG'}")

    # Calculate METRICS
    success_cases = [r for r in results if "error" not in r]
    total = len(success_cases)
    
    if total > 0:
        top1_acc = sum(1 for r in success_cases if r['is_top1_correct']) / total
        top3_acc = sum(1 for r in success_cases if r['is_top3_correct']) / total
        over_crim_rate = sum(1 for r in success_cases if r['over_criminalized']) / total
        
        all_irrelevant = []
        for r in success_cases:
            all_irrelevant.extend(r['irrelevant_laws'])
        irrelevant_rate = len(all_irrelevant) / total

        summary = {
            "top1_accuracy": round(top1_acc, 4),
            "top3_accuracy": round(top3_acc, 4),
            "over_criminalization_rate": round(over_crim_rate, 4),
            "irrelevant_law_per_case": round(irrelevant_rate, 4),
            "total_cases": total
        }
    else:
        summary = {"error": "No cases processed successfully"}

    final_report = {
        "summary": summary,
        "details": results
    }
    
    with open(OUTPUT_REPORT, 'w') as f:
        json.dump(final_report, f, indent=2)
        
    print("\n" + "="*30)
    print("EVALUATION COMPLETE")
    print(f"Report saved to: {OUTPUT_REPORT}")
    print(json.dumps(summary, indent=2))
    print("="*30)

if __name__ == "__main__":
    run_evaluation()
