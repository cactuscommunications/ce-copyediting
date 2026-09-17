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



def get_acknowledgement_prompt(acknowledgement_rules):
    acknowledgement_prompt = f"""
You are an expert editorial copy editor.
Use your editing expertise to do following task.
Given the Acknowledgements block of a scientific article and the list of styling guidelines that the Acknowledgements block MUST follow, 
evaluate the block against each given guideline.
Finally return all suggested edits in case any guideline is violated, a short one line(4-5 words) reason behind the violation, part of the block where
the edit is required and confidence score of the accuracy of edit performed(0-1).

Use following guidelines to analyse the given Acknowledgements block.
{acknowledgement_rules}

Editing Rules:

- Do not rewrite or edit unnecessarily, only edit if absolutely required.
- Understand each guideline_id and the explaination thoroughly before making any edits.
- Stick to the guidelines strictly.
- NEVER invent new guidelines or constraints, use only the ones provided.
- NEVER mark acknowledgements sub-sections incorrectly, do not mark if unsure.
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
    return acknowledgement_prompt


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



class AcknowledgementEdit(BaseModel):
    guideline_followed: bool
    guideline_id: str
    reason: str
    affected_text:str
    suggested_replacement: str
    edit_score: float

class AcknowledgementEditList(BaseModel):
    edits: List[AcknowledgementEdit]


sections_list = ['Acknowledgments','Disclaimers:','Supported by:','Presented at:','Funding:','Declaration of interest:',]

acknowledgement_rules = {
    "start_constraint": (
        "Acknowledgments block MUST start with 'ACKNOWLEDGMENTS' and then the content should start from a newline."
    ),
    "sections_constraint": (
        f"Acknowledgments block should contain following sub-sections in general: {','.join(s for s in sections_list)}. Order the sections if not in order."
    ),
    "end_constraint": (
        "Acknowledgement block MUST end with 'Declaration of interest' as last section, if nothing to declare use None, like 'Declaration of interest: None.'."
    ),
}

def check_acknowledgement(acknowledgements, acknowledgement_rules, model, api_key):
    if acknowledgements == "":
        return []
    print(acknowledgements)
    user_prompt = f"""Now analyse this Acknowledgements block:\n{acknowledgements}"""
    # print(get_title_prompt(title_rules))
    payload = build_payload(get_acknowledgement_prompt(acknowledgement_rules), user_prompt, model) #gpt-5.4 llama-3.3-70b
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
    res = parse_repaired_objects(r, AcknowledgementEdit)
    # print(res)
    
    print(f"input tokens: {result['results'][0]['usage']['input_token_count']}\noutput tokens: {result['results'][0]['usage']['output_token_count']}")
    print(f"time taken: {result['processing_time_seconds']}")
    print()
    return res