import json
import os
import sys
from typing import List, Dict, Any

# Add parent directory to path to import local modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hybrid_retrieval import run_hybrid_retrieval
from legal_engine.models import (
    ExpandedIntent, IssueExpansion, DomainRoutingDecision, 
    RetrievalResult, Snippet
)

# Simplified mock of hybrid retrieval args for now
class MockArgs:
    def __init__(self, query: str):
        self.q = query
        self.corpus = "all"
        self.top_k = 5
        self.dense_k = 50
        self.bm25_k = 50
        self.dense_weight = 0.6
        self.bm25_weight = 0.4
        self.rerank = False
        self.max_context_chars = 10000

def retrieve_multi_domain(
    intent: ExpandedIntent,
    issues: IssueExpansion,
    routing: DomainRoutingDecision,
    answered_fields: Dict[str, Any]
) -> List[RetrievalResult]:
    results = []
    
    for domain in routing.domains_selected:
        # Generate multiple queries for this domain
        # Heuristic: combine primary issue with domain or use specific issue labels
        queries = []
        for issue in issues.issues:
            if issue.category == domain:
                queries.append(f"{issue.label} {domain} law India")
        
        if not queries:
            queries.append(f"{intent.primary_issue} {domain}")
            
        all_snippets = []
        snippet_id_counter = 1
        
        for q in queries:
            args = MockArgs(q)
            # Existing hybrid retrieval logic
            raw_results = run_hybrid_retrieval(args)
            
            for res in raw_results:
                snippet = Snippet(
                    snippet_id=f"S_{domain}_{snippet_id_counter}",
                    source_type="statute" if "JSON_acts" in (res.get("context_path") or "") else "case",
                    source_name=res.get("title") or "Unknown source",
                    section_or_citation=res.get("section_number") or "N/A",
                    text=res.get("chunk_text") or "",
                    relevance_score=res.get("hybrid_score") or 1.0,
                    url=None
                )
                all_snippets.append(snippet)
                snippet_id_counter += 1
                
        # Deduplicate snippets if needed
        # Sort by relevance and return
        all_snippets.sort(key=lambda x: x.relevance_score, reverse=True)
        
        results.append(RetrievalResult(
            domain=domain,
            queries_used=queries,
            snippets=all_snippets[:10] # Top 10 per domain
        ))
        
    return results
