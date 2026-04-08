import json
import os
import re
import sys

def clean_text(text):
    if not isinstance(text, str):
        return text
    
    # 2. REMOVE NON-LEGAL NOISE
    text = re.sub(r'\[.*?\]', '', text)
    
    # Remove stray headers like "Chapter II" appearing in the middle of a line.
    # The prompt actually says: stray headers like "Chapter II ..." inside section text.
    # We can remove lines matching exact chapter headers. Wait, replacing lines might be dangerous.
    # Let's just remove specific stray patterns if any. Rule 2 specifically mentioned it.
    text = re.sub(r'\bChapter\s+[IVXLCDM]+\b[^\.]*?(?=\s|$)', '', text, flags=re.IGNORECASE)
    
    # 1. PRESERVE LEGAL TEXT (Fix extra spaces, broken line breaks, punctuation spacing)
    text = text.replace('\n', ' ')
    
    # Extra spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def build_unit_id(section_num, unit_type, label, counters):
    ut = unit_type.lower()
    val = ""
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
        m = re.search(r'\(([A-Za-z])\)', label)
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
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return
        
    # 6. Delete 'chunks' & related globally
    if 'document' in data and 'chunks_count' in data['document']:
        del data['document']['chunks_count']
    if 'chunks' in data:
        del data['chunks']
        
    for section in data.get('sections', []):
        if 'chunks' in section:
            del section['chunks']
            
        section_num = str(section.get('section_number', '')).strip()
        section_title = clean_text(section.get('section_title', ''))
        section['section_title'] = section_title
        
        if 'full_section_text' in section:
            section['full_section_text'] = clean_text(section['full_section_text'])
            
        units = section.get('units', [])
        counters = {'SUB': 0, 'CL': 0, 'SCL': 0, 'PROV': 0, 'EXPL': 0, 'SEC': 0}
        cleaned_units = []
        
        current_sub_label = None
        current_cl_label = None
        current_scl_label = None
        
        for unit in units:
            unit_type = unit.get('unit_type', '').lower()
            label = str(unit.get('label', '')).strip()
            text = unit.get('text', '')
            
            text = clean_text(text)
            if not text:
                continue
                
            text_stripped = text.lstrip()
            if re.match(r'^Provided\s+(that|further)', text_stripped, re.IGNORECASE):
                unit_type = 'proviso'
            elif re.match(r'^Explanation\b', text_stripped, re.IGNORECASE):
                unit_type = 'explanation'
                
            if unit_type == 'proviso' and 'prov' not in label.lower():
                label = f"proviso_{counters['PROV']+1}"
            elif unit_type == 'explanation' and 'exp' not in label.lower():
                label = f"explanation_{counters['EXPL']+1}"
            
            # hierarchy tracking
            if 'subsection' in unit_type:
                current_sub_label = label
                current_cl_label = None
                current_scl_label = None
            elif 'clause' in unit_type and 'sub' not in unit_type:
                current_cl_label = label
                current_scl_label = None
            elif 'subclause' in unit_type or 'sub-clause' in unit_type:
                current_scl_label = label
                
            parent_parts = [f"Section {section_num}"]
            
            if 'subsection' in unit_type:
                pass
            elif 'clause' in unit_type and 'sub' not in unit_type:
                if current_sub_label:
                    parent_parts.append(current_sub_label)
            elif 'subclause' in unit_type or 'sub-clause' in unit_type:
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
                if current_sub_label:
                    parent_parts.append(current_sub_label)
            
            parent_context = " > ".join(parent_parts)
            
            if unit_type == 'subsection' or ('clause' in unit_type and 'sub' not in unit_type) or ('subclause' in unit_type or 'sub-clause' in unit_type):
                context_path = " > ".join(parent_parts + [label])
            else:
                if label:
                    context_path = " > ".join(parent_parts + [label])
                else:
                    context_path = parent_context

            # 4. ID Format
            unit_id = build_unit_id(section_num, unit_type, label, counters)
            
            # 3. Required keys
            cleaned_unit = {
                "unit_id": unit_id,
                "section_number": section_num,
                "unit_type": unit_type if unit_type else "section",
                "label": label if label else "No Label",
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