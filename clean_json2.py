import json
import re
import os
def clean_text(text):
    if not isinstance(text, str):
        return text
    
    # 2. REMOVE NON-LEGAL NOISE
    # Remove things like "[Similar to Section ...]"
    text = re.sub(r'\[.*?\]', '', text)
    # Remove stray Chapter headers inside text if present, like "Chapter II ..."
    # We should be careful not to remove valid part of text, but "Chapter " at the beginning of a line
    text = re.sub(r'^\s*Chapter\s+[IVXLCDM]+\s*-?\s*.*?\n', '', text, flags=re.IGNORECASE|re.MULTILINE)
    
    # 1. PRESERVE LEGAL TEXT (Fix extra spaces, broken line breaks, punctuation spacing)
    text = text.replace('\n', ' ')
    
    # Punctuation spacing: ensure a space after full stop and comma, unless it's a number like 1.2
    # This might be tricky, so let's stick to safe replaces.
    # Replace multiple spaces with single space.
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def parse_label_from_text_or_current(text, current_label):
    # Try to extract the true label if the unit is somewhat misclassified initially
    return current_label

def detect_type_and_label(text, current_type, current_label):
    text_stripped = text.strip()
    # Check if Proviso
    if re.match(r'^Provided\s+(that|further)', text_stripped, re.IGNORECASE):
        return 'proviso', current_label if 'prov' in current_type.lower() else ''
    # Check if Explanation
    if re.match(r'^Explanation\b', text_stripped, re.IGNORECASE):
        return 'explanation', current_label if 'exp' in current_type.lower() else ''
        
    return current_type, current_label

def build_unit_id(section_num, unit_type, label, counters):
    ut = unit_type.lower()
    if 'subclause' in ut or 'sub-clause' in ut:
        prefix = 'SCL'
        m = re.search(r'\(([ivxIVX]+)\)', label)
        if m:
            val = m.group(1).upper()
        else:
            counters['SCL'] += 1
            val = str(counters['SCL'])
    elif 'clause' in ut:
        prefix = 'CL'
        m = re.search(r'\(([a-zA-Z])\)', label)
        if m:
            val = m.group(1).upper()
        else:
            counters['CL'] += 1
            val = str(counters['CL'])
    elif 'subsection' in ut:
        prefix = 'SUB'
        m = re.search(r'\((\d+)\)', label)
        if m:
            val = m.group(1).upper()
        else:
            counters['SUB'] += 1
            val = str(counters['SUB'])
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
        
    return f"BNSS_2023_S{section_num}_{prefix}{val}"

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # 6. REMOVE chunks completely globally
    if 'document' in data and 'chunks_count' in data['document']:
        del data['document']['chunks_count']
    if 'chunks' in data:
        del data['chunks']
        
    for section in data.get('sections', []):
        if 'chunks' in section:
            del section['chunks']
            
        section_num = str(section.get('section_number', ''))
        section_title = clean_text(section.get('section_title', ''))
        section['section_title'] = section_title
        
        # Clean section text? Prompt doesn't explicitly mention it, but usually good to do
        if 'full_section_text' in section:
            section['full_section_text'] = clean_text(section['full_section_text'])
            
        units = section.get('units', [])
        
        counters = {'SUB': 0, 'CL': 0, 'SCL': 0, 'PROV': 0, 'EXPL': 0, 'SEC': 0}
        cleaned_units = []
        
        # Track hierarchy state
        current_sub_label = None
        current_cl_label = None
        current_scl_label = None
        
        for unit in units:
            unit_type = unit.get('unit_type', '').lower()
            label = str(unit.get('label', '')).strip()
            text = unit.get('text', '')
            
            # 8. DO NOT ADD variables like embeddings, keywords, summaries
            for key in list(unit.keys()):
                if key not in ['unit_id', 'section_number', 'unit_type', 'label', 'context_path', 'parent_context', 'text']:
                    del unit[key]
                    
            text = clean_text(text)
            if not text:
                continue
            
            # Detect Proviso and Explanation based on text
            unit_type, label = detect_type_and_label(text, unit_type, label)
            if unit_type == 'proviso' and not label:
                label = f"proviso_{counters['PROV']+1}"
            elif unit_type == 'explanation' and not label:
                label = f"explanation_{counters['EXPL']+1}"
                
            # If label has no brackets but should for sub/cl/scl based on original text (e.g. 1 instead of (1))
            # Just keep label as is or use the detected match
            
            # Rule 5: Fix Hierarchy
            if 'subsection' in unit_type:
                current_sub_label = label
                current_cl_label = None
                current_scl_label = None
            elif 'clause' in unit_type and 'sub' not in unit_type:
                current_cl_label = label
                current_scl_label = None
            elif 'subclause' in unit_type or 'sub-clause' in unit_type:
                current_scl_label = label
                
            # Construct parent_context and context_path based on logical tracker
            # Parent of subsection -> Section
            # Parent of clause -> Section > (1) [subsection] OR Section (if no sub)
            # Parent of proviso -> Section > (1) > (a) OR Section > (1) OR Section
            # Explanation -> Section OR Section > (1)
            parent_parts = [f"Section {section_num}"]
            
            if unit_type == 'subsection':
                pass # Parent is just Section
            elif unit_type == 'clause':
                if current_sub_label:
                    parent_parts.append(current_sub_label)
            elif unit_type == 'subclause' or unit_type == 'sub-clause':
                if current_sub_label:
                    parent_parts.append(current_sub_label)
                if current_cl_label:
                    parent_parts.append(current_cl_label)
            elif unit_type == 'proviso':
                if current_sub_label:
                    parent_parts.append(current_sub_label)
                if current_cl_label:
                    parent_parts.append(current_cl_label)
                if current_scl_label:
                    parent_parts.append(current_scl_label)
            elif unit_type == 'explanation':
                # Explanations can be attached to sections or subsections.
                if current_sub_label:
                    parent_parts.append(current_sub_label)
                # Usually not to clauses unless specifically stated. We'll attach to the deepest non-proviso
                if current_cl_label:
                    parent_parts.append(current_cl_label)
            else:
                pass
                
            parent_context = " > ".join(parent_parts)
            
            # For context path, append the current unit's label
            # E.g. "Section 1 > (1) > (a)"
            if unit_type == 'subsection' or unit_type == 'clause' or 'subclause' in unit_type:
                context_path = " > ".join(parent_parts + [label])
            else:
                # Provisos and explanations don't always naturally nest as paths in the same way, 
                # but they are part of the unit. The prompt implies path should exist and match hierarchy.
                # E.g. Section 1 > (1) ...
                if label:
                    context_path = " > ".join(parent_parts + [label])
                else:
                    context_path = parent_context
            
            # 4. Unit ID Format
            unit_id = build_unit_id(section_num, unit_type, label, counters)
            
            # 3. Ensure each unit includes ALL fields
            cleaned_unit = {
                "unit_id": unit_id,
                "section_number": section_num,
                "unit_type": unit_type,
                "label": label,
                "context_path": context_path,
                "parent_context": parent_context,
                "text": text
            }
            cleaned_units.append(cleaned_unit)
            
        section['units'] = cleaned_units
        
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    Path="New_JSON_acts"
    for filename in os.listdir(Path):
        if filename.endswith(".json"):
            process_file(f"{Path}/{filename}")
