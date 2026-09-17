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



def get_corresponding_address_prompt(corr_add_rules):
    corr_add_prompt = f"""
You are an expert editorial copy editor.
Use your editing expertise to do following task.
Given the Correspondence address block of a scientific article and the list of styling guidelines that the correspondence address block MUST follow, 
evaluate the block against each given guideline.
Finally return all suggested edits in case any guideline is violated, a short one line(4-5 words) reason behind the violation, part of the block where
the edit is required and confidence score of the accuracy of edit performed(0-1).

Use following guidelines to analyse the given correspondence address block.
{corr_add_rules}

Editing Rules:

- Do not rewrite or edit unnecessarily, only edit if absolutely required.
- Understand each guideline_id and the explaination thoroughly before making any edits.
- Stick to the guidelines strictly.
- NEVER invent new guidelines or constraints, use only the ones provided.
- Keep the reasons as short as possible.
- Evaluate True/False for EACH given guideline_id regardless of the fact that it is being followed or not.
- DO NOT miss out on ANY guideline.
- DO NOT include the whole block in affected_text field in the output, show only tokens affected by the guideline violation or adherence.
- Revisit the whole block explicitly before suggesting edits.


## Output format
Return **one** machine-readable JSON array, no extra spaces, markdown characters or line-breaks outside string literals**.
Structure of each edit should be like:
{{"guideline_followed": True/False, "guideline_id": "Text", "reason": "Text", "affected_text": "Text" , "suggested_replacement": "Text/NA", "edit_score": double}}

"""
    return corr_add_prompt


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



class CorrespondenceAddressEdit(BaseModel):
    guideline_followed: bool
    guideline_id: str
    reason: str
    affected_text:str
    suggested_replacement: str
    edit_score: float

class CorrespondenceAddressEditList(BaseModel):
    edits: List[CorrespondenceAddressEdit]

corr_addr_rules = {
    "start_constraint": (
        "Correspondence address block must start with 'Address correspondence to:'."
    ),
    "fullname_constraint": (
        "Correspondence address block MUST HAVE full name of the corresponding author."
    ),
    "degrees_constraint": (
        "Correspondence address block MUST HAVE degrees of the corresponding author."
    ),
    "full_address_constraint": (
        "Correspondence address block MUST HAVE address of the corresponding author."
    ),
    "email_constraint": (
        "Correspondence address block MUST HAVE e-mail address of the corresponding author."
    ),
    "abbreviation_constraint":(
        "Any abbreviated parts of the address must be spelled out in the Correspondence address block, eg, St.-> Street, Ave. -> Avenue ."
    ),
    "phone_constraint":(
        "Do NOT include phone numbers in the correspondence address."
    ),
    "fax_constraint":(
        "Do NOT include fax numbers in the correspondence address."
    ),
    "home_constraint":(
        "Do NOT include home address in the correspondence address."
    ),
    "title_constraint":(
        "Do NOT include titles in the correspondence address, like Dr., Mr. etc."
    ),
    "private_constraint":(
        "If the author is a private consultant, use the name of his/her consulting business; if no business name, use only the author’s name, private consultant, e-mail address."
    ),
    "state_designation_constraint":(
        "Use the USPS 2-letter designation for the state in the mailing address in the correspondence address block, like Denver CO, Sacramento CA."
    ),
    "hyperlink_constraint":(
        "Remove e-mail hyperlinks from any correspondence address of electronic manuscripts, email address format should be like E-mail: tdicey@dhs.ca.gov."
    ),
    "end_constraint":(
        "Add a period at the end of the correspondence address line, IF missing."
    ),
}

def check_corr_address(corr_addr, corr_addr_rules, model, api_key):
    if corr_addr == "":
        return []
    print(corr_addr)
    user_prompt = f"""Now analyse this Correspondence address block:\n{corr_addr}"""
    # print(get_title_prompt(title_rules))
    payload = build_payload(get_corresponding_address_prompt(corr_addr_rules), user_prompt, model) #gpt-5.4 llama-3.3-70b
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
    res = parse_repaired_objects(r, CorrespondenceAddressEdit)
    # print(res)
    
    print(f"input tokens: {result['results'][0]['usage']['input_token_count']}\noutput tokens: {result['results'][0]['usage']['output_token_count']}")
    print(f"time taken: {result['processing_time_seconds']}")
    print()
    return res