#PREPOSITION CHECK START
import spacy
nlp = spacy.load("en_core_web_sm")

AMBIGUOUS_PREPOSITIONS = {
    "about","above","across","after","against","along","around","before","behind","below",
    "beneath","beside","between","beyond","during","inside","outside","over","past","round",
    "since","through","throughout","toward","towards","under","underneath","until","upon","within",
    "without","like",}

AMBIGUOUS_CONJUNCTIONS = {
    "and", "but", "or", "nor", "for", "yet", "so",
}

def fix_title_case(title: str) -> str:
    doc = nlp(title)
    output = []

    for token in doc:
        text = token.text

        if token.i == 0:
            output.append(text + token.whitespace_)
            continue
        
        if token.is_alpha:
            lower = token.lemma_.lower()

            is_preposition = (
                token.pos_ == "ADP"
                or lower in AMBIGUOUS_PREPOSITIONS
            )

            is_conjunction = (
                token.pos_ == "CCONJ"
                or lower in AMBIGUOUS_CONJUNCTIONS
            )

            is_pronoun = (
                token.pos_ in {"DET", "PRON"}
            )

            if is_preposition or is_conjunction or is_pronoun:
                if len(lower) >= 4:
                    text = lower.capitalize()
                else:
                    text = lower

        output.append(text + token.whitespace_)

    return "".join(output)


# print(fix_title_case('Alcohol Use Disorder And Depression Among Community-Based Clinic Patients Before And During 
# The COVID-19 Public Health Emergency By Smoking Status'))




import errant

def call_errant(original_text, edited_text) -> str:
    annotator = errant.load("en")
    orig_parsed = annotator.parse(original_text)
    edited_parsed = annotator.parse(edited_text)
    edits = annotator.annotate(orig_parsed, edited_parsed)

    # print(edits)
    # Generate errant edits string
    # errant_edits_list = [f'edit {i} : "{e.o_str}" to "{e.c_str}"' for i, e in enumerate(edits)]
    errant_edits_list = [{"from": e.o_str, "to": e.c_str} for i, e in enumerate(edits)]
    # print(errant_edits_list)
    errant_edits_map = {
        f"edit {i}": {
            "from": e.o_str,
            "to": e.c_str,
        }
        for i, e in enumerate(edits)
    }
    # print(errant_edits_list)
    # for i, e in enumerate(edits):
    #     print(e.o_start, e.o_end, e.o_str, e.c_start, e.c_end, e.c_str, e.type)
    if not errant_edits_list:
        return []
    return errant_edits_list

# print(call_errant('Title:Testing for Lipid Levels and Diabetes Among Autistic Youth Who Are and Are Not Prescribed Anti-Psychotics:
#  A Cohort Study','Testing for Lipid Levels and Diabetes Among Youth With Autism Who Are and Are Not Prescribed Antipsychotics: A Cohort Study'))


def prepositions_check_method(titles):
    results = dict()
    for f,t in titles.items():
        # print(f)
        # print(t)
        all_edits = []
        if ':' in t:
            print('Subtitle found!')
            t1 = t.split(':')[0].strip()
            t2 = t.split(':')[1].strip()
            all_edits = call_errant(t1, fix_title_case(t1))
            all_edits += call_errant(t2, fix_title_case(t2))
            # print(all_edits)
            results[f] = all_edits
            # print(call_errant(t1, fix_title_case(t1)))
            # print(call_errant(t2, fix_title_case(t2)))
            continue

        fixed_case = fix_title_case(t)
        all_edits = call_errant(t,fixed_case)
        # print(all_edits)
        results[f] = all_edits
        # print(call_errant(t,fixed_case))
    all_results = {}

    for f, r in results.items():
        all_results[f] = []

        for e in r:
            temp = {
                "guideline_followed": False,
                "guideline_id": "title_case_constraint",
                "reason": "Inconsistent case",
                "affected_text": e["from"],
                "suggested_replacement": e["to"],
            }

            all_results[f].append(temp)
    return all_results

def prepositions_check_method_single(title):
    results = dict()
    # for f,t in titles.items():
    # print(f)
    t = title
    all_edits = []
    if ':' in t:
        print('Subtitle found!')
        t1 = t.split(':')[0]
        t2 = t.split(':')[1]
        all_edits = call_errant(t1, fix_title_case(t1))
        all_edits += call_errant(t2, fix_title_case(t2))
        # print(all_edits)
        # results[f] = all_edits
        # print(call_errant(t1, fix_title_case(t1)))
        # print(call_errant(t2, fix_title_case(t2)))
    else:
        fixed_case = fix_title_case(t)
        all_edits = call_errant(t,fixed_case)
    # print(all_edits)
    # results[f] = all_edits
    # print(call_errant(t,fixed_case))
    all_results = []

    for e in all_edits:
        temp = {
            "guideline_followed": False,
            "guideline_id": "title_case_constraint",
            "reason": "Inconsistent case",
            "affected_text": e["from"],
            "suggested_replacement": e["to"],
        }
        all_results.append(temp)

    return all_results

#PREPOSITION CHECK END


import json
import requests
import re
import time


class PollingTimeoutError(Exception):
    pass

def post_and_poll(
    submit_url: str,
    poll_url: str,
    payload: str,
    headers,
    poll_interval: int = 5,
    timeout: int = 300,
    verify_ssl: bool = True,
):

    response = requests.request("POST", submit_url, headers=headers, data=payload)
    # response.raise_for_status()

    submit_response = response.json()
    # print(submit_response)
    job_id = submit_response.get("fetch_id")
    if not job_id:
        raise RuntimeError("No jobId found in submission response.")

    start = time.time()

    while True:
        if time.time() - start > timeout:
            raise PollingTimeoutError(
                f"Polling timed out after {timeout} seconds."
            )
        
        poll_response = requests.request("GET", f"{poll_url}?fetch_id={job_id}", headers=headers)
        # poll_response.raise_for_status()

        result = poll_response.json()
        # print(result)
        status = str(result.get("status", "")).upper()

        if status in ("COMPLETED", "SUCCESS", "DONE", "TRUE"):
            return result

        if status in ("FAILED", "ERROR"):
            raise RuntimeError(f"Job failed: {result}")

        time.sleep(poll_interval)


def build_payload(system_prompt, user_prompt, model):
    payload = json.dumps(
    [
        {
            "job_config": {
                "chat_params": {
                    "model": model,  #llama-3.3-70b,claude-4.6-opus, Minotaur,gpt-4o,claude-3-sonnet,claude-3.5-sonnet
                    "temperature": 0,
                    # "max_tokens": 10000,
                    "stream": False
                },
                "verbose": False,
                "check_input_for_sensitivity": False,
                "to_mock_response": False,
            },
            "metadata": {},
            "list_of_messages": [
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompt,
                        },
                        {"role": "assistant", "content": "Okay"},
                        {
                            "role": "user",
                            "content": user_prompt,
                        },
                    ]
                }
            ],
        }
    ]
)
    return payload       

import re
import json
from json_repair import repair_json
from pydantic import BaseModel
from typing import Type, TypeVar

T = TypeVar("T", bound=BaseModel)


def extract_json_objects(text: str):
    objects = []
    depth = 0
    start = None
    in_string = False
    escape = False

    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue

        if ch == "\\":
            escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(text[start:i + 1])

    return objects


def parse_repaired_objects(response: str, model: Type[T]) -> list[T]:
    result = []

    for obj in extract_json_objects(response):
        repaired = repair_json(obj)
        parsed = json.loads(repaired)
        result.append(model.model_validate(parsed))

    return result


import requests
import time
import json
import re
from typing import List, Dict

# Common non-abbreviation words that may appear in all caps (mostly headings)
STOPWORDS = {
    "THE", "AND", "FOR", "WITH", "FROM", "THIS", "THAT",
    "TABLE", "FIGURE", "RESULTS", "METHODS", "INTRODUCTION",
    "DISCUSSION", "CONCLUSION", "ABSTRACT", "KEYWORDS" ,"E.G.",
    "CI"
}

PATTERNS = {
    # DNA, RNA, MRI, WHO
    "uppercase": re.compile(r"\b[A-Z]{2,}(?:[A-Z0-9-]*)\b"),

    # U.S., U.K., e.g., i.e.
    "dotted": re.compile(r"\b(?:[A-Za-z]\.){2,}"),

    # COVID-19, IL-6, SARS-CoV-2, TNF-α
    "scientific": re.compile(
        # r"\b[A-Za-z0-9]+(?:[-/][A-Za-z0-9α-ωΑ-Ω]+)+\b"
        r"\b[A-Za-z][A-Za-z0-9]*(?:[-/][A-Za-z0-9α-ωΑ-Ω]+)+\b"
    ),

    # p53, BRCA1, AKT2, CD4+
    "gene": re.compile(
        r"\b(?:[A-Za-z]{1,6}\d+[A-Za-z+-]*|\d+[A-Za-z]{1,6})\b"
    ),

    # qPCR, mRNA, scRNA
    "camel": re.compile(
        r"\b[a-z]{1,3}[A-Z]{2,}[A-Za-z0-9-]*\b"
    ),

    # α-SMA, β-actin
    "greek": re.compile(
        r"\b(?:[A-Za-z]+-?[α-ωΑ-Ω]+|[α-ωΑ-Ω]+-?[A-Za-z0-9]+)\b"
    ),

    # H2O, CO2, NaCl
    "chemical": re.compile(
        r"\b(?:[A-Z][a-z]?\d*){2,}\b"
    ),
}


def extract_abbreviations(text: str) -> List[Dict]:
    matches = []

    for pattern_name, pattern in PATTERNS.items():
        for m in pattern.finditer(text):

            token = m.group()

            # remove obvious false positives
            if token.upper() in STOPWORDS:
                continue

            matches.append({
                "text": token,
                "start": m.start(),
                "end": m.end(),
                "type": pattern_name
            })

    # -----------------------------
    # Remove overlapping duplicates
    # Prefer the longer match
    # -----------------------------
    matches.sort(key=lambda x: (x["start"], -(x["end"] - x["start"])))

    result = []

    for match in matches:

        overlap = False

        for existing in result:

            if not (
                match["end"] <= existing["start"] or
                match["start"] >= existing["end"]
            ):
                overlap = True
                break

        if not overlap:
            result.append(match)

    return sorted(result, key=lambda x: x["start"])

def build_abbreviation_check_prompt():
    
    common_ab_list = ['AIDS','ANCOVA','ANOVA','AOR(s)','BMI','CI(s)','CONSORT','E-cigarette','E-liquid','ENDS','HHS','DSM-IV',
                  'DSM-5','GED','GIS','GPS','HbA1c','HIV','HMO','ICD-10','ICD-10-CM','IRB','IQR','IV','MCO','METs','N','n',
                  'NIH','OR(s)','Pap','PRISMA','RCT','ref','RR','SD','SE','SES','STROBE','TREND','TV','UN','WHO','ZIP','U.S.', 
                  'COVID-19', 'SARS-CoV-2']
    prompt = f"""
You are an expert journal copy editor for scientific documents.
Given the title of a scientific article, a list(comma separated) of abbreviations extracted from the title, for each abbreviation T do the following steps:
Step 1:
Determine whether T is a scientifically meaningful abbreviation. it is meaningful if:
    - it can expand to a well-known scientific concept or proper noun
    - the expansion is widely accepted in peer-reviewed literature
    - If yes, valid_abbreviation=true.
    - some abbreviations do not require expansion like rule/act names which are more widely known by the abbreviated form.
Note: Treat periods, spaces, and hyphens in abbreviations as optional.

Step 2:
Independently determine whether an equivalent exists in the supplied common_abbreviation list.

- A valid abbreviation may have no equivalent in the list.

common_abbreviation list(comma separated):
{common_ab_list}

## Output format
Return **one** machine-readable JSON array, **single-line, no extra spaces or line-breaks outside string literals**.
{{"term":Text, "valid_abbreviation": True/False, "expanded_form": Text/NA, "equivalent_in_common_list": Text/NA}}
"""
    return prompt


import re

LOWERCASE_WORDS = {
    "a", "an", "the",
    "and", "or", "nor", "but",
    "as", "at", "by", "for", "from",
    "in", "into", "of", "on", "onto",
    "per", "to", "up", "via", "with", "without"
}

def _capitalize_token(token: str, first: bool) -> str:
    # Preserve acronyms
    if len(token) > 1 and token.isupper():
        return token

    # Preserve mixed-case words (mRNA, eGFR, iPSC)
    if any(c.islower() for c in token) and any(c.isupper() for c in token):
        return token

    # Preserve Greek letters/symbols
    if re.fullmatch(r"[α-ωΑ-Ωβγδεζηθικλμνξοπρστυφχψωκ]+", token):
        return token

    # Lowercase stop words unless first word
    if not first and token.lower() in LOWERCASE_WORDS:
        return token.lower()

    # Capitalize first alphabetic character only
    return token[:1].upper() + token[1:].lower()


def capitalize_expansion(expansion: str) -> str:
    words = expansion.split()

    result = []
    for i, word in enumerate(words):
        # Handle hyphenated words individually
        if "-" in word:
            parts = word.split("-")
            word = "-".join(
                _capitalize_token(part, first=(i == 0 and j == 0))
                for j, part in enumerate(parts)
            )
        else:
            word = _capitalize_token(word, first=(i == 0))

        result.append(word)

    return " ".join(result)

def check_for_abbreviation(title, model, api_key):
    abb_result = extract_abbreviations(title)
    # print(result)
    all_abbr = set()
    for res in abb_result:
        all_abbr.add(res['text'])
    if len(all_abbr) > 0:
        print(f"Abbreviations found : {list(all_abbr)}")
        user_prompt = f"""Title: {t}\nAnalyse these abbreviations: {list(all_abbr)}"""
        payload = build_payload(build_abbreviation_check_prompt(), user_prompt, model) 
        # print(payload)
        headers = {"x-api-key": f"{api_key}","Content-Type": "application/json",}
        result = post_and_poll(
            submit_url="https://test-llm-wrapper.cactuslabs.io/chat/v1/submit",
            poll_url="https://test-llm-wrapper.cactuslabs.io/chat/v1/fetch",
            payload=payload,
            headers=headers,
            poll_interval=5,
            timeout=300,
        )
        # print(f"Rule: {rule}")
        # print(result['results'][0]['list_chat_resp'])
        # res = result['results'][0]['list_chat_resp']
        r = result['results'][0]['list_chat_resp'][0]
        res = parse_repaired_objects(r, AbbreviationEdit)
        # for r in res:
        #     print(r)
        #     print()
        # results_arr.append({"abbr":list(all_abbr), "extract_json":extract_json(res[0])})
        print(f"input tokens: {result['results'][0]['usage']['input_token_count']}\noutput tokens: {result['results'][0]['usage']['output_token_count']}")
        print(f"time taken: {result['processing_time_seconds']}")
        print()
        return res
    else:
        return []

def create_edit_map_abbreviation(result_list):
    all_results = []

    for e in result_list:
        temp = {}
        r = e.model_dump()
        if not r['valid_abbreviation']:
            continue
        else:
            if r['equivalent_in_common_list'] == 'NA':
                temp = {
                    "guideline_followed": False,
                    "guideline_id": "title_abbreviation_constraint",
                    "reason": "Uncommon Abbreviations not allowed in titles",
                    "affected_text": r["term"],
                    "suggested_replacement": capitalize_expansion(r["expanded_form"]),
                }
            else:
                if r['term'].strip() == r['equivalent_in_common_list'].strip():
                    continue
                temp = {
                    "guideline_followed": False,
                    "guideline_id": "title_abbreviation_constraint",
                    "reason": "kindly use this standard form",
                    "affected_text": r["term"],
                    "suggested_replacement": r["equivalent_in_common_list"],
                }
            all_results.append(temp)

    return all_results

from typing import List
from pydantic import BaseModel

class AbbreviationEdit(BaseModel):
    term: str
    valid_abbreviation: bool
    expanded_form: str
    equivalent_in_common_list: str


class TitleEditNotFollowed(BaseModel):
    guideline_followed: bool
    guideline_id: str
    reason: str
    affected_text:str
    suggested_replacement: str
    edit_score: float

class EditListNotFollowed(BaseModel):
    edits: List[TitleEditNotFollowed]

def get_title_prompt_not_followed_rules(rules, examples):
    title_prompt = f"""
You are an expert editorial copy editor.
Use your expertise to perform quality checks on the title of a scientific paper.
Given an article title identify the edits required so that it follows professional grammatical,syntactic and semantic style of writing.
Also you ensure that the given title string follows all the given guidelines.
Finally return all suggested edits in case any guideline is violated, a short one line(4-5 words) reason behind the violation and
confidence score of the accuracy of edit performed(0-1). Return a list of edits in case of multiple violations.

Use following guidelines to analyse the given title.
{rules}

Editing Rules:

- Preserve the meaning while adhering to the guidelines.
- Do not rewrite or edit unnecessarily, only edit if absolutely required.
- Enforce grammatical correctness.
- Understand each guideline_id and the explaination thoroughly before making any edits.
- Stick to the guidelines strictly.
- NEVER invent new guidelines or constraints, use only the ones provided.
- Keep the reasons as short as possible.
- Evaluate True/False for EACH given guideline_id regardless of the fact that it is being followed or not.
- There could be multiple edits in the title against single guideline.

Examples of edits:
{examples}

## Output format
Return **one** machine-readable JSON array, no extra spaces, markdown characters or line-breaks outside string literals**.
Structure of each edit should be like:
{{"guideline_followed": True/False, "guideline_id": "Text", "reason": "Text", "affected_text": "Text" , "suggested_replacement": "Text/NA", "edit_score": double}}

"""
    return title_prompt

def not_followed_guidelines_check_single(title, title_rules, examples, model, api_key):
    results_all = dict()
    # for filename,title in titles.items():
    print(title)
    user_prompt = f"""Analyse this title\n{title}"""
    # print(get_title_prompt(title_rules))
    payload = build_payload(get_title_prompt_not_followed_rules(title_rules, examples), user_prompt, model) #gpt-5.4 llama-3.3-70b
    # print(payload)
    headers = {"x-api-key": f"{api_key}","Content-Type": "application/json",}
    result = post_and_poll(
        submit_url="https://test-llm-wrapper.cactuslabs.io/chat/v1/submit",
        poll_url="https://test-llm-wrapper.cactuslabs.io/chat/v1/fetch",
        payload=payload,
        headers=headers,
        poll_interval=5,
        timeout=300,
    )
    # print(f"Rule: {rule}")
    # print(result['results'][0]['list_chat_resp'])
    r = result['results'][0]['list_chat_resp'][0]
    res = parse_repaired_objects(r, TitleEditNotFollowed)
    # print(res)
    
    print(f"input tokens: {result['results'][0]['usage']['input_token_count']}\noutput tokens: {result['results'][0]['usage']['output_token_count']}")
    print(f"time taken: {result['processing_time_seconds']}")
    print()
    return res
    

examples_new = """
{"title":"Association of Life-Course Social Mobility With Cardiovascular Disease and Modifiable Risk Factors: Evidence From the Longitudinal Aging Study in India"}

[{"guideline_followed": Flase, "guideline_id": "title_hyphenation_constraint", "reason": "Hyphenated word", "affected_text": "Life-Course", "suggested_replacement": "Life Course"},]

{"title":"Title:  Testing for Lipid Levels and Diabetes Among Autistic Youth who are and are not Prescribed Anti-Psychotics: A Cohort Study"}

[{"guideline_followed": False, "guideline_id": "title_content_constraint", "reason": "Unnecesary word", "affected_text": "Title:  ", "suggested_replacement": ""},
{"guideline_followed": False, "guideline_id": "title_hyphenation_constraint", "reason": "Hyphenated word", "affected_text": "Anti-Psychotics", "suggested_replacement": "Antipsychotics"},
{"guideline_followed": False, "guideline_id": "title_content_constraint", "reason": "Grammatical rephrase", "affected_text": "Autistic Youth", "suggested_replacement": "Youth With Autism"}]

{"title":"Alcohol Use Disorder and Depression Among Community-Based Clinic Patients Before and During the COVID-19 Public Health Emergency by Smoking Status"}

[{"guideline_followed": False, "guideline_id": "title_punctuation_constraint", "reason": "Comma missing", "affected_text": "Public Health Emergency by Smoking Status", "suggested_replacement": "Public Health Emergency, by Smoking Status"}]
"""

title_rules = {
    "title_content_constraint": (
        "Titles must use dense nouns for searchability."
    ),
    "title_verb_constraint": (
        "Titles should avoid too many verbs, verbs are okay to be used to address what has been done in the article."
    ),
    "title_form_constraint": (
        "The title should not be a sentence, statement, or question and should not begin with or contain generic descriptive openings such as 'The Relationship of'."
    ),
    "title_punctuation_constraint": (
        "Titles should be punctuated properly(if missing)."
    ),
    "title_hyphenation_constraint": (
        "Titles should avoid hyphenated words(use synonyms or non hyphenated version instead), hyphens are ok if no synonym exists for the phrase."
    ),
    "subtitle_placement_and_separator": (
        "An optional subtitle(if any) may appear directly after the main title with no line breaks and should be separated from the title by a colon."
    ),
}

def do_all_title_checks(title, model, api_key):
    title_results = []
    nfg = not_followed_guidelines_check_single(title, title_rules, examples_new, model, api_key)
    not_followed_edts = [temp.model_dump() for temp in nfg]
    title_results.extend(not_followed_edts)
    print(not_followed_edts)

    pe = prepositions_check_method_single(t)
    title_results.extend(pe)
    print(pe)

    ae = check_for_abbreviation(t,model,api_key)
    abe = create_edit_map_abbreviation(ae)
    title_results.extend(abe)
    print(abe)

    return title_results