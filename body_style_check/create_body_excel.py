import csv
import json
from pathlib import Path
from typing import Dict, Any, List


def validation_json_to_csv(
    json_res: dict,
    csv_path: str | None = None,
):
    """
    Convert a single document validation JSON into one CSV.

    One row = one section/heading.

    Document-level validation fields are repeated for every row
    so that the resulting CSV remains self-contained.
    """

    # json_path = Path(json_path)

    # if csv_path is None:
    #     csv_path = json_path.with_suffix(".csv")
    # else:
    #     csv_path = Path(csv_path)

    # # --------------------------------------------------------
    # # Load JSON
    # # --------------------------------------------------------

    # with open(json_path, "r", encoding="utf-8") as f:
    #     data = json.load(f)

    data = json_res
    document_order = data.get("document_order", {})
    sections = data.get("sections", [])

    # --------------------------------------------------------
    # CSV columns
    # --------------------------------------------------------

    fieldnames = [
        # Document
        "document",
        "document_valid",

        # Document order
        "document_order_valid",
        "actual_order",
        "expected_order",
        "document_order_followed",
        "document_order_issues",

        # Section identity
        "section_id",
        "parent_id",
        "section_name",
        "level",
        "heading_text",

        # Overall section validation
        "section_valid",

        # Text validation
        "text_valid",
        "text_issues",

        # Style validation
        "style_valid",
        "style_followed",
        "style_issues",

        # Hierarchy validation
        "hierarchy_valid",
        "hierarchy_followed",
        "hierarchy_issues",

        # Actual style
        "font_name",
        "font_size",
        "bold",
        "italic",
        "underline",
        "strike",
        "color",
        "highlight",
        "vert_align",
        "all_caps",
    ]

    # --------------------------------------------------------
    # Convert list values to CSV-safe strings
    # --------------------------------------------------------

    def list_to_string(value):
        if not value:
            return ""

        return " | ".join(str(v) for v in value)

    # --------------------------------------------------------
    # Write CSV
    # --------------------------------------------------------

    with open(
        csv_path,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()

        for section in sections:

            actual_style = (
                section.get("actual_style") or {}
            )

            writer.writerow({
                # ------------------------------------------------
                # Document
                # ------------------------------------------------
                "document": csv_path,
                "document_valid": data.get(
                    "valid",
                    False
                ),

                # ------------------------------------------------
                # Document order
                # ------------------------------------------------
                "document_order_valid": document_order.get(
                    "valid",
                    False
                ),

                "actual_order": list_to_string(
                    document_order.get(
                        "actual_order",
                        []
                    )
                ),

                "expected_order": list_to_string(
                    document_order.get(
                        "expected_order",
                        []
                    )
                ),

                "document_order_followed": list_to_string(
                    document_order.get(
                        "followed",
                        []
                    )
                ),

                "document_order_issues": list_to_string(
                    document_order.get(
                        "issues",
                        []
                    )
                ),

                # ------------------------------------------------
                # Section identity
                # ------------------------------------------------
                "section_id": section.get("id"),

                "parent_id": section.get(
                    "parent_id"
                ),

                "section_name": section.get(
                    "name",
                    ""
                ),

                "level": section.get(
                    "level"
                ),

                "heading_text": section.get(
                    "heading_text",
                    ""
                ),

                # ------------------------------------------------
                # Overall
                # ------------------------------------------------
                "section_valid": section.get(
                    "valid",
                    False
                ),

                # ------------------------------------------------
                # Text
                # ------------------------------------------------
                "text_valid": section.get(
                    "text_valid",
                    False
                ),

                "text_issues": list_to_string(
                    section.get(
                        "text_issues",
                        []
                    )
                ),

                # ------------------------------------------------
                # Style
                # ------------------------------------------------
                "style_valid": section.get(
                    "style_valid",
                    False
                ),

                "style_followed": list_to_string(
                    section.get(
                        "style_followed",
                        []
                    )
                ),

                "style_issues": list_to_string(
                    section.get(
                        "style_issues",
                        []
                    )
                ),

                # ------------------------------------------------
                # Hierarchy
                # ------------------------------------------------
                "hierarchy_valid": section.get(
                    "hierarchy_valid",
                    False
                ),

                "hierarchy_followed": list_to_string(
                    section.get(
                        "hierarchy_followed",
                        []
                    )
                ),

                "hierarchy_issues": list_to_string(
                    section.get(
                        "hierarchy_issues",
                        []
                    )
                ),

                # ------------------------------------------------
                # Actual style
                # ------------------------------------------------
                "font_name": actual_style.get(
                    "font_name"
                ),

                "font_size": actual_style.get(
                    "font_size"
                ),

                "bold": actual_style.get(
                    "bold"
                ),

                "italic": actual_style.get(
                    "italic"
                ),

                "underline": actual_style.get(
                    "underline"
                ),

                "strike": actual_style.get(
                    "strike"
                ),

                "color": actual_style.get(
                    "color"
                ),

                "highlight": actual_style.get(
                    "highlight"
                ),

                "vert_align": actual_style.get(
                    "vert_align"
                ),

                "all_caps": actual_style.get(
                    "all_caps"
                ),
            })

    return str(csv_path)


# import json
# from typing import Dict, Any, List

# from openpyxl import Workbook
# from openpyxl.styles import Font, Alignment


# ------------------------------------------------------------------
# Guideline definitions
# ------------------------------------------------------------------

GUIDELINES = {
    # H1
    "h1_all_caps": {
        "id": "H1-01",
        "guideline": "Heading must be all caps",
        "reason": "Heading is not written in all caps",
    },
    "h1_font_name": {
        "id": "H1-02",
        "guideline": "Font must be 'Franklin Gothic Medium'",
        "reason": "Font is not 'Franklin Gothic Medium'",
    },
    "h1_font_size": {
        "id": "H1-03",
        "guideline": "Font size must be 14 pt",
        "reason": "Font size is not 14 pt",
    },
    "h1_bold": {
        "id": "H1-04",
        "guideline": "Font must be bold",
        "reason": "Font is not bold",
    },
    "h1_not_italic": {
        "id": "H1-05",
        "guideline": "Font must not be italic",
        "reason": "Font is italic",
    },

    # H2
    "h2_headline_case": {
        "id": "H2-01",
        "guideline": "Heading must use headline case",
        "reason": "Heading is not written in headline case",
    },
    "h2_font_name": {
        "id": "H2-02",
        "guideline": "Font must be 'Franklin Gothic Medium'",
        "reason": "Font is not 'Franklin Gothic Medium'",
    },
    "h2_font_size": {
        "id": "H2-03",
        "guideline": "Font size must be 11 pt",
        "reason": "Font size is not 11 pt",
    },
    "h2_bold": {
        "id": "H2-04",
        "guideline": "Font must be bold",
        "reason": "Font is not bold",
    },
    "h2_not_italic": {
        "id": "H2-05",
        "guideline": "Font must not be italic",
        "reason": "Font is italic",
    },

    # H3
    "h3_sentence_case": {
        "id": "H3-01",
        "guideline": "Heading must use sentence case",
        "reason": "Heading is not written in sentence case",
    },
    "h3_final_period": {
        "id": "H3-02",
        "guideline": "Heading must end with a period",
        "reason": "Heading does not end with a period",
    },
    "h3_font_name": {
        "id": "H3-03",
        "guideline": "Font must match the body text font",
        "reason": "Heading font does not match the body text font",
    },
    "h3_font_size": {
        "id": "H3-04",
        "guideline": "Font size must match the body text font size",
        "reason": "Heading font size does not match the body text font size",
    },
    "h3_bold": {
        "id": "H3-05",
        "guideline": "Font must be bold",
        "reason": "Font is not bold",
    },
    "h3_not_italic": {
        "id": "H3-06",
        "guideline": "Font must not be italic",
        "reason": "Font is italic",
    },

    # H4
    "h4_sentence_case": {
        "id": "H4-01",
        "guideline": "Heading must use sentence case",
        "reason": "Heading is not written in sentence case",
    },
    "h4_final_period": {
        "id": "H4-02",
        "guideline": "Heading must end with a period",
        "reason": "Heading does not end with a period",
    },
    "h4_font_name": {
        "id": "H4-03",
        "guideline": "Font must match the body text font",
        "reason": "Heading font does not match the body text font",
    },
    "h4_font_size": {
        "id": "H4-04",
        "guideline": "Font size must match the body text font size",
        "reason": "Heading font size does not match the body text font size",
    },
    "h4_bold": {
        "id": "H4-05",
        "guideline": "Font must be bold",
        "reason": "Font is not bold",
    },
    "h4_italic": {
        "id": "H4-06",
        "guideline": "Font must be italic",
        "reason": "Font is not italic",
    },

    # --------------------------------------------------------------
    # Hierarchy
    # --------------------------------------------------------------
    "correct_level": {
        "id": "HIER-01",
        "guideline": "Section must have the correct hierarchy level",
        "reason": "Section has an incorrect hierarchy level",
    },
    "correct_parent": {
        "id": "HIER-02",
        "guideline": "Section must have the correct parent section",
        "reason": "Section has an incorrect parent section",
    },

    # --------------------------------------------------------------
    # Document order
    # --------------------------------------------------------------
    "contains_introduction": {
        "id": "ORD-01",
        "guideline": "Document must contain an Introduction section",
        "reason": "Introduction section is missing",
    },
    "contains_methods": {
        "id": "ORD-02",
        "guideline": "Document must contain a Methods section",
        "reason": "Methods section is missing",
    },
    "contains_results": {
        "id": "ORD-03",
        "guideline": "Document must contain a Results section",
        "reason": "Results section is missing",
    },
    "contains_discussion": {
        "id": "ORD-04",
        "guideline": "Document must contain a Discussion section",
        "reason": "Discussion section is missing",
    },
    "contains_conclusions": {
        "id": "ORD-05",
        "guideline": "Document must contain a Conclusions section",
        "reason": "Conclusions section is missing",
    },
    "correct_top_level_order": {
        "id": "ORD-06",
        "guideline": "Top-level sections must appear in the required order",
        "reason": "Top-level sections are not in the required order",
    },
    "no_unexpected_top_level_sections": {
        "id": "ORD-07",
        "guideline": "Document must not contain unexpected top-level sections",
        "reason": "Unexpected top-level section detected",
    },
}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

# def get_guideline_info(guideline_key: str) -> Dict[str, str]:
#     print(guideline_key)
#     """
#     Return guideline metadata.

#     Unknown guideline keys are handled gracefully.
#     """

#     if guideline_key in GUIDELINES:
#         return GUIDELINES[guideline_key]

#     return {
#         "id": guideline_key,
#         "guideline": guideline_key.replace("_", " ").capitalize(),
#         "reason": f"Guideline '{guideline_key}' was not followed",
#     }


# def add_guideline_row(
#     rows: List[Dict[str, Any]],
#     content: str,
#     section: str,
#     guideline_key: str,
#     followed: bool,
# ):
#     """
#     Add a single guideline result.
#     """

#     info = get_guideline_info(guideline_key)

#     rows.append({
#         "Content": content,
#         "Section": section,
#         "Guideline_Followed": followed,
#         "Guideline ID": info["id"],
#         "Guideline": info["guideline"],
#         "Reason": "" if followed else info["reason"],
#     })


# def process_validation_group(
#     rows: List[Dict[str, Any]],
#     content: str,
#     section: str,
#     followed_list: List[str],
#     issues_list: List[str],
# ):
#     """
#     Convert a followed/issues pair into individual Excel rows.
#     """

#     followed_set = set(followed_list)
#     issues_set = set(issues_list)

#     # Include both passed and failed guidelines.
#     guideline_keys = followed_set | issues_set

#     for guideline_key in guideline_keys:

#         add_guideline_row(
#             rows=rows,
#             content=content,
#             section=section,
#             guideline_key=guideline_key,
#             followed=guideline_key in followed_set,
#         )

def get_guideline_info(guideline_key: str) -> Dict[str, str]:
    """
    Resolve a guideline key to its ID, text and failure reason.
    """

    # Normal case: guideline key exists in GUIDELINES
    if guideline_key in GUIDELINES:
        return GUIDELINES[guideline_key]

    # If the value is already a guideline description,
    # try to match it against the configured guideline text.
    normalized_value = guideline_key.strip().lower()

    for key, info in GUIDELINES.items():

        guideline_text = info.get("guideline", "").strip().lower()
        reason_text = info.get("reason", "").strip().lower()

        if (
            normalized_value == guideline_text
            or normalized_value == reason_text
        ):
            return {
                "id": info["id"],
                "guideline": info["guideline"],
                "reason": info["reason"],
            }

    # Unknown guideline text.
    # Keep the text as the guideline, but don't put it in Guideline ID.
    return {
        "id": "",
        "guideline": guideline_key,
        "reason": guideline_key,
    }


def add_guideline_row(
    rows: List[Dict[str, Any]],
    content: str,
    section: str,
    guideline_key: str,
    followed: bool,
):
    """
    Add a single guideline validation result.
    """

    info = get_guideline_info(guideline_key)

    rows.append({
        "Content": content,
        "Section": section,
        "Guideline_Followed": int(followed),
        "Guideline ID": info["id"],
        "Guideline": info["guideline"],
        "Reason": "" if followed else info["reason"],
    })


def process_validation_group(
    rows: List[Dict[str, Any]],
    content: str,
    section: str,
    followed_list: List[str],
    issues_list: List[str],
):
    """
    Convert followed/issue lists into individual Excel rows.

    Supports both:
        ["font_name", "bold"]

    and:

        ["Font must be 'Franklin Gothic Medium'"]
    """

    # Passed guidelines
    for guideline_key in followed_list:

        add_guideline_row(
            rows=rows,
            content=content,
            section=section,
            guideline_key=guideline_key,
            followed=True,
        )

    # Failed guidelines
    for issue in issues_list:
        print(issue)
        add_guideline_row(
            rows=rows,
            content=content,
            section=section,
            guideline_key=issue,
            followed=False,
        )

# ------------------------------------------------------------------
# Main conversion
# ------------------------------------------------------------------

# def validation_json_to_excel(
#     validation_result: Dict[str, Any],
#     output_file: str,
# ):
#     """
#     Convert validation JSON into an Excel workbook.

#     One row = one guideline validation.

#     Columns:
#         Content
#         Section
#         Guideline_Followed
#         Guideline ID
#         Guideline
#         Reason
#     """

#     rows = []

#     # ==============================================================
#     # Section-level validation
#     # ==============================================================

#     for section in validation_result.get("sections", []):

#         section_name = section.get("name", "")
#         heading_text = section.get("heading_text", "")

#         # ----------------------------------------------------------
#         # Style validation
#         # ----------------------------------------------------------

#         process_validation_group(
#             rows=rows,
#             content=heading_text,
#             section=section_name,
#             followed_list=section.get("style_followed", []),
#             issues_list=section.get("style_issues", []),
#         )

#         # ----------------------------------------------------------
#         # Text validation
#         # ----------------------------------------------------------

#         process_validation_group(
#             rows=rows,
#             content=heading_text,
#             section=section_name,
#             followed_list=section.get("text_followed", []),
#             issues_list=section.get("text_issues", []),
#         )

#         # ----------------------------------------------------------
#         # Hierarchy validation
#         # ----------------------------------------------------------

#         process_validation_group(
#             rows=rows,
#             content=heading_text,
#             section=section_name,
#             followed_list=section.get("hierarchy_followed", []),
#             issues_list=section.get("hierarchy_issues", []),
#         )

#     # ==============================================================
#     # Document-order validation
#     # ==============================================================

#     document_order = validation_result.get("document_order", {})

#     process_validation_group(
#         rows=rows,
#         content="",
#         section="Document Order",
#         followed_list=document_order.get("followed", []),
#         issues_list=document_order.get("issues", []),
#     )

#     # ==============================================================
#     # Create workbook
#     # ==============================================================

#     wb = Workbook()
#     ws = wb.active
#     ws.title = "Validation"

#     headers = [
#         "Content",
#         "Section",
#         "Guideline_Followed",
#         "Guideline ID",
#         "Guideline",
#         "Reason",
#     ]

#     ws.append(headers)

#     # ==============================================================
#     # Write data
#     # ==============================================================

#     for row in rows:
#         ws.append([
#             row["Content"],
#             row["Section"],
#             row["Guideline_Followed"],
#             row["Guideline ID"],
#             row["Guideline"],
#             row["Reason"],
#         ])

#     # ==============================================================
#     # Formatting
#     # ==============================================================

#     # Header
#     for cell in ws[1]:
#         cell.font = Font(bold=True)
#         cell.alignment = Alignment(
#             horizontal="center",
#             vertical="center",
#         )

#     # Data
#     for row in ws.iter_rows(min_row=2):

#         for cell in row:
#             cell.alignment = Alignment(
#                 vertical="top",
#                 wrap_text=True,
#             )

#         # Guideline followed column
#         row[2].alignment = Alignment(
#             horizontal="center",
#             vertical="top",
#         )

#         # Guideline ID
#         row[3].alignment = Alignment(
#             horizontal="center",
#             vertical="top",
#         )

#     # ==============================================================
#     # Column widths
#     # ==============================================================

#     column_widths = {
#         "A": 40,   # Content
#         "B": 25,   # Section
#         "C": 20,   # Guideline_Followed
#         "D": 15,   # Guideline ID
#         "E": 60,   # Guideline
#         "F": 50,   # Reason
#     }

#     for column, width in column_widths.items():
#         ws.column_dimensions[column].width = width

#     # ==============================================================
#     # Sheet settings
#     # ==============================================================

#     ws.freeze_panes = "A2"
#     ws.auto_filter.ref = ws.dimensions

#     # ==============================================================
#     # Save
#     # ==============================================================

#     wb.save(output_file)

#     return output_file

import re
from pathlib import Path
from typing import Dict, Any, List

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment


def sanitize_sheet_name(name: str) -> str:
    """
    Convert a filename into a valid Excel sheet name.

    Excel restrictions:
    - Maximum 31 characters
    - Cannot contain: \\ / * ? : [ ]
    """

    name = Path(name).stem

    # Remove invalid Excel characters
    name = re.sub(r'[\\/*?:\[\]]', "_", name)

    # Excel does not allow an empty sheet name
    if not name:
        name = "Validation"

    # Maximum Excel sheet name length
    return name[:31]


def get_unique_sheet_name(
    wb: Workbook,
    desired_name: str,
) -> str:
    """
    Ensure the sheet name is unique within the workbook.
    """

    base_name = desired_name[:31]
    sheet_name = base_name
    counter = 1

    while sheet_name in wb.sheetnames:

        suffix = f"_{counter}"
        sheet_name = base_name[:31 - len(suffix)] + suffix

        counter += 1

    return sheet_name


def add_validation_sheet(
    wb: Workbook,
    validation_result: Dict[str, Any],
    sheet_name: str,
):
    """
    Add one document's validation result as a worksheet.
    """

    rows = []

    # ==============================================================
    # Section-level validation
    # ==============================================================

    for section in validation_result.get("sections", []):

        section_name = section.get("name", "")
        heading_text = section.get("heading_text", "")

        # Style
        process_validation_group(
            rows=rows,
            content=heading_text,
            section=section_name,
            followed_list=section.get("style_followed", []),
            issues_list=section.get("style_issues", []),
        )

        # Text
        process_validation_group(
            rows=rows,
            content=heading_text,
            section=section_name,
            followed_list=section.get("text_followed", []),
            issues_list=section.get("text_issues", []),
        )

        # Hierarchy
        process_validation_group(
            rows=rows,
            content=heading_text,
            section=section_name,
            followed_list=section.get("hierarchy_followed", []),
            issues_list=section.get("hierarchy_issues", []),
        )

    # ==============================================================
    # Document order
    # ==============================================================

    document_order = validation_result.get("document_order", {})

    process_validation_group(
        rows=rows,
        content="",
        section="Document Order",
        followed_list=document_order.get("followed", []),
        issues_list=document_order.get("issues", []),
    )

    # ==============================================================
    # Create worksheet
    # ==============================================================

    ws = wb.create_sheet(title=sheet_name)

    headers = [
        "Content",
        "Section",
        "Guideline_Followed",
        "Guideline ID",
        "Guideline",
        "Reason",
    ]

    ws.append(headers)

    # ==============================================================
    # Write data
    # ==============================================================

    for row in rows:
        ws.append([
            row["Content"],
            row["Section"],
            row["Guideline_Followed"],
            row["Guideline ID"],
            row["Guideline"],
            row["Reason"],
        ])

    # ==============================================================
    # Formatting
    # ==============================================================

    # Header
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

    # Data
    for row in ws.iter_rows(min_row=2):

        for cell in row:
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )

        # Guideline followed
        row[2].alignment = Alignment(
            horizontal="center",
            vertical="top",
        )

        # Guideline ID
        row[3].alignment = Alignment(
            horizontal="center",
            vertical="top",
        )

    # ==============================================================
    # Column widths
    # ==============================================================

    column_widths = {
        "A": 40,
        "B": 25,
        "C": 20,
        "D": 15,
        "E": 60,
        "F": 50,
    }

    for column, width in column_widths.items():
        ws.column_dimensions[column].width = width

    # ==============================================================
    # Sheet settings
    # ==============================================================

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def create_validation_workbook(
    validation_files: Dict,
    output_file: str,
):
    """
    Create a single Excel workbook containing one worksheet
    per validation JSON file.

    Example:

        validation_results/
            article_001.json
            article_002.json
            article_003.json

    produces:

        validation_results.xlsx

        ├── article_001
        ├── article_002
        └── article_003
    """

    wb = Workbook()

    # Remove the default worksheet.
    default_sheet = wb.active
    wb.remove(default_sheet)

    # ==============================================================
    # Process every validation JSON
    # ==============================================================

    for key,value in validation_files.items():

        # Create valid + unique Excel sheet name
        sheet_name = key

        add_validation_sheet(
            wb=wb,
            validation_result=value,
            sheet_name=sheet_name,
        )

    # ==============================================================
    # Save one workbook
    # ==============================================================

    wb.save(output_file)

    return output_file