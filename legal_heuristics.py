"""
Legal Heuristic Engine — Phase 2

Maps facts → applicable laws + remedies based on keyword detection.
Runs BEFORE or ALONGSIDE retrieval to give the LLM legal priors
even when RAG retrieval is weak or empty.
"""

from typing import Any, Dict, List


# =====================================================
# STEP 1: HEURISTIC MAPPING — FACTS → LAWS + REMEDIES
# =====================================================

LEGAL_HEURISTICS: Dict[str, Dict[str, Any]] = {

    # ---------- LABOUR / EMPLOYMENT ----------

    "salary unpaid": {
        "laws": [
            "Payment of Wages Act, 1936",
            "Code on Wages, 2019",
            "Industrial Disputes Act, 1947",
        ],
        "remedies": [
            "Approach Labour Commissioner",
            "File claim before Labour Court",
            "Send legal notice to employer under Section 15 of Payment of Wages Act",
        ],
        "keywords": ["salary", "wages", "unpaid", "non-payment", "salary not paid", "wages not paid"],
    },

    "wrongful termination": {
        "laws": [
            "Industrial Disputes Act, 1947 — Sections 25-F, 25-G, 25-N",
            "Shops and Establishments Act (state-specific)",
            "Industrial Relations Code, 2020",
        ],
        "remedies": [
            "File dispute before Labour Court / Industrial Tribunal",
            "Claim reinstatement or back-wages compensation",
            "Send legal notice to employer demanding compliance",
        ],
        "keywords": ["termination", "fired", "dismissed", "sacked", "wrongful termination", "illegal termination"],
    },

    "gratuity": {
        "laws": [
            "Payment of Gratuity Act, 1972",
        ],
        "remedies": [
            "File application before Controlling Authority under Section 7",
            "Appeal to Appellate Authority if denied",
        ],
        "keywords": ["gratuity", "gratuity not paid", "gratuity denied"],
    },

    "provident fund": {
        "laws": [
            "Employees' Provident Funds and Miscellaneous Provisions Act, 1952",
        ],
        "remedies": [
            "File complaint with EPFO (Employees' Provident Fund Organisation)",
            "Approach EPF Appellate Tribunal",
        ],
        "keywords": ["provident fund", "pf", "epf", "pf not deposited", "employer not depositing pf"],
    },

    # ---------- CRIMINAL ----------

    "cheque bounce": {
        "laws": [
            "Negotiable Instruments Act, 1881 — Section 138",
        ],
        "remedies": [
            "Send demand notice within 30 days of receiving 'return memo' from bank",
            "If not paid within 15 days of notice, file criminal complaint under Section 138 in Magistrate Court",
            "Complaint must be filed within 1 month of expiry of 15-day notice period",
        ],
        "keywords": ["cheque", "check", "bounce", "dishonour", "dishonor", "cheque bounce", "bounced cheque"],
    },

    "theft": {
        "laws": [
            "Bharatiya Nyaya Sanhita, 2023 (BNS) — Sections 303-305 (replacing IPC Sections 378-382)",
            "Indian Penal Code, 1860 — Section 378 (if offence before 1 July 2024)",
        ],
        "remedies": [
            "File FIR at nearest Police Station",
            "If police refuses, approach Superintendent of Police or Magistrate under Section 175(3) BNSS / Section 156(3) CrPC",
        ],
        "keywords": ["theft", "stole", "stolen", "robbery", "burglary", "loot"],
    },

    "assault": {
        "laws": [
            "Bharatiya Nyaya Sanhita, 2023 (BNS) — Sections 115-117 (replacing IPC Sections 351-358)",
            "Indian Penal Code, 1860 — Sections 351-358 (if offence before 1 July 2024)",
        ],
        "remedies": [
            "File FIR immediately",
            "Get medico-legal certificate (MLC) from hospital",
            "File private complaint before Magistrate if FIR refused",
        ],
        "keywords": ["assault", "attack", "beaten", "hit", "physically attacked", "hurt", "grievous hurt"],
    },

    "murder": {
        "laws": [
            "Bharatiya Nyaya Sanhita, 2023 (BNS) — Section 101 (replacing IPC Section 302)",
            "Indian Penal Code, 1860 — Section 302 (if offence before 1 July 2024)",
        ],
        "remedies": [
            "File FIR immediately — cognizable, non-bailable offence",
            "Police is bound to investigate",
        ],
        "keywords": ["murder", "homicide", "killed", "killing"],
    },

    "rape": {
        "laws": [
            "Bharatiya Nyaya Sanhita, 2023 (BNS) — Sections 63-69 (replacing IPC Section 376)",
            "POCSO Act, 2012 (if victim is minor)",
        ],
        "remedies": [
            "File FIR — zero FIR can be filed at ANY police station",
            "Medical examination within 24 hours",
            "Victim has right to legal aid and privacy protection",
        ],
        "keywords": ["rape", "sexual assault", "molestation", "sexual harassment"],
    },

    "bail": {
        "laws": [
            "Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS) — Sections 478-484 (replacing CrPC Sections 436-439)",
            "Code of Criminal Procedure, 1973 — Sections 436-439 (if proceedings before 1 July 2024)",
        ],
        "remedies": [
            "Apply for bail before concerned Magistrate or Sessions Court",
            "For non-bailable offence, apply under Section 480 BNSS / Section 437 CrPC",
            "Can approach High Court under Section 482 BNSS / Section 439 CrPC if lower court denies",
        ],
        "keywords": ["bail", "anticipatory bail", "regular bail", "interim bail"],
    },

    "fir": {
        "laws": [
            "Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS) — Section 173 (replacing CrPC Section 154)",
        ],
        "remedies": [
            "Go to nearest police station and insist on written FIR",
            "If police refuses, send complaint by registered post to Superintendent of Police",
            "Approach Magistrate under Section 175(3) BNSS / Section 156(3) CrPC for direction to register FIR",
        ],
        "keywords": ["fir", "police complaint", "police report", "file fir", "lodge fir", "police not filing fir"],
    },

    "cyber crime": {
        "laws": [
            "Information Technology Act, 2000 — Sections 43, 66, 66C, 66D, 67",
            "Bharatiya Nyaya Sanhita, 2023 (BNS) — Sections relevant to cheating, identity theft",
        ],
        "remedies": [
            "Report on National Cyber Crime Reporting Portal (cybercrime.gov.in)",
            "File FIR at Cyber Crime Police Station",
            "Preserve all digital evidence (screenshots, URLs, emails)",
        ],
        "keywords": ["cyber", "hacking", "online fraud", "phishing", "identity theft", "cyber crime",
                     "data breach", "online scam", "upi fraud"],
    },

    "defamation": {
        "laws": [
            "Bharatiya Nyaya Sanhita, 2023 (BNS) — Sections 356-358 (replacing IPC Sections 499-500)",
            "Indian Penal Code, 1860 — Sections 499-500 (criminal defamation)",
            "Law of Torts (civil defamation)",
        ],
        "remedies": [
            "Send cease-and-desist legal notice",
            "File criminal complaint before Magistrate (for criminal defamation)",
            "File civil suit for damages and injunction",
        ],
        "keywords": ["defamation", "defame", "slander", "libel", "false accusation", "reputation"],
    },

    # ---------- CONSUMER ----------

    "consumer complaint": {
        "laws": [
            "Consumer Protection Act, 2019",
            "Consumer Protection (E-Commerce) Rules, 2020",
        ],
        "remedies": [
            "File complaint before District Consumer Disputes Redressal Commission (up to ₹1 crore)",
            "State Commission (₹1 crore to ₹10 crore)",
            "National Commission (above ₹10 crore)",
            "File online at edaakhil.nic.in",
        ],
        "keywords": ["consumer", "defective product", "deficient service", "refund", "warranty",
                     "consumer complaint", "unfair trade"],
    },

    # ---------- PROPERTY / TENANCY ----------

    "tenant deposit": {
        "laws": [
            "Transfer of Property Act, 1882 — Sections 105-117",
            "Indian Contract Act, 1872",
            "Specific Relief Act, 1963",
            "State Rent Control Act (state-specific)",
        ],
        "remedies": [
            "Send legal notice to landlord demanding refund of security deposit",
            "File suit for recovery in Civil Court",
            "If amount is below ₹1 crore, can file under Consumer Protection Act, 2019 also",
        ],
        "keywords": ["security deposit", "deposit refund", "landlord refusing", "tenant deposit",
                     "landlord not returning deposit", "rent deposit"],
    },

    "eviction": {
        "laws": [
            "Transfer of Property Act, 1882 — Sections 106, 111",
            "State Rent Control Act (state-specific)",
        ],
        "remedies": [
            "Tenant can challenge illegal eviction in Civil Court",
            "Seek stay/injunction",
            "If locked out, file police complaint for criminal intimidation",
        ],
        "keywords": ["eviction", "evict", "vacate", "locked out", "thrown out", "illegal eviction"],
    },

    "property dispute": {
        "laws": [
            "Transfer of Property Act, 1882",
            "Indian Registration Act, 1908",
            "Specific Relief Act, 1963",
            "Limitation Act, 1963",
        ],
        "remedies": [
            "File civil suit for declaration, injunction, or specific performance",
            "Check title documents and encumbrance certificate",
            "Verify limitation period (typically 3-12 years depending on nature of suit)",
        ],
        "keywords": ["property dispute", "land dispute", "title dispute", "encroachment", "illegal possession",
                     "property fraud", "real estate fraud"],
    },

    # ---------- FAMILY / MATRIMONIAL ----------

    "divorce": {
        "laws": [
            "Hindu Marriage Act, 1955 — Sections 13, 13B (if Hindu/Sikh/Jain/Buddhist)",
            "Special Marriage Act, 1954 — Section 27 (if inter-faith or civil marriage)",
            "Dissolution of Muslim Marriages Act, 1939 (if Muslim)",
            "Indian Divorce Act, 1869 (if Christian)",
        ],
        "remedies": [
            "File petition for divorce in Family Court",
            "Mutual consent divorce under Section 13B (minimum 6-month cooling period)",
            "Contested divorce on grounds of cruelty, adultery, desertion, etc.",
        ],
        "keywords": ["divorce", "separation", "mutual consent divorce", "contested divorce"],
    },

    "domestic violence": {
        "laws": [
            "Protection of Women from Domestic Violence Act, 2005",
            "Bharatiya Nyaya Sanhita, 2023 (BNS) — Section 85-86 (replacing IPC Section 498A)",
            "Indian Penal Code, 1860 — Section 498A (if offence before 1 July 2024)",
        ],
        "remedies": [
            "File complaint before Protection Officer or Magistrate",
            "Seek protection order, residence order, monetary relief",
            "File FIR for criminal prosecution",
        ],
        "keywords": ["domestic violence", "cruelty by husband", "dowry harassment", "498a",
                     "wife beating", "marital cruelty"],
    },

    "maintenance alimony": {
        "laws": [
            "Hindu Adoptions and Maintenance Act, 1956 — Section 18",
            "Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS) — Section 144 (replacing CrPC Section 125)",
            "Code of Criminal Procedure, 1973 — Section 125",
            "Protection of Women from Domestic Violence Act, 2005 — Section 20",
        ],
        "remedies": [
            "File application for maintenance before Family Court",
            "File under Section 144 BNSS / 125 CrPC for immediate maintenance",
            "Interim maintenance can be sought while case is pending",
        ],
        "keywords": ["maintenance", "alimony", "wife maintenance", "child maintenance",
                     "husband not paying maintenance"],
    },

    "child custody": {
        "laws": [
            "Guardians and Wards Act, 1890",
            "Hindu Minority and Guardianship Act, 1956",
        ],
        "remedies": [
            "File petition for custody/guardianship in Family Court / District Court",
            "Court decides based on 'welfare of the child' principle",
        ],
        "keywords": ["custody", "child custody", "guardianship", "visitation rights"],
    },

    # ---------- CONTRACT ----------

    "breach of contract": {
        "laws": [
            "Indian Contract Act, 1872 — Sections 73, 74, 75",
            "Specific Relief Act, 1963",
        ],
        "remedies": [
            "Send legal notice claiming damages",
            "File civil suit for damages or specific performance",
            "If amount is below ₹1 crore, consider arbitration clause if present",
        ],
        "keywords": ["breach of contract", "contract broken", "agreement violated", "contract dispute"],
    },

    # ---------- MOTOR ACCIDENT ----------

    "motor accident": {
        "laws": [
            "Motor Vehicles Act, 1988 — Sections 140, 163A, 166",
        ],
        "remedies": [
            "File claim before Motor Accident Claims Tribunal (MACT)",
            "No-fault liability claim under Section 140 (up to ₹50,000 for injury, ₹2,00,000 for death)",
            "Claim compensation under Section 166 based on income, age, dependency",
        ],
        "keywords": ["accident", "road accident", "motor accident", "hit and run", "vehicle accident",
                     "insurance claim accident"],
    },

    # ---------- RTI ----------

    "rti": {
        "laws": [
            "Right to Information Act, 2005 — Sections 6, 7, 19",
        ],
        "remedies": [
            "File RTI application with ₹10 fee to Public Information Officer (PIO)",
            "If no reply in 30 days, file First Appeal to First Appellate Authority",
            "If still unsatisfied, file Second Appeal to Central/State Information Commission",
        ],
        "keywords": ["rti", "right to information", "information request", "public information"],
    },

    # ---------- DOWRY ----------

    "dowry": {
        "laws": [
            "Dowry Prohibition Act, 1961",
            "Bharatiya Nyaya Sanhita, 2023 (BNS) — Sections 80, 85-86 (replacing IPC Sections 304B, 498A)",
            "Indian Penal Code, 1860 — Sections 304B, 498A",
        ],
        "remedies": [
            "File FIR at police station",
            "File complaint before Dowry Prohibition Officer",
            "Seek protection under Domestic Violence Act, 2005",
        ],
        "keywords": ["dowry", "dowry demand", "dowry death", "dahej"],
    },

    # ---------- WRIT / CONSTITUTIONAL ----------

    "fundamental rights": {
        "laws": [
            "Constitution of India — Articles 14-32 (Fundamental Rights)",
            "Constitution of India — Article 32 (Supreme Court writ jurisdiction)",
            "Constitution of India — Article 226 (High Court writ jurisdiction)",
        ],
        "remedies": [
            "File writ petition (Habeas Corpus, Mandamus, Prohibition, Certiorari, Quo Warranto) in High Court or Supreme Court",
            "Public Interest Litigation (PIL) if matter affects public at large",
        ],
        "keywords": ["fundamental rights", "writ petition", "article 21", "right to life",
                     "right to equality", "habeas corpus", "mandamus", "pil"],
    },

    # ---------- CHEATING / FRAUD ----------

    "cheating fraud": {
        "laws": [
            "Bharatiya Nyaya Sanhita, 2023 (BNS) — Sections 318-320 (replacing IPC Sections 415-420)",
            "Indian Penal Code, 1860 — Sections 415-420 (if offence before 1 July 2024)",
        ],
        "remedies": [
            "File FIR for cheating",
            "File civil suit for recovery of money with interest",
            "Attach property of accused through court order if flight risk",
        ],
        "keywords": ["cheating", "fraud", "scam", "deceived", "cheated", "money fraud", "financial fraud"],
    },

    # ---------- ARBITRATION ----------

    "arbitration": {
        "laws": [
            "Arbitration and Conciliation Act, 1996",
        ],
        "remedies": [
            "Invoke arbitration clause in the contract",
            "Apply to court under Section 9 for interim measures",
            "Challenge arbitral award under Section 34",
        ],
        "keywords": ["arbitration", "arbitration clause", "arbitral award", "mediation", "conciliation"],
    },

    # ---------- SEXUAL HARASSMENT AT WORKPLACE ----------

    "sexual harassment workplace": {
        "laws": [
            "Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013",
        ],
        "remedies": [
            "File complaint with Internal Complaints Committee (ICC) within 3 months",
            "If no ICC, file with Local Complaints Committee (LCC)",
            "Can also file FIR for criminal proceedings",
        ],
        "keywords": ["sexual harassment workplace", "posh", "workplace harassment",
                     "icc complaint", "harassment at office"],
    },

    # ---------- LAND ACQUISITION ----------

    "land acquisition": {
        "laws": [
            "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act, 2013 (LARR Act)",
        ],
        "remedies": [
            "File objection during Social Impact Assessment (SIA) stage",
            "Challenge inadequate compensation before Reference Court",
            "Approach High Court under Article 226 for illegal acquisition",
        ],
        "keywords": ["land acquisition", "government taking land", "acquisition compensation",
                     "eminent domain", "compulsory acquisition"],
    },
}


# =====================================================
# STEP 2: MATCHING LOGIC
# =====================================================

def match_heuristics(query: str) -> List[Dict[str, Any]]:
    """Match user query against legal heuristics.

    Returns a list of matching heuristic entries with their keys.
    Runs in O(keywords) — fast enough to be called on every request.
    """
    query_lower = query.lower()
    matches: List[Dict[str, Any]] = []
    seen_keys: set = set()

    for key, value in LEGAL_HEURISTICS.items():
        if key in seen_keys:
            continue
        for kw in value["keywords"]:
            if kw in query_lower:
                matches.append({
                    "heuristic_key": key,
                    "laws": value["laws"],
                    "remedies": value["remedies"],
                    "matched_keyword": kw,
                })
                seen_keys.add(key)
                break

    return matches


def format_heuristics_for_prompt(matches: List[Dict[str, Any]]) -> str:
    """Format matched heuristics into a text block for LLM prompt injection."""
    if not matches:
        return ""

    lines = ["Known Legal Signals (from legal knowledge base):"]
    for match in matches:
        lines.append(f"\n  Area: {match['heuristic_key'].replace('_', ' ').title()}")
        lines.append("  Applicable Laws:")
        for law in match["laws"]:
            lines.append(f"    - {law}")
        lines.append("  Available Remedies:")
        for remedy in match["remedies"]:
            lines.append(f"    - {remedy}")

    return "\n".join(lines)


def format_heuristics_for_debug(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compact format for debug/log output."""
    return [
        {
            "key": m["heuristic_key"],
            "matched_keyword": m["matched_keyword"],
            "laws_count": len(m["laws"]),
            "remedies_count": len(m["remedies"]),
        }
        for m in matches
    ]
