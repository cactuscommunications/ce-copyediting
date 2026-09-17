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

def get_acknowledgement_prompt_optimized():
    acknowledgement_prompt = f"""
ROLE: You are an expert editorial copy editor for scientific articles.

TASK: Structure a provided Acknowledgements block into relevant subsections and output as a JSON array.

INPUT: Raw Acknowledgements text.

OUTPUT FORMAT: A JSON array of objects. Each object must be: {{"subsection": "String", "content": "String", "confidence": double (0-1)}}.

ALLOWED SUBSECTION NAMES & ORDER:
- "Acknowledgements"
- "Supported by"
- "Presented at"
- "Disclaimers"
- "Funding" (Content must start with "Funding:")
- "Declaration of Interest" (Content must start with "Declaration of Interest:")
- "Others"

RULES:
- Preserve all original text. Replace "We" with "The authors" where applicable.
- Assign ambiguous text to "Others" without duplication.
- Do not force subdivision. Not all subsections are mandatory.
- Merge duplicate subsections of the same type.
- For "Declaration of Interest": if no conflicts or not applicable, content is "Declaration of Interest: None.". Use author initials only if full name is present in original text.
"""
    return acknowledgement_prompt

def get_acknowledgement_prompt():
    acknowledgement_prompt = f"""
You are an expert editorial copy editor.
You are given the Acknowledgements block of a scientific article.
Use your editing expertise to structure the block into relevant sub-sections.
The original block could be structured into sub-sections already and do not require further division.
Go through the content throughly before aligning parts of the Acknowledgment block to sub-sections.
Finally return a json array containing the subsection name, subsection text and confidence score of identification of subsection.

Rules:
- Use only provided subsection names.
- Preserve original text; do not rewrite or omit.
- Do not force unnecessary subdivision.
- It is not mandatory for a block to have all subsections.
- Assign ambiguous text to 'others' subsection without duplication.
- Aim to replace 'We' as 'The authors' wherever applicable.
- The Acknowledgment section should be structured, in the following order:
    - General acknowledgements (no separate heading; for example, Thanks to the reviewers . . .)
    - Optional elements (eg, Supported by, Presented at, Disclaimers)
    - Funding (with “Funding:” stem)
    - Declaration of Interest (with “Declaration of Interest:” stem).
        - If no conflicts of interest to disclose or declare by any author use 'Declaration of interest: None.'
        - If declaration of interest are not applicable use 'Declaration of interest: None.'
- Use only Author initials in Declaration of Interest sub-section if full author name is present.
- If multiple/duplicate sub-sections of the same type are found, merge the content to keep a single sub-section.
- Return only valid JSON with scores from 0-1.

## Output format
Return **one** machine-readable JSON array, no extra spaces, markdown characters or line-breaks outside string literals**.
Structure of each sub-section should be like:
{{"subsection": "Text", "content": "Text", "confidence": double}}
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



class AcknowledgementSection(BaseModel):
    subsection: str
    content: str
    confidence: float

class AcknowledgementSectionList(BaseModel):
    edits: List[AcknowledgementSection]


sections_list = ['Acknowledgments', 'Disclaimers:','Supported by:','Presented at:','Funding:','Declaration of interest:','Others',]

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

def check_acknowledgement_sections(acknowledgements, sections, model, api_key):
    if acknowledgements == "":
        return []
    print(acknowledgements)
    user_prompt = f"""Structure this Acknowledgements block:\n{acknowledgements} \ninto following sub-sections:\n{','.join(s for s in sections_list)}"""
    # print(get_title_prompt(title_rules))
    # payload = build_payload(get_acknowledgement_prompt(), user_prompt, model) #gpt-5.4 llama-3.3-70b
    payload = build_payload(get_acknowledgement_prompt_optimized(), user_prompt, model)
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
    res = parse_repaired_objects(r, AcknowledgementSection)
    # print(res)
    
    print(f"input tokens: {result['results'][0]['usage']['input_token_count']}\noutput tokens: {result['results'][0]['usage']['output_token_count']}")
    print(f"time taken: {result['processing_time_seconds']}")
    print()
    return res