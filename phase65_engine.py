import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from case_model import CaseModel
from law_engine import LawEngineResponse
from signal_registry import get_signals_for_tag


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _safe_lower(text: Any) -> str:
    return str(text or "").strip().lower()


def normalize_user_confidence(answer: str) -> Optional[float]:
    text = _safe_lower(answer)
    if not text:
        return None
    if any(token in text for token in ["absolutely", "definitely", "yes", "sure", "certain", "100%", "completely"]):
        return 1.0
    if any(token in text for token in ["probably", "i think", "maybe", "not fully", "around", "somewhat"]):
        return 0.6
    if any(token in text for token in ["not sure", "unsure", "don't know", "do not know", "uncertain"]):
        return 0.35
    if any(token in text for token in ["no", "incorrect", "wrong", "not really"]):
        return 0.2
    return None


def extract_signal_updates(text: str) -> Dict[str, Dict[str, Any]]:
    low = _safe_lower(text)
    updates: Dict[str, Dict[str, Any]] = {}

    payment_keywords = [
        ("monthly_salary", ["salary", "monthly salary", "wages", "pay slip", "salary slip"]),
        ("gratuity", ["gratuity", "final settlement", "full and final", "fnf", "retirement benefit after leaving"]),
        ("retirement_benefit", ["pf", "provident fund", "retirement benefit", "uan"]),
        ("bonus", ["bonus", "performance bonus", "incentive"]),
    ]
    for value, keywords in payment_keywords:
        if any(token in low for token in keywords):
            updates["payment_type"] = {
                "value": value,
                "source": "query",
                "user_confidence": 0.7,
                "confirmed": False,
                "raw_text": text,
            }
            break

    if any(token in low for token in ["freelancer", "consultant", "independent contractor", "contractor"]):
        updates["work_relationship"] = {
            "value": "freelancer",
            "source": "query",
            "user_confidence": 0.75,
            "confirmed": False,
            "raw_text": text,
        }
    elif any(token in low for token in ["employee", "employer", "company terminated me", "my salary", "my wages", "hr", "payroll"]):
        updates["work_relationship"] = {
            "value": "employee",
            "source": "query",
            "user_confidence": 0.7,
            "confirmed": False,
            "raw_text": text,
        }

    years_match = re.search(r"(\d+)\s*\+?\s*years?", low)
    if years_match:
        years = int(years_match.group(1))
        updates["service_years"] = {
            "value": years,
            "source": "query",
            "user_confidence": 0.7,
            "confirmed": False,
            "raw_text": text,
        }
        updates["employment_end"] = {
            "value": years >= 5,
            "source": "query",
            "user_confidence": 0.7,
            "confirmed": False,
            "raw_text": text,
        }

    if any(token in low for token in ["terminated", "fired", "left job", "resigned", "after leaving", "after i left", "former employee"]):
        updates["employment_end"] = {
            "value": True,
            "source": "query",
            "user_confidence": 0.75,
            "confirmed": False,
            "raw_text": text,
        }
    elif any(token in low for token in ["still employed", "still working", "currently employed", "i am still working"]):
        updates["employment_end"] = {
            "value": False,
            "source": "query",
            "user_confidence": 0.75,
            "confirmed": False,
            "raw_text": text,
        }

    if any(token in low for token in ["proof", "salary slips", "bank statement", "invoice", "agreement", "screenshots"]):
        updates["documentary_proof"] = {
            "value": True,
            "source": "query",
            "user_confidence": 0.8,
            "confirmed": False,
            "raw_text": text,
        }

    return updates


def merge_signal_state(
    current: Dict[str, Dict[str, Any]],
    updates: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    merged = dict(current or {})
    for signal_name, incoming in updates.items():
        existing = merged.get(signal_name)
        if not existing:
            merged[signal_name] = incoming
            continue

        incoming_conf = float(incoming.get("user_confidence", 0.0))
        existing_conf = float(existing.get("user_confidence", 0.0))
        if incoming.get("value") != existing.get("value") or incoming_conf >= existing_conf:
            merged[signal_name] = {
                **existing,
                **incoming,
                "confirmed": bool(existing.get("confirmed")) or bool(incoming.get("confirmed")),
            }
    return merged


def derive_confirmed_tags(signal_state: Dict[str, Dict[str, Any]]) -> Tuple[List[str], Dict[str, float]]:
    confirmed_tags: List[str] = []
    tag_confidence: Dict[str, float] = {}

    payment_type = ((signal_state or {}).get("payment_type") or {}).get("value")
    employment_end = ((signal_state or {}).get("employment_end") or {}).get("value")

    if payment_type == "monthly_salary":
        conf = float((signal_state["payment_type"]).get("user_confidence", 0.6))
        confirmed_tags.append("under_payment")
        tag_confidence["under_payment"] = conf
    elif payment_type == "gratuity":
        base_conf = min(
            float((signal_state.get("payment_type") or {}).get("user_confidence", 0.6)),
            float((signal_state.get("employment_end") or {}).get("user_confidence", 0.6)),
        )
        if employment_end is True:
            confirmed_tags.append("gratuity_dispute")
            tag_confidence["gratuity_dispute"] = base_conf
        else:
            confirmed_tags.append("money_not_paid")
            tag_confidence["money_not_paid"] = base_conf
    elif payment_type == "retirement_benefit":
        conf = float((signal_state["payment_type"]).get("user_confidence", 0.6))
        confirmed_tags.append("pf_dispute")
        tag_confidence["pf_dispute"] = conf
    elif payment_type == "bonus":
        conf = float((signal_state["payment_type"]).get("user_confidence", 0.6))
        confirmed_tags.append("bonus_not_paid")
        tag_confidence["bonus_not_paid"] = conf

    return list(dict.fromkeys(confirmed_tags)), tag_confidence


def detect_contradictions(
    signal_state: Dict[str, Dict[str, Any]],
    facts: Dict[str, Any],
    case_model: Optional[CaseModel] = None,
) -> List[Dict[str, Any]]:
    contradictions: List[Dict[str, Any]] = []
    payment_type = ((signal_state or {}).get("payment_type") or {}).get("value")
    relationship = ((signal_state or {}).get("work_relationship") or {}).get("value")
    employment_end = ((signal_state or {}).get("employment_end") or {}).get("value")

    if relationship == "freelancer" and payment_type in {"monthly_salary", "gratuity", "retirement_benefit", "bonus"}:
        contradictions.append(
            {
                "code": "freelancer_vs_employment_dues",
                "message": "The user described a freelancer relationship but selected an employment-style payment category.",
                "severity": "high",
                "clarification_question": "You mentioned freelance/contract work, but the payment sounds like employee dues. Were you legally an employee or an independent freelancer?",
            }
        )

    if payment_type == "gratuity" and employment_end is False:
        contradictions.append(
            {
                "code": "gratuity_vs_still_employed",
                "message": "Gratuity usually depends on employment ending, but the signals indicate the user is still employed.",
                "severity": "medium",
                "clarification_question": "You mentioned gratuity but also indicated you are still working there. Has your employment actually ended?",
            }
        )

    if case_model:
        relationship_hints = " ".join(
            filter(
                None,
                [case_model.detected_relationship]
                + [p.relationship_to_client or "" for p in case_model.parties]
                + [p.role or "" for p in case_model.parties],
            )
        ).lower()
        if relationship == "freelancer" and "employer" in relationship_hints:
            contradictions.append(
                {
                    "code": "freelancer_vs_case_model_employment",
                    "message": "The case model suggests an employer-employee relationship, but the signal state says freelancer.",
                    "severity": "medium",
                    "clarification_question": "Your case model looks employment-related. Should this be treated as an employee dispute or a freelance contract dispute?",
                }
            )

    if facts.get("status") is True and employment_end is False and payment_type == "gratuity":
        contradictions.append(
            {
                "code": "active_status_vs_gratuity",
                "message": "The stored facts imply active employment while the payment signal points to gratuity.",
                "severity": "medium",
                "clarification_question": "Are you claiming unpaid salary while still employed, or gratuity after your employment ended?",
            }
        )

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in contradictions:
        code = item["code"]
        if code not in seen:
            deduped.append(item)
            seen.add(code)
    return deduped


def contradiction_penalty(contradictions: List[Dict[str, Any]]) -> float:
    if not contradictions:
        return 1.0
    high = sum(1 for c in contradictions if c.get("severity") == "high")
    medium = sum(1 for c in contradictions if c.get("severity") == "medium")
    penalty = 1.0 - (0.2 * high) - (0.1 * medium)
    return max(0.5, round(penalty, 2))


def summarize_signal_state(signal_state: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return {
        name: {
            "value": payload.get("value"),
            "user_confidence": round(float(payload.get("user_confidence", 0.0)), 2),
            "confirmed": bool(payload.get("confirmed")),
            "source": payload.get("source", "query"),
        }
        for name, payload in (signal_state or {}).items()
    }


def choose_confirmation_question(
    signal_state: Dict[str, Dict[str, Any]],
    asked_questions: List[str],
) -> Optional[Dict[str, Any]]:
    priority_signals = ["payment_type", "employment_end", "work_relationship"]
    ordered_names = priority_signals + [name for name in (signal_state or {}).keys() if name not in priority_signals]
    for signal_name in ordered_names:
        payload = (signal_state or {}).get(signal_name)
        if not payload:
            continue
        if payload.get("confirmed"):
            continue
        question_id = f"confirm_{signal_name}"
        if question_id in (asked_questions or []):
            continue
        return {
            "id": question_id,
            "signal_name": signal_name,
            "question": f"Are you sure about this: {signal_name.replace('_', ' ')} = {payload.get('value')}?",
        }
    return None


def _top_law_signature(res: LawEngineResponse) -> Tuple[str, float]:
    if not res.applicable_laws:
        return ("", 0.0)
    top = res.applicable_laws[0]
    return (f"{top.law}:{top.section}", float(top.final_score))


def rank_signal_questions(
    laws_response: LawEngineResponse,
    case_model: CaseModel,
    brain_response: Any,
    law_engine: Any,
    current_confirmed_tags: List[str],
    confirmed_tag_confidence: Dict[str, float],
    signal_state: Dict[str, Dict[str, Any]],
    contradictions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    missing_signals = (laws_response.uncertainty.missing_signals if laws_response.uncertainty else []) or []
    top_tags = (laws_response.uncertainty.top_tags if laws_response.uncertainty else []) or []
    if not missing_signals:
        return candidates

    base_signature, base_score = _top_law_signature(laws_response)
    ranking_uncertainty = 1.0
    if laws_response.uncertainty and laws_response.uncertainty.confidence:
        top_scores = laws_response.uncertainty.confidence
        if len(top_scores) > 1:
            gap = abs(top_scores[0] - top_scores[1])
            ranking_uncertainty = round(max(0.15, 1.0 - min(gap, 1.0)), 2)
        else:
            ranking_uncertainty = round(max(0.2, 1.0 - min(top_scores[0], 1.0)), 2)

    for tag in top_tags:
        for sig_def in get_signals_for_tag(tag):
            if sig_def.signal_name not in missing_signals:
                continue
            if signal_state.get(sig_def.signal_name):
                continue

            impacts: List[float] = []
            for option in sig_def.options:
                hypothetical_tags = list(dict.fromkeys(current_confirmed_tags + [option.refined_tag]))
                hypothetical_conf = dict(confirmed_tag_confidence)
                hypothetical_conf[option.refined_tag] = 1.0
                hypothetical = law_engine.map_laws(
                    case_model,
                    brain_response,
                    confirmed_tags=hypothetical_tags,
                    confirmed_tag_confidence=hypothetical_conf,
                    contradiction_penalty=contradiction_penalty(contradictions),
                )
                option_signature, option_score = _top_law_signature(hypothetical)
                changed_top = 1.0 if option_signature and option_signature != base_signature else 0.0
                score_delta = abs(option_score - base_score)
                impacts.append(max(changed_top, round(score_delta, 3)))

            impact_on_ranking = round(max(impacts or [0.0]), 3)
            priority_score = round(impact_on_ranking * ranking_uncertainty, 3)
            candidates.append(
                {
                    "id": f"signal_{sig_def.signal_name}",
                    "question": sig_def.question,
                    "signal_name": sig_def.signal_name,
                    "source_tag": tag,
                    "impact_on_ranking": impact_on_ranking,
                    "uncertainty": ranking_uncertainty,
                    "priority_score": priority_score,
                    "options": [opt.label for opt in sig_def.options],
                }
            )

    candidates.sort(key=lambda item: (-item["priority_score"], -item["impact_on_ranking"], item["question"]))
    return candidates


def analyze_interaction_logs(log_path: str, days: int = 7) -> Dict[str, Any]:
    if not os.path.exists(log_path):
        return {
            "window_days": days,
            "entries": 0,
            "questions_improving_accuracy": [],
            "signals_most_impactful": [],
            "confusion_hotspots": [],
        }

    cutoff = datetime.utcnow() - timedelta(days=days)
    question_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"asked": 0, "law_changed": 0})
    signal_counter: Counter = Counter()
    confusion_counter: Counter = Counter()
    entries = 0

    with open(log_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = row.get("timestamp")
            if ts and ts != "@timestamp":
                try:
                    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if parsed.replace(tzinfo=None) < cutoff:
                        continue
                except ValueError:
                    pass

            entries += 1
            question = row.get("question_asked") or row.get("question_id") or "unknown"
            question_stats[question]["asked"] += 1
            if row.get("law_changed"):
                question_stats[question]["law_changed"] += 1

            for signal_name in row.get("signals", {}).keys():
                signal_counter[signal_name] += 1

            for contradiction in row.get("contradictions", []):
                confusion_counter[contradiction.get("code", "unknown")] += 1

            if row.get("user_confidence", 1.0) < 0.5:
                confusion_counter["low_user_confidence"] += 1

    improving_questions = []
    for question, stats in question_stats.items():
        asked = stats["asked"]
        if asked == 0:
            continue
        improving_questions.append(
            {
                "question": question,
                "asked": asked,
                "law_change_rate": round(stats["law_changed"] / asked, 3),
            }
        )
    improving_questions.sort(key=lambda item: (-item["law_change_rate"], -item["asked"], item["question"]))

    signals_most_impactful = [
        {"signal": name, "count": count}
        for name, count in signal_counter.most_common(5)
    ]
    confusion_hotspots = [
        {"topic": name, "count": count}
        for name, count in confusion_counter.most_common(5)
    ]

    return {
        "window_days": days,
        "entries": entries,
        "questions_improving_accuracy": improving_questions[:5],
        "signals_most_impactful": signals_most_impactful,
        "confusion_hotspots": confusion_hotspots,
    }


def build_log_entry(
    question_id: str,
    question_text: str,
    signal_state: Dict[str, Dict[str, Any]],
    contradictions: List[Dict[str, Any]],
    previous_top_law: Optional[str],
    current_top_law: Optional[str],
    user_confidence: Optional[float] = None,
) -> Dict[str, Any]:
    return {
        "timestamp": _utc_now_iso(),
        "question_id": question_id,
        "question_asked": question_text,
        "signals": summarize_signal_state(signal_state),
        "contradictions": contradictions,
        "law_changed": bool(previous_top_law and current_top_law and previous_top_law != current_top_law),
        "previous_top_law": previous_top_law,
        "current_top_law": current_top_law,
        "user_confidence": user_confidence,
    }


def append_interaction_log(log_path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
