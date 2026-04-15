"""
Legal Notice Generation Engine — Phase 3+

Generates professional Indian legal notices from structured input.
Uses:
- Legal heuristics (Phase 2) for claim → law mapping
- RAG retrieval for supporting legal context
- Dual-generation (Phase 3) for quality
- Citation injection for authority
"""

import re
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from legal_heuristics import match_heuristics, format_heuristics_for_prompt


# =====================================================
# STEP 1: NOTICE TYPE DEFINITIONS
# =====================================================

NOTICE_TYPES = {
    "unpaid_salary": {
        "label": "Unpaid Salary / Wages",
        "laws": [
            "Payment of Wages Act, 1936",
            "Code on Wages, 2019",
            "Industrial Disputes Act, 1947 — Section 33C",
        ],
        "relief": [
            "Immediate payment of all outstanding salary/wages",
            "Interest on delayed payment as per applicable rates",
            "Compensation for mental harassment and financial distress",
        ],
        "deadline_days": 15,
        "keywords": ["salary", "wages", "unpaid", "non-payment"],
    },
    "cheque_bounce": {
        "label": "Cheque Bounce / Dishonour",
        "laws": [
            "Negotiable Instruments Act, 1881 — Section 138",
            "Negotiable Instruments Act, 1881 — Section 141 (company liability)",
        ],
        "relief": [
            "Payment of the cheque amount in full",
            "Interest on the dishonoured amount",
            "Compensation for legal costs incurred",
        ],
        "deadline_days": 15,
        "keywords": ["cheque", "bounce", "dishonour", "dishonor"],
    },
    "wrongful_termination": {
        "label": "Wrongful Termination",
        "laws": [
            "Industrial Disputes Act, 1947 — Sections 25-F, 25-G, 25-N",
            "Shops and Establishments Act (state-specific)",
        ],
        "relief": [
            "Reinstatement to the original position",
            "Payment of back wages from the date of termination",
            "Compensation for wrongful and illegal termination",
        ],
        "deadline_days": 30,
        "keywords": ["termination", "fired", "dismissed", "sacked"],
    },
    "tenant_deposit_refund": {
        "label": "Security Deposit Refund",
        "laws": [
            "Transfer of Property Act, 1882 — Sections 105-117",
            "Indian Contract Act, 1872",
            "Specific Relief Act, 1963",
        ],
        "relief": [
            "Immediate refund of the security deposit amount",
            "Interest on the withheld deposit amount",
        ],
        "deadline_days": 15,
        "keywords": ["deposit", "refund", "landlord", "tenant"],
    },
    "breach_of_contract": {
        "label": "Breach of Contract",
        "laws": [
            "Indian Contract Act, 1872 — Sections 73, 74, 75",
            "Specific Relief Act, 1963",
        ],
        "relief": [
            "Specific performance of the contract obligations",
            "Compensation for damages suffered due to the breach",
            "Interest on any outstanding amounts",
        ],
        "deadline_days": 15,
        "keywords": ["breach", "contract", "agreement", "violated"],
    },
    "consumer_complaint": {
        "label": "Consumer Complaint Notice",
        "laws": [
            "Consumer Protection Act, 2019",
            "Consumer Protection (E-Commerce) Rules, 2020",
        ],
        "relief": [
            "Replacement or refund of the defective product/service",
            "Compensation for deficiency in service",
            "Compensation for mental agony and inconvenience",
        ],
        "deadline_days": 15,
        "keywords": ["consumer", "defective", "refund", "warranty", "product"],
    },
    "recovery_of_money": {
        "label": "Recovery of Money / Debt",
        "laws": [
            "Indian Contract Act, 1872",
            "Order XXXVII of the Code of Civil Procedure, 1908",
        ],
        "relief": [
            "Immediate repayment of the outstanding amount",
            "Interest at the agreed rate or prevailing commercial rate",
        ],
        "deadline_days": 15,
        "keywords": ["money", "debt", "loan", "recovery", "repay"],
    },
    "defamation": {
        "label": "Defamation Notice",
        "laws": [
            "Bharatiya Nyaya Sanhita, 2023 — Sections 356-358",
            "Indian Penal Code, 1860 — Sections 499-500 (if prior to 1 July 2024)",
            "Law of Torts — Civil Defamation",
        ],
        "relief": [
            "Immediate removal of the defamatory content",
            "Public apology and retraction",
            "Compensation for damage to reputation",
        ],
        "deadline_days": 7,
        "keywords": ["defamation", "defame", "slander", "libel"],
    },
    "eviction": {
        "label": "Eviction Notice",
        "laws": [
            "Transfer of Property Act, 1882 — Section 106",
            "State Rent Control Act (state-specific)",
        ],
        "relief": [
            "Vacate the premises within the stipulated period",
            "Payment of all outstanding rent and dues",
            "Restoration of the property in its original condition",
        ],
        "deadline_days": 30,
        "keywords": ["eviction", "vacate", "tenant", "premises"],
    },
    "rent_arrears": {
        "label": "Rent Arrears Recovery Notice",
        "laws": [
            "Transfer of Property Act, 1882 - Section 108",
            "State Rent Control Act (state-specific)",
            "Code of Civil Procedure, 1908",
        ],
        "relief": [
            "Payment of all outstanding rent arrears",
            "Interest on delayed rent as per agreement/law",
            "Compliance with tenancy obligations within the notice period",
        ],
        "deadline_days": 15,
        "keywords": ["rent", "arrears", "unpaid rent", "rent due", "defaulted rent"],
    },
    "maintenance_nonpayment": {
        "label": "Maintenance / Alimony Non-Payment Notice",
        "laws": [
            "Bharatiya Nagarik Suraksha Sanhita, 2023 - Section 144",
            "Hindu Marriage Act, 1955 - Sections 24, 25",
            "Protection of Women from Domestic Violence Act, 2005 - Section 20",
        ],
        "relief": [
            "Immediate payment of pending maintenance/alimony dues",
            "Clear schedule for future monthly payments",
            "Interest/compensation for delayed compliance",
        ],
        "deadline_days": 15,
        "keywords": ["maintenance", "alimony", "monthly support", "maintenance due", "spousal support"],
    },
    "ip_infringement": {
        "label": "Intellectual Property Infringement Notice",
        "laws": [
            "Trade Marks Act, 1999",
            "Copyright Act, 1957",
            "Patents Act, 1970 (where applicable)",
        ],
        "relief": [
            "Immediate cease-and-desist from infringing use",
            "Removal of infringing content/products from all channels",
            "Disclosure of profits earned and compensation for losses",
        ],
        "deadline_days": 7,
        "keywords": ["trademark", "copyright", "infringement", "piracy", "counterfeit", "brand misuse"],
    },
    "cyber_fraud": {
        "label": "Cyber Fraud / Online Scam Notice",
        "laws": [
            "Information Technology Act, 2000",
            "Bharatiya Nyaya Sanhita, 2023 - cheating and cyber-related offences",
            "RBI digital payment and grievance directions (where applicable)",
        ],
        "relief": [
            "Immediate reversal/refund of fraudulently transferred amount",
            "Preservation of logs, transaction records, and device metadata",
            "Formal confirmation of fraud investigation and action taken",
        ],
        "deadline_days": 7,
        "keywords": ["cyber fraud", "online scam", "phishing", "upi fraud", "otp fraud", "unauthorized transaction"],
    },
    "data_privacy_breach": {
        "label": "Data Privacy Breach Notice",
        "laws": [
            "Digital Personal Data Protection Act, 2023",
            "Information Technology Act, 2000",
            "Information Technology (Reasonable Security Practices and Procedures and Sensitive Personal Data or Information) Rules, 2011",
        ],
        "relief": [
            "Disclosure of the nature and scope of personal data breach",
            "Immediate remedial security controls and user protection measures",
            "Compensation for losses and distress caused by data misuse",
        ],
        "deadline_days": 10,
        "keywords": ["data breach", "privacy", "personal data leak", "data leak", "unauthorized access"],
    },
    "workplace_harassment": {
        "label": "Workplace Harassment Notice",
        "laws": [
            "Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013",
            "Industrial Employment and service rules (where applicable)",
            "Bharatiya Nyaya Sanhita, 2023 (where criminal intimidation/assault is involved)",
        ],
        "relief": [
            "Immediate cessation of harassment and retaliatory actions",
            "Initiation of lawful internal inquiry/ICC process",
            "Protection of complainant and compensation as per law",
        ],
        "deadline_days": 7,
        "keywords": ["harassment", "workplace harassment", "sexual harassment", "hostile workplace", "intimidation at work"],
    },
    "builder_delay": {
        "label": "Builder Delay / Possession Notice",
        "laws": [
            "Real Estate (Regulation and Development) Act, 2016",
            "Consumer Protection Act, 2019",
            "Indian Contract Act, 1872",
        ],
        "relief": [
            "Immediate handover of possession with occupancy formalities",
            "Interest/compensation for delayed possession period",
            "Refund with interest if possession is not delivered",
        ],
        "deadline_days": 15,
        "keywords": ["builder delay", "delayed possession", "rera", "flat possession", "real estate project delay"],
    },
    "title_ownership_dispute": {
        "label": "Property Title / Ownership Dispute Notice",
        "laws": [
            "Transfer of Property Act, 1882",
            "Specific Relief Act, 1963",
            "Registration Act, 1908",
        ],
        "relief": [
            "Immediate cessation of interference with lawful ownership/possession",
            "Rectification of records and title-related defects",
            "Compensation for loss arising from unlawful claims or obstruction",
        ],
        "deadline_days": 15,
        "keywords": ["title dispute", "ownership dispute", "property title", "mutation dispute", "encumbrance issue"],
    },
    "general": {
        "label": "General Legal Notice",
        "laws": [],
        "relief": [],
        "deadline_days": 15,
        "keywords": [],
    },
}


def get_available_notice_types() -> List[Dict[str, str]]:
    """Return the list of available notice types for the frontend dropdown."""
    return [
        {"id": key, "label": val["label"]}
        for key, val in NOTICE_TYPES.items()
        if key != "general"
    ]


def auto_detect_notice_type(claim: str, facts: List[str]) -> str:
    """Auto-detect the best notice type from the claim and facts text."""
    combined = f"{claim} {' '.join(facts)}".lower()

    best_type = "general"
    best_score = 0

    for type_id, config in NOTICE_TYPES.items():
        if type_id == "general":
            continue
        score = sum(1 for kw in config["keywords"] if kw in combined)
        if score > best_score:
            best_score = score
            best_type = type_id

    return best_type


# =====================================================
# STEP 2: NOTICE GENERATION PROMPT
# =====================================================

def build_notice_prompt(
    sender_name: str,
    advocate_name: str,
    advocate_address: str,
    advocate_mobile: str,
    advocate_email: str,
    advocate_contact: str,
    receiver_name: str,
    relationship: str,
    facts: List[str],
    claim: str,
    notice_type: str,
    jurisdiction: str = "India",
    retrieved_context: str = "",
    legal_priors: str = "",
    custom_relief: Optional[List[str]] = None,
    custom_deadline: Optional[int] = None,
    tone: str = "firm",
) -> str:
    """Build the master prompt for legal notice generation."""

    config = NOTICE_TYPES.get(notice_type, NOTICE_TYPES["general"])
    laws = config["laws"]
    relief = custom_relief or config["relief"]
    deadline = custom_deadline or config["deadline_days"]

    # Format facts as numbered list
    facts_text = "\n".join(f"  {i+1}. {fact}" for i, fact in enumerate(facts))
    laws_text = "\n".join(f"  - {law}" for law in laws) if laws else "  - To be determined based on facts"
    relief_text = "\n".join(f"  - {r}" for r in relief) if relief else "  - As per applicable law"

    tone_instruction = {
        "firm": "Use firm but professional legal language. Be direct about consequences.",
        "aggressive": "Use strong, assertive legal language. Emphasize urgency and consequences forcefully.",
        "polite": "Use polite but legally precise language. Maintain professionalism while clearly stating demands.",
    }.get(tone, "Use firm but professional legal language.")

    context_block = f"\n\nRelevant Legal Provisions (from database):\n{retrieved_context}\n" if retrieved_context else ""
    priors_block = f"\n\n{legal_priors}\n" if legal_priors else ""

    today = datetime.now().strftime("%d %B %Y")
    deadline_date = (datetime.now() + timedelta(days=deadline)).strftime("%d %B %Y")
    advocate_name_display = advocate_name or "[Your Name]"
    advocate_address_display = advocate_address or "[Your Address]"
    advocate_mobile_display = advocate_mobile or "[Your Mobile]"
    advocate_email_display = advocate_email or "[Your Email]"

    return (
        "You are a senior Indian advocate drafting a formal legal notice.\n\n"
        f"{tone_instruction}\n\n"
        "Draft a professional legal notice following this EXACT structure and ordering:\n\n"
        "---\n"
        "LEGAL NOTICE\n\n"
        f"Date: {today}\n\n"
        "To,\n"
        f"{receiver_name}\n"
        "[Address]\n\n"
        "From,\n"
        f"{sender_name}\n"
        "[Address]\n"
        "Through,\n"
        f"{advocate_name_display}, Advocate\n"
        f"{advocate_address_display}\n"
        f"Mobile: {advocate_mobile_display}\n"
        f"Email: {advocate_email_display}\n"
        "\n"
        "Subject: Legal Notice under [applicable law(s)]\n\n"
        "Sir/Madam,\n\n"
        "Under instructions from and on behalf of my client, I hereby serve upon you "
        "the following legal notice:\n\n"
        "1. INTRODUCTION\n"
        "   [State the relationship and background]\n\n"
        "2. FACTS OF THE CASE\n"
        "   [Present facts in chronological order, numbered]\n\n"
        "3. LEGAL GROUNDS\n"
        "   [Cite applicable laws with specific sections]\n"
        "   [Explain how the receiver's actions violate these laws]\n\n"
        "4. BREACH BY THE RECEIVER\n"
        "   [Clearly state what obligations were breached]\n\n"
        "5. DEMAND / RELIEF SOUGHT\n"
        "   [List specific demands clearly]\n\n"
        f"6. DEADLINE: Within {deadline} days from receipt of this notice (i.e., by {deadline_date})\n\n"
        "7. CONSEQUENCES OF NON-COMPLIANCE\n"
        "   [State clearly what legal proceedings will be initiated]\n\n"
        "---\n\n"
        "INPUT DETAILS:\n\n"
        f"Sender: {sender_name}\n"
        f"Advocate: {advocate_name or 'Not provided'}\n"
        f"Advocate Address: {advocate_address or 'Not provided'}\n"
        f"Advocate Mobile: {advocate_mobile or 'Not provided'}\n"
        f"Advocate Email: {advocate_email or 'Not provided'}\n"
        f"Advocate Contact: {advocate_contact or 'Not provided'}\n"
        f"Receiver: {receiver_name}\n"
        f"Relationship: {relationship}\n"
        f"Jurisdiction: {jurisdiction}\n"
        f"Claim Type: {config['label']}\n\n"
        f"Facts:\n{facts_text}\n\n"
        f"Applicable Laws:\n{laws_text}\n\n"
        f"Relief Sought:\n{relief_text}\n\n"
        f"Deadline: {deadline} days from receipt\n"
        f"{context_block}"
        f"{priors_block}\n"
        "IMPORTANT RULES:\n"
        "- Use ONLY Indian laws and legal terminology\n"
        "- Include specific section numbers where applicable\n"
        "- Make the notice self-contained and legally complete\n"
        "- Use formal legal language throughout\n"
        "- Do NOT include any disclaimer about being AI-generated\n"
        "- End with proper advocate signature block\n"
        "- Mention that a copy is kept for records\n"
        "- Keep the exact opening block labels: To, From, Through\n"
        "- 'Through' must always contain advocate name, advocate address, and advocate mobile (not client details)\n"
    )


def build_refinement_prompt(draft_notice: str, tone: str = "firm") -> str:
    """Build the refinement prompt for dual-pass generation."""
    tone_instruction = {
        "firm": "Maintain a firm but professional tone.",
        "aggressive": "Strengthen the assertive and urgent tone.",
        "polite": "Keep the tone polite but legally precise.",
    }.get(tone, "Maintain a firm but professional tone.")

    return (
        "You are a senior Indian advocate reviewing a draft legal notice.\n\n"
        "Refine the following legal notice by:\n"
        "1. Improving clarity and removing redundancy\n"
        "2. Strengthening legal language and references\n"
        "3. Ensuring logical flow (facts → law → breach → demand → consequence)\n"
        "4. Adding any missing legal formalities\n"
        "5. Making section citations more precise\n"
        f"6. {tone_instruction}\n"
        "7. Ensuring the deadline and consequences are clearly stated\n\n"
        "8. Preserve the exact To/From/Through opening format and label order\n\n"
        "Do NOT change the fundamental structure or facts.\n"
        "Do NOT add any AI disclaimer.\n"
        "Return the complete refined notice.\n\n"
        f"Draft Notice:\n{draft_notice}\n"
    )


def build_authority_appendix(laws: List[str], legal_priors: str = "") -> str:
    """Build the authority appendix to append after the notice body."""
    if not laws and not legal_priors:
        return ""

    lines = [
        "\n---",
        "AUTHORITIES RELIED UPON:",
        "",
    ]
    for i, law in enumerate(laws, 1):
        lines.append(f"  {i}. {law}")

    if legal_priors:
        lines.append("")
        lines.append("ADDITIONAL LEGAL FRAMEWORK:")
        lines.append(legal_priors)

    return "\n".join(lines)
