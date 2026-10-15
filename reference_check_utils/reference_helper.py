import format_author_name
import errant
import doi_cache_helper_new
import re
from typing import Dict
import json
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter
import gliner_util
import html

DOI_RE = re.compile(
    r'\b(?:https?://doi\.org/|doi:\s*)?'
    r'(10\.\d{4,9}/[-._;()/:A-Z0-9]+)',
    re.IGNORECASE
)

# Typical journal citation:
# J Psychopharmacol. 2019;33(9):1039-1057.
# NUMBERS_RE = re.compile(
#     r'\b\d{4};\s*\d+(?:\([^)]*\))?:\s*[\w-]+(?:-[\w-]+)?\.?$'
# )
YEAR_RE = r"(?:18|19|20|21)\d{2}"

NUMBERS_RE = re.compile(
    rf"""
    (?P<numbers>
        (?P<journal>.+?)
        \.\s*

        (?P<year>{YEAR_RE})
        \s*;\s*

        (?P<volume>\d+[A-Za-z]?)

        # Support multiple parenthesized groups:
        # 29(3)(suppl 9)
        (?:\s*\([^)]*\))*

        # Optional pages or electronic article number
        (?:
            \s*:\s*
            (?P<location>
                [A-Za-z]{{0,10}}?\d+
                (?:\s*[-–—]\s*[A-Za-z]{{0,10}}?\d+)?
            )
        )?

        \.?
        \s*$
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

SEP_NUMBERS_RE = re.compile(
    r'^(?P<name>.*?)\s+(?P<numbers>\d{4};\s*\d+(?:\([^)]*\))?:\s*[\w-]+(?:-[\w-]+)?)\.?$'
)



def parse_numbers_part(numbers: str) -> str:
    """
    Parse the bibliographic numbers portion of a scientific reference.
    """

    result = {
        "year": "",
        "volume": "",
        "issue": "",
        "pages": "",
        "article_number": "",
    }

    print(f'--------NUMBERS FROM parse_numbers_part() {numbers}')

    if not numbers:
        return result

    text = numbers.strip()

    # ---------------------------------------------------------
    # Normalize whitespace
    # ---------------------------------------------------------

    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)

    # Normalize Unicode dash characters
    text = re.sub(r"[‐-‒–—−]", "-", text)

    # Remove trailing punctuation
    text = text.strip(" .;:")

    # ---------------------------------------------------------
    # YEAR
    # ---------------------------------------------------------

    year_match = re.search(
        rf"\b(?P<year>{YEAR_RE})\b",
        text,
        flags=re.IGNORECASE,
    )

    if not year_match:
        return result

    result["year"] = year_match.group("year")

    # Everything after year
    remainder = text[year_match.end():].strip()

    # Remove separator between year and volume
    remainder = remainder.lstrip(" ;,.")

    # ---------------------------------------------------------
    # VOLUME
    # ---------------------------------------------------------

    volume_match = re.match(
        r"(?P<volume>\d+[A-Za-z]*)",
        remainder,
        flags=re.IGNORECASE,
    )

    if not volume_match:
        return result

    result["volume"] = volume_match.group("volume")

    remainder = remainder[volume_match.end():].strip()

    # ---------------------------------------------------------
    # ISSUE / SUPPLEMENT
    #
    # Important:
    #
    # 29(3)(suppl 9):9-16
    #
    # contains TWO parenthesized components.
    #
    # Collect all consecutive (...) groups.
    # ---------------------------------------------------------

    issue_parts = []

    while remainder.startswith("("):

        # Find the matching closing parenthesis.
        #
        # This also handles nested parentheses reasonably safely.
        depth = 0
        closing_index = None

        for i, char in enumerate(remainder):
            if char == "(":
                depth += 1

            elif char == ")":
                depth -= 1

                if depth == 0:
                    closing_index = i
                    break

        if closing_index is None:
            break

        part = remainder[1:closing_index].strip()

        if part:
            issue_parts.append(part)

        remainder = remainder[closing_index + 1:].strip()

    # Combine issue components.
    #
    # (3)(suppl 9)
    # ->
    # "3 (suppl 9)"
    #
    if issue_parts:
        result["issue"] = " ".join(issue_parts)

    # ---------------------------------------------------------
    # PAGE / ARTICLE separator
    # ---------------------------------------------------------

    remainder = remainder.lstrip(" :;,.")

    if not remainder:
        return result

    location = remainder.strip(" .;,")

    # ---------------------------------------------------------
    # PAGE RANGE
    #
    # 9-16
    # 1039-1057
    # S10-S15
    # e123-e130
    # ---------------------------------------------------------

    page_range_match = re.fullmatch(
        r"""
        (?P<start>[A-Za-z]?\d+)
        \s*-\s*
        (?P<end>[A-Za-z]?\d+)
        """,
        location,
        flags=re.VERBOSE,
    )

    if page_range_match:
        result["pages"] = (
            f"{page_range_match.group('start')}-"
            f"{page_range_match.group('end')}"
        )
        return result

    # ---------------------------------------------------------
    # ARTICLE NUMBER
    #
    # e12345
    # m123
    # A123
    # ---------------------------------------------------------

    article_match = re.fullmatch(
        r"[A-Za-z]+\d+",
        location,
    )

    if article_match:
        result["article_number"] = location
        return result

    # ---------------------------------------------------------
    # SINGLE NUMERIC PAGE
    # ---------------------------------------------------------

    if re.fullmatch(r"\d+", location):
        result["pages"] = location
        return result

    # ---------------------------------------------------------
    # Unknown location.
    #
    # Preserve it rather than silently losing information.
    # ---------------------------------------------------------

    result["article_number"] = location

    bib_result = extract_numbers(result['numbers'])

    if bib_result['year'] and bib_result['volume'] and bib_result['issue'] and bib_result['pages']:
        if bib_result['issue'] == bib_result['pages']:
            return "Confirm issue and pages numbers in reference"
        formatted_numbers = f'{bib_result['year']};{bib_result['volume']}({bib_result['issue']}):{bib_result['pages']}'
        return formatted_numbers
    
    return "Confirm bibliographical numbers in reference"




def parse_reference_deter(ref: str) -> dict:
    result = {
        "author": "",
        "title": "",
        "numbers": "",
        "doi": "",
        "actual_ref": ref,
    }

    if not ref or not ref.strip():
        return result

    # ---------------------------------------------------------
    # 1. Normalize whitespace and dash characters
    # ---------------------------------------------------------
    text = re.sub(r"\s+", " ", ref).strip()
    text = re.sub(r"[‐‒–—−]", "-", text)

    # ---------------------------------------------------------
    # 2. Remove reference number
    # Supports: 1. Reference, [1] Reference, 1) Reference
    # ---------------------------------------------------------
    text = re.sub(
        r"^\s*(?:\[\d+\]|\(\d+\)|\d+[.)])\s*",
        "",
        text,
    )

    # ---------------------------------------------------------
    # 3. Extract DOI
    # ---------------------------------------------------------
    doi_match = DOI_RE.search(text)

    if doi_match:
        result["doi"] = doi_match.group(1).rstrip(".,;)]}")

        # Remove the DOI and any trailing text after it.
        text = text[:doi_match.start()].rstrip(" .,;")

    # ---------------------------------------------------------
    # 4. Extract journal/year/volume/issue/pages
    # ---------------------------------------------------------
    numbers_match = NUMBERS_RE.search(text)

    if numbers_match:
        result["numbers"] = numbers_match.group("numbers").strip()

        # Everything before the numbers part contains authors
        # and title.
        text = text[:numbers_match.start()].strip()

    # ---------------------------------------------------------
    # 5. Split author and title
    # ---------------------------------------------------------
    et_al_match = re.match(
        r"^(?P<author>.+?\bet al\.?)\s+(?P<title>.+)$",
        text,
        re.IGNORECASE,
    )

    if et_al_match:
        result["author"] = et_al_match.group("author").strip()
        result["title"] = et_al_match.group("title").strip()
        return result

    # ---------------------------------------------------------
    # 6. References without et al.
    # ---------------------------------------------------------
    author_match = re.match(
        r"^(?P<author>[^.]+?)\.\s+(?P<title>.+)$",
        text,
    )

    if author_match:
        result["author"] = author_match.group("author").strip()
        result["title"] = author_match.group("title").strip()
    else:
        result["title"] = text

    return result


# ref = '1.	Kuypers KP, Ng L, Erritzoe D, et al. Microdosing psychedelics: More questions than answers? An overview and suggestions for future research. J Psychopharmacol. 2019;33(9):1039-1057. doi:10.1177/0269881119857204'
# result = parse_reference_deter(ref)

# print(result)

import errant


def call_errant_with_pos(original_text, edited_text) -> list[dict]:
    annotator = errant.load("en")

    orig_parsed = annotator.parse(original_text)
    edited_parsed = annotator.parse(edited_text)

    edits = annotator.annotate(orig_parsed, edited_parsed)

    errant_edits_list = []

    def get_char_position(doc, start, end, text):
        """
        Convert token positions to character positions.

        Includes whitespace between tokens when it belongs to
        the changed span.
        """
        if start < end:
            char_start = doc[start].idx
            char_end = doc[end - 1].idx + len(doc[end - 1])
        else:
            # Insertion: position immediately before the next token,
            # or at the end of the text.
            char_start = (
                doc[start].idx
                if start < len(doc)
                else len(text)
            )
            char_end = char_start

        return char_start, char_end

    for e in edits:
        original_start, original_end = get_char_position(
            orig_parsed,
            e.o_start,
            e.o_end,
            original_text,
        )

        edited_start, edited_end = get_char_position(
            edited_parsed,
            e.c_start,
            e.c_end,
            edited_text,
        )

        # Include whitespace immediately surrounding the edit when
        # it differs between the original and edited strings.
        #
        # This is especially useful for changes involving tabs,
        # multiple spaces, and newlines.
        while (
            original_start > 0
            and edited_start > 0
            and original_text[original_start - 1].isspace()
            and edited_text[edited_start - 1].isspace()
        ):
            if (
                original_text[original_start - 1]
                != edited_text[edited_start - 1]
            ):
                break

            original_start -= 1
            edited_start -= 1

        original_changed = original_text[
            original_start:original_end
        ]
        edited_changed = edited_text[
            edited_start:edited_end
        ]

        errant_edits_list.append({
            "original_text": original_changed,
            "edited_text": edited_changed,
            "original_position": {
                "start": original_start,
                "end": original_end,
            },
            "edited_position": {
                "start": edited_start,
                "end": edited_end,
            },
            "edit_type": e.type,
        })

    if not errant_edits_list:
        return []

    return errant_edits_list

def call_errant(original_text, edited_text) -> str:
    annotator = errant.load("en")
    orig_parsed = annotator.parse(original_text)
    edited_parsed = annotator.parse(edited_text)
    edits = annotator.annotate(orig_parsed, edited_parsed)

    for e in edits:
        print(e)
    # Generate errant edits string
    errant_edits_list = [f'{e.o_str} to {e.c_str}' for i, e in enumerate(edits)]
    # for i, e in enumerate(edits):
    #     print(e)
    if not errant_edits_list:
        return "No edits found."
    return errant_edits_list

def normalize_journal_name(name):
    if not name:
        return ""

    return html.unescape(str(name)).strip().lower().replace('.','')

def fetch_journal_name_from_location_name_list(location_list, journal_dict):
    for location in location_list:
        if not location:
            continue

        location = normalize_journal_name(location.strip())
        
        # Try direct lookup
        journal_name = journal_dict.get(location)
        if journal_name:
            print("Found in dict")
            return journal_name
        
        # Try partial lookup as a fallback
        for journal_key, journal_name in journal_dict.items():
            if location in journal_key and abs(len(location)-len(journal_key))<3:
                print("Found in dict")
                return journal_name

    return None

import re

def sentence_case(text: str) -> str:
    return re.sub(
        r'(^|[.!?]\s+)([a-zA-Z])',
        lambda m: m.group(1) + m.group(2).upper(),
        text.lower()
    )

def extract_numbers(text:str) -> str:
    match = SEP_NUMBERS_RE.search(text)

    if match.group("numbers"):
        print(match.group("numbers"))
        return match.group("numbers")
    else:
        return "Bibliographical Numbers missing for Reference"


def get_ref_result_list(all_ref_objs, journal_dict, max_refs=None):

    cache = doi_cache_helper_new.OpenAlexCache("cache/new_openalex_cache.db")
    list_for_xl = []

    refs_to_process = (
        all_ref_objs[:max_refs]
        if max_refs is not None
        else all_ref_objs
    )

    def clean(value):
        """Convert an optional value into a stripped string."""
        if value is None:
            return ""

        if not isinstance(value, str):
            value = str(value)

        return value.strip()

    def normalize_doi(doi):
        """Remove a DOI URL prefix if one is present."""
        doi = clean(doi)

        for prefix in (
            "https://doi.org/",
            "http://doi.org/",
            "https://dx.doi.org/",
            "http://dx.doi.org/",
            "doi:"
        ):
            if doi.lower().startswith(prefix):
                return doi[len(prefix):].strip()

        return doi

    def get_openalex_metadata(doi):
        """Retrieve cached metadata without failing on cache misses."""
        if not doi:
            return {}

        try:
            result = cache.get(doi)
            # print(result)
            if not isinstance(result, dict):
                return {}

            metadata = result.get("metadata")
            source = result.get("source")
            if isinstance(metadata, dict) and isinstance(source, str):
                return {"metadata": metadata, "source": source}
            
            return {}

        except Exception as exc:
            print(f"Metadata lookup failed for DOI {doi}: {exc}")
            return {}

    def format_bibliographic_numbers(numbers):
        """Format parsed bibliographic numbers safely."""

        if not isinstance(numbers, dict):
            return None

        if "Confirm" in numbers:
            return None

        year = str(numbers.get("year") or "").strip()
        volume = str(numbers.get("volume") or "").strip()
        issue = str(numbers.get("issue") or "").strip()
        pages = str(numbers.get("pages") or "").strip()
        article_number = str(
            numbers.get("article_number") or ""
        ).strip()

        # Year and volume are required for the expected citation style.
        if not year or not volume:
            return None

        if len(year) > 4:
            match = re.search(r'\b(?:18|19|20|21)\d{2}\b', str(year))
            year = match.group() if match else None

        result = f"{year};{volume}"

        if issue:
            result += f"({issue})"

        # Prefer page ranges; use article number when pages are absent.
        page_or_article = pages or article_number

        if page_or_article:
            result += f":{page_or_article}"

        return result

    def get_author_names_from_source(metadata):
        # print(f"source: {metadata["source"]}")
        if 'openalex' in metadata["source"]:
            authorships = metadata.get("metadata").get("authorships") or []
            print(f'author length: {len(authorships)}')  
            author_names = [
                authorship["author"]["display_name"]
                for authorship in authorships
                if isinstance(authorship, dict)
                and isinstance(authorship.get("author"), dict)
                and authorship["author"].get("display_name")
            ]
            return author_names
        
        elif 'crossref' in metadata["source"]:
            
            authorships = metadata.get("metadata").get("author") or []
            print(f'author length: {len(authorships)}')                
            author_names = [
                f'{authorship["given"]} {authorship["family"]}'
                for authorship in authorships
                if isinstance(authorship, dict)
                and isinstance(authorship.get("given"), str)
                and isinstance(authorship.get("family"), str)
            ]
            return author_names
        else:
            return ""


    def get_title_from_source(metadata):
        # print(f"source: {metadata["source"]}")
        if 'openalex' in metadata["source"]:
            title = metadata.get("metadata").get("title") or ""
            return title
        
        elif 'crossref' in metadata["source"]:
            title = metadata.get("metadata").get("title")[0] or ""
            return title
        else:
            return ""


    def get_author_names(ref, metadata):
        """Get authors from OpenAlex first, then from the input object."""
        author_names = get_author_names_from_source(metadata)
        print(f'-------Author names: {author_names}')
        if not author_names:
            source_authors = (
                ref.get("authors")
                or ref.get("author_names")
                or []
            )

            if isinstance(source_authors, str):
                source_authors = [source_authors]

            author_names = [
                clean(author)
                for author in source_authors
                if clean(author)
            ]

        if not author_names:
            return ""

        try:
            return clean(
                format_author_name.format_authors(author_names)
            )
        except Exception:
            return ", ".join(author_names)

    def get_journal_names_from_source(metadata):
        if 'openalex' in metadata["source"]:
            locations = metadata.get("metadata").get("locations") or []

            journal_names = [
                clean(location.get("raw_source_name"))
                for location in locations
                if isinstance(location, dict)
                and clean(location.get("raw_source_name"))
            ]
            return journal_names
        
        elif 'crossref' in metadata["source"]:
            container_title = metadata.get("metadata").get("container-title") or []

            journal_names = [
                clean(title)
                for title in container_title
                if isinstance(title, str)
                and clean(title)
            ]
            return journal_names
        
        else:
            return []



    def get_journal_abbreviation(ref, metadata):
        """Resolve a journal abbreviation with sensible fallbacks."""
        # print(f"source: {metadata["source"]}")
        journal_names = get_journal_names_from_source(metadata)
        print(f'Raw Journal names from metadata: {journal_names}')
        if journal_names:
            try:
                result = fetch_journal_name_from_location_name_list(
                    journal_names,
                    journal_dict
                )

                if isinstance(result, dict) and result.get("med_abbr"):
                    return clean(result["med_abbr"])
            except Exception as exc:
                print(f"Journal lookup failed: {exc}")

        # Use an abbreviation already provided in the input.
        # for key in ("journal_abbr", "med_abbr"):
        #     value = clean(ref.get(key))

        #     if value:
        #         return value

        # If no abbreviation is available, retain the full journal name.
        # for key in ("journal_name", "journal", "name"):
        #     value = clean(ref.get(key))

        #     if value:
        #         return value

        # OpenAlex may contain a source name even when the global
        # journal abbreviation lookup fails.
        if journal_names:
            return journal_names[0]

        return ""

    try:
        print(f"Processing {len(refs_to_process)} references")

        for i, ref in enumerate(refs_to_process, start=1):

            if not isinstance(ref, dict):
                ref = {"actual_ref": str(ref)}

            actual_ref = clean(ref.get("actual_ref"))
            print(f"Cleaned ACTUAL REF in helper -> {actual_ref}")
            # doi = normalize_doi(ref.get("doi"))
            doi = normalize_doi(gliner_util.extract_dois(actual_ref))
            print(f"Extracted doi: {doi}")
            # Track metadata problems without skipping the reference.
            missing_components = []
            warnings = []

            # ------------------------------------------------------
            # 1. Retrieve metadata
            # ------------------------------------------------------
            metadata = get_openalex_metadata(doi)

            if not doi:
                missing_components.append("DOI")

                list_for_xl.append({
                    "original": actual_ref,
                    "edited": "",
                    "edits": {
                        "text_edits": [],
                        "missing_components": missing_components,
                        "warnings": warnings,
                    }
                })

                continue
            elif not metadata:
                warnings.append(
                    "OpenAlex metadata unavailable; input fields "
                    "were used where possible."
                )
                list_for_xl.append({
                    "original": actual_ref,
                    "edited": "",
                    "edits": {
                        "text_edits": [],
                        "missing_components": missing_components,
                        "warnings": warnings,
                    }
                })
                
                continue

            # ------------------------------------------------------
            # 2. Authors
            # ------------------------------------------------------
            formatted_names = get_author_names(ref, metadata)
            print(f'Formatted author names: {formatted_names}')

            if not formatted_names:
                missing_components.append("Authors")

            # ------------------------------------------------------
            # 3. Article title
            # ------------------------------------------------------
            # title = clean(metadata.get("title"))
            title = clean(get_title_from_source(metadata))
            print(f'Formatted title: {title}')

            if not title:
                title = clean(ref.get("title"))

            if not title:
                missing_components.append("Title")

            # ------------------------------------------------------
            # 4. Journal
            # ------------------------------------------------------
            journal_name = get_journal_abbreviation(ref, metadata)

            if not journal_name:
                missing_components.append("Journal name/abbreviation")

            # ------------------------------------------------------
            # 5. Bibliographic numbers
            # ------------------------------------------------------
            numbers = gliner_util.extract_page_info(actual_ref)
            print(f'----------NUMBERS: {numbers}')
            # Support separately supplied number fields.
            if not numbers and any(
                numbers.get(key)
                for key in ("year", "volume", "issue", "pages")
            ):
                numbers = {
                    key: numbers.get(key)
                    for key in (
                        "year",
                        "volume",
                        "issue",
                        "pages",
                        "article_number",
                    )
                }

            number_text = ""

            if numbers:
                try:
                    number_text = format_bibliographic_numbers(
                        numbers
                    )
                    # warnings.extend(number_warnings)
                except Exception as exc:
                    warnings.append(
                        f"Bibliographic number formatting failed: {exc}"
                    )
                print(f'---------NUMBERS TEXT: {number_text}')
            if not number_text:
                missing_components.append("Bibliographic numbers")

            # ------------------------------------------------------
            # 6. Construct the reference from available components
            # ------------------------------------------------------
            components = []

            if formatted_names:
                components.append(formatted_names)

            if title:
                components.append(f"{sentence_case(title)}.")

            if journal_name:
                components.append(f"{journal_name}.")

            if number_text:
                components.append(f"{number_text}.")

            if doi:
                components.append(f"https://doi.org/{doi}.")

            if components:
                final_ref = f"{i}. " + " ".join(components)

            elif actual_ref:
                # If no structured components can be recovered,
                # retain the original rather than return an error.
                final_ref = actual_ref

                warnings.append(
                    "No structured components could be recovered; "
                    "the original reference was retained."
                )

            else:
                # Preserve one output row even for an empty input.
                final_ref = f"{i}."

                warnings.append(
                    "The reference contains no usable source information."
                )

            # ------------------------------------------------------
            # 7. Compare the original and edited references
            # ------------------------------------------------------
            try:
                errant_edits = (
                    call_errant_with_pos(actual_ref, final_ref)
                    if actual_ref
                    else {}
                )
                # print(errant_edits)
            except Exception as exc:
                errant_edits = {}

                warnings.append(
                    f"Text edit comparison failed: {exc}"
                )

            # ------------------------------------------------------
            # 8. Record all edits and missing components
            # ------------------------------------------------------
            list_for_xl.append({
                "original": actual_ref,
                "edited": final_ref,
                "edits": {
                    "text_edits": errant_edits if 'DOI' not in missing_components else [],
                    "missing_components": missing_components,
                    "warnings": warnings,
                }
            })

            print(f"FINAL REF:\n{final_ref}\n")

    finally:
        cache.close()

    return list_for_xl
