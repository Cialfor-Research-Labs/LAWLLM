def domain_safe_fallback(domain: str) -> str:
    if domain == "consumer":
        return (
            "General Legal Framework (Consumer): Under the Consumer Protection Act, 2019, you can usually seek "
            "refund/replacement/repair, and compensation where applicable. "
            "Pecuniary forum is typically District (up to INR 50 lakh), State (above INR 50 lakh up to INR 2 crore), "
            "and National (above INR 2 crore). "
            "Limitation is generally 2 years from cause of action. "
            "Please share claim amount and incident date to provide a precise filing strategy."
        )
    if domain == "property":
        return (
            "General Legal Framework (Property): Property disputes usually require notice, proof of possession/title, "
            "and remedy selection (injunction, possession, damages, or specific performance depending on facts). "
            "Please share property type, agreement date, possession status, and value involved for a precise forum and remedy path."
        )
    if domain == "criminal":
        return (
            "General Legal Framework (Criminal): Criminal remedy normally starts with complaint/FIR and evidence preservation. "
            "Applicable code depends on incident date: IPC/CrPC for incidents before 2024-07-01, and BNS/BNSS for later incidents. "
            "Please share incident date and FIR/police status for precise section-level guidance."
        )
    return (
        "General Legal Framework: The issue appears legally actionable, but specific relief depends on incident date, amount/value, "
        "party type, and documents. Please share these details for targeted statutory and forum guidance."
    )
