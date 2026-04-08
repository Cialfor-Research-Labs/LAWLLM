import json
import os
from collections import defaultdict

folder = 'New_JSON_acts'
files = [f for f in os.listdir(folder) if f.endswith('.json')]

# Expected top-level sections
expected_keys = {'schema_version', 'document', 'sections'}
doc_expected_keys = {'document_id', 'document_type', 'title', 'jurisdiction', 'source_file', 'sections_count'}
section_expected_keys = {'section_number', 'section_title', 'full_section_text', 'units'}
unit_expected_keys = {'unit_id', 'section_number', 'unit_type', 'label', 'context_path', 'parent_context', 'text_original', 'text_cleaned'}

missing_report = defaultdict(list)
files_with_issues = []

print(f'Analyzing {len(files)} JSON files...\n')

for file in sorted(files):
    try:
        with open(os.path.join(folder, file), 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Check top-level keys
        missing_top = expected_keys - set(data.keys())
        if missing_top:
            files_with_issues.append(file)
            missing_report[file].append(f'Missing top-level keys: {missing_top}')
        
        # Check document keys
        if 'document' in data:
            missing_doc = doc_expected_keys - set(data['document'].keys())
            if missing_doc:
                files_with_issues.append(file)
                missing_report[file].append(f'Missing document keys: {missing_doc}')
        
        # Check sections
        if 'sections' in data:
            for idx, section in enumerate(data['sections'][:2]):  # Check first 2 sections
                missing_sec = section_expected_keys - set(section.keys())
                if missing_sec:
                    missing_report[file].append(f'Section {idx} missing keys: {missing_sec}')
                
                # Check units
                if 'units' in section:
                    for u_idx, unit in enumerate(section['units'][:1]):
                        missing_unit = unit_expected_keys - set(unit.keys())
                        if missing_unit and u_idx == 0:
                            missing_report[file].append(f'Section {idx}, Unit {u_idx} missing keys: {missing_unit}')
    except Exception as e:
        missing_report[file].append(f'Error reading file: {str(e)[:100]}')
        files_with_issues.append(file)

# Print summary
print('=== JSON STRUCTURE ANALYSIS ===\n')

if files_with_issues:
    for file in sorted(missing_report.keys()):
        if missing_report[file]:
            print(f'{file}:')
            for issue in missing_report[file]:
                print(f'  - {issue}')
            print()
else:
    print('✓ All JSON files have complete structure!')

print(f'\nSummary:')
print(f'  Total files analyzed: {len(files)}')
print(f'  Files with issues: {len(files_with_issues)}')
print(f'  Files with complete structure: {len(files) - len(files_with_issues)}')
