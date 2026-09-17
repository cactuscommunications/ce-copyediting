import json
import requests
import re
import time

from typing import List
from pydantic import BaseModel

from json_repair import repair_json
from typing import Type, TypeVar


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
    # print(response)
    for obj in extract_json_objects(response):
        repaired = repair_json(obj)
        parsed = json.loads(repaired)
        result.append(model.model_validate(parsed))

    return result



def get_credit_statement_prompt(credit_statement_rules):
    credit_statement_prompt = f"""
You are an expert editorial copy editor.
Use your editing expertise to do following task.
Given the CRediT Author Statement block, authors-byline of a scientific article and the list of styling guidelines that the CRediT Author Statement block MUST follow, 
evaluate the block against each given guideline.
Finally return all suggested edits in case any guideline is violated, a short one line(4-5 words) reason behind the violation, part of the block where
the edit is required and confidence score of the accuracy of edit performed(0-1).

Use following guidelines to analyse the given correspondence address block.
{credit_statement_rules}

Editing Rules:

- Do not rewrite or edit unnecessarily, only edit if absolutely required.
- Understand each guideline_id and the explaination thoroughly before making any edits.
- Stick to the guidelines strictly.
- NEVER invent new guidelines or constraints, use only the ones provided.
- Keep the reasons as short as possible.
- Evaluate True/False for EACH given guideline_id regardless of the fact that it is being followed or not.
- DO NOT misinterpret initials as degrees.
- DO NOT miss out on ANY guideline.
- DO NOT include the whole block in affected_text field in the output, show only tokens affected by the guideline violation or adherence.
- Revisit the whole block explicitly before suggesting edits.


## Output format
Return **one** machine-readable JSON array, no extra spaces, markdown characters or line-breaks outside string literals**.
Structure of each edit should be like:
{{"guideline_followed": True/False, "guideline_id": "Text", "reason": "Text", "affected_text": "Text" , "suggested_replacement": "Text/NA", "edit_score": double}}

"""
    return credit_statement_prompt


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



class CreditStatementEdit(BaseModel):
    guideline_followed: bool
    guideline_id: str
    reason: str
    affected_text:str
    suggested_replacement: str
    edit_score: float

class CreditStatementEditList(BaseModel):
    edits: List[CreditStatementEdit]


category_list = ['Conceptualization','Data curation','Formal analysis','Funding acquisition','Investigation','Methodology','Project administration',
                 'Resources','Software','Supervision','Validation','Visualization','Writing - original draft','Writing - review & editing']

credit_statement_rules = {
    "start_constraint": (
        "CRediT Author Statement block MUST start with 'CRediT Author Statement' and then the content should start from a newline."
    ),
    "authors_constraint": (
        "CRediT Author Statement block MUST HAVE names of all authors mentioned in author-byline."
    ),
    "fullname_constraint": (
        "CRediT Author Statement block MUST HAVE fullnames, query if initials are used."
    ),
    "role_constraint": (
        f"All roles in the CRediT Author Statement block MUST be among below roles:\n{category_list}, modify unknown roles to match provided roles list."
    ),
    "format_constraint": (
        "All statements in the CRediT Author Statement block MUST be separated by ';' and incase a single author has multiple roles the roles should be separated by ','."
    ),
}

def check_credit_statement(author_byline, credit_statement, credit_statement_rules, model, api_key):
    if credit_statement == "":
        return []
    print(f"author-byline: \n{author_byline}")
    print(f"credit statement: \n{credit_statement}")
    user_prompt = f"""Author-byline:{author_byline}\nCRediT Author Statement block:\n{credit_statement}"""
    # print(get_title_prompt(title_rules))
    payload = build_payload(get_credit_statement_prompt(credit_statement_rules), user_prompt, model) #gpt-5.4 llama-3.3-70b
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
    res = parse_repaired_objects(r, CreditStatementEdit)
    # print(res)
    
    print(f"input tokens: {result['results'][0]['usage']['input_token_count']}\noutput tokens: {result['results'][0]['usage']['output_token_count']}")
    print(f"time taken: {result['processing_time_seconds']}")
    print()
    return res