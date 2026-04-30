"""
Legal AI: Complete 5-Domain Legal Interview & Reasoning Engine

This module defines the core intelligence for:
1. Wage Dispute
2. Consumer Dispute
3. Defamation
4. Cheque Bounce (Section 138 NI Act)
5. Property Dispute (Encroachment/Title/Rent)

It implements the full 5-Phase Logic:
- Issue Detection
- Stateful Fact Extraction
- Intelligent Question Selection
- FIRAC Reasoning (Facts, Issue, Law, Analysis, Conclusion)
- Legal Notice Drafting & Case Strategy
"""

import json
import re
from typing import List, Dict, Any, Optional

from llama_legal_answer import call_llm
from legal_notice_engine import (
    NOTICE_TYPES, build_notice_prompt, build_refinement_prompt as build_notice_refinement_prompt
)

# Foundation Issue Types (Full 14 Domains)
ISSUE_TYPES = [
    "wage_dispute",
    "termination_dispute",
    "consumer_dispute",
    "defamation",
    "cheque_bounce",
    "rent_dispute",
    "eviction_issue",
    "ownership_dispute",
    "builder_delay",
    "property_fraud",
    "harassment",
    "fraud",
    "contract_dispute",
    "criminal_complaint",
    "account_hacking",
    "online_fraud",
    "identity_theft",
    "data_breach",
    "harassment_cyber"
]

ISSUE_ONTOLOGY = {
    "defamation": ["false", "defame", "posted", "reputation", "libel", "slander", "accusation"],
    "consumer_dispute": ["bought", "purchased", "defective", "not working", "refund", "item", "service"],
    "wage_dispute": ["salary", "wages", "not paid", "stipend", "pay"],
    "termination_dispute": ["fired", "terminated", "resigned", "forced resignation", "notice period"],
    "cheque_bounce": ["cheque", "bounce", "dishonour", "138", "bank return"],
    "rent_dispute": ["rent", "deposit", "landlord", "unpaid rent", "lease"],
    "eviction_issue": ["evict", "vacate", "possession", "leave house"],
    "ownership_dispute": ["ownership", "title", "ancestral", "heir", "registry"],
    "builder_delay": ["builder", "possession", "flat delay", "rera", "booking"],
    "property_fraud": ["property fraud", "fake papers", "duplicate registry"],
    "harassment": ["threat", "harass", "abuse", "workplace harassment", "bullying"],
    "fraud": ["fraud", "cheat", "scam", "money stolen", "transaction"],
    "contract_dispute": ["agreement", "contract", "breach", "claus", "signed"],
    "criminal_complaint": ["theft", "assault", "police", "robbery", "crime"],
    "account_hacking": ["hacked", "unauthorized access", "login issue", "password changed", "instagram", "facebook"],
    "online_fraud": ["money lost", "scam", "fraud", "upi", "gpay", "phishing", "cheated online"],
    "identity_theft": ["fake account", "impersonation", "stole my identity", "using my photo"],
    "data_breach": ["data leaked", "privacy", "information stolen", "records exposed"],
    "harassment_cyber": ["online abuse", "cyber bullying", "stalking", "mutilated photos"]
}

# Structured Question Database (Full 10 Domains)
QUESTION_DB = [
    # 1. Wage Dispute
    {"id": "wd_txn_1", "question": "Are you currently employed or have you been terminated?", "issue_type": "wage_dispute", "category": "transaction", "priority": 1, "required": True, "fact_key": "status"},
    {"id": "wd_issue_1", "question": "How many months of salary are unpaid?", "issue_type": "wage_dispute", "category": "issue", "priority": 1, "required": True, "fact_key": "months_unpaid"},
    {"id": "wd_issue_2", "question": "What is the total amount due?", "issue_type": "wage_dispute", "category": "issue", "priority": 1, "required": True, "fact_key": "amount"},
    {"id": "wd_evd_1", "question": "Do you have proof of salary (slips, bank statements)?", "issue_type": "wage_dispute", "category": "evidence", "priority": 1, "required": True, "fact_key": "proof"},
    {"id": "wd_op_1", "question": "Has your employer responded to your requests for payment?", "issue_type": "wage_dispute", "category": "opposite_party", "priority": 2, "required": False, "fact_key": "response"},

    # 2. Termination Dispute
    {"id": "td_issue_1", "question": "Were you terminated or forced to resign?", "issue_type": "termination_dispute", "category": "issue", "priority": 1, "required": True, "fact_key": "type"},
    {"id": "td_issue_2", "question": "Was any notice period given as per your contract?", "issue_type": "termination_dispute", "category": "issue", "priority": 1, "required": True, "fact_key": "notice"},
    {"id": "td_txn_1", "question": "Do you have a copy of your employment contract?", "issue_type": "termination_dispute", "category": "transaction", "priority": 1, "required": True, "fact_key": "contract"},
    {"id": "td_txn_2", "question": "What reason did the employer give for termination?", "issue_type": "termination_dispute", "category": "transaction", "priority": 1, "required": True, "fact_key": "reason"},
    {"id": "td_issue_3", "question": "Are there any pending dues or exit formalities?", "issue_type": "termination_dispute", "category": "issue", "priority": 1, "required": True, "fact_key": "dues"},

    # 3. Consumer Dispute
    {"id": "cd_txn_1", "question": "What product or service did you purchase?", "issue_type": "consumer_dispute", "category": "transaction", "priority": 1, "required": True, "fact_key": "product"},
    {"id": "cd_issue_1", "question": "What exactly is the defect or issue you encountered?", "issue_type": "consumer_dispute", "category": "issue", "priority": 1, "required": True, "fact_key": "issue"},
    {"id": "cd_txn_2", "question": "When exactly did this issue occur?", "issue_type": "consumer_dispute", "category": "transaction", "priority": 1, "required": True, "fact_key": "timeline"},
    {"id": "cd_evd_1", "question": "Do you have the invoice or proof of purchase?", "issue_type": "consumer_dispute", "category": "evidence", "priority": 1, "required": True, "fact_key": "invoice"},
    {"id": "cd_op_1", "question": "Have you contacted the seller? If so, what was their response?", "issue_type": "consumer_dispute", "category": "opposite_party", "priority": 1, "required": True, "fact_key": "seller_contact"},

    # 4. Defamation
    {"id": "df_issue_1", "question": "What exactly was said or published about you?", "issue_type": "defamation", "category": "issue", "priority": 1, "required": True, "fact_key": "statement"},
    {"id": "df_txn_1", "question": "Where was it posted or published (e.g., social media)?", "issue_type": "defamation", "category": "transaction", "priority": 1, "required": True, "fact_key": "platform"},
    {"id": "df_issue_2", "question": "Is the statement false? Can you prove it is a lie?", "issue_type": "defamation", "category": "issue", "priority": 1, "required": True, "fact_key": "is_false"},
    {"id": "df_evd_1", "question": "Do you have evidence (screenshots, links, etc.)?", "issue_type": "defamation", "category": "evidence", "priority": 1, "required": True, "fact_key": "proof"},
    {"id": "df_issue_3", "question": "Has this statement caused harm to your reputation or business?", "issue_type": "defamation", "category": "issue", "priority": 2, "required": False, "fact_key": "harm"},

    # 5. Cheque Bounce
    {"id": "cb_issue_1", "question": "What is the cheque amount and date?", "issue_type": "cheque_bounce", "category": "issue", "priority": 1, "required": True, "fact_key": "amount_date"},
    {"id": "cb_issue_2", "question": "What was the reason for the bounce given by the bank?", "issue_type": "cheque_bounce", "category": "issue", "priority": 1, "required": True, "fact_key": "reason"},
    {"id": "cb_evd_1", "question": "Do you have the original cheque and the bank return memo?", "issue_type": "cheque_bounce", "category": "evidence", "priority": 1, "required": True, "fact_key": "memo"},
    {"id": "cb_op_1", "question": "Was a statutory legal notice sent within 30 days of the bounce?", "issue_type": "cheque_bounce", "category": "opposite_party", "priority": 1, "required": True, "fact_key": "notice"},

    # 6. Rent Dispute
    {"id": "rd_issue_1", "question": "Are you the tenant or landlord?", "issue_type": "rent_dispute", "subtype": "general", "category": "issue", "priority": 1, "required": True, "fact_key": "role"},
    {"id": "rd_issue_2", "question": "What is the total unpaid rent amount?", "issue_type": "rent_dispute", "subtype": "unpaid_rent", "category": "issue", "priority": 1, "required": True, "fact_key": "amount"},
    {"id": "rd_issue_3", "question": "What is the security deposit amount that is pending?", "issue_type": "rent_dispute", "subtype": "security_deposit", "category": "issue", "priority": 1, "required": True, "fact_key": "amount_deposit"},
    {"id": "rd_txn_1", "question": "Do you have a written rent agreement?", "issue_type": "rent_dispute", "subtype": "general", "category": "transaction", "priority": 1, "required": True, "fact_key": "agreement"},
    {"id": "rd_op_1", "question": "Have you already sent a formal notice for this demand?", "issue_type": "rent_dispute", "subtype": "general", "category": "opposite_party", "priority": 2, "required": False, "fact_key": "notice_served"},

    # 7. Eviction Issue
    {"id": "ev_issue_1", "question": "Are you the landlord seeking eviction or the tenant facing it?", "issue_type": "eviction_issue", "subtype": "general", "category": "issue", "priority": 1, "required": True, "fact_key": "role"},
    {"id": "ev_issue_2", "question": "Has a formal notice to vacate been served?", "issue_type": "eviction_issue", "subtype": "general", "category": "issue", "priority": 1, "required": True, "fact_key": "notice_served"},
    {"id": "ev_txn_1", "question": "Is there a registered lease/rent agreement?", "issue_type": "eviction_issue", "subtype": "general", "category": "transaction", "priority": 1, "required": True, "fact_key": "agreement"},
    {"id": "ev_issue_3", "question": "What is the reason for eviction (e.g. non-payment, personal use)?", "issue_type": "eviction_issue", "subtype": "general", "category": "issue", "priority": 1, "required": True, "fact_key": "action_requested"},

    # 8. Ownership Dispute
    {"id": "od_issue_1", "question": "What is the nature of the ownership dispute (e.g., family, boundary, title)?", "issue_type": "ownership_dispute", "category": "issue", "priority": 1, "required": True, "fact_key": "issue"},
    {"id": "od_txn_1", "question": "Do you have the title deeds or sale registry documents?", "issue_type": "ownership_dispute", "category": "transaction", "priority": 1, "required": True, "fact_key": "documents"},
    {"id": "od_txn_2", "question": "Is this property inherited or self-purchased?", "issue_type": "ownership_dispute", "category": "transaction", "priority": 1, "required": True, "fact_key": "prop_type"},
    {"id": "od_op_1", "question": "Has any court case or injunction already been filed?", "issue_type": "ownership_dispute", "category": "opposite_party", "priority": 1, "required": True, "fact_key": "case_status"},

    # 9. Builder Delay
    {"id": "bd_txn_1", "question": "Which project and builder are involved?", "issue_type": "builder_delay", "category": "transaction", "priority": 1, "required": True, "fact_key": "builder"},
    {"id": "bd_issue_1", "question": "What was the promised date of possession in the agreement?", "issue_type": "builder_delay", "category": "issue", "priority": 1, "required": True, "fact_key": "promise_date"},
    {"id": "bd_issue_2", "question": "How many months of delay have occurred so far?", "issue_type": "builder_delay", "category": "issue", "priority": 1, "required": True, "fact_key": "delay_months"},
    {"id": "bd_evd_1", "question": "Do you have the builder-buyer agreement or booking receipt?", "issue_type": "builder_delay", "category": "evidence", "priority": 1, "required": True, "fact_key": "documents"},

    # 10. Property Fraud
    {"id": "pf_issue_1", "question": "What kind of fraud occurred (fake papers, duplicate registry, etc.)?", "issue_type": "property_fraud", "category": "issue", "priority": 1, "required": True, "fact_key": "fraud_type"},
    {"id": "pf_issue_2", "question": "How much money has been lost or involved in this incident?", "issue_type": "property_fraud", "category": "issue", "priority": 1, "required": True, "fact_key": "amount"},
    {"id": "pf_evd_1", "question": "Do you have the documents that you believe are fake or forged?", "issue_type": "property_fraud", "category": "evidence", "priority": 1, "required": True, "fact_key": "proof"},
    {"id": "pf_op_1", "question": "Have you already filed a police complaint or FIR?", "issue_type": "property_fraud", "category": "opposite_party", "priority": 1, "required": True, "fact_key": "complaint"},

    # 11. Harassment
    {"id": "hr_issue_1", "question": "What kind of harassment are you facing (threats, workplace, etc.)?", "issue_type": "harassment", "category": "issue", "priority": 1, "required": True, "fact_key": "type"},
    {"id": "hr_txn_1", "question": "Who is the person involved?", "issue_type": "harassment", "category": "transaction", "priority": 1, "required": True, "fact_key": "person"},
    {"id": "hr_txn_2", "question": "Where did these incidents take place?", "issue_type": "harassment", "category": "transaction", "priority": 1, "required": True, "fact_key": "place"},
    {"id": "hr_evd_1", "question": "Do you have any proof like recordings, messages, or witnesses?", "issue_type": "harassment", "category": "evidence", "priority": 1, "required": True, "fact_key": "proof"},

    # 8. Fraud
    {"id": "fr_issue_1", "question": "What was the nature of the incident (scam, cheating, fraud)?", "issue_type": "fraud", "category": "issue", "priority": 1, "required": True, "fact_key": "incident"},
    {"id": "fr_issue_2", "question": "How much money was involved in this fraud?", "issue_type": "fraud", "category": "issue", "priority": 1, "required": True, "fact_key": "amount"},
    {"id": "fr_evd_1", "question": "Do you have transaction records or any physical/digital proof?", "issue_type": "fraud", "category": "evidence", "priority": 1, "required": True, "fact_key": "proof"},
    {"id": "fr_op_1", "question": "Have you already filed a police or cyber complaint?", "issue_type": "fraud", "category": "opposite_party", "priority": 1, "required": True, "fact_key": "complaint"},

    # 9. Contract Dispute
    {"id": "cn_txn_1", "question": "What agreement or contract is being discussed?", "issue_type": "contract_dispute", "category": "transaction", "priority": 1, "required": True, "fact_key": "type"},
    {"id": "cn_issue_1", "question": "What specific part of the contract was breached?", "issue_type": "contract_dispute", "category": "issue", "priority": 1, "required": True, "fact_key": "breach"},
    {"id": "cn_evd_1", "question": "Do you have a signed copy of the contract?", "issue_type": "contract_dispute", "category": "evidence", "priority": 1, "required": True, "fact_key": "contract"},
    {"id": "cn_issue_2", "question": "What financial or other loss has occurred?", "issue_type": "contract_dispute", "category": "issue", "priority": 1, "required": True, "fact_key": "loss"},

    # 10. Criminal Complaint
    {"id": "cm_issue_1", "question": "What happened exactly (theft, assault, theft, etc.)?", "issue_type": "criminal_complaint", "category": "issue", "priority": 1, "required": True, "fact_key": "incident"},
    {"id": "cm_txn_1", "question": "Where and when did this incident occur?", "issue_type": "criminal_complaint", "category": "transaction", "priority": 1, "required": True, "fact_key": "place"},
    {"id": "cm_txn_2", "question": "Who was involved (if known)?", "issue_type": "criminal_complaint", "category": "transaction", "priority": 1, "required": True, "fact_key": "person"},
    {"id": "cm_evd_1", "question": "Was a police complaint (FIR) filed?", "issue_type": "criminal_complaint", "category": "evidence", "priority": 1, "required": True, "fact_key": "complaint"},

    # 11. IT Act - Account Hacking
    {"id": "ah_ent_1", "question": "Which platform or account was hacked (e.g., Instagram, Gmail)?", "issue_type": "account_hacking", "category": "entities", "priority": 1, "required": True, "fact_key": "platform"},
    {"id": "ah_iss_1", "question": "Did you lose access to the account completely?", "issue_type": "account_hacking", "category": "issue", "priority": 1, "required": True, "fact_key": "access_loss"},
    {"id": "ah_tim_1", "question": "When did you first notice the unauthorized access?", "issue_type": "account_hacking", "category": "timeline", "priority": 1, "required": True, "fact_key": "incident_date"},
    {"id": "ah_evd_1", "question": "Do you have screenshots of any modifications or recovery emails?", "issue_type": "account_hacking", "category": "evidence", "priority": 2, "required": False, "fact_key": "proof"},

    # 12. IT Act - Online Fraud
    {"id": "of_iss_1", "question": "How much money was lost in this transaction?", "issue_type": "online_fraud", "category": "issue", "priority": 1, "required": True, "fact_key": "amount"},
    {"id": "of_ent_1", "question": "Which app or bank was used for the transaction (e.g., GPay, SBI)?", "issue_type": "online_fraud", "category": "entities", "priority": 1, "required": True, "fact_key": "financial_institution"},
    {"id": "of_tim_1", "question": "Have you reported this to the National Cyber Crime Portal or your bank?", "issue_type": "online_fraud", "category": "timeline", "priority": 1, "required": True, "fact_key": "reported"},
    {"id": "of_evd_1", "question": "Do you have the transaction ID or SMS alerts?", "issue_type": "online_fraud", "category": "evidence", "priority": 1, "required": True, "fact_key": "proof"},

    # 13. IT Act - Identity Theft
    {"id": "it_iss_1", "question": "Is someone using your photos or name to create a fake profile?", "issue_type": "identity_theft", "category": "issue", "priority": 1, "required": True, "fact_key": "impersonation"},
    {"id": "it_ent_1", "question": "On which platform is this fake profile active?", "issue_type": "identity_theft", "category": "entities", "priority": 1, "required": True, "fact_key": "platform"},
    {"id": "it_evd_1", "question": "Do you have a link to the fake profile or screenshots?", "issue_type": "identity_theft", "category": "evidence", "priority": 1, "required": True, "fact_key": "proof"}
]

# Phase 23: Tactical Evidence Checklists
EVIDENCE_CHECKLISTS = {
    "wage_dispute": [
        "Employment Contract / Offer Letter",
        "Salary Slips for the disputed period",
        "Bank Account Statement (showing non-payment)",
        "Resignation/Termination Letter (if applicable)",
        "WhatsApp/Email communications regarding salary"
    ],
    "termination_dispute": [
        "Employment Contract (Notice Period Clause)",
        "Termination Letter / Email",
        "Proof of performance (if terminated for 'low performance')",
        "Communication regarding exit formalities / Full & Final (F&F)"
    ],
    "consumer_dispute": [
        "Invoice / Bill of Purchase",
        "Warranty Card / Guarantee Document",
        "Photos/Videos of the defective product",
        "Email/Chat records with customer support",
        "Courier receipts (if returned for repair)"
    ],
    "cheque_bounce": [
        "Original Dishonoured Cheque",
        "Bank Return Memo (stating 'Insufficient Funds', etc.)",
        "Statutory 15-day Demand Notice (Copy)",
        "Postal Tracking Receipt / Acknowledgment of notice delivery"
    ],
    "rent_dispute": [
        "Registered Rent/Lease Agreement",
        "Rent Receipts or Bank Statements (proof of last payment)",
        "Security Deposit payment proof",
        "Maintenance/Utility bills paid by tenant"
    ],
    "eviction_issue": [
        "Rent Agreement",
        "Formal Notice to Vacate (served by landlord)",
        "Proof of ground for eviction (e.g., non-payment or nuisance)",
        "Photos/Videos of the premises condition"
    ],
    "builder_delay": [
        "Builder-Buyer Agreement (BBA) / Allotment Letter",
        "Payment Receipts for all instalments paid",
        "RERA Registration details of the project",
        "Latest construction site photos",
        "Demand letters sent by builder (if any)"
    ],
    "property_fraud": [
        "Original Sale Deed / Registry",
        "Certified Copy of Index-II from Sub-Registrar",
        "Police Complaint / FIR copy",
        "Encumbrance Certificate (EC) / 7/12 Extract"
    ],
    "harassment": [
        "Call logs / Audio recordings",
        "Screenshots of abusive messages/emails",
        "CCTV footage (if available)",
        "Witness statements (list of people who saw/heard)",
        "Police complaint acknowledgment"
    ],
    "fraud": [
        "Bank Statement / Transaction History (UTR number)",
        "Screenshots of the fraudulent website/app/message",
        "WhatsApp/Phone call records with the fraudster",
        "Cyber Cell complaint copy"
    ],
    "contract_dispute": [
        "Signed Copy of the Contract/MOU",
        "Addendums or modified terms agreed over email",
        "Proof of your performance of contractual duties",
        "Invoices/Payments made under the contract"
    ],
    "criminal_complaint": [
        "MLC (Medico-Legal Case) report if physical injury",
        "List of stolen articles and their bills",
        "CCTV footage / Mobile recordings",
        "Copy of the written complaint submitted to Police"
    ]
}

# Phase 3 Thresholds (Full 10 Domains)
REQUIRED_FACTS = {
    "wage_dispute": ["status", "months_unpaid", "amount", "proof"],
    "termination_dispute": ["type", "notice", "contract", "reason", "dues"],
    "consumer_dispute": ["product", "issue", "timeline", "invoice", "seller_contact"],
    "defamation": ["statement", "platform", "is_false", "proof"],
    "cheque_bounce": ["amount_date", "reason", "memo", "notice"],
    "rent_dispute": ["role", "issue_type", "agreement", "amount"],
    "eviction_issue": ["role", "notice", "agreement", "reason"],
    "ownership_dispute": ["issue", "documents", "prop_type", "case_status"],
    "builder_delay": ["builder", "promise_date", "delay_months", "documents"],
    "property_fraud": ["fraud_type", "amount", "proof", "complaint"],
    "harassment": ["type", "person", "place", "proof"],
    "fraud": ["incident", "amount", "proof", "complaint"],
    "contract_dispute": ["type", "breach", "contract", "loss"],
    "criminal_complaint": ["incident", "place", "person", "complaint"],
    "account_hacking": ["platform", "access_loss", "incident_date"],
    "online_fraud": ["amount", "financial_institution", "reported", "proof"],
    "identity_theft": ["impersonation", "platform", "proof"],
    "data_breach": ["data_type", "platform", "impact"],
    "harassment_cyber": ["platform", "abuse_type", "proof"]
}

# Legal Knowledge Mappings (Full 10 Domains - Strictly Indian)
ALLOWED_LAWS = {
    "wage_dispute": ["Code on Wages, 2019", "Payment of Wages Act, 1936"],
    "termination_dispute": ["Industrial Disputes Act, 1947", "Shops and Establishments Act"],
    "consumer_dispute": ["Consumer Protection Act, 2019"],
    "defamation": ["Bharatiya Nyaya Sanhita, 2023"],
    "cheque_bounce": ["Negotiable Instruments Act, 1881"],
    "rent_dispute": ["Transfer of Property Act, 1882", "Rent Control Act"],
    "eviction_issue": ["Transfer of Property Act, 1882", "Rent Control Act"],
    "ownership_dispute": ["Transfer of Property Act, 1882", "Specific Relief Act, 1963"],
    "builder_delay": ["Consumer Protection Act, 2019", "RERA, 2016"],
    "property_fraud": ["Bharatiya Nyaya Sanhita, 2023", "Registration Act, 1908"],
    "harassment": ["Bharatiya Nyaya Sanhita, 2023", "POSH Act, 2013 (if workplace)"],
    "fraud": ["Bharatiya Nyaya Sanhita, 2023", "Information Technology Act, 2000"],
    "contract_dispute": ["Indian Contract Act, 1872"],
    "criminal_complaint": ["Bharatiya Nyaya Sanhita, 2023"]
}

ISSUE_ACTIONS = {
    "wage_dispute": ["Send written demand", "Approach Labour Commissioner", "File claim"],
    "termination_dispute": ["Legal notice for reinstatement/dues", "File industrial dispute"],
    "consumer_dispute": ["Contact seller formally", "Request refund/replacement", "Consumer Court"],
    "defamation": ["Preserve evidence", "Send legal notice for apology", "Civil/Criminal case"],
    "cheque_bounce": ["Send statutory notice", "File complaint under Section 138 NI Act"],
    "rent_dispute": ["Notice for recovery of rent/deposit", "File eviction suit"],
    "eviction_issue": ["Notice to vacate", "File eviction petition", "Mesne profits claim"],
    "ownership_dispute": ["Suit for Declaration and Possession", "Injunction suit"],
    "builder_delay": ["Notice to builder", "Consumer Court (CPA)", "RERA Complaint"],
    "property_fraud": ["Police/Cyber complaint", "Suit for cancellation of deed"],
    "harassment": ["Preserve records", "Internal Complaints Committee (ICC)", "Police complaint"],
    "fraud": ["Freeze accounts", "File FIR with Cyber Cell/Police", "Recovery suit"],
    "contract_dispute": ["Notice of breach", "Mediation", "Suit for specific performance/damages"],
    "criminal_complaint": ["Seek physical safety", "File FIR at nearest Police Station"],
    "account_hacking": ["Change passwords", "Enable 2FA", "Report to platform", "Cyber Cell complaint"],
    "online_fraud": ["Report to 1930 / Cyber Crime Portal", "Block bank account", "Dispute transaction with bank"],
    "identity_theft": ["Report profile", "Verify your own account", "Cyber Cell complaint"],
    "data_breach": ["Change passwords", "Monitor financial accounts", "Legal notice to entity for negligence"],
    "harassment_cyber": ["Block & Report", "Save evidence", "File Cyber Cell FIR"]
}

ISSUE_TO_NOTICE_TYPE = {
    "wage_dispute": "unpaid_salary",
    "termination_dispute": "wrongful_termination",
    "consumer_dispute": "consumer_complaint",
    "defamation": "defamation",
    "cheque_bounce": "cheque_bounce",
    "rent_dispute": "rent_notice",
    "eviction_issue": "eviction_notice",
    "ownership_dispute": "title_notice",
    "builder_delay": "builder_notice",
    "property_fraud": "fraud_notice",
    "harassment": "cease_and_desist",
    "fraud": "fraud_recovery",
    "contract_dispute": "breach_of_contract",
    "criminal_complaint": "police_complaint",
    "account_hacking": "cyber_crime_notice",
    "online_fraud": "cyber_fraud_notice",
    "identity_theft": "cyber_impersonation_notice",
    "data_breach": "data_privacy_breach",
    "harassment_cyber": "cyber_harassment_notice"
}


SYSTEM_PERSONA = (
    "You are an expert Indian lawyer advising a USER (Consumer/Employee).\n"
    "Strict Jurisdiction: Only use Indian laws. No foreign laws.\n"
    "Role Focus: You are an advocate for the USER. Never provide side-switching advice for the company/employer.\n"
    "Constraints: Stick to the Facts. Do not assume facts. Do not suggest internal company resolutions as legal advice."
)


def detect_issues(query: str) -> Dict[str, Any]:
    """Multi-Signal Detection Engine (Fix Phase 13)."""
    q = query.lower()
    detected_issues = []

    # Signal Mapping & Collection
    if any(w in q for w in ["fraud", "fake", "sold my land", "already belongs", "scam"]):
        detected_issues.append("property_fraud")
    
    if any(w in q for w in ["threat", "harass", "abuse", "scared", "safety"]):
        detected_issues.append("harassment")

    if any(w in q for w in ["vacate", "evict", "leave the house", "throwing me out", "kicked out", "forced out", "without notice"]):
        detected_issues.append("eviction_issue")

    if any(w in q for w in ["tenant", "rent", "landlord", "deposit"]):
        detected_issues.append("rent_dispute")

    if any(w in q for w in ["builder", "possession", "flat delay", "rera", "booking"]):
        detected_issues.append("builder_delay")

    if any(w in q for w in ["brother", "father", "share", "inheritance", "ancestral", "heir"]):
        detected_issues.append("ownership_dispute")

    if any(w in q for w in ["fired", "terminated", "dismissed", "wrongful termination", "boss fired", "manager fired"]):
        detected_issues.append("termination_dispute")

    if "salary" in q or "wages" in q or "pay" in q:
        if any(w in q for w in ["fired", "terminated", "resign"]): 
            detected_issues.append("termination_dispute")
        else:
            detected_issues.append("wage_dispute")

    if any(w in q for w in ["bought", "purchased", "defective", "refund", "receipt"]):
        detected_issues.append("consumer_dispute")
    
    if any(w in q for w in ["cheque", "bounce", "dishonour", "138"]):
        detected_issues.append("cheque_bounce")

    if any(w in q for w in ["agreement", "contract", "signed", "breach"]):
        detected_issues.append("contract_dispute")

    if any(w in q for w in ["theft", "assault", "police", "robbery", "criminal"]):
        detected_issues.append("criminal_complaint")

    if any(w in q for w in ["false", "defame", "posted", "reputation"]):
        detected_issues.append("defamation")

    # IT Act & Cyber domains
    if any(w in q for w in ["hacked", "unauthorized access", "login", "password changed"]):
        detected_issues.append("account_hacking")
    
    if any(w in q for w in ["upi", "gpay", "phishing", "money stolen online", "bank fraud"]):
        detected_issues.append("online_fraud")
    
    if any(w in q for w in ["fake account", "impersonation", "stole my photo", "using my name"]):
        detected_issues.append("identity_theft")
    
    if any(w in q for w in ["data leak", "privacy breach", "records exposed"]):
        detected_issues.append("data_breach")
    
    if any(w in q for w in ["cyber stalking", "online abuse", "morphing"]):
        detected_issues.append("harassment_cyber")

    explicit_online_fraud_markers = ["upi", "gpay", "phishing", "money stolen online", "bank fraud"]
    has_explicit_online_fraud = any(w in q for w in explicit_online_fraud_markers)
    is_consumer_safety_incident = (
        any(w in q for w in ["bought", "purchased", "ordered", "product", "item", "appliance", "pressure cooker"])
        and any(w in q for w in ["defective", "exploded", "blast", "burst", "unsafe", "injury", "burn", "hospital", "medical"])
        and any(w in q for w in ["seller", "manufacturer", "refund", "replace", "compensate", "liability"])
    )
    if is_consumer_safety_incident:
        if "consumer_dispute" not in detected_issues:
            detected_issues.append("consumer_dispute")
        if not has_explicit_online_fraud:
            detected_issues = [i for i in detected_issues if i != "online_fraud"]

    # 1. PRIORITY SORTING
    priority_ladder = [
        "account_hacking", "online_fraud", "identity_theft", 
        "property_fraud", "harassment", "criminal_complaint", 
        "eviction_issue", "cheque_bounce", "rent_dispute", 
        "builder_delay", "ownership_dispute", "termination_dispute", 
        "wage_dispute", "consumer_dispute", "contract_dispute", "defamation"
    ]

    deduped = list(dict.fromkeys(detected_issues))
    if is_consumer_safety_incident and "consumer_dispute" in deduped:
        detected_issues = ["consumer_dispute"] + [i for i in deduped if i != "consumer_dispute"]
    else:
        detected_issues = sorted(deduped, key=lambda x: priority_ladder.index(x) if x in priority_ladder else 99)

    if not detected_issues:
        return {"primary": "unknown", "secondary": [], "confidence": 0.0, "subtype": "none"}

    primary = detected_issues[0]
    secondary = detected_issues[1:]

    # 2. Subtype Logic (Primary Only for now)
    subtype = "general"
    if primary == "rent_dispute":
        subtype = "unpaid_rent" if "rent" in q else "security_deposit" if "deposit" in q else "general"
    elif primary == "consumer_dispute":
        subtype = "defect" if any(w in q for w in ["working", "defective", "broke"]) else "delay" if "delay" in q else "general"

    # 3. Confidence/Strength will be calculated after fact extraction in the API layer.
    return {
        "primary": primary,
        "secondary": secondary,
        "subtype": subtype
    }


def compute_signal_strength(
    issue: str,
    facts: dict,
    signals: Optional[dict] = None,
    contradictions: Optional[List[Dict[str, Any]]] = None,
) -> float:
    """Fact-based Signal Strength Scoring (Phase 21)."""
    if not facts: return 0.0
    
    # 1. Base score based on relevant facts for the issue
    relevant_keys = {
        "eviction_issue": ["role", "action_requested", "notice_served", "agreement"],
        "rent_dispute": ["role", "issue_type", "amount", "agreement"],
        "builder_delay": ["builder", "stoppage", "payment", "delay_months", "documents"],
        "property_fraud": ["fraud_type", "amount", "complaint"],
        "wage_dispute": ["status", "months_unpaid", "amount", "proof"],
        "termination_dispute": ["type", "notice", "contract", "reason", "dues"],
        "consumer_dispute": ["product", "issue", "timeline", "invoice"],
        "account_hacking": ["platform", "access_loss", "incident_date"],
        "online_fraud": ["amount", "financial_institution", "reported"],
        "identity_theft": ["impersonation", "platform", "proof"]
    }
    
    expected = relevant_keys.get(issue, [])
    if not expected: return 0.3 # Default for unknown
    
    # Weight non-empty values
    score = sum(1 for k in expected if facts.get(k) is not None and facts.get(k) != "")
    strength = score / len(expected)
    
    # 2. Critical Fact Boosts
    if issue == "eviction_issue" and facts.get("notice_served") is False:
        strength = min(1.0, strength + 0.3)
        
    if issue == "account_hacking" and facts.get("access_loss"):
        strength = min(1.0, strength + 0.2)
        
    if signals:
        confirmed_signals = sum(1 for payload in signals.values() if payload.get("value") is not None)
        signal_bonus = min(0.2, confirmed_signals * 0.04)
        strength = min(1.0, strength + signal_bonus)

    if contradictions:
        strength = max(0.0, strength - min(0.25, 0.1 * len(contradictions)))

    return round(strength, 2)


def is_fact_sufficient(issue: str, facts: dict) -> bool:
    """Minimum Viable Threshold for Assessment (Phase 21)."""
    # Does the system have enough to give a FIRAC?
    min_viable = {
        "eviction_issue": ["role", "action_requested", "notice_served"],
        "rent_dispute": ["role", "amount", "agreement"],
        "builder_delay": ["builder", "delay_months"],
        "account_hacking": ["platform", "access_loss"],
        "online_fraud": ["amount", "financial_institution"],
        "identity_theft": ["impersonation", "platform"],
        "fraud": ["incident", "amount"],
        "harassment_cyber": ["platform", "abuse_type"],
        "data_breach": ["platform", "data_type"]
    }

    if issue in min_viable:
        return all(facts.get(k) is not None and str(facts.get(k)).strip() != "" for k in min_viable[issue])

    required = REQUIRED_FACTS.get(issue, [])
    if not required: return False 
    
    if required and isinstance(required[0], str) and (len(required[0]) > 20 or " " in required[0]):
        return len(facts) >= 3
        
    return all(facts.get(k) is not None for k in required)


def decide_next_step(
    issue: str,
    facts: dict,
    strength: float,
    contradictions: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Decision Layer (CLARIFY, INTERVIEW, ASSESS). Phase 21."""
    if issue == "unknown" or strength < 0.30: # Reduced from 0.35 (Phase 21 Refinement)
        return "CLARIFY"

    if contradictions:
        return "INTERVIEW"
        
    if is_fact_sufficient(issue, facts) or strength >= 0.75:
        return "ASSESS"
        
    return "INTERVIEW"




def detect_role(query: str) -> str:
    """Explicitly detects user role (Tenant vs Landlord) using contextual signals."""
    q = query.lower()
    
    # 1. Tenant Signals
    if any(w in q for w in ["my landlord", "landlord kicked", "landlord threat", "pay rent to", "my deposit"]):
        return "tenant"
    
    # 2. Landlord Signals
    if any(w in q for w in ["my tenant", "tenant not paying", "tenant not vacating", "rent from", "security deposit to"]):
        return "landlord"
        
    # 3. Keyword Heuristics
    if "tenant" in q and ("i am" in q or "being" in q): return "tenant"
    if "landlord" in q and ("i am" in q or "acting as" in q): return "landlord"
    
    return "unknown"


def extract_facts(user_input: str, issue: str, current_facts: dict) -> dict:
    """Extract key categorical and numerical facts from user input.
    Note: In this version, we bridge the deterministic code with the raw user input.
    """
    q = user_input.lower()
    new_facts = dict(current_facts)
    
    # Platform / Entities extraction
    if "platform" in q or any(w in q for w in ["instagram", "facebook", "twitter", "whatsapp", "gmail"]):
        match = re.search(r"(instagram|facebook|twitter|whatsapp|gmail|gpay|phonepe)", q)
        if match: new_facts["platform"] = match.group(1)

    # Access loss
    if any(w in q for w in ["hacked", "stole my account", "cannot login", "lost access"]):
        new_facts["access_loss"] = True

    # Financial amount
    amount_match = re.search(r"(?:rs\.?|inr|₹)?\s*(\d+(?:,\d+)*(?:\.\d+)?)", q)
    if amount_match:
        new_facts["amount"] = amount_match.group(1).replace(",", "")

    # Global Role Detection
    role = detect_role(q)
    if role != "unknown":
        new_facts["role"] = role

    # Industry specific logic (Consumer/Wage)
    if issue == "consumer_dispute":
        if any(w in q for w in ["phone", "tv", "car", "service"]): new_facts["product"] = True
        if any(w in q for w in ["broke", "defective", "working", "problem"]): new_facts["issue"] = True
        if any(w in q for w in ["days", "ago", "last week", "yesterday"]): new_facts["timeline"] = True
        if any(w in q for w in ["yes", "have", "invoice", "receipt"]): new_facts["invoice"] = True
        if any(w in q for w in ["contacted", "called", "emailed"]): new_facts["seller_contact"] = True

    elif issue == "wage_dispute":
        if any(w in q for w in ["working", "resign", "left", "terminated"]): new_facts["status"] = True
        if any(w in q for w in ["months", "salary", "pay"]):
             match = re.search(r"(\d+)\s*months?", q)
             new_facts["months_unpaid"] = int(match.group(1)) if match else True
        if any(w in q for w in ["slips", "record", "bank"]): new_facts["proof"] = True

    elif issue == "defamation":
        if "statement" in q or "said" in q or "posted" in q: new_facts["statement"] = True
        if any(w in q for w in ["facebook", "whatsapp", "online", "post"]): new_facts["platform"] = True
        if "false" in q or "lie" in q: new_facts["is_false"] = True
        if any(w in q for w in ["screenshot", "link", "photo"]): new_facts["proof"] = True

    elif issue == "termination_dispute":
        if "fired" in q or "terminated" in q: new_facts["type"] = "termination"
        if "resigned" in q: new_facts["type"] = "resignation"
        if "notice" in q: new_facts["notice"] = True
        if "contract" in q: new_facts["contract"] = True
        if "reason" in q: new_facts["reason"] = True
        if "dues" in q or "money" in q: new_facts["dues"] = True

    elif issue == "fraud":
        if any(w in q for w in ["money", "scam", "cheated"]): new_facts["incident"] = True
        if any(char.isdigit() for char in q): new_facts["amount"] = True
        if any(w in q for w in ["record", "transfer", "bank"]): new_facts["proof"] = True
        if "complaint" in q or "police" in q: new_facts["complaint"] = True

    elif issue == "rent_dispute":
        if "tenant" in q: new_facts["role"] = "tenant"
        if "landlord" in q: new_facts["role"] = "landlord"
        if "rent" in q: new_facts["issue_type"] = "unpaid_rent"
        if "deposit" in q: new_facts["issue_type"] = "security_deposit"
        if "agreement" in q: new_facts["agreement"] = True
        if any(char.isdigit() for char in q): 
            match = re.search(r"(\d+)\s*(?:months?|days?)", q)
            if match: new_facts["period"] = match.group(0)
            new_facts["amount"] = True

    elif issue == "eviction_issue":
        if any(w in q for w in ["vacate", "evict", "leave", "kicked", "forced"]): new_facts["action_requested"] = True
        if "notice" in q:
            if any(w in q for w in ["without", "no notice", "never received"]):
                new_facts["notice_served"] = False
            else:
                new_facts["notice_served"] = True
        if "agreement" in q or "contract" in q:
            new_facts["agreement"] = True

    elif issue == "account_hacking":
        if any(w in q for w in ["insta", "fb", "google", "email", "gmail", "account", "profile"]): 
            new_facts["platform"] = True
        if any(w in q for w in ["lock", "not access", "cannot login", "pass changed", "hacked"]):
            new_facts["access_loss"] = True
        if any(w in q for w in ["today", "yesterday", "since", "date", "when"]):
            new_facts["incident_date"] = True

    elif issue == "online_fraud":
        if any(char.isdigit() for char in q): new_facts["amount"] = True
        if any(w in q for w in ["upi", "gpay", "bank", "sbi", "hdfc", "icici"]):
            new_facts["financial_institution"] = True
        if any(w in q for w in ["reported", "complaint", "cyber", "portal", "fir"]):
            new_facts["reported"] = True

    elif issue == "identity_theft":
        if any(w in q for w in ["fake", "impersonat", "using my", "stole"]):
            new_facts["impersonation"] = True
        if any(w in q for w in ["insta", "fb", "profile", "online", "platform"]):
            new_facts["platform"] = True

    elif issue == "builder_delay":
        if any(w in q for w in ["project", "builder", "flat"]): new_facts["builder"] = True
        if any(w in q for w in ["stop", "construction", "halt", "not started"]): new_facts["stoppage"] = True
        if any(w in q for w in ["paid", "payment", "booking", "money"]): new_facts["payment"] = True
        if any(char.isdigit() for char in q): new_facts["delay_months"] = True
        if any(w in q for w in ["agreement", "receipt", "papers"]): new_facts["documents"] = True

    elif issue == "property_fraud":
        if "fake" in q or "registry" in q or "duplicate" in q: new_facts["fraud_type"] = True
        if any(char.isdigit() for char in q): new_facts["amount"] = True
        if "complaint" in q or "fir" in q: new_facts["complaint"] = True

    elif issue == "ownership_dispute":
        if any(w in q for w in ["brother", "father", "share", "inheritance"]): new_facts["dispute_type"] = "inheritance"
        if "registry" in q or "title" in q: new_facts["dispute_type"] = "title"

    elif issue == "harassment":
        if any(w in q for w in ["threat", "abuse", "landlord", "employer"]): new_facts["severity"] = "high"

    return new_facts


def classify_severity(issue_type: str, subtype: str, facts: dict) -> str:
    """Deterministic severity model (Production Grade)."""
    # 1. Consumer
    if issue_type == "consumer_dispute":
        if subtype == "defect" or "defect" in str(facts.get("issue", "")).lower(): return "high"
        return "medium"

    # 2. Wage
    if issue_type == "wage_dispute":
        months = facts.get("months_unpaid", 0)
        if isinstance(months, int) and months >= 2: return "high"
        return "low"

    # 3. Defamation
    if issue_type == "defamation":
        if facts.get("proof") and facts.get("harm"): return "high"
        return "medium"

    # 4. Level 1: Hard Crucials (Always High)
    high_severity_issues = [
        "criminal_complaint", "fraud", "harassment", "property_fraud", 
        "eviction_issue", "account_hacking", "online_fraud", 
        "identity_theft", "data_breach", "harassment_cyber"
    ]
    if issue_type in high_severity_issues:
        return "high"

    # 5. Property & Commercial Sub-thresholds
    if issue_type == "builder_delay":
        months = facts.get("delay_months", 0)
        if isinstance(months, int) and months > 6: return "high"
        return "medium"

    if issue_type == "rent_dispute":
        amount = facts.get("amount", 0)
        # Try to extract number from fact if it was stored as True/digit-exists
        if isinstance(amount, int) and amount > 50000: return "medium"
        return "low"

    return "medium"




def generate_firac_analysis(issue: str, facts: dict, is_complete: bool, llm_model: str) -> str:
    """Generates a structured FIRAC legal analysis for HIGH severity cases."""
    if not is_complete:
        return "Legal Fact-Finding Phase: Still gathering necessary details before assessment."

    laws = ALLOWED_LAWS.get(issue, [])
    fact_str = "\n".join([f"- {k.replace('_', ' ').capitalize()}" for k, v in facts.items() if v])

    prompt = (
        f"{SYSTEM_PERSONA}\n\n"
        f"STRICT INSTRUCTION: The issue is '{issue}'. You MUST NOT change the domain or mention unrelated laws.\n"
        f"LAWS TO USE: {', '.join(laws)}\n"
        f"FACTS:\n{fact_str}\n\n"
        "Generate a FIRAC analysis strictly following this format:\n"
        "1. Facts: Summary of user situation.\n"
        "2. Issue: Core legal question at play.\n"
        "3. Rule: Specific Sections/Acts applicable (Indian Law only).\n"
        "4. Analysis: How the rule applies to these specific facts.\n"
        "5. Conclusion: Your legal finding.\n"
        "6. Remedies: Next 3 legal actions."
    )
    draft = call_llm(model_name=llm_model, prompt=prompt, timeout_sec=20, max_tokens=1000)
    refine_prompt = f"Refine this FIRAC for professional advocate tone. Ensure no domain drift from {issue}:\n{draft}"
    return call_llm(model_name=llm_model, prompt=refine_prompt, timeout_sec=20, max_tokens=1000)


def generate_guidance_output(issue: str, facts: dict, llm_model: str) -> str:
    """Provides non-legal guidance for LOW severity cases."""
    prompt = (
        f"{SYSTEM_PERSONA}\n\n"
        f"STRICT INSTRUCTION: Domain is '{issue}'. Focus only on this context.\n\n"
        f"User situation: {facts}\n"
        "Provide GUIDANCE MODE output (No Laws, No FIRAC):\n"
        "1. Direct Assessment: Why this is likely administrative/minor.\n"
        "2. Suggestion: Practical non-legal next steps.\n"
        "3. Escalation: When to consult a lawyer."
    )
    return call_llm(model_name=llm_model, prompt=prompt, timeout_sec=20, max_tokens=1000)


def generate_advisory_output(issue: str, facts: dict, llm_model: str) -> str:
    """Provides professional advisory for MEDIUM severity cases."""
    prompt = (
        f"{SYSTEM_PERSONA}\n\n"
        f"STRICT INSTRUCTION: Domain is '{issue}'. Focus only on this context.\n\n"
        f"User situation: {facts}\n"
        "Provide ADVISORY MODE output (Balanced, Light Law):\n"
        "1. Context: Brief mention of legal standing.\n"
        "2. Record-keeping: Tactical evidence steps.\n"
        "3. Strategy: Why internal grievance is better than court now."
    )
    return call_llm(model_name=llm_model, prompt=prompt, timeout_sec=20, max_tokens=1000)


def generate_notice_from_session(issue: str, facts: dict, analysis: str, llm_model: str) -> str:
    """Drafts a formal legal notice based on the session details. Phase 22."""
    notice_type = ISSUE_TO_NOTICE_TYPE.get(issue, "general")
    
    # 1. Enriched Fact-to-Notice Mapping
    fact_details = []
    for k, v in facts.items():
        if not v: continue
        key_label = k.replace('_', ' ').capitalize()
        if k == "amount": fact_details.append(f"Disputed Amount: ₹{v}")
        elif k == "period": fact_details.append(f"Duration of Issue: {v}")
        elif k == "notice_served": fact_details.append("Status: Event occurred WITHOUT notice" if v is False else "Status: Notice served previously")
        elif k == "role": pass # Handled in sender/receiver
        else: fact_details.append(f"{key_label} confirmed")
        
    # 2. Role-Aware Address mapping
    role = facts.get("role", "unknown")
    if role == "tenant":
        sender = "The Tenant ([CLIENT NAME])"
        receiver = "The Landlord"
    elif role == "landlord":
        sender = "The Landlord ([CLIENT NAME])"
        receiver = "The Tenant"
    else:
        sender = "[SENDER NAME]"
        receiver = "[OPPOSITE PARTY]"

    prompt = build_notice_prompt(
        sender_name=sender, 
        receiver_name=receiver,
        relationship=f"Contractual relation in {issue.replace('_', ' ')}", 
        facts=fact_details, 
        claim=f"Formal Notice for {issue.replace('_', ' ')}",
        notice_type=notice_type, 
        retrieved_context=analysis
    )
    draft = call_llm(model_name=llm_model, prompt=prompt, timeout_sec=30, max_tokens=4000)
    refine = build_notice_refinement_prompt(draft, tone="firm")
    return call_llm(model_name=llm_model, prompt=refine, timeout_sec=20, max_tokens=4000)



def generate_legal_output(issue: str, subtype: str, facts: dict, is_complete: bool, llm_model: str) -> Dict[str, Any]:
    """Deterministic output mode selection with logic gating (Fix 4 & 6)."""
    
    # NEW: Phase 23 - Evidence Checklist
    evidence = EVIDENCE_CHECKLISTS.get(issue, ["Copy of all relevant documents", "Identity Proof (Aadhar/PAN)", "Address Proof"])

    # 1. Handle Unknown Issue (Fix 6)
    if issue == "unknown":
        return {
            "analysis": "I am not sure I understand the legal domain yet. Could you describe the situation in more detail?",
            "summary": "Clarification Required.",
            "severity": "low",
            "applicable_laws": [],
            "legal_options": [],
            "next_steps": ["Provide more details"],
            "confidence": 0,
            "notice_draft": None,
            "case_strategy": ["Explain context clearly"],
            "evidence_checklist": evidence
        }

    severity = classify_severity(issue, subtype, facts)
    
    # 2. Strict Interview Gating (Fix 4)
    # No FIRAC or Notice until all required facts are collected.
    if not is_complete:
        return {
            "analysis": "FACT COLLECTION PHASE: Still interviewing to build a precise legal assessment. No assessment generated yet.",
            "summary": f"Interviewing — {issue.replace('_', ' ').capitalize()}.",
            "severity": severity,
            "applicable_laws": ALLOWED_LAWS.get(issue, []),
            "legal_options": ["Wait for full assessment"],
            "next_steps": ["Answer all questions"],
            "confidence": round(sum(1 for f in REQUIRED_FACTS.get(issue, []) if facts.get(f)) / len(REQUIRED_FACTS.get(issue, [1])), 2),
            "notice_draft": None,
            "case_strategy": ["Provide factual responses", "Complete the interview"],
            "evidence_checklist": evidence
        }

    # 3. Content Generation (Only if is_complete=True)
    if severity == "low":
        analysis = generate_guidance_output(issue, facts, llm_model)
        notice = None
        summary = "Operational Guidance Generated."
    elif severity == "medium":
        analysis = generate_advisory_output(issue, facts, llm_model)
        notice = None
        summary = "Legal Advisory Generated."
    else:
        # High Severity -> Full FIRAC (Fix 6)
        analysis = generate_firac_analysis(issue, facts, is_complete, llm_model)
        # Notice drafting/prefill is temporarily disabled while the generator contract is updated.
        notice = None
        summary = "Full Case Assessment Generated."

    # 4. Strategy Enforcement (Refined Phase 22/23)
    strategy = ["Gather documentation", "Record all communications"]
    if severity == "low":
        strategy.append("Internal follow-up via HR/Helpdesk.")
    elif severity == "medium":
        strategy.append("Draft non-legal formal grievance.")
    else:
        strategy.extend(["Consult legal counsel", "Send legal notice via Speed Post."])
    
    return {
        "analysis": analysis,
        "summary": summary,
        "severity": severity,
        "applicable_laws": ALLOWED_LAWS.get(issue, []),
        "legal_options": ISSUE_ACTIONS.get(issue, []) if severity != "low" else ["Administrative Follow-up"],
        "next_steps": ["Verify documents in the checklist", "Review the legal strategy before drafting any notice"],
        "confidence": 1.0,
        "notice_draft": notice,
        "case_strategy": strategy,
        "evidence_checklist": evidence
    }



def select_questions(issue: str, facts: dict, asked_questions: list, llm_model: str, subtype: str = "general", secondary: list = []) -> List[Dict[str, Any]]:
    """Selects missing factual questions based on primary issue, subtype, and secondary signals."""
    
    # 0. Fact Persistence: Ensure we don't ask for things already in 'facts'
    # The 'facts' dict stores existing extractions.
    
    def score_question(question: Dict[str, Any], issue_bias: float = 1.0) -> Dict[str, Any]:
        category_weight = {
            "issue": 1.0,
            "transaction": 0.85,
            "evidence": 0.75,
            "opposite_party": 0.65,
            "timeline": 0.7,
            "entities": 0.7,
        }
        impact_on_ranking = category_weight.get(question.get("category"), 0.6)
        if question.get("required"):
            impact_on_ranking += 0.2
        uncertainty = 1.0 if facts.get(question["fact_key"]) in [None, ""] else 0.2
        priority = round(impact_on_ranking * uncertainty * issue_bias, 3)
        return {**question, "dynamic_priority": priority}

    def _build_cyber_triage_questions() -> List[Dict[str, Any]]:
        return [
            {
                "id": "cy_triage_platform",
                "question": "Which platform was used to threaten the leak (WhatsApp, Instagram, Telegram, email, etc.)?",
                "issue_type": issue,
                "category": "entities",
                "priority": 1,
                "required": True,
                "fact_key": "platform",
            },
            {
                "id": "cy_triage_proof",
                "question": "Do you have screenshots/URLs/chat logs of the threat and the AI-generated video or preview?",
                "issue_type": issue,
                "category": "evidence",
                "priority": 1,
                "required": True,
                "fact_key": "proof",
            },
            {
                "id": "cy_triage_amount",
                "question": "What exact amount/payment demand was made, and by which payment method/account?",
                "issue_type": issue,
                "category": "issue",
                "priority": 1,
                "required": True,
                "fact_key": "amount",
            },
            {
                "id": "cy_triage_accused",
                "question": "Do you know the identity/contact of the accused (phone, handle, email, bank/UPI details)?",
                "issue_type": issue,
                "category": "transaction",
                "priority": 1,
                "required": True,
                "fact_key": "person",
            },
            {
                "id": "cy_triage_reported",
                "question": "Have you already filed a complaint on cybercrime.gov.in, called 1930, or filed an FIR?",
                "issue_type": issue,
                "category": "timeline",
                "priority": 1,
                "required": True,
                "fact_key": "reported",
            },
        ]

    cyber_urgent_issues = {"harassment_cyber", "identity_theft", "online_fraud", "account_hacking", "criminal_complaint"}
    is_cyber_urgent = issue in cyber_urgent_issues or any(s in cyber_urgent_issues for s in (secondary or []))

    # 1. Primary Candidates
    candidates = [
        score_question(q, issue_bias=1.0)
        for q in QUESTION_DB 
        if q["issue_type"] == issue
        and q.get("subtype", "general") in ["general", subtype]
        and q["id"] not in asked_questions
        and (facts.get(q["fact_key"]) is None or facts.get(q["fact_key"]) == "")
    ]
    
    # 2. Secondary Signals (Add highest priority question from each secondary issue)
    secondary_questions = []
    for s_issue in secondary:
        if s_issue == issue: continue # Skip primary
        s_candidates = [
            score_question(q, issue_bias=0.9)
            for q in QUESTION_DB 
            if q["issue_type"] == s_issue 
            and q["id"] not in asked_questions 
            and (facts.get(q["fact_key"]) is None or facts.get(q["fact_key"]) == "")
        ]
        if s_candidates:
            secondary_questions.append(max(s_candidates, key=lambda x: (x["dynamic_priority"], -x["priority"])))

    # Combine: Primary (sorted) + Secondary
    final_list = sorted(candidates, key=lambda x: (-x["dynamic_priority"], x["priority"]))
    
    # Inject secondary questions early if they are high priority
    for sq in secondary_questions:
        if sq not in final_list:
            final_list.insert(0, sq)

    # Cyber blackmail/deepfake-style matters need immediate triage facts first.
    if is_cyber_urgent:
        urgent_candidates = [
            score_question(q, issue_bias=1.2)
            for q in _build_cyber_triage_questions()
            if q["id"] not in asked_questions and (facts.get(q["fact_key"]) is None or facts.get(q["fact_key"]) == "")
        ]
        urgent_candidates = sorted(urgent_candidates, key=lambda x: (-x["dynamic_priority"], x["priority"]))

        merged: List[Dict[str, Any]] = []
        seen_ids = set()
        for item in urgent_candidates + final_list:
            item_id = item.get("id")
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            merged.append(item)
        final_list = merged

    return final_list[:3]
