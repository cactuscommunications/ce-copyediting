"""Public API: extract sections from a DOCX file or plain text."""
from __future__ import annotations

import os

from .assemble import assemble
from .docx_reader import read_docx
from .model import DocumentResult
from .text_reader import read_text


def extract_docx(path: str, mode: str = "accept") -> DocumentResult:
    blocks, full_text, excluded, warnings = read_docx(path, mode=mode)
    sections, aw = assemble(blocks, full_text, text_mode=False)
    return DocumentResult(
        source=os.path.abspath(path), mode=mode, full_text=full_text,
        blocks=blocks, sections=sections, excluded_streams=excluded,
        warnings=warnings + aw,
    )


def extract_text(raw: str, source: str = "<text>") -> DocumentResult:
    blocks, full_text, excluded, warnings = read_text(raw)
    sections, aw = assemble(blocks, full_text, text_mode=True)
    return DocumentResult(
        source=source, mode="text", full_text=full_text, blocks=blocks,
        sections=sections, excluded_streams=excluded,
        warnings=warnings + aw,
    )


def extract(path: str, mode: str = "accept") -> DocumentResult:
    low = path.lower()
    if low.endswith(".docx"):
        return extract_docx(path, mode=mode)
    if low.endswith((".txt", ".text")):
        with open(path, encoding="utf-8", errors="replace") as f:
            return extract_text(f.read(), source=path)
    raise ValueError(
        f"unsupported input format: {path!r} \u2014 supported: .docx, .txt "
        "(PDF is not supported natively; extract text first and pass .txt; "
        "this limitation is documented)")


STANDARD_ELEMENTS = [
    "Title", "Authors' names", "Authors' affiliations",
    "Corresponding author's address", "Abstract", "Text", "Acknowledgments",
    "CRediT Author Statement", "References", "Figure legends", "Tables",
    "Appendixes", "Figures", "other",
]


def standard_json(res: DocumentResult) -> dict:
    """Fixed-schema result: every STANDARD MANUSCRIPT ELEMENT is always
    present as a field; empty string means the paper does not contain it.
    Element fields hold primary content only; duplicated copies are listed
    under 'duplicates' (kept, never silently removed). 'Figures' (image
    objects) carry no text in DOCX; their text counterpart is
    'Figure legends'."""
    import os as _os
    import re as _re
    from .model import standard_element
    sim_rx = _re.compile(r"similarity=([\d.]+)")
    l1 = sorted([s for s in res.sections if s.level == 1],
                key=lambda s: s.start)
    buckets = {e: [] for e in STANDARD_ELEMENTS}
    spans = {e: [] for e in STANDARD_ELEMENTS}
    for s in l1:
        if s.flags.get("duplicate_of"):
            continue
        elem = standard_element(s.section_type)
        buckets[elem].append(s.text)
        spans[elem].append([s.start, s.end])
    fields = {e: "\n\n".join(buckets[e]) for e in STANDARD_ELEMENTS}
    duplicates = []
    for s in res.sections:
        if not s.flags.get("duplicate_of"):
            continue
        prim = next(x for x in res.sections if x.id == s.flags["duplicate_of"])
        m = sim_rx.search(next((e for e in s.evidence
                                if "similarity=" in e), ""))
        duplicates.append({
            "standard_element": standard_element(s.section_type),
            "section_type": s.section_type,
            "duplicate_heading": s.name.strip() or
                " ".join(s.text.split())[:60],
            "duplicate_span": [s.start, s.end],
            "primary_span": [prim.start, prim.end],
            "text_similarity": float(m.group(1)) if m else None,
            "duplicate_text": s.text,
        })
    details = [{
        "standard_element": standard_element(s.section_type),
        "section_type": s.section_type, "heading": s.name.strip(),
        "start_position": s.start, "end_position": s.end,
        "confidence": round(s.confidence, 2), "uncertain": s.uncertain,
        "is_duplicate": bool(s.flags.get("duplicate_of")),
    } for s in l1]
    return {"file": _os.path.basename(res.source),
            "note": ("every standard element is always present as a field; "
                     "empty string means the paper does not contain it. "
                     "Element fields hold primary content only; duplicated "
                     "copies are listed under 'duplicates'. All positions "
                     "are character offsets into 'source_text' (the "
                     "tracked-changes-resolved document text): "
                     "source_text[start:end] reproduces any span exactly, "
                     "and each element field is its 'element_spans' parts "
                     "joined by one blank line."),
            **fields, "duplicates": duplicates, "section_details": details,
            "element_spans": {e: spans[e] for e in STANDARD_ELEMENTS},
            "source_text": res.full_text}


def span_styles(res: DocumentResult, start: int, end: int) -> list:
    """Styling info for an arbitrary [start, end) span of res.full_text -
    the positions reported everywhere (JSON section_details / element_spans,
    CSV start_position / end_position) feed straight in.

    Returns one dict per document block the span touches: paragraph-level
    style (style id + human name, outline level, alignment, list/table
    role, exact block span) plus the formatting runs overlapping the span,
    each clipped to it with its own exact [start, end) offsets, so
    full_text[run.start:run.end] == run.text always holds.

    Styling captured by the reader today: bold, italic, all-caps runs;
    paragraph style; outline level; justification; list/table role.
    Font name/size/underline/superscript are NOT collected yet - extend
    docx_reader run collection if a style check needs them.
    """
    out = []
    for b in res.blocks:
        if b.end <= start or b.start >= end:
            continue
        runs = []
        pos = b.start
        for r in b.runs:
            r_start, r_end = pos, pos + len(r.text)
            pos = r_end
            if r_end <= start or r_start >= end:
                continue
            lo, hi = max(r_start, start), min(r_end, end)
            runs.append({
                "start": lo, "end": hi,
                "text": r.text[lo - r_start: hi - r_start],
                "bold": r.bold, "italic": r.italic, "all_caps": r.caps,
            })
        out.append({
            "block": b.idx, "block_span": [b.start, b.end],
            "style_id": b.style, "style_name": b.style_name,
            "outline_level": b.outline, "alignment": b.jc,
            "is_list": b.is_list, "is_table": b.is_table,
            "runs": runs,
        })
    return out


def extract_range(path: str, start_char: int, end_char: int,
                  mode: str = "accept") -> list:
    """Standalone styling lookup: give it a .docx path plus a start/end
    position from any of the outputs (sections_FLAT.csv start_position /
    end_position, JSON section_details / element_spans) and get the
    formatting runs covering exactly that span of the canonical text.

    Each entry: {"text", "start_char", "end_char", "style": {"font_name",
    "font_size" (points), "bold", "italic", "underline" (w:u value, e.g.
    "single", None = off), "strike", "color" (hex RRGGBB, None = auto),
    "highlight", "vert_align" ("superscript"/"subscript"/None),
    "all_caps"}}. Properties are resolved the way Word does: direct run
    formatting -> run style -> paragraph style -> default style ->
    document defaults (theme fonts resolved).

    Paragraph boundaries inside the span appear as {"text": "\n",
    "style": None, "paragraph_break": True} entries, so the concatenation
    of all "text" fields equals the requested slice of the canonical text
    exactly. A span with no run data (e.g. inside a table) yields an
    entry with "style": None. Adjacent runs with identical styling are
    merged. Positions are the extractor's own (tracked-changes-resolved
    text), NOT Word's character counts - always take them from this
    package's outputs.
    """
    res = extract(path, mode=mode)
    n = len(res.full_text)
    start = max(0, min(int(start_char), n))
    end = max(start, min(int(end_char), n))

    def style_of(r):
        sz = r.font_size
        if isinstance(sz, float) and sz.is_integer():
            sz = int(sz)
        return {"font_name": r.font_name, "font_size": sz,
                "bold": r.bold, "italic": r.italic,
                "underline": r.underline, "strike": r.strike,
                "color": r.color, "highlight": r.highlight,
                "vert_align": r.vert_align, "all_caps": r.caps}

    out = []
    cursor = start

    def emit(lo, hi, text, style, is_break=False):
        nonlocal cursor
        if hi <= lo:
            return
        prev = out[-1] if out else None
        if (prev is not None and not is_break
                and not prev.get("paragraph_break")
                and prev["style"] == style and prev["end_char"] == lo):
            prev["text"] += text
            prev["end_char"] = hi
        else:
            entry = {"text": text, "start_char": lo, "end_char": hi,
                     "style": style}
            if is_break:
                entry["paragraph_break"] = True
            out.append(entry)
        cursor = hi

    for b in res.blocks:
        if b.end <= start or b.start >= end:
            continue
        if cursor < min(b.start, end):
            lo, hi = cursor, min(b.start, end)
            emit(lo, hi, res.full_text[lo:hi], None, is_break=True)
        if b.runs:
            pos = b.start
            for r in b.runs:
                r_start, r_end = pos, pos + len(r.text)
                pos = r_end
                if r_end <= start or r_start >= end:
                    continue
                lo, hi = max(r_start, start), min(r_end, end)
                emit(lo, hi, r.text[lo - r_start: hi - r_start], style_of(r))
        else:
            lo, hi = max(b.start, start), min(b.end, end)
            emit(lo, hi, res.full_text[lo:hi], None)
    if cursor < end:
        emit(cursor, end, res.full_text[cursor:end], None, is_break=True)
    assert "".join(e["text"] for e in out) == res.full_text[start:end]
    return out
