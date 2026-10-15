# from gliner import GLiNER
import re


# model = GLiNER.from_pretrained(
#     "gliner-community/gliner_medium-v2.5"
# )

DOI_RE = re.compile(
    r'\b(?:https?://doi\.org/|doi:\s*)?'
    r'(10\.\d{4,9}/[-._;()/:A-Z0-9]+)',
    re.IGNORECASE
)
def extract_dois(text: str) -> str:
    dois = []

    for match in DOI_RE.finditer(text):
        doi = match.group(0)

        # Remove trailing punctuation from the citation.
        doi = doi.rstrip(".,;:")

        dois.append(doi)

    if len(dois) >= 1:
        return dois[0]
    else:
        return None




BIBLIOGRAPHICAL_NUMBERS_RE = re.compile(
    r"""
    (?<!\d)

    # Year: optional, e.g., 2019, 19, or absent
    (?P<year>
        (?:
            (?:18|19|20|21)\d{2}       # Full year: 2022
            (?:\s+[A-Za-z]{3,9})?      # Optional month: Dec
            (?:\s+\d{1,2})?            # Optional day: 20
          |
            \d{1,2}                    # Day: 20
            (?:\s+[A-Za-z]{3,9})       # Month: Mar
          |
            [A-Za-z]{3,9}              # Month only: Mar
        )
    )?

    # Optional separator between year and volume
    \s* ; \s*

    # Volume, optionally followed by a supplement designation
    (?P<volume>
        \d+
        (?:\s+(?:Suppl|Supplement|Spec|Special)\s*\w+)?
    )?

    # Issue: optional, e.g., (9), (suppl 9), or (S1)
    (?: \s* \( \s*
        (?P<issue>[^()]+?)
    \s* \) )?

    # Optional separator before pages
    \s* : \s*

    # Pages: optional, e.g., 1039-1057, e1039, or S10-S15
    (?P<pages>
        [A-Za-z]?\d+
        (?: \s* [-‐-‒–—] \s* [A-Za-z]?\d+ )?
    )?

    (?!\w)
    """,
    re.VERBOSE | re.IGNORECASE,
)

def extract_page_info(text: str) -> dict:
    result = {
        "year": None,
        "volume": None,
        "issue": None,
        "pages": None,
    }

    match = BIBLIOGRAPHICAL_NUMBERS_RE.search(text)

    if match:
        result.update(match.groupdict())

        # Normalize whitespace in the extracted fields.
        for key, value in result.items():
            if isinstance(value, str):
                result[key] = value.strip()

    return result