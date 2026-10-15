import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont


def get_field(obj, field_name, default=None):
    """Support both dataclass objects and dictionaries."""
    if isinstance(obj, dict):
        return obj.get(field_name, default)

    return getattr(obj, field_name, default)


def parse_text_edit(text_edit):
    """
    Extract the original and replacement text from a text edit.

    Expected format:
        'old text to new text'

    Returns:
        (old_text, new_text)

    If 'to' is missing, returns (None, None).
    """
    if isinstance(text_edit, dict):
        old_text = (
            text_edit.get("before")
            or text_edit.get("original")
            or text_edit.get("old_text")
        )
        new_text = (
            text_edit.get("after")
            or text_edit.get("replacement")
            or text_edit.get("new_text")
        )

        if old_text is not None and new_text is not None:
            return str(old_text).strip(), str(new_text).strip()

    text = str(text_edit)

    # Split only at the first occurrence of "to".
    # Whitespace boundaries prevent splitting words such as "together".
    match = re.search(r"\s+to\s+", text, flags=re.IGNORECASE)

    if not match:
        return None, None

    old_text = text[:match.start()].strip()
    new_text = text[match.end():].strip()

    return old_text, new_text

def make_rich_text(text, spans, color):
    """
    Return an Excel rich-text value with changed portions
    highlighted in bold red.

    Text outside the specified spans retains normal formatting.
    red - FFFF0000
    green - 008000
    """
    if not text or not spans:
        return text

    rich_text = CellRichText()
    position = 0

    highlight_font = InlineFont(
        b=True,
        color = color,
    )

    for start, end in spans:

        # Normal text before the changed portion.
        if position < start:
            rich_text.append(text[position:start])

        # Changed portion.
        rich_text.append(
            TextBlock(
                highlight_font,
                text[start:end],
            )
        )

        position = end

    # Remaining normal text.
    if position < len(text):
        rich_text.append(text[position:])

    return rich_text


def make_highlighted_text(full_text, target_text, color):
    """
    Return rich text with only target_text highlighted.

    If target_text occurs multiple times, highlight its first occurrence.
    If it does not occur, return the full text without highlighting.
    """
    full_text = str(full_text or "")
    target_text = str(target_text or "")

    if not full_text or not target_text:
        return full_text

    start = full_text.find(target_text)

    if start == -1:
        return full_text

    end = start + len(target_text)

    # InlineFont uses RGB without the usual eight-character ARGB prefix.
    normal_font = InlineFont(color="000000")
    highlight_font = InlineFont(color=color)

    rich_text = CellRichText()

    # Text before the highlighted portion.
    if start > 0:
        rich_text.append(
            TextBlock(normal_font, full_text[:start])
        )

    # Highlighted portion.
    rich_text.append(
        TextBlock(highlight_font, full_text[start:end])
    )

    # Text after the highlighted portion.
    if end < len(full_text):
        rich_text.append(
            TextBlock(normal_font, full_text[end:])
        )

    return rich_text

def extract_change(text_edit):
    """
    Parse text edits into pairs of (old_text, new_text).

    Example:
        'KP, to KPC,' -> ('KP,', 'KPC,')
    """
    changes = []
    if not isinstance(text_edit, str):
        return "",""
    
    parts = re.split(r"\s+to\s+", text_edit.strip(), maxsplit=1)
    if len(parts) != 2:
        return "",""

    old_text, new_text = parts[0].strip(), parts[1].strip()
    if old_text and new_text:
        return old_text, new_text
    
    # for edit in text_edits or []:
    #     if not isinstance(edit, str):
    #         continue

    #     parts = re.split(r"\s+to\s+", edit.strip(), maxsplit=1)

    #     if len(parts) != 2:
    #         continue

    #     old_text, new_text = parts[0].strip(), parts[1].strip()

    #     if old_text and new_text:
    #         changes.append((old_text, new_text))

    # return changes


def find_change_span(text, change, side, offset):
    print(f'received offset: {offset}')
    """
    Find the character ranges to highlight.

    side='original' -> highlight old text
    side='edited'   -> highlight new text

    Returns:
        [(start, end), ...]
    """
    spans = []

    for old_text, new_text in change:
        target = old_text if side == "original" else new_text
        print(target)
        print(text)
        start = text.find(target, offset)

        if start == -1:
            continue

        end = start + len(target)
        spans.append((start, end))

    # Sort spans by their starting positions.
    spans.sort()

    # Merge overlapping spans to prevent duplicate formatting.
    merged = []

    for start, end in spans:
        if merged and start < merged[-1][1]:
            merged[-1] = (
                merged[-1][0],
                max(merged[-1][1], end),
            )
        else:
            merged.append((start, end))

    return merged


def create_highlighted_workbook(final_ref_map, output_path):
    """
    Create an Excel workbook with one row per text edit.

    Columns:
        1. Original Reference
        2. Edited Reference
        3. Entry Type
        4. Details

    Rules:
        - One row per text edit.
        - Only the changed portion of Original Reference is red.
        - Only the replacement portion of Edited Reference is green.
        - Warnings follow all text edits for that reference.
        - Incomplete components follow warnings.
        - Original and edited references are blank in warning
          and incomplete-component rows.
    """

    wb = Workbook()
    wb.remove(wb.active)

    # Styles
    header_font = Font(bold=True)
    header_fill = PatternFill(
        fill_type="solid",
        fgColor="D9EAF7",
    )

    warning_font = Font(color="FFFF0000")
    incomplete_font = Font(color="FFBF7600")

    headers = [
        "Original Reference",
        "Edited Reference",
        "Entry Type",
        "Details",
    ]

    used_sheet_names = set()

    for filename, references in final_ref_map.items():

        # Excel worksheet names are limited to 31 characters.
        base_name = re.sub(
            r'[\\/*?:\[\]]',
            "_",
            str(filename),
        )[:31] or "References"

        sheet_name = base_name
        counter = 1

        while sheet_name.lower() in used_sheet_names:
            suffix = f"_{counter}"
            sheet_name = base_name[:31 - len(suffix)] + suffix
            counter += 1

        used_sheet_names.add(sheet_name.lower())

        ws = wb.create_sheet(title=sheet_name)
        ws.append(headers)

        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )

        for ref in references:
            print(f'REFERENCE in excel: {ref}')

            original = get_field(
                ref, "original", ""
            ) or ""

            edited = get_field(
                ref, "edited", ""
            ) or ""

            text_edits = get_field(
                ref['edits'], "text_edits", []
            ) or []

            warnings = get_field(
                ref['edits'], "warnings", []
            ) or []

            incomplete_components = get_field(
                ref['edits'], "missing_components", []
            ) or []

            print(f'Warning in excel: {warnings}')
            print()
            print(f'TEXT EDITSSSS--- {text_edits}')
            for text_edit in text_edits:

                old_text, new_text = text_edit['original_text'],text_edit['edited_text']
                print(old_text)
                print(new_text)

                if old_text is not None and new_text is not None:

                    original_spans = (text_edit['original_position'].get('start'),text_edit['original_position'].get('end'))
                    print(original_spans)
                    
                    # original_span_start = original_spans[0]
                    original_span_start, original_span_end = original_spans
                    print(original_span_start)
                    edited_spans = (text_edit['edited_position'].get('start'),text_edit['edited_position'].get('end'))
                    
                    print(edited_spans)

                    original_cell_value = make_rich_text(original, [original_spans], "FFFF0000")
                    edited_cell_value = make_rich_text(edited, [edited_spans], "008000")
                    # original_cell_value = make_highlighted_text(
                    #     original,
                    #     old_text,
                    #     "FF0000",
                    # )

                    # edited_cell_value = make_highlighted_text(
                    #     edited,
                    #     new_text,
                    #     "008000",
                    # )

                else:
                    # Preserve the reference if the edit format
                    # cannot be parsed.
                    original_cell_value = original
                    edited_cell_value = edited

                ws.append([
                    original_cell_value,
                    edited_cell_value,
                    "Text Edit",
                    str(text_edit),
                ])

            # --------------------------------------------------
            # 2. Warnings after all text edits
            # --------------------------------------------------
            for warning in warnings:

                ws.append([
                    "",
                    "",
                    "Warning",
                    str(warning),
                ])

                ws.cell(ws.max_row, 4).font = warning_font

            # --------------------------------------------------
            # 3. Incomplete components after warnings
            # --------------------------------------------------
            for component in incomplete_components:

                ws.append([
                    original,
                    "",
                    "Incomplete Component",
                    str(component),
                ])

                ws.cell(ws.max_row, 4).font = incomplete_font

            # --------------------------------------------------
            # 4. Preserve references that have no entries
            # --------------------------------------------------
            if (
                not text_edits
                and not warnings
                and not incomplete_components
            ):
                ws.append([
                    original,
                    edited,
                    "No Edits",
                    "",
                ])
            if (
                not text_edits
                and not warnings
                and not incomplete_components
            ):
                ws.append([
                    original,
                    edited,
                    "No Edits",
                    "",
                ])
            ws.append(["","","",""])
        # ------------------------------------------------------
        # Worksheet formatting
        # ------------------------------------------------------
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        ws.column_dimensions["A"].width = 65
        ws.column_dimensions["B"].width = 65
        ws.column_dimensions["C"].width = 25
        ws.column_dimensions["D"].width = 60

        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(
                    vertical="top",
                    wrap_text=True,
                )

        for row_num in range(2, ws.max_row + 1):
            ws.row_dimensions[row_num].height = 80

    # Save workbook
    output_path = Path(output_path)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    wb.save(output_path)

    print(f"Workbook saved to: {output_path}")