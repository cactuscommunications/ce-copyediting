from pathlib import Path
import json
import journal_list_helper
import reference_helper
import new_excel_helper
import gliner_util

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
        # print(r)
        # print(f'--------ACTUAL REF{r}')
        # extracted_doi = gliner_util.extract_dois(r)
        # if 'No DOI found' not in extracted_doi:
        #     print(f'EXTRACTED DOI -> {extracted_doi}')
        #     page_info = gliner_util.extract_page_info(r)
        ref_dict = reference_helper.parse_reference_deter(r)
        # # print(page_info)
        # print()
        all_ref_objs.append(ref_dict)
        # print()
    res_list[k] = all_ref_objs
    final_ref_map[k] = reference_helper.get_ref_result_list(res_list[k], journal_dict)

# print(len(res_list))



# for k,all_refs in res_list.items():
#     final_ref_map[k] = reference_helper.get_ref_result_list(all_refs, journal_dict, 3)

# new_excel_helper.create_reference_edits_excel(
#     final_ref_map,
#     "final_reference_results.xlsx",
# )

import highlight_excel

highlight_excel.create_highlighted_workbook(
    final_ref_map,
    "final_reference_results.xlsx",
)