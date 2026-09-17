from pathlib import Path
import json
import title_process
import authors_process

API_KEY = '1zTVOtVqV24hSlNNeF2YZ14aduaPiHyPaZ1YmJwC'

title = {}
title_edits = {}
authors = {}
authors_edits = {}
affiliations = {}
affiliations_edits = {}
corresponding_address = {}
corresponding_address_edits = {}
abstract = {}
abstract_edits = {}

def main():
    print("Hello from main.py!")
    for path in Path("/home/souvikm/elsevier-notebooks/unedited").iterdir():
        if path.is_file() and path.suffix == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # print(data['file'])
                # print(f"Loaded {path.name}:")
                # print(data.keys())
                c = 0
                for d in data.keys():
                    # print(data['file'])
                    if 'Title' in d:
                        title[data['file']] = data[d] or ""
                        # print(data[d])
                    if 'Author' in d and 'name' in d:
                        authors[data['file']] = data[d] or ""
                        # print(data[d])
                    if 'Author' in d and 'affiliation' in d:
                        affiliations[data['file']] = data[d] or ""
                        # print(data[d])
                    # if 'Corresponding' in d and 'author' in d and 'address' in d:
                    #     corresponding_address[data['file']] = data[d]
                    #     print(data[d])
                    if 'Abstract' in d:
                        abstract[data['file']] = data[d]
                        # print(data[d])
            print(data['file'])
            key = data['file']
            title_edits[key] = title_process.do_all_title_checks(title[key],"gpt-5.4",API_KEY)
            print(title_edits)
            authors_edits[key] = authors_process.do_all_authors_checks(authors[key],"gpt-5.4",API_KEY)

            print("=================================================================")
    print(title_edits)
    print(authors_edits)

if __name__ == "__main__":
    main()