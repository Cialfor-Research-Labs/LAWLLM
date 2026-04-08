import argparse
import json
from pathlib import Path
from typing import Dict, List

from retrieval_api import QueryRequest, query


def _pct(n: int, d: int) -> float:
    return 0.0 if d == 0 else round((n / d) * 100, 2)


def run_case(case: Dict, with_llm: bool) -> Dict:
    payload = QueryRequest(
        query=case["query"],
        generate_answer=with_llm,
        top_k=8,
    )
    resp = query(payload)
    meta = resp.meta or {}
    facts = meta.get("facts") or {}
    answer = (resp.answer or "").lower()

    out = {
        "id": case["id"],
        "domain_ok": meta.get("issue_domain") == case.get("expected_domain"),
        "statute_ok": True,
        "forum_ok": True,
        "regime_ok": True,
        "contamination_ok": True,
        "structure_ok": True,
    }

    if case.get("expected_statute_hint"):
        hint = str(case["expected_statute_hint"]).lower()
        source_blob = " ".join([(c.title or "") + " " + (c.source_file or "") for c in resp.citations]).lower()
        out["statute_ok"] = hint in source_blob or hint in answer

    if case.get("expected_forum"):
        out["forum_ok"] = facts.get("recommended_forum") == case.get("expected_forum")

    if case.get("expected_regime"):
        out["regime_ok"] = facts.get("statute_regime") == case.get("expected_regime")

    if case.get("expected_no_terms"):
        blocked = [t.lower() for t in case.get("expected_no_terms", [])]
        out["contamination_ok"] = not any(t in answer for t in blocked)

    if with_llm and case.get("expected_action_steps"):
        out["structure_ok"] = (
            "facts summary" in answer
            and "legal issue" in answer
            and "applicable law" in answer
            and "analysis" in answer
            and "practical next steps" in answer
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Run legal assistant evaluation harness")
    parser.add_argument("--cases", default="eval_cases.json")
    parser.add_argument("--with-llm", action="store_true")
    parser.add_argument("--report", default="eval_report.json")
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    results: List[Dict] = []
    for case in cases:
        try:
            results.append(run_case(case, with_llm=args.with_llm))
        except Exception as exc:
            results.append(
                {
                    "id": case.get("id"),
                    "error": str(exc),
                    "domain_ok": False,
                    "statute_ok": False,
                    "forum_ok": False,
                    "regime_ok": False,
                    "contamination_ok": False,
                    "structure_ok": False,
                }
            )

    totals = len(results)
    domain_hits = sum(1 for r in results if r.get("domain_ok"))
    statute_hits = sum(1 for r in results if r.get("statute_ok"))
    forum_hits = sum(1 for r in results if r.get("forum_ok"))
    regime_hits = sum(1 for r in results if r.get("regime_ok"))
    contamination_hits = sum(1 for r in results if r.get("contamination_ok"))
    structure_hits = sum(1 for r in results if r.get("structure_ok"))

    summary = {
        "total_cases": totals,
        "domain_precision_pct": _pct(domain_hits, totals),
        "statute_correctness_pct": _pct(statute_hits, totals),
        "forum_correctness_pct": _pct(forum_hits, totals),
        "regime_correctness_pct": _pct(regime_hits, totals),
        "contamination_clean_pct": _pct(contamination_hits, totals),
        "structure_compliance_pct": _pct(structure_hits, totals),
        "with_llm": args.with_llm,
    }

    report = {"summary": summary, "results": results}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved report: {args.report}")


if __name__ == "__main__":
    main()
