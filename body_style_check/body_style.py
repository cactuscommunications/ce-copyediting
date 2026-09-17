import re
from typing import Any, Dict, List, Optional
from section_extractor.api import extract_range


EXPECTED_HEADER_FONT = "Franklin Gothic Medium"


# ============================================================
# Expected hierarchy
# ============================================================

EXPECTED_HIERARCHY = {
    "INTRODUCTION": {
        "level": 1,
        "parent": None,
    },
    "METHODS": {
        "level": 1,
        "parent": None,
    },
    "STUDY SAMPLE": {
        "level": 2,
        "parent": "METHODS",
    },
    "STUDY POPULATION": {
        "level": 2,
        "parent": "METHODS",
    },
    "MEASURES": {
        "level": 2,
        "parent": "METHODS",
    },
    "STATISTICAL ANALYSIS": {
        "level": 2,
        "parent": "METHODS",
    },
    "RESULTS": {
        "level": 1,
        "parent": None,
    },
    "DISCUSSION": {
        "level": 1,
        "parent": None,
    },
    "LIMITATIONS": {
        "level": 2,
        "parent": "DISCUSSION",
    },
    "CONCLUSIONS": {
        "level": 1,
        "parent": None,
    },
}


# ============================================================
# Generic helpers
# ============================================================

def normalize_name(value: Optional[str]) -> str:
    if not value:
        return ""

    return re.sub(r"\s+", " ", value.strip()).upper()


def normalize_font_name(value: Optional[str]) -> str:
    if not value:
        return ""

    return re.sub(r"\s+", " ", value.strip()).lower()


def is_all_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]

    if not letters:
        return False

    return all(c.isupper() for c in letters)


def is_headline_case(text: str) -> bool:
    """
    Basic headline/initial capitalization.

    Examples:
        Study Sample
        Statistical Analysis
        Patient Characteristics
    """

    words = re.findall(r"[A-Za-z]+", text)

    if not words:
        return False

    for word in words:
        if not word[0].isupper():
            return False

    return True


def is_sentence_case(text: str) -> bool:
    """
    Basic sentence-case validation.

    Examples:
        Wellness program.
        Statistical analysis was performed.
    """

    text = text.strip()

    if not text:
        return False

    words = re.findall(r"[A-Za-z]+", text)

    if not words:
        return False

    if not words[0][0].isupper():
        return False

    for word in words[1:]:
        if word[0].isupper() and word.isalpha():
            return False

    return True


# ============================================================
# Style extraction helpers
# ============================================================

def get_text_runs(
    style_info: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    return [
        item
        for item in style_info
        if not item.get("paragraph_break", False)
        and item.get("text", "") != "\n"
        and item.get("style") is not None
    ]


def get_first_style(
    style_info: List[Dict[str, Any]]
) -> Dict[str, Any]:
    runs = get_text_runs(style_info)

    if not runs:
        return {}

    return runs[0].get("style") or {}


def get_body_style(
    style_info: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Finds the first styled text after the heading paragraph break.
    """

    found_break = False

    for item in style_info:

        if item.get("paragraph_break"):
            found_break = True
            continue

        if found_break and item.get("style"):
            return item["style"]

    return None


# ============================================================
# Heading style validation
# ============================================================

# def validate_heading_style(
#     section: Dict[str, Any],
#     style_info: List[Dict[str, Any]],
# ) -> Dict[str, Any]:

#     level = section.get("level")
#     name = section.get("name", "").strip()

#     runs = get_text_runs(style_info)

#     style_followed = []
#     style_issues = []
#     text_issues = []

#     if not runs:
#         return {
#             "valid": False,
#             "style_followed": [],
#             "style_issues": ["No styled text found"],
#             "text_issues": ["No heading text found"],
#             "actual_style": {},
#             "heading_text": name,
#         }

#     first_style = runs[0].get("style") or {}

#     # --------------------------------------------------------
#     # Heading text
#     # --------------------------------------------------------

#     heading_text = name

#     extracted_text = section.get("extracted_text", "")

#     if extracted_text:
#         first_line = extracted_text.splitlines()[0].strip()

#         if first_line:
#             heading_text = first_line

#     # --------------------------------------------------------
#     # Level 1
#     # --------------------------------------------------------

#     if level == 1:

#         if is_all_caps(heading_text):
#             style_followed.append("all_caps")
#         else:
#             text_issues.append(
#                 "Level 1 heading must be all caps"
#             )

#         if (
#             normalize_font_name(first_style.get("font_name"))
#             == normalize_font_name(EXPECTED_HEADER_FONT)
#         ):
#             style_followed.append("font_name")
#         else:
#             style_issues.append(
#                 f"Font must be '{EXPECTED_HEADER_FONT}'"
#             )

#         if first_style.get("font_size") == 14:
#             style_followed.append("font_size")
#         else:
#             style_issues.append(
#                 "Font size must be 14 pt"
#             )

#         if first_style.get("bold") is True:
#             style_followed.append("bold")
#         else:
#             style_issues.append(
#                 "Heading must be bold"
#             )

#         if first_style.get("italic") is not True:
#             style_followed.append("not_italic")
#         else:
#             style_issues.append(
#                 "Level 1 heading must not be italic"
#             )

#     # --------------------------------------------------------
#     # Level 2
#     # --------------------------------------------------------

#     elif level == 2:

#         if is_headline_case(heading_text):
#             style_followed.append("headline_case")
#         else:
#             text_issues.append(
#                 "Level 2 heading must use initial/headline capitalization"
#             )

#         if (
#             normalize_font_name(first_style.get("font_name"))
#             == normalize_font_name(EXPECTED_HEADER_FONT)
#         ):
#             style_followed.append("font_name")
#         else:
#             style_issues.append(
#                 f"Font must be '{EXPECTED_HEADER_FONT}'"
#             )

#         if first_style.get("font_size") == 11:
#             style_followed.append("font_size")
#         else:
#             style_issues.append(
#                 "Font size must be 11 pt"
#             )

#         if first_style.get("bold") is True:
#             style_followed.append("bold")
#         else:
#             style_issues.append(
#                 "Heading must be bold"
#             )

#         if first_style.get("italic") is not True:
#             style_followed.append("not_italic")
#         else:
#             style_issues.append(
#                 "Level 2 heading must not be italic"
#             )

#     # --------------------------------------------------------
#     # Level 3
#     # --------------------------------------------------------

#     elif level == 3:

#         if is_sentence_case(heading_text):
#             style_followed.append("sentence_case")
#         else:
#             text_issues.append(
#                 "Level 3 heading must use sentence case"
#             )

#         if heading_text.endswith("."):
#             style_followed.append("final_period")
#         else:
#             text_issues.append(
#                 "Level 3 heading must end with a period"
#             )

#         if first_style.get("bold") is True:
#             style_followed.append("bold")
#         else:
#             style_issues.append(
#                 "Heading must be bold"
#             )

#         if first_style.get("italic") is not True:
#             style_followed.append("not_italic")
#         else:
#             style_issues.append(
#                 "Level 3 heading must not be italic"
#             )

#         body_style = get_body_style(style_info)

#         if body_style:

#             if (
#                 normalize_font_name(first_style.get("font_name"))
#                 == normalize_font_name(body_style.get("font_name"))
#             ):
#                 style_followed.append("same_font_as_body")
#             else:
#                 style_issues.append(
#                     "Heading font must match body text font"
#                 )

#             if (
#                 first_style.get("font_size")
#                 == body_style.get("font_size")
#             ):
#                 style_followed.append("same_size_as_body")
#             else:
#                 style_issues.append(
#                     "Heading font size must match body text size"
#                 )

#     # --------------------------------------------------------
#     # Level 4
#     # --------------------------------------------------------

#     elif level == 4:

#         if is_sentence_case(heading_text):
#             style_followed.append("sentence_case")
#         else:
#             text_issues.append(
#                 "Level 4 heading must use sentence case"
#             )

#         if heading_text.endswith("."):
#             style_followed.append("final_period")
#         else:
#             text_issues.append(
#                 "Level 4 heading must end with a period"
#             )

#         if first_style.get("bold") is True:
#             style_followed.append("bold")
#         else:
#             style_issues.append(
#                 "Heading must be bold"
#             )

#         if first_style.get("italic") is True:
#             style_followed.append("italic")
#         else:
#             style_issues.append(
#                 "Level 4 heading must be italic"
#             )

#         body_style = get_body_style(style_info)

#         if body_style:

#             if (
#                 normalize_font_name(first_style.get("font_name"))
#                 == normalize_font_name(body_style.get("font_name"))
#             ):
#                 style_followed.append("same_font_as_body")
#             else:
#                 style_issues.append(
#                     "Heading font must match body text font"
#                 )

#             if (
#                 first_style.get("font_size")
#                 == body_style.get("font_size")
#             ):
#                 style_followed.append("same_size_as_body")
#             else:
#                 style_issues.append(
#                     "Heading font size must match body text size"
#                 )

#     else:
#         style_issues.append(
#             f"Unsupported heading level: {level}"
#         )

#     return {
#         "valid": (
#             len(style_issues) == 0
#             and len(text_issues) == 0
#         ),
#         "style_followed": style_followed,
#         "style_issues": style_issues,
#         "text_issues": text_issues,
#         "actual_style": first_style,
#         "heading_text": heading_text,
#     }

def validate_heading_style(
    section: Dict[str, Any],
    style_info: List[Dict[str, Any]],
) -> Dict[str, Any]:

    level = section.get("level")
    name = section.get("name", "").strip()

    runs = get_text_runs(style_info)

    style_followed = []
    style_issues = []
    text_issues = []

    if not runs:
        return {
            "valid": False,
            "style_followed": [],
            "style_issues": ["no_styled_text"],
            "text_issues": ["no_heading_text"],
            "actual_style": {},
            "heading_text": name,
        }

    first_style = runs[0].get("style") or {}

    # --------------------------------------------------------
    # Heading text
    # --------------------------------------------------------

    heading_text = name

    extracted_text = section.get("extracted_text", "")

    if extracted_text:
        first_line = extracted_text.splitlines()[0].strip()

        if first_line:
            heading_text = first_line

    # --------------------------------------------------------
    # Level 1
    # --------------------------------------------------------

    if level == 1:

        # H1-01
        if is_all_caps(heading_text):
            style_followed.append("h1_all_caps")
        else:
            text_issues.append("h1_all_caps")

        # H1-02
        if (
            normalize_font_name(first_style.get("font_name"))
            == normalize_font_name(EXPECTED_HEADER_FONT)
        ):
            style_followed.append("h1_font_name")
        else:
            style_issues.append("h1_font_name")

        # H1-03
        if first_style.get("font_size") == 14:
            style_followed.append("h1_font_size")
        else:
            style_issues.append("h1_font_size")

        # H1-04
        if first_style.get("bold") is True:
            style_followed.append("h1_bold")
        else:
            style_issues.append("h1_bold")

        # H1-05
        if first_style.get("italic") is not True:
            style_followed.append("h1_not_italic")
        else:
            style_issues.append("h1_not_italic")

    # --------------------------------------------------------
    # Level 2
    # --------------------------------------------------------

    elif level == 2:

        # H2-01
        if is_headline_case(heading_text):
            style_followed.append("h2_headline_case")
        else:
            text_issues.append("h2_headline_case")

        # H2-02
        if (
            normalize_font_name(first_style.get("font_name"))
            == normalize_font_name(EXPECTED_HEADER_FONT)
        ):
            style_followed.append("h2_font_name")
        else:
            style_issues.append("h2_font_name")

        # H2-03
        if first_style.get("font_size") == 11:
            style_followed.append("h2_font_size")
        else:
            style_issues.append("h2_font_size")

        # H2-04
        if first_style.get("bold") is True:
            style_followed.append("h2_bold")
        else:
            style_issues.append("h2_bold")

        # H2-05
        if first_style.get("italic") is not True:
            style_followed.append("h2_not_italic")
        else:
            style_issues.append("h2_not_italic")

    # --------------------------------------------------------
    # Level 3
    # --------------------------------------------------------

    elif level == 3:

        # H3-01
        if is_sentence_case(heading_text):
            style_followed.append("h3_sentence_case")
        else:
            text_issues.append("h3_sentence_case")

        # H3-02
        if heading_text.endswith("."):
            style_followed.append("h3_final_period")
        else:
            text_issues.append("h3_final_period")

        # H3-05
        if first_style.get("bold") is True:
            style_followed.append("h3_bold")
        else:
            style_issues.append("h3_bold")

        # H3-06
        if first_style.get("italic") is not True:
            style_followed.append("h3_not_italic")
        else:
            style_issues.append("h3_not_italic")

        body_style = get_body_style(style_info)

        if body_style:

            # H3-03
            if (
                normalize_font_name(first_style.get("font_name"))
                == normalize_font_name(body_style.get("font_name"))
            ):
                style_followed.append("h3_font_name")
            else:
                style_issues.append("h3_font_name")

            # H3-04
            if (
                first_style.get("font_size")
                == body_style.get("font_size")
            ):
                style_followed.append("h3_font_size")
            else:
                style_issues.append("h3_font_size")

    # --------------------------------------------------------
    # Level 4
    # --------------------------------------------------------

    elif level == 4:

        # H4-01
        if is_sentence_case(heading_text):
            style_followed.append("h4_sentence_case")
        else:
            text_issues.append("h4_sentence_case")

        # H4-02
        if heading_text.endswith("."):
            style_followed.append("h4_final_period")
        else:
            text_issues.append("h4_final_period")

        # H4-05
        if first_style.get("bold") is True:
            style_followed.append("h4_bold")
        else:
            style_issues.append("h4_bold")

        # H4-06
        if first_style.get("italic") is True:
            style_followed.append("h4_italic")
        else:
            style_issues.append("h4_italic")

        body_style = get_body_style(style_info)

        if body_style:

            # H4-03
            if (
                normalize_font_name(first_style.get("font_name"))
                == normalize_font_name(body_style.get("font_name"))
            ):
                style_followed.append("h4_font_name")
            else:
                style_issues.append("h4_font_name")

            # H4-04
            if (
                first_style.get("font_size")
                == body_style.get("font_size")
            ):
                style_followed.append("h4_font_size")
            else:
                style_issues.append("h4_font_size")

    # --------------------------------------------------------
    # Unsupported level
    # --------------------------------------------------------

    else:
        style_issues.append(
            f"Unsupported heading level: {level}"
        )

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    return {
        "valid": (
            len(style_issues) == 0
            and len(text_issues) == 0
        ),
        "style_followed": style_followed,
        "style_issues": style_issues,
        "text_issues": text_issues,
        "actual_style": first_style,
        "heading_text": heading_text,
    }

# ============================================================
# Hierarchy validation
# ============================================================

def validate_hierarchy(
    sections: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Validates hierarchy using actual id / parent_id relationships.

    The expected hierarchy is defined independently of the actual IDs.

    Example:

        METHODS (id=25, parent_id=None)
            STUDY POPULATION (id=26, parent_id=25)
            MEASURES (id=27, parent_id=25)

        DISCUSSION (id=30, parent_id=None)
            LIMITATIONS (id=31, parent_id=30)
    """

    results = []

    # --------------------------------------------------------
    # Index sections by ID
    # --------------------------------------------------------

    by_id = {
        section["id"]: section
        for section in sections
        if section.get("id") is not None
    }

    # --------------------------------------------------------
    # Index sections by normalized name
    # --------------------------------------------------------

    by_name = {}

    for section in sections:

        name = normalize_name(
            section.get("name", "")
        )

        if name:
            by_name[name] = section

    # --------------------------------------------------------
    # Validate each section
    # --------------------------------------------------------

    for section in sections:

        section_id = section.get("id")
        parent_id = section.get("parent_id")
        actual_level = section.get("level")
        name = normalize_name(
            section.get("name", "")
        )

        hierarchy_followed = []
        hierarchy_issues = []

        expected = EXPECTED_HIERARCHY.get(name)

        # ----------------------------------------------------
        # Unknown heading
        # ----------------------------------------------------

        if expected is None:

            results.append({
                "id": section_id,
                "parent_id": parent_id,
                "name": section.get("name"),
                "hierarchy_valid": False,
                "hierarchy_followed": [],
                "hierarchy_issues": [
                    "Section is not defined in expected hierarchy"
                ],
            })

            continue

        expected_level = expected["level"]
        expected_parent_name = expected["parent"]

        # ----------------------------------------------------
        # Validate level
        # ----------------------------------------------------

        if actual_level == expected_level:

            hierarchy_followed.append("correct_level")

        else:

            hierarchy_issues.append(
                f"Expected level {expected_level}, "
                f"found level {actual_level}"
            )

        # ----------------------------------------------------
        # Top-level section
        # ----------------------------------------------------

        if expected_parent_name is None:

            if parent_id is None:

                hierarchy_followed.append(
                    "correct_parent"
                )

            else:

                actual_parent = by_id.get(parent_id)

                actual_parent_name = (
                    actual_parent.get("name")
                    if actual_parent
                    else f"id={parent_id}"
                )

                hierarchy_issues.append(
                    f"Expected parent_id=None, "
                    f"found parent '{actual_parent_name}' "
                    f"(id={parent_id})"
                )

        # ----------------------------------------------------
        # Nested section
        # ----------------------------------------------------

        else:

            expected_parent = by_name.get(
                normalize_name(expected_parent_name)
            )

            if expected_parent is None:

                hierarchy_issues.append(
                    f"Expected parent '{expected_parent_name}' "
                    f"does not exist"
                )

            else:

                expected_parent_id = expected_parent.get("id")

                # Parent ID is the authoritative relationship.
                if parent_id == expected_parent_id:

                    hierarchy_followed.append(
                        "correct_parent"
                    )

                else:

                    actual_parent = by_id.get(parent_id)

                    actual_parent_name = (
                        actual_parent.get("name")
                        if actual_parent
                        else f"id={parent_id}"
                    )

                    hierarchy_issues.append(
                        f"Expected parent_id={expected_parent_id} "
                        f"('{expected_parent_name}'), "
                        f"found parent_id={parent_id} "
                        f"('{actual_parent_name}')"
                    )

    # --------------------------------------------------------
    # Build result
    # --------------------------------------------------------

        results.append({
            "id": section_id,
            "parent_id": parent_id,
            "name": section.get("name"),
            "hierarchy_valid": len(hierarchy_issues) == 0,
            "hierarchy_followed": hierarchy_followed,
            "hierarchy_issues": hierarchy_issues,
        })

    return results


# ============================================================
# Overall section validation
# ============================================================

def validate_sections(
    DOC,
    sections: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Validates:

    1. Heading text capitalization
    2. Heading font
    3. Heading size
    4. Bold/italic properties
    5. Body font/size for Level 3/4
    6. Heading level
    7. parent_id relationship
    8. Overall validity
    """

    hierarchy_results = validate_hierarchy(
        sections
    )

    hierarchy_by_id = {
        result["id"]: result
        for result in hierarchy_results
    }

    results = []

    # --------------------------------------------------------
    # Validate each section
    # --------------------------------------------------------

    for section in sections:

        section_id = section.get("id")
        start_position = section.get(
            "start_position",
            0
        )
        end_position = section.get(
            "end_position",
            start_position
        )

        # Include heading + paragraph break +
        # beginning of following body text.
        extraction_end = min(
            start_position + 500,
            end_position
        )

        style_info = extract_range(
            DOC,
            start_position,
            extraction_end
        )

        style_result = validate_heading_style(
            section,
            style_info
        )

        hierarchy_result = hierarchy_by_id.get(
            section_id,
            {
                "hierarchy_valid": False,
                "hierarchy_followed": [],
                "hierarchy_issues": [
                    "Hierarchy result not found"
                ],
            }
        )

        style_valid = (
            len(style_result["style_issues"]) == 0
        )

        text_valid = (
            len(style_result["text_issues"]) == 0
        )

        hierarchy_valid = hierarchy_result.get(
            "hierarchy_valid",
            False
        )

        results.append({
            # ------------------------------------------------
            # Identity
            # ------------------------------------------------
            "id": section_id,
            "parent_id": section.get("parent_id"),
            "name": section.get("name"),
            "level": section.get("level"),

            # ------------------------------------------------
            # Heading text
            # ------------------------------------------------
            "heading_text": style_result[
                "heading_text"
            ],

            # ------------------------------------------------
            # Style validation
            # ------------------------------------------------
            "style_valid": style_valid,
            "style_followed": style_result[
                "style_followed"
            ],
            "style_issues": style_result[
                "style_issues"
            ],

            # ------------------------------------------------
            # Text validation
            # ------------------------------------------------
            "text_valid": text_valid,
            "text_issues": style_result[
                "text_issues"
            ],

            # ------------------------------------------------
            # Hierarchy validation
            # ------------------------------------------------
            "hierarchy_valid": hierarchy_valid,
            "hierarchy_followed": hierarchy_result.get(
                "hierarchy_followed",
                []
            ),
            "hierarchy_issues": hierarchy_result.get(
                "hierarchy_issues",
                []
            ),

            # ------------------------------------------------
            # Overall
            # ------------------------------------------------
            "valid": (
                style_valid
                and text_valid
                and hierarchy_valid
            ),

            # ------------------------------------------------
            # Actual style
            # ------------------------------------------------
            "actual_style": style_result[
                "actual_style"
            ],
        })

    return results


# ============================================================
# Optional: document-level hierarchy validation
# ============================================================

def validate_document_order(
    sections: List[Dict[str, Any]]
) -> Dict[str, Any]:

    top_level = [
        section
        for section in sections
        if section.get("parent_id") is None
    ]

    # Sort according to document position.
    top_level.sort(
        key=lambda x: x.get("start_position", 0)
    )

    actual_order = [
        normalize_name(
            section.get("name", "")
        )
        for section in top_level
    ]

    expected_order = [
        "INTRODUCTION",
        "METHODS",
        "RESULTS",
        "DISCUSSION",
        "CONCLUSIONS",
    ]

    followed = []
    issues = []

    # --------------------------------------------------------
    # Check expected top-level sections
    # --------------------------------------------------------

    for name in expected_order:

        if name in actual_order:
            followed.append(
                f"contains_{name.lower()}"
            )
        else:
            issues.append(
                f"Missing top-level section '{name}'"
            )

    # --------------------------------------------------------
    # Check order
    # --------------------------------------------------------

    positions = {
        name: actual_order.index(name)
        for name in actual_order
    }

    present_expected = [
        name
        for name in expected_order
        if name in positions
    ]

    expected_present_order = [
        name
        for name in expected_order
        if name in positions
    ]

    if present_expected == expected_present_order:
        followed.append("correct_top_level_order")
    else:
        issues.append(
            "Top-level sections are not in expected order"
        )

    # --------------------------------------------------------
    # Detect unexpected top-level sections
    # --------------------------------------------------------

    unexpected = [
        name
        for name in actual_order
        if name not in expected_order
    ]

    if not unexpected:
        followed.append(
            "no_unexpected_top_level_sections"
        )
    else:
        issues.append(
            "Unexpected top-level sections: "
            + ", ".join(unexpected)
        )

    return {
        "valid": len(issues) == 0,
        "actual_order": actual_order,
        "expected_order": expected_order,
        "followed": followed,
        "issues": issues,
    }


# ============================================================
# Complete document validator
# ============================================================

def validate_document(
    DOC,
    sections: List[Dict[str, Any]],
) -> Dict[str, Any]:

    section_results = validate_sections(
        DOC,
        sections
    )

    document_order = validate_document_order(
        sections
    )

    return {
        "valid": (
            document_order["valid"]
            and all(
                result["valid"]
                for result in section_results
            )
        ),
        "document_order": document_order,
        "sections": section_results,
    }
