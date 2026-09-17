import json
import requests
import time
from json_repair import repair_json
from pydantic import BaseModel
from typing import Type, TypeVar, List
from pydantic import BaseModel

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



class AuthorEdit(BaseModel):
    guideline_followed: bool
    guideline_id: str
    reason: str
    affected_text:str
    suggested_replacement: str

class AuthorEditList(BaseModel):
    edits: List[AuthorEdit]


def followed_guidelines_check_single(authors_string, author_rules, model, api_key):
    results_all = dict()
    # for filename,title in titles.items():
    print(authors_string)
    user_prompt = f"""Now analyse this author names' string:\n{authors_string}"""
    # print(get_title_prompt(title_rules))
    payload = build_payload(get_author_prompt(author_rules), user_prompt, model) #gpt-5.4 llama-3.3-70b
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
    res = parse_repaired_objects(r, AuthorEdit)
    # print(res)
    
    print(f"input tokens: {result['results'][0]['usage']['input_token_count']}\noutput tokens: {result['results'][0]['usage']['output_token_count']}")
    print(f"time taken: {result['processing_time_seconds']}")
    print()
    return res

def get_author_prompt(author_rules):
    prompt = f"""
    You are an expert journal copy editor for scientific documents.
Use your expertise to perform quality and formatting checks on a given string of author names of a scientific article.
Step 1:
Use following guidelines and analyse the given author names' string against each guideline.
{author_rules}

Step 2:
Finally return your all suggested edits in case any guideline is violated and a short one line(4-5 words) reason behind each edit performed.
Incase there are multiple violations of the same type, use a list.

Editing rules:

- Do not rewrite or edit unnecessarily, only edit if absolutely required.
- Understand each guideline thoroughly before making any edits.
- Stick to the guidelines strictly.
- Keep the reasons as short as possible.
- Apply each rule/guideline on the author string provided.
- DO NOT change the order of authors incase of multiple authors.
- DO NOT interpret name initials as degrees.
- Evaluate True/False for EACH given guideline_id regardless of the fact that it is being followed or not.
- There could be multiple edits in the author string against single guideline.
- Ensure proper structure of json output.

## Output format
Return **one** machine-readable JSON array, **single-line, no extra spaces or line-breaks outside string literals**.
{{guideline_id: text ,guideline_followed: True/False, reason: text, affected_text: text , suggested_replacement: text}}
"""
    return prompt


author_rules = {
    "fullname_constraint": (
        "For each author include first name, applicable middle initial(s), and surname; query if a middle initial appears to be missing in ANY author name."
    ),
    "academic_degree": (
        "Include the highest academic degree for each author, omit fellowship degrees beginning with 'F', and write degrees without periods."
    ),
    "affiliation_sequence": (
        "Affiliation superscript numbers should begin at 1 and appear sequentially in author order."
    ),
    "author_sequence": (
        "Authors decide order of names, only authors can change that order."
    ),
    "working_group":(
        "Do not use 'and' between author names; 'and' may be used only before a collaboration or working-group name."
    )
}

def get_reflect_author_prompt():
    prompt = f"""
    You are an expert journal copy editor for scientific documents.
You will be given a list of formatting and quality edits done in a author-byline of a scientific article according to set of guidelines
Use your expertise to analyse and provide feedback against each edit in the list.
Categorize 'edit_valid' as True or False depending on the guideline_rule, guideline_followed, affected_text, suggested_replacement and the reason for the edit
In case of invalid edits, provide a 'feedback' field as well which should represent how to make that edit valid according to the guideline_rule of the edit.


Validation rules:

- Evaluate EACH edit in the json list independently.
- Determine whether the edit made(affected_text->suggested_replacement) represents the guideline_rule appropriately or not.
- Reject edits that are unnecessary, incorrect, unsupported by the guideline_rule, or change valid text.
- Do not suggest additional edits unless they are explicitly required by a guideline.
- If multiple edits violate the same guideline, return all of them as a list.
- A guideline may be marked as followed even when no edit was required.
- For every suggested edit, verify:
   - affected_text exists in the original string.
   - suggested_replacement is appropriate.
   - the edit is required by the cited guideline.
   - the edit does not introduce a new violation.
- Do not accept an edit merely because it improves style; it must be required by a guideline.
- Ensure proper structure of json output.

## Input format (single-edit)
{{guideline_rule: text, guideline_followed: True/False, reason: text, affected_text: text , suggested_replacement: text}}

## Output format
Return **one** machine-readable JSON array, **single-line, no extra spaces, code fences or line-breaks outside string literals**.
{{guideline_rule: text, guideline_followed: True/False, "edit_valid": True/False, reason: text, affected_text: text , suggested_replacement: text}}
"""
    return prompt

def do_all_authors_checks(authors, model, api_key):
    fg = followed_guidelines_check_single(authors, author_rules, model, api_key)
    followed_edts = [temp.model_dump() for temp in fg]
    return followed_edts