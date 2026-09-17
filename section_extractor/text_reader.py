"""Plain-text adapter (for PDF-extracted text or .txt input).

Limitations are explicit: plain text carries no bold/style evidence, so
detection relies on line structure, casing, numbering and the lexicon. This
path is exercised by the adversarial suite and by a formatting-blind ablation
of the DOCX corpus; it has NOT been validated on real PDF extractions (none
were provided) and that is documented as a limitation.

Header/footer suppression: when form-feed page markers are present, lines
that repeat (normalized) on >=3 pages near page starts/ends are moved to an
excluded stream, as are pure page-number lines.
"""
from __future__ import annotations

import re

from .model import Block, Run
from . import lexicon as lx

_PAGENUM_RX = re.compile(r"^\s*(page\s+)?\d{1,4}(\s+of\s+\d{1,4})?\s*$", re.I)


def _norm_line(s: str) -> str:
    s = re.sub(r"\d+", "#", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def read_text(raw: str):
    warnings: list[str] = []
    excluded = {"headers_footers": [], "page_numbers": []}
    pages = raw.split("\f")
    multi_page = len(pages) >= 3

    # ---- repeated header/footer detection across pages ----
    banned: set = set()
    if multi_page:
        from collections import Counter
        edge_lines = Counter()
        for p in pages:
            lines = [l for l in p.splitlines() if l.strip()]
            for l in lines[:2] + lines[-2:]:
                # real running headers/footers are short lines
                if not _PAGENUM_RX.match(l) and len(l.strip()) <= 120:
                    edge_lines[_norm_line(l)] += 1
        for key, cnt in edge_lines.items():
            if cnt >= 3 and key:
                banned.add(key)

    blocks: list[Block] = []
    blank = 0
    page_break_pending = False

    def add_block(text: str):
        nonlocal blank, page_break_pending
        text = text.rstrip()
        if not text.strip():
            blank += 1
            return
        b = Block(idx=len(blocks), text=text,
                  runs=[Run(text=text)], blank_before=blank,
                  page_break_before=page_break_pending)
        blocks.append(b)
        blank = 0
        page_break_pending = False

    for pi, page in enumerate(pages):
        if pi > 0:
            page_break_pending = True
        para_lines: list[str] = []

        def flush_para():
            nonlocal para_lines
            if not para_lines:
                return
            # peel leading standalone heading-ish or caption lines off a
            # wrapped block
            while para_lines:
                first = para_lines[0].strip()
                if len(para_lines) > 1 and (
                        (len(first) <= 70 and
                         (lx.match(first) or
                          (first.isupper() and
                           sum(c.isalpha() for c in first) >= 4))) or
                        lx.CAPTION_RX.match(first)):
                    add_block(first)
                    para_lines = para_lines[1:]
                else:
                    break
            if para_lines:
                add_block(" ".join(l.strip() for l in para_lines))
            para_lines = []

        for line in page.splitlines():
            if not line.strip():
                flush_para()
                blank += 1
                continue
            if _PAGENUM_RX.match(line):
                excluded["page_numbers"].append(line.strip())
                continue
            if multi_page and _norm_line(line) in banned:
                excluded["headers_footers"].append(line.strip())
                continue
            para_lines.append(line)
        flush_para()

    pos = 0
    for b in blocks:
        b.start = pos
        b.end = pos + len(b.text)
        pos = b.end + 1
        b.featurize()
    full_text = "\n".join(b.text for b in blocks)
    if excluded["headers_footers"]:
        warnings.append(
            f"{len(excluded['headers_footers'])} repeated header/footer "
            "line(s) excluded from body text (kept in excluded_streams)")
    return blocks, full_text, excluded, warnings
