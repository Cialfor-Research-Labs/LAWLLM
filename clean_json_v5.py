import json
import os
import re
import sys

def clean_text_with_log(text):
    if not isinstance(text, str):
        return text, []
    
    log = []
    original_text = text
    
    # 1. CRITICAL BUG: Fix precise removal
    # Only remove known junk patterns.
    junk_pattern = r'\[(Similar to Section|Also refer|Also Refer).*?\]'
    if re.search(junk_pattern, text, flags=re.IGNORECASE):
        text = re.sub(junk_pattern, '', text, flags=re.IGNORECASE)
        log.append("Removed known junk patterns ([Similar to Section...])")
        
    # Remove stray headers
    chapter_pattern = r'\bChapter\s+[IVXLCDM]+\b[^\.]*?(?=\s|$)'
    if re.search(chapter_pattern, text, flags=re.IGNORECASE):
        text = re.sub(chapter_pattern, '', text, flags=re.IGNORECASE)
        log.append("Removed stray Chapter headers")
    
    # 5. Fix: Line breaks
    if '\n' in text:
        text = re.sub(r'\n+', ' \n ', text)
        log.append("Preserved line breaks as structural hints")
        
    # Extra spaces (but careful not to destroy ` \n `)
    # We can clean multiple spaces that are NOT around newlines, but simply replacing `  ` with ` ` is safer.
    text_before_space_clean = text
    text = re.sub(r'[ \t]+', ' ', text).strip()  # preserve \n because [ \t] doesn't match \n
    if text != text_before_space_clean:
        if "Normalized horizontal spaces" not in log:
            log.append("Normalized horizontal spaces")
            
    return text, log

def build_unit_id(section_num, unit_type, label, counters, current_sub_label, current_cl_label, current_scl_label):
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
        # Scope subclause by its parent clause and subsection
        scope = ""
        if current_sub_label:
            ms = re.search(r'\((\d+)\)', current_sub_label)
            if ms: scope += f"{ms.group(1)}_"
        if current_cl_label:
            mc = re.search(r'\(([A-Za-z])\)', current_cl_label)
            if mc: scope += f"{mc.group(1).upper()}_"
        val = scope + val

    elif 'item' in ut:
        prefix = 'ITEM'
        m = re.search(r'\(([A-Za-z])\)', label)
        if m: val = m.group(1).upper()
        else:
            counters['ITEM'] = counters.get('ITEM', 0) + 1
            val = str(counters['ITEM'])
        scope = ""
        if current_sub_label:
            ms = re.search(r'\((\d+)\)', current_sub_label)
            if ms: scope += f"{ms.group(1)}_"
        if current_cl_label:
            mc = re.search(r'\(([A-Za-z])\)', current_cl_label)
            if mc: scope += f"{mc.group(1).upper()}_"
        # add SCL scope just in case, but usually we don't have current_scl_label passed here.
        # Wait, I didn't pass current_scl_label to build_unit_id. Let's just pass it!
        val = scope + val

    elif 'clause' in ut:
        prefix = 'CL'
        m = re.search(r'\(([A-Za-z])\)', label)
        if m:
            val = m.group(1).upper()
        else:
            counters['CL'] += 1
            val = str(counters['CL'])
        scope = ""
        if current_sub_label:
            ms = re.search(r'\((\d+)\)', current_sub_label)
            if ms: scope += f"{ms.group(1)}_"
        val = scope + val

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
        
    return f"BNSS_2023_S{section_num}_{prefix}_{val}"

def process_file(filepath, output_filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return
        
    if 'document' in data and 'chunks_count' in data['document']:
        del data['document']['chunks_count']
    if 'chunks' in data:
        del data['chunks']
        
    seen_ids = set()
    
    for section in data.get('sections', []):
        if 'chunks' in section:
            del section['chunks']
            
        section_num = str(section.get('section_number', '')).strip()
        
        section_title_orig = section.get('section_title', '')
        section_title_cleaned, _ = clean_text_with_log(section_title_orig)
        section['section_title'] = section_title_cleaned
        
        if 'full_section_text' in section:
            fst_cleaned, _ = clean_text_with_log(section['full_section_text'])
            section['full_section_text'] = fst_cleaned
            
        units = section.get('units', [])
        counters = {'SUB': 0, 'CL': 0, 'SCL': 0, 'PROV': 0, 'EXPL': 0, 'SEC': 0}
        cleaned_units = []
        
        current_sub_label = None
        current_cl_label = None
        current_scl_label = None
        current_item_label = None
        last_structural_unit = 'section'  # to attach provisos properly
        
        for i, unit in enumerate(units):
            original_type = unit.get('unit_type', '').lower()
            label = str(unit.get('label', '')).strip()
            original_text = unit.get('text', '')
            if original_text is None:
                original_text = ''
            
            # 6. Silent Data Loss Fix
            if not str(original_text).strip():
                original_text = "[EMPTY]"
                
            text_cleaned, cleaning_log = clean_text_with_log(original_text)
            text_stripped = text_cleaned.lstrip()
            
            unit_type = original_type
            
            # 2. LOGIC FLAW - TYPE DETECTION ORDER (1. Label first, 2. Text override)
            detected_from_label = False
            
            # Simple lookahead to disambiguate (i) as clause or subclause or item
            if label == '(i)':
                is_subclause = False
                # Look ahead in the remaining units
                for ahead_unit in units[i+1:]:
                    ahead_label = str(ahead_unit.get('label', '')).strip()
                    if ahead_label == '(ii)':
                        is_subclause = True
                        break
                    elif ahead_label == '(j)':
                        is_subclause = False
                        break
                    # if we see (a) or (1) it means we exited the block, so default to clause if following (h)
                
                if is_subclause:
                    if current_item_label == '(h)':
                        unit_type = 'item'
                    elif current_cl_label == '(h)':
                        unit_type = 'clause'
                    else:
                        unit_type = 'subclause'
                else:
                    if current_cl_label == '(h)':
                        unit_type = 'clause'
                    elif current_item_label == '(h)':
                        unit_type = 'item'
                    else:
                        unit_type = 'subclause'
                detected_from_label = True

            elif re.match(r'^\(\d+\)$', label):
                unit_type = 'subsection'
                detected_from_label = True
            elif re.match(r'^\([a-z]\)$', label) and not re.match(r'^\(x{0,3}(ix|iv|v?i{0,3})\)$', label):
                if current_scl_label:
                    char_curr = label[1:-1]
                    if not current_item_label and char_curr == 'a':
                        unit_type = 'item'
                    elif current_item_label:
                        char_prev_item = current_item_label[1:-1]
                        if ord(char_curr) == ord(char_prev_item) + 1:
                            unit_type = 'item'
                        else:
                            unit_type = 'clause'
                    else:
                        unit_type = 'clause'
                else:
                    unit_type = 'clause'
                detected_from_label = True
            elif re.match(r'^\(x{0,3}(ix|iv|v?i{0,3})\)$', label) and label != '()':
                if current_cl_label:
                    unit_type = 'subclause'
                else:
                    unit_type = 'clause'
                detected_from_label = True

            # If label didn't strictly give a structural type, check text for proviso/explanation
            if not detected_from_label:
                if re.match(r'^Provided\s+(that|further)', text_stripped, re.IGNORECASE):
                    unit_type = 'proviso'
                elif re.match(r'^Explanation\b', text_stripped, re.IGNORECASE):
                    unit_type = 'explanation'
                
            if unit_type == 'proviso' and 'prov' not in label.lower():
                label = f"proviso_{counters['PROV']+1}"
            elif unit_type == 'explanation' and 'exp' not in label.lower():
                label = f"explanation_{counters['EXPL']+1}"
            
            # 4. HIERARCHY DRIFT (SUBTLE BUT DEADLY)
            
            # Incorporate original annotations ONLY for subsection to catch completely missing headers (e.g. Section 151(2))
            orig_sub = str(unit.get('subsection', '')).strip()

            if orig_sub and orig_sub != 'None' and orig_sub != current_sub_label:
                # We crossed a subsection boundary that wasn't explicitly represented by a standalone subsection unit
                current_sub_label = orig_sub
                current_cl_label = None
                current_scl_label = None
                current_item_label = None
                last_structural_unit = 'subsection'

            if 'subsection' in unit_type:
                current_sub_label = label
                current_cl_label = None
                current_scl_label = None
                current_item_label = None
                last_structural_unit = 'subsection'
            elif 'clause' in unit_type and 'sub' not in unit_type:
                current_cl_label = label
                current_scl_label = None
                current_item_label = None
                if 'clause' not in last_structural_unit:
                    last_structural_unit = 'clause'
            elif 'subclause' in unit_type or 'sub-clause' in unit_type:
                current_scl_label = label
                current_item_label = None
                last_structural_unit = 'subclause'
            elif unit_type == 'item':
                current_item_label = label
                last_structural_unit = 'item'
                
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
            elif unit_type == 'item':
                if current_sub_label:
                    parent_parts.append(current_sub_label)
                if current_cl_label:
                    parent_parts.append(current_cl_label)
                if current_scl_label:
                    parent_parts.append(current_scl_label)
            elif unit_type == 'proviso':
                # Attach based on last structural unit
                if current_sub_label:
                    parent_parts.append(current_sub_label)
                if last_structural_unit in ['clause', 'subclause'] and current_cl_label:
                    parent_parts.append(current_cl_label)
                if last_structural_unit == 'subclause' and current_scl_label:
                    parent_parts.append(current_scl_label)
            elif unit_type == 'explanation':
                # Explanations often attach to section or subsection.
                if current_sub_label:
                    parent_parts.append(current_sub_label)
                if last_structural_unit in ['clause', 'subclause'] and current_cl_label:
                    parent_parts.append(current_cl_label)
            
            parent_context = " > ".join(parent_parts)
            
            if unit_type == 'subsection' or ('clause' in unit_type and 'sub' not in unit_type) or ('subclause' in unit_type or 'sub-clause' in unit_type):
                context_path = " > ".join(parent_parts + [label])
            else:
                if label:
                    context_path = " > ".join(parent_parts + [label])
                else:
                    context_path = parent_context

            # 3. ID COLLISION RISK
            if section_num == "193":
                print(f"Sec 193 -> Label: {label}, UnitType: {unit_type}, Sub: {current_sub_label}, Cl: {current_cl_label}, Scl: {current_scl_label}")
            unit_id_base = build_unit_id(section_num, unit_type, label, counters, current_sub_label, current_cl_label, current_scl_label)
            unit_id = unit_id_base
            collision_counter = 1
            while unit_id in seen_ids:
                print(f"DUPLICATE RESOLVED! Section: {section_num}, Unit type: {unit_type}, Label: {label}")
                # Append disambiguator to not crash the batch job, because Schedules are stuffed in Section 531
                unit_id = f"{unit_id_base}_DUP{collision_counter}"
                collision_counter += 1
                
            seen_ids.add(unit_id)
            
            # 8. BIGGEST ARCHITECTURAL GAP (Audit Trail)
            cleaned_unit = {
                "unit_id": unit_id,
                "section_number": section_num,
                "unit_type": unit_type if unit_type else "section",
                "label": label if label else "No Label",
                "context_path": context_path,
                "parent_context": parent_context,
                "text_original": original_text,
                "text_cleaned": text_cleaned,
                "cleaning_log": cleaning_log
            }
            cleaned_units.append(cleaned_unit)
            
        section['units'] = cleaned_units
        
    with open(output_filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Done generating V5!")

if __name__ == "__main__":
    Path="New_JSON_acts"
    for filename in os.listdir(Path):
        if filename.endswith(".json"):
            process_file((f"{Path}/{filename}"),( f"{Path}/{filename}"))