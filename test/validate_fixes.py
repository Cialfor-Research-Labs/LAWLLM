import sys, os, json, time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from extractor_pipeline import run_case_extractor_pipeline
from legal_primitives import LegalBrain
from law_engine import LawEngine

MODEL_NAME = "mistral.ministral-3-14b-instruct"
OUTPUT_FILE = "test/validation_results_output.json"

# --- 7 targeted cases: 4 prev FAILED + 3 new ---
TEST_CASES = [
    # ---- PREVIOUSLY FAILED ----
    {
        "id": "emp_03",
        "domain": "employment",
        "input": "Company refusing to pay my gratuity after 5 years of service.",
        "expected": "Payment of Gratuity Act, 1972",
        "was_failing": True,
        "failure_reason": "Phase 1 returned NO events; Phase 2 empty; zero laws mapped."
    },
    {
        "id": "emp_04",
        "domain": "employment",
        "input": "Manager harassed me at the workplace.",
        "expected": "Sexual Harassment of Women at Workplace Act, 2013",
        "was_failing": True,
        "failure_reason": "threat_made detected but interpretation 'sexual_harassment' not triggered; no laws ranked."
    },
    {
        "id": "fin_04",
        "domain": "financial",
        "input": "Company took my money for investment and suddenly shut down.",
        "expected": "Bharatiya Nyaya Sanhita, 2023",
        "was_failing": True,
        "failure_reason": "false_statement_made not extracted; fraud signal missed; wrong law ranked #1."
    },
    {
        "id": "con_04",
        "domain": "consumer",
        "input": "E-commerce site delivered a stone instead of a laptop I ordered.",
        "expected": "Consumer Protection Act, 2019",
        "was_failing": True,
        "failure_reason": "product_defective not tagged; service_not_delivered missed; CPA not surfaced."
    },
    # ---- NEW GENERALIZATION CASES ----
    {
        "id": "emp_01",
        "domain": "employment",
        "input": "Company hasn't paid my salary for 2 months.",
        "expected": "Payment of Wages Act, 1936",
        "was_failing": False,
        "failure_reason": "N/A"
    },
    {
        "id": "cyb_01",
        "domain": "cyber",
        "input": "Someone hacked my bank account and stole money using my OTP.",
        "expected": "Information Technology Act, 2000",
        "was_failing": False,
        "failure_reason": "N/A"
    },
    {
        "id": "fin_02_new",
        "domain": "financial",
        "input": "I gave a post-dated cheque for rent and it bounced.",
        "expected": "Negotiable Instruments Act, 1881",
        "was_failing": False,
        "failure_reason": "N/A"
    }
]

def run_validation():
    brain = LegalBrain()
    engine = LawEngine()
    results = []

    print(f"\n{'='*60}")
    print("VIDHI AI — PHASE 5 VALIDATION RUN")
    print(f"Model: {MODEL_NAME}")
    print(f"Cases: {len(TEST_CASES)}")
    print(f"{'='*60}\n")

    for case in TEST_CASES:
        print(f"▶ [{case['id']}] {case['input'][:55]}...")
        t0 = time.time()

        try:
            # Phase 1 + Normalization
            case_model = run_case_extractor_pipeline(case['input'], MODEL_NAME)

            # Phase 2: Primitives
            brain_resp = brain.detect_primitives(case_model)

            # Phase 3: Law Mapping & Ranking
            laws_resp = engine.map_laws(case_model, brain_resp)

            top_laws = laws_resp.applicable_laws
            predicted_top = top_laws[0].law if top_laws else "NONE"
            is_top1 = (predicted_top == case['expected'])
            is_top3 = any(l.law == case['expected'] for l in top_laws[:3])

            result = {
                "case_id": case['id'],
                "domain": case['domain'],
                "input": case['input'],
                "expected": case['expected'],
                "was_failing_before": case['was_failing'],
                "previous_failure_reason": case['failure_reason'],

                # Phase 1
                "phase1_events": [
                    {
                        "seq": e.sequence,
                        "action": e.action,
                        "description": e.description,
                        "event_type": e.event_type,
                        "semantic_tags": e.semantic_tags
                    }
                    for e in case_model.events
                ],
                "phase1_parties": [
                    {"id": p.id, "role": p.role, "relationship": p.relationship_to_client}
                    for p in case_model.parties
                ],
                "inferred_domain": case_model.domain,

                # Phase 2
                "phase2_behaviors": [b.name for b in brain_resp.behavioral_primitives],
                "phase2_interpretations": [
                    {"label": i.label, "confidence": round(i.confidence, 2)}
                    for i in brain_resp.interpretations
                ],

                # Phase 3
                "phase3_ranked_laws": [
                    {
                        "rank": l.rank,
                        "law": l.law,
                        "section": l.section,
                        "score": round(l.final_score, 3),
                        "confidence_level": l.confidence_level,
                        "reasoning": l.reasoning
                    }
                    for l in top_laws
                ],

                # Verdict
                "predicted_top": predicted_top,
                "is_top1_correct": is_top1,
                "is_top3_correct": is_top3,
                "status": "✅ CORRECT" if is_top1 else ("⚠️ TOP-3" if is_top3 else "❌ WRONG"),
                "fixed_by_remediation": (is_top1 and case['was_failing'])
            }
            results.append(result)

        except Exception as e:
            import traceback
            results.append({
                "case_id": case['id'],
                "input": case['input'],
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            predicted_top = f"ERROR: {e}"
            is_top1 = False

        elapsed = time.time() - t0
        prefix = "✅" if is_top1 else "❌"
        print(f"  {prefix} Top Law: {predicted_top[:55]} ({elapsed:.1f}s)\n")

    # Summary
    valid = [r for r in results if "error" not in r]
    total = len(valid)
    top1 = sum(1 for r in valid if r['is_top1_correct'])
    top3 = sum(1 for r in valid if r['is_top3_correct'])
    fixed = sum(1 for r in valid if r.get('fixed_by_remediation'))
    prev_failed = sum(1 for r in valid if r['was_failing_before'])

    summary = {
        "total_cases": total,
        "top1_correct": top1,
        "top3_correct": top3,
        "top1_accuracy": round(top1 / total, 3) if total else 0,
        "top3_accuracy": round(top3 / total, 3) if total else 0,
        "previously_failed_cases": prev_failed,
        "now_fixed": fixed,
        "fix_rate": f"{fixed}/{prev_failed}" if prev_failed else "N/A"
    }

    output = {"summary": summary, "cases": results}
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*60}")
    print("VALIDATION COMPLETE")
    print(json.dumps(summary, indent=2))
    print(f"{'='*60}")
    print(f"Report: {OUTPUT_FILE}")

if __name__ == "__main__":
    run_validation()
