import re
from typing import Dict


YEAR_RE = r"(?:18|19|20|21)\d{2}"


def parse_numbers_part(numbers: str) -> Dict[str, str]:
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

    return result
