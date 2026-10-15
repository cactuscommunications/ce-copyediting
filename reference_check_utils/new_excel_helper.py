import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter


def create_reference_edits_excel(data, output_path="reference_edits.xlsx"):
    """
    Create an Excel workbook from reference-edit JSON data.

    Parameters
    ----------
    data : dict
        Dictionary in the format:
        {
            "filename1.docx": [
                {
                    "original": "...",
                    "edited": "...",
                    "edits": {
                        "text_edits": [...],
                        "missing_components": [...],
                        "warnings": [...]
                    }
                }
            ],
            "filename2.docx": [...]
        }

    output_path : str
        Path where the Excel workbook will be saved.

    Returns
    -------
    str
        Path to the generated Excel workbook.
    """

    wb = Workbook()
    wb.remove(wb.active)

    # ---------------------------------------------------------
    # Styles
    # ---------------------------------------------------------

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(
        fill_type="solid",
        fgColor="1F4E78"
    )

    thin_gray = Side(style="thin", color="D9E1F2")
    cell_border = Border(
        left=thin_gray,
        right=thin_gray,
        top=thin_gray,
        bottom=thin_gray
    )

    headers = [
        "Original",
        "Edited",
        "Edit Type",
        "Details"
    ]

    # ---------------------------------------------------------
    # Helper: create a valid, unique worksheet name
    # ---------------------------------------------------------

    used_sheet_names = set()

    def get_sheet_name(filename):
        # Excel prohibits: \ / * ? : [ ]
        name = re.sub(r'[\\/*?:\[\]]', "_", str(filename))
        name = name.strip("'") or "Sheet"

        # Excel worksheet names cannot exceed 31 characters.
        base_name = name[:31]
        sheet_name = base_name
        counter = 1

        while sheet_name.casefold() in used_sheet_names:
            suffix = f"_{counter}"
            sheet_name = base_name[:31 - len(suffix)] + suffix
            counter += 1

        used_sheet_names.add(sheet_name.casefold())
        return sheet_name

    # ---------------------------------------------------------
    # Create one worksheet for each file
    # ---------------------------------------------------------

    for filename, references in data.items():

        ws = wb.create_sheet(
            title=get_sheet_name(filename)
        )

        ws.append(headers)

        # Format header
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True
            )
            cell.border = cell_border

        ws.row_dimensions[1].height = 25

        # -----------------------------------------------------
        # Process each reference
        # -----------------------------------------------------

        for reference in references:
            original = reference.get("original", "")
            edited = reference.get("edited", "")

            edits = reference.get("edits") or {}

            edit_rows = []

            for item in edits.get("text_edits") or []:
                edit_rows.append(("Text Edit", item))

            for item in edits.get("missing_components") or []:
                edit_rows.append(("Incomplete Component", item))

            for item in edits.get("warnings") or []:
                edit_rows.append(("Warning", item))

    # Ensure every reference appears at least once.
            if not edit_rows:
                edit_rows.append(("", ""))

    # Write Original and Edited only in the first row.
            for index, (edit_type, details) in enumerate(edit_rows):
                ws.append([
                    original if index == 0 else "",
                    edited if index == 0 else "",
                    edit_type,
                    details
                ])

    # Add an empty row between references.
            ws.append([])
        # -----------------------------------------------------
        # Worksheet formatting
        # -----------------------------------------------------

        column_widths = {
            "A": 55,  # Original
            "B": 55,  # Edited
            "C": 23,  # Edit Type
            "D": 75,  # Details
        }

        for column, width in column_widths.items():
            ws.column_dimensions[column].width = width

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:D{ws.max_row}"

        # Do not print excessive empty rows in the worksheet.
        # ws.sheet_view.showGridLines = False

    # ---------------------------------------------------------
    # Save workbook
    # ---------------------------------------------------------

    output_path = Path(output_path)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    wb.save(output_path)

    return str(output_path)