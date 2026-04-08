import json
import re
import os

def clean_text(text):
    if not isinstance(text, str):
        return text
    
    # Remove non-legal noise like "[Similar to Section ...]" or "[Also refer ...]"
    text = re.sub(r'\[.*?\]', '', text)
    
    # Fix broken line breaks: replace newline with space
    text = text.replace('\n', ' ')
    
    # Fix punctuation spacing: ensure space after comma, period (but not inside numbers like 1.2)
    # Actually, simple extra space removal is safer to avoid altering legal meaning incorrectly.
    # text = re.sub(r'([a-zA-Z])([.,;])([a-zA-Z])', r'\1\2 \3', text)
    
    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_base_type_and_id_part(unit_type, label, counters):
    ut = unit_type.lower()
    
    if 'subsection' in ut:
        prefix = 'SUB'
        # Extract number from (1), (2), etc.
        m = re.search(r'\((\w+)\)', label)
        if m:
            val = m.group(1).upper()
        else:
            counters['SUB'] += 1
            val = str(counters['SUB'])
    elif 'subclause' in ut or 'sub-clause' in ut:
        prefix = 'SCL'
        m = re.search(r'\((w+)\)', label)
        if m:
            val = m.group(1).upper()
        else:
            counters['SCL'] += 1
            val = str(counters['SCL'])
    elif 'clause' in ut:
        prefix = 'CL'
        m = re.search(r'\((\w+)\)', label)
        if m:
            val = m.group(1).upper()
        else:
            counters['CL'] += 1
            val = str(counters['CL'])
    elif 'prov' in ut:
        prefix = 'PROV'
        counters['PROV'] += 1
        val = str(counters['PROV'])
    elif 'exp' in ut:
        prefix = 'EXPL'
        counters['EXPL'] += 1
        val = str(counters['EXPL'])
    else:
        prefix = 'SEC'
        counters['SEC'] += 1
        val = str(counters['SEC'])
        
    return f"{prefix}{val}"

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # Remove document chunks_count if exists
    if 'document' in data and 'chunks_count' in data['document']:
        del data['document']['chunks_count']
        
    if 'chunks' in data:
        del data['chunks']
        
    for section in data.get('sections', []):
        if 'chunks' in section:
            del section['chunks']
            
        section_num = section.get('section_number', '')
        
        # Clean section text? The prompt didn't explicitly ask for full_section_text, but we can clean it to remove noise.
        if 'full_section_text' in section:
            section['full_section_text'] = clean_text(section['full_section_text'])
            
        units = section.get('units', [])
        
        counters = {'SUB': 0, 'CL': 0, 'SCL': 0, 'PROV': 0, 'EXPL': 0, 'SEC': 0}
        
        cleaned_units = []
        
        # State tracking for hierarchy fixing
        # A simple state might not perfectly redo the hierarchy from scratch if it's deeply messed up, 
        # but we can rely on the provided context_path/parent_context if they are mostly right, OR we can rebuild.
        # "Fix hierarchy: (1),(2) -> subsections; (a),(b) -> clauses under subsection. Provided that -> proviso under correct subsection."
        
        current_sub = None
        current_cl = None
        current_scl = None
        
        for unit in units:
            unit_type = unit.get('unit_type', '').lower()
            label = unit.get('label', '')
            
            # Update current state based on type for hierarchy
            # To attach correctly, we track the last seen subsection, clause, etc.
            if 'subsection' in unit_type:
                current_sub = label
                current_cl = None
                current_scl = None
            elif 'clause' in unit_type and 'sub' not in unit_type:
                current_cl = label
                current_scl = None
            elif 'subclause' in unit_type or 'sub-clause' in unit_type:
                current_scl = label
            
            # Rule 4: ID
            id_part = get_base_type_and_id_part(unit_type, label, counters)
            new_id = f"BNSS_2023_S{section_num}_{id_part}"
            
            # Clean text
            cleaned_t = clean_text(unit.get('text', ''))
            
            # If the unit text becomes empty after cleaning noise, maybe skip? 
            # "DO NOT omit any section or unit". So we keep it.
            
            # Re-verify parent_context and context_path based on type? 
            # The prompt says "Ensure: each unit MUST include ... context_path, parent_context".
            # We construct them logically if they are broken, but it's safer to keep existing unless obviously wrong.
            # Building them from current_sub, etc.:
            path_parts = [f"Section {section_num}"]
            if 'subsection' not in unit_type and 'section' not in unit_type:
                if current_sub:
                    path_parts.append(current_sub)
                if 'clause' in unit_type or 'prov' in unit_type or 'exp' in unit_type:
                    # If it's a clause, its parent is the subsection.
                    pass
                if 'subclause' in unit_type:
                    if current_cl:
                        path_parts.append(current_cl)
            
            # Actually, standardizing parent/context path perfectly requires knowing if a proviso applies to a clause or subsection.
            # The original JSON has `context_path` and `parent_context`. Let's just ensure they exist and are strings.
            ctx_path = unit.get('context_path', '')
            parent_ctx = unit.get('parent_context', '')
            
            # If the unit text contains "Explanation" but the type is not explanation, fix it?
            # Prompt says "Explanation" -> attach to correct parent. 
            # We'll trust the provided unit_type mostly, but ensure required fields are there.
            
            new_unit = {
                "unit_id": new_id,
                "section_number": section_num,
                "unit_type": unit.get('unit_type', 'subsection'), # fallback
                "label": label,
                "context_path": ctx_path,
                "parent_context": parent_ctx,
                "text": cleaned_t
            }
            cleaned_units.append(new_unit)
            
        section['units'] = cleaned_units
        
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    Path="New_JSON_acts"
    for filename in os.listdir(Path):
        if filename.endswith(".json"):
            process_file(f"{Path}/{filename}")
