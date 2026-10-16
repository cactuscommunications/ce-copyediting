from pathlib import Path
import json
import journal_list_helper
import reference_helper

path = journal_list_helper.download_medline_journals()

journals = journal_list_helper.parse_medline_journals(path)

journal_dict = journal_list_helper.create_journal_dict(journals)

print(len(journal_dict))
print(journal_dict.get("American Journal of Preventive Medicine".lower())['med_abbr'])

references = {}

for path in Path("/home/souvikm/Downloads/test-elsevier/test-pipeline/doc_json").iterdir():
    if path.is_file() and path.suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # print(data['file'])
            # print(f"Loaded {path.name}:")
            # print(data.keys())
            c = 0
            for d in data.keys():
                # print(data['file'])
                if 'References' in d :
                    references[data['file']] = data[d] or ""

print(len(references))


print(len(references))
res_list = dict()
final_ref_map = {}
for k, ref in references.items():
    all_refs = ref.split('\n')
    # all_refs = all_refs[:3]
    print(len(all_refs))
    all_ref_objs = []
    for r in all_refs:
        if 'reference' in r.lower():
            continue
        ref_dict = reference_helper.parse_reference_deter(r)
        all_ref_objs.append(ref_dict)
    res_list[k] = all_ref_objs
    final_ref_map[k] = reference_helper.get_ref_result_list(res_list[k], journal_dict)


import highlight_excel

highlight_excel.create_highlighted_workbook(
    final_ref_map,
    "final_reference_results.xlsx",
)