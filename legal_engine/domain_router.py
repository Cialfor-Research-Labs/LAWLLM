from typing import List
from legal_engine.models import IssueExpansion, DomainRoutingDecision

def route_domains(issue_expansion: IssueExpansion) -> DomainRoutingDecision:
    """
    Decide which domains to activate based on identified issues.
    Logic is based on category matching and relevance scores.
    """
    selected_domains = set()
    justifications = []
    
    # Primary domain is the one with the highest relevance score
    highest_rel = -1.0
    primary_domain = "general"
    
    for issue in issue_expansion.issues:
        if issue.relevance_score > 0.5:
            selected_domains.add(issue.category)
            justifications.append(f"Issue '{issue.label}' (score {issue.relevance_score}) activates domain '{issue.category}'.")
            
            if issue.relevance_score > highest_rel:
                highest_rel = issue.relevance_score
                primary_domain = issue.category

    # Heuristic: If physical injury is present, include tort/criminal if not already there
    # (Note: IssueExpansion already covers these if prompt is good, but we can double check)
    
    domains_list = list(selected_domains)
    if not domains_list:
        domains_list = ["general"]
        primary_domain = "general"
        justifications.append("No specific high-relevance issues found; falling back to general domain.")

    secondary_domains = [d for d in domains_list if d != primary_domain]

    return DomainRoutingDecision(
        domains_selected=domains_list,
        primary_domain=primary_domain,
        secondary_domains=secondary_domains,
        justification=" ".join(justifications)
    )
