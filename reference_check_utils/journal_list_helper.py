import re
import requests
from pathlib import Path
import html


def normalize_journal_name(name):
    if not name:
        return ""

    return html.unescape(str(name)).strip().lower().replace('.','')


MEDLINE_URL = "https://ftp.ncbi.nih.gov/pubmed/J_Medline.txt"


def download_medline_journals(
    output_file: str = "J_Medline.txt",
) -> Path:
    """
    Download the NLM MEDLINE journal list only if the file does not exist.
    """
    output_path = Path(output_file)

    if output_path.exists():
        return output_path

    response = requests.get(
        MEDLINE_URL,
        timeout=120,
    )
    response.raise_for_status()

    output_path.write_text(
        response.text,
        encoding="utf-8",
    )

    return output_path


def parse_medline_journals(file_path: str | Path) -> list[dict]:
    """
    Parse J_Medline.txt into a list of journal dictionaries.
    """

    file_path = Path(file_path)

    text = file_path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    # Records are separated by a line of dashes.
    records = re.split(
        r"\n-{20,}\n",
        text,
    )

    journals = []

    for record in records:
        record = record.strip()

        if not record:
            continue

        journal = {}

        for line in record.splitlines():
            line = line.strip()

            if not line or ":" not in line:
                continue

            key, value = line.split(":", 1)

            key = key.strip()
            value = value.strip()
            value = re.sub(r"\s*\([^)]*\)", "", value).strip()
            # value = value.split(":")[0].strip()

            if value:
                journal[key] = value

        if journal:
            journals.append(journal)

    return journals

def create_journal_dict(journals: list[dict]) -> dict:
    """
    Create a dictionary keyed by journal title.

    Example:
    {
        "Annals of internal medicine.": {
            "jrid": "596",
            "med_abbr": "Ann Intern Med",
            "issn_print": "0003-4819",
            "issn_online": "1539-3704",
            "iso_abbr": "Ann. Intern. Med.",
            "nlm_id": "0372351"
        }
    }
    """

    journal_dict = {}

    for journal in journals:

        title = normalize_journal_name(journal.get("JournalTitle"))

        if not title:
            continue

        journal_dict[title] = {
            "jrid": journal.get("JrId", ""),
            "med_abbr": journal.get("MedAbbr", ""),
            "issn_print": journal.get("ISSN (Print)", ""),
            "issn_online": journal.get("ISSN (Online)", ""),
            "iso_abbr": journal.get("IsoAbbr", ""),
            "nlm_id": journal.get("NlmId", ""),
        }

    return journal_dict

# path = download_medline_journals()

# journals = parse_medline_journals(path)

# journal_dict = create_journal_dict(journals)

# print(len(journal_dict))
# print(journal_dict.get("American Journal of Preventive Medicine".lower())['med_abbr'])