import json
import re
import sys
import os
from collections import Counter
from bedrock_client import call_bedrock_chat, DEFAULT_BEDROCK_MODEL_ID

# AWS Bedrock model config (legacy env fallback kept for compatibility)
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)

# Global acts mapping: {act_label: {section_num: section_data}}
acts_data = {}
# Mapping of full act names to labels: {"the information technology act": "TITA"}
act_names_map = {
    "it act": "TITA",
    "it act 2000": "TITA",
    "ita": "TITA",
    "information technology act": "TITA",
    "information technology": "TITA",
    "ipc": "BNS",  # Mapping old acts to new ones for convenience
    "crpc": "BNSS",
    "evidence act": "BSA",
    "contract act": "TCONA",
    "companies act": "TCA",
    "civil procedure": "TCOCP",
    "cpc": "TCOCP",
    "limitation act": "TLA",
}

FULL_ACT_NAMES = {
    "TITA": "**The Information Technology Act, 2000**",
    "BNS": "**The Bharatiya Nyaya Sanhita, 2023**",
    "BNSS": "**The Bharatiya Nagarik Suraksha Sanhita, 2023**",
    "BSA": "**The Bharatiya Sakshya Adhiniyam, 2023**",
    "TCONA": "**The Indian Contract Act, 1872**",
    "TCA": "**The Companies Act, 2013**",
    "TCOCP": "**The Code of Civil Procedure, 1908**",
    "TLA": "**The Limitation Act, 1963**",
}
# Token cache for all sections: List of (act_label, section_num)
sections_corpus = []

def load_data():
    global sections_corpus, act_names_map
    folder = "JSON_acts"
    if not os.path.exists(folder):
        print(f"[ERROR] {folder} not found.")
        return

    # BNSS v5 is special, others have _cleaned.json
    files = [f for f in os.listdir(folder) if (f.endswith("_cleaned.json") or "_v5.json" in f) and not f.startswith("._")]
    
    for filename in files:
        filepath = os.path.join(folder, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            doc_id = data.get('document', {}).get('document_id', 'Unknown')
            # Extract common label (e.g. BNSS, BNS) from doc_id or filename
            act_label = "".join([w[0] for w in doc_id.split() if w[0].isalnum()]).upper()
            if not act_label: act_label = filename.split('.')[0][:4].upper()
            
            # Map full name for better detection
            act_names_map[doc_id.lower()] = act_label
            # Add shortened common name (e.g. "Information Technology Act" -> TITA)
            short_name = doc_id.lower().replace("the ", "").strip()
            act_names_map[short_name] = act_label
            
            # Map sections
            act_sections = {}
            for sec in data.get('sections', []):
                s_num = str(sec.get('section_number', '')).strip()
                act_sections[s_num] = sec
                
                # Tokenize for weighted search
                title = str(sec.get('section_title', '')).lower()
                text = str(sec.get('full_section_text', '')).lower()
                act_sections[s_num]['_tokens_title'] = tokenize(title)
                act_sections[s_num]['_tokens_text'] = tokenize(text)
                
                sections_corpus.append((act_label, s_num))
            
            acts_data[act_label] = act_sections
            print(f"[LOADED] {act_label}: {len(act_sections)} sections from {filename}")
            
        except Exception as e:
            print(f"[ERROR] Failed to load {filename}: {e}")
            
def tokenize(text: str) -> list:
    """Extract semantic tokens ignoring generic words and normalizing suffixes."""
    stopwords = {
        'what', 'is', 'the', 'a', 'an', 'in', 'of', 'for', 'to', 'and', 'or', 'by', 'who', 
        'with', 'from', 'as', 'any', 'under', 'be', 'been', 'which', 'has', 'have', 'shall',
        'explain', 'question', 'tell', 'me', 'about', 'how', 'does', 'where'
    }
    # Suffix normalization for simple stemming
    def stem(word):
        word = word.lower()
        if word.endswith('s') and len(word) > 4: word = word[:-1]
        if word.endswith('ing') and len(word) > 5: word = word[:-3]
        if word.endswith('ed') and len(word) > 5: word = word[:-2]
        return word

    tokens = [stem(w) for w in re.findall(r'\b[a-zA-Z]{3,}\b', text)]
    return [t for t in tokens if t not in stopwords]

def _is_unrelated(query: str) -> bool:
    unrelated_terms = {'weather', 'recipe', 'sports', 'lyrics', 'movie', 'song', 'joke', 'random', 'unrelated'}
    q_tokens = set([w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', query)])
    return any(term in q_tokens for term in unrelated_terms)

def is_explanation_query(query: str) -> bool:
    """Detect if the user is asking for an explanation, procedure, or conceptual info."""
    explanation_keywords = [
        r'\bexpla', r'\bmean', r'\binterpret', r'\bwhat does\b', 
        r'\bsimple term', r'\bsimplify', r'\bunderst',
        r'\bpower', r'\bright', r'\bduty', r'\bduties', r'\bprocedure',
        r'\bhow to', r'\bwhat are', r'\bpunish'
    ]
    query_lower = query.lower()
    return any(re.search(pattern, query_lower) for pattern in explanation_keywords)

def call_qwen(query: str, section_text: str, full_act_name: str) -> str:
    """Calls AWS Bedrock for explanatory answer generation."""
    
    # Pre-formatting the system prompt with context values
    system_prompt = f"""
You are an expert legal assistant.

STRICT RULES:
1. Answer only from the statutory text provided.
2. Do not invent missing text.
3. Keep each heading on its own line.
4. Keep each bullet or numbered point on its own line.
5. Do not place multiple headings or sections on the same line.

OUTPUT FORMAT:

## {full_act_name} - Section Analysis

**Section**
Section reference and title

**Official Statutory Text**
Short quoted extract from the provision

**Legal Answer**
Direct explanation in 2-4 sentences

**Quick Pillars**
- **Actor**: ...
- **Offense**: ...
- **Penalty**: ...

**Limits**
Mention any important interpretive limit if needed.
"""

    try:
        return call_bedrock_chat(
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"USER QUERY: {query}\n\n"
                        f"LEGAL PROVISION TEXT:\n{section_text}\n\n"
                        "Return clean markdown with proper line breaks."
                    ),
                }
            ],
            system_prompt=system_prompt,
            model_id=BEDROCK_MODEL_ID,
            temperature=0.2,
            max_tokens=1024,
            top_p=0.9,
        )
    except Exception as e:
        return f"[ERROR] AWS Bedrock call failed: {str(e)}"

def reconstruct_section(act_label, sec_num):
    sec = acts_data.get(act_label, {}).get(sec_num)
    if not sec:
        return f"[ERROR] Section {sec_num} not found in {act_label}."
    
    sec_title = sec.get('section_title', 'No Title')
    
    # Remove stray Chapter headers if they bled into title
    sec_title = re.sub(r'\s+[A-Z][a-z]+ of [A-Z].*$', '', sec_title)
    
    full_name = FULL_ACT_NAMES.get(act_label, f"**{act_label}**")
    parts = [f"Act: {full_name}", f"Section {sec_num} – {sec_title}\n"]
    
    for unit in sec.get('units', []):
        label = str(unit.get('label', '')).strip()
        text_raw = unit.get('text_cleaned', unit.get('text', ''))
        text = str(text_raw if text_raw is not None else '').strip()
        
        if text == '[EMPTY]':
            continue
            
        # Format hierarchy
        if re.match(r'^\(\d+\)$', label): # Subsection (1)
            parts.append(f"{label} {text}")
        elif re.match(r'^\([a-z]\)$', label): # Clause (a)
            parts.append(f"    {label} {text}")
        elif re.match(r'^\([ivx]+\)$', label): # Subclause (i)
            parts.append(f"        {label} {text}")
        elif "Proviso" in label or text.startswith("Provided"):
            parts.append(f"\n{text}")
        elif "Explanation" in label or text.startswith("Explanation"):
            parts.append(f"\n{text}")
        else:
            if label and label != "No Label" and label != sec_num:
                parts.append(f"{label} {text}")
            else:
                parts.append(text)
        
    return "\n".join(parts)

def search_sections(query: str) -> list[tuple[str, str, float]]:
    """Comprehensive search handling synonyms, direct matches, and semantic ranking."""
    query_tokens = tokenize(query)
    query_upper = query.upper()
    
    # 1. Detect target act (including synonyms)
    target_act = None
    for full_name, label in act_names_map.items():
        if full_name.upper() in query_upper:
            target_act = label
            break
            
    if not target_act:
        for act_label_key in acts_data.keys():
            if re.search(rf'\b{act_label_key}\b', query_upper):
                target_act = act_label_key
                break
                
    # 2. Detect section number
    sec_match = re.search(r'\b(?:sec|section|s|u/s)\.?\s*(\d+[A-Z]?)\b', query, re.IGNORECASE)
    target_sec = sec_match.group(1).upper() if sec_match else None
    
    # 3. Handle Direct Match (Highest priority)
    if target_act and target_sec:
        act_sec_map = acts_data.get(target_act)
        if act_sec_map and target_sec in act_sec_map:
            return [(target_act, target_sec, 1000.0)]
        # If the user explicitly asked for a section inside a specific act and it is
        # not present in that act dataset, do not drift into other acts.
        return []
            
    # 4. Handle Direct Match without Act (Check all acts for this section)
    if target_sec and not any(word in query_upper for word in ["WHICH", "LIST", "SHOW", "ALL"]):
        direct_results = []
        for act_label in acts_data:
            if target_sec in acts_data[act_label]:
                direct_results.append((act_label, target_sec, 1000.0))
        if direct_results:
            return direct_results[:3]

    # 5. Semantic Search (Weighted scoring)
    scores = {}
    for act_label, s_num in sections_corpus:
        # Filtering logic
        act_boost = 1.0
        if target_act:
            if act_label == target_act:
                act_boost = 2.0
            else:
                # If they explicitly asked for an act, we filter out others for keyword queries
                if any(word in query_upper for word in ["BNS", "BNSS", "BSA", "TITA", "TCA", "ITA"]):
                    continue 

        sec = acts_data[act_label][s_num]
        key = (act_label, s_num)
        
        current_score = 0.0
        # Title matches
        for t in query_tokens:
            if t in sec['_tokens_title']:
                current_score += 15.0
        # Text matches
        for t in query_tokens:
            if t in sec['_tokens_text']:
                weight = 1.0
                if s_num == "2": weight = 1.5
                current_score += weight
        
        if current_score > 0.0:
            scores[key] = float(current_score) * float(act_boost)
                    
    results = []
    for key_tuple, final_score in scores.items():
        results.append((str(key_tuple[0]), str(key_tuple[1]), float(final_score)))
            
    results.sort(key=lambda x: x[2], reverse=True)
    return results[:5]

def chat():
    load_data()
    if not acts_data:
        print("No acts loaded. Exiting.")
        return
        
    print("\nBNSS & Allied Acts Deterministic Retrieval System V6")
    print("Type 'exit' or 'quit' to stop.")
    
    while True:
        query = input("\nUSER Query: ").strip()
        if not query: continue
        if query.lower() in ['exit', 'quit']: break
        
        if _is_unrelated(query):
            print("SYSTEM: The query does not match any provision in the loaded datasets.")
            continue

        # Use unified search logic
        results = search_sections(query)
            
        if not results:
            print("SYSTEM: No relevant sections found.")
            continue
            
        top_res = results[0]
        top_act, top_sec, top_score = top_res[0], top_res[1], top_res[2]
        full_act_name = FULL_ACT_NAMES.get(top_act, f"**{top_act}**")
        
        # Aggregate multiple sections for conceptual queries without a specific section number
        sec_match = re.search(r'\b(?:sec|section|s|u/s)\.?\s*(\d+[A-Z]?)\b', query, re.IGNORECASE)
        if is_explanation_query(query) and not sec_match and len(results) > 1:
            # Combine top 3 sections for conceptual summary
            combined_texts = []
            for r in results[:3]:
                combined_texts.append(reconstruct_section(r[0], r[1]))
            text_for_explanation = "\n\n---\n\n".join(combined_texts)
            print(f"\nSYSTEM (Conceptual Analysis for {full_act_name}):")
            answer = call_qwen(query, text_for_explanation, full_act_name)
            print(answer)
        elif is_explanation_query(query):
            text_for_explanation = reconstruct_section(top_act, top_sec)
            print(f"\nSYSTEM (Explanation for {full_act_name} Section {top_sec}):")
            answer = call_qwen(query, text_for_explanation, full_act_name)
            print(answer)
        else:
            text_for_explanation = reconstruct_section(top_act, top_sec)
            print(f"\nSYSTEM (Source: {top_act}):")
            print("-" * 50)
            print(text_for_explanation)
            print("-" * 50)
            
            if len(results) > 1:
                # Format extra results cleanly
                others = []
                for r in results[1:3]:
                    others.append(f"{r[0]} S{r[1]}")
                print(f"Note: Also found other relevant sections: {', '.join(others)}")

if __name__ == "__main__":
    chat()
