"""Core data model for section extraction.

Design principles:
- The canonical extracted text is preserved verbatim; every block and section
  carries [start, end) character offsets into it, so all boundaries are
  traceable back to the source extraction.
- Sections form a tree (parent_id); leaf sections tile the document text with
  no gaps and no overlaps. Unclassifiable text becomes an explicit
  ``unlabeled`` section instead of being silently attached or invented.
- Confidence is a heuristic ordinal score in [0, 1] derived from accumulated
  evidence. It is NOT a calibrated probability and is documented as such.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Run:
    """A formatting-homogeneous piece of text inside a block."""
    text: str
    bold: bool = False
    italic: bool = False
    caps: bool = False  # w:caps display-uppercase formatting
    # rich styling (v0.5, for style checks): resolved through direct rPr ->
    # run style -> paragraph style -> default style -> docDefaults; None
    # means the property is not set anywhere in that chain
    font_name: Optional[str] = None
    font_size: Optional[float] = None   # points
    underline: Optional[str] = None     # w:u val, e.g. "single"; None = off
    strike: bool = False
    color: Optional[str] = None         # hex RRGGBB, None for auto/unset
    highlight: Optional[str] = None     # w:highlight val, e.g. "yellow"
    vert_align: Optional[str] = None    # "superscript" / "subscript"


@dataclass
class Block:
    """One paragraph-level unit of the extracted document."""
    idx: int                      # 0-based index over non-empty body blocks
    text: str                     # verbatim extracted text of the block
    runs: list = field(default_factory=list)
    style: str = ""               # style id, e.g. "Heading1", "Reference"
    style_name: str = ""          # human style name from styles.xml
    outline: Optional[int] = None  # outline level (0 = Heading 1)
    jc: str = ""                  # justification: left/center/right/both
    blank_before: int = 0         # count of empty paragraphs before this block
    page_break_before: bool = False
    is_table: bool = False
    is_list: bool = False
    merged_from: int = 1          # number of source paragraphs merged into this
    src: str = "body"
    start: int = -1               # char offset into canonical full_text
    end: int = -1

    # --- derived features (filled by featurize) ---
    stripped: str = ""
    n_words: int = 0
    n_letters: int = 0
    caps_ratio: float = 0.0       # uppercase letters / letters (display case)
    bold_ratio: float = 0.0       # bold non-space chars / non-space chars
    italic_ratio: float = 0.0
    style_heading_level: Optional[int] = None  # from style/outline, 1-based

    def featurize(self) -> None:
        self.stripped = self.text.strip()
        self.n_words = len(self.stripped.split())
        disp = []
        nonspace = 0
        bold_n = 0
        ital_n = 0
        for r in self.runs:
            t = r.text.upper() if r.caps else r.text
            disp.append(t)
            for ch in r.text:
                if not ch.isspace():
                    nonspace += 1
                    if r.bold:
                        bold_n += 1
                    if r.italic:
                        ital_n += 1
        display = "".join(disp) if disp else self.text
        letters = [c for c in display if c.isalpha()]
        self.n_letters = len(letters)
        self.caps_ratio = (
            sum(1 for c in letters if c.isupper()) / len(letters) if letters else 0.0
        )
        self.bold_ratio = bold_n / nonspace if nonspace else 0.0
        self.italic_ratio = ital_n / nonspace if nonspace else 0.0
        lvl = None
        s = (self.style or "").lower().replace(" ", "")
        if s.startswith("heading") and s[7:8].isdigit():
            lvl = int(s[7:8])
        elif self.outline is not None:
            lvl = self.outline + 1
        self.style_heading_level = lvl


@dataclass
class Section:
    """A detected section with traceable boundaries and evidence."""
    id: int
    section_type: str             # canonical type, e.g. "methods"
    name: str                     # literal heading/label text ('' if none)
    level: int                    # 1 = top-level, 2/3 = nested
    start_block: int
    end_block: int                # inclusive
    start: int                    # char offset into full_text
    end: int                      # exclusive
    text: str
    confidence: float
    uncertain: bool
    evidence: list = field(default_factory=list)
    parent_id: Optional[int] = None
    flags: dict = field(default_factory=dict)  # e.g. {"duplicate_of": 3}

    def to_dict(self, include_text: bool = True) -> dict:
        d = {
            "id": self.id,
            "parent_id": self.parent_id,
            "section_type": self.section_type,
            "standard_element": standard_element(self.section_type),
            "name": self.name,
            "level": self.level,
            "start_position": self.start,
            "end_position": self.end,
            "start_block": self.start_block,
            "end_block": self.end_block,
            "confidence": round(self.confidence, 3),
            "uncertain": self.uncertain,
            "evidence": list(self.evidence),
            "flags": dict(self.flags),
        }
        if include_text:
            d["extracted_text"] = self.text
        return d


@dataclass
class DocumentResult:
    source: str
    mode: str                     # "accept" | "reject" | "text"
    full_text: str
    blocks: list
    sections: list
    excluded_streams: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def to_dict(self, include_text: bool = True) -> dict:
        return {
            "source": self.source,
            "mode": self.mode,
            "n_chars": len(self.full_text),
            "n_blocks": len(self.blocks),
            "sections": [s.to_dict(include_text) for s in self.sections],
            "warnings": list(self.warnings),
            "excluded_streams": {
                k: v for k, v in self.excluded_streams.items() if v
            },
            "confidence_note": (
                "confidence is a heuristic ordinal score derived from listed "
                "evidence; it is not a calibrated probability"
            ),
        }


# ---------------------------------------------------------------------------
# Rollup to the journal's STANDARD MANUSCRIPT ELEMENTS list (style guide).
# Every fine-grained section_type maps to one standard element; anything not
# on the journal's list is flagged "other" per editorial requirement.
# ---------------------------------------------------------------------------
_STANDARD_ELEMENT_MAP = {
    "title": "Title",
    "authors": "Authors' names",
    "authors_marker": "Authors' names",
    "affiliations": "Authors' affiliations",
    "correspondence": "Corresponding author's address",
    "abstract": "Abstract",
    "introduction": "Text", "objectives": "Text", "methods": "Text",
    "results": "Text", "results_and_discussion": "Text",
    "discussion": "Text", "limitations": "Text", "conclusions": "Text",
    "implications": "Text", "recommendations": "Text",
    "future_work": "Text", "related_work": "Text",
    "study_sample": "Text", "measures": "Text",
    "statistical_analysis": "Text", "framework": "Text",
    "procedures": "Text", "other_heading": "Text",
    "acknowledgments": "Acknowledgments", "funding": "Acknowledgments",
    "declaration_of_interest": "Acknowledgments",
    "disclaimer": "Acknowledgments", "presented_at": "Acknowledgments",
    "credit_statement": "CRediT Author Statement",
    "references": "References",
    "figure_legends": "Figure legends",
    "tables_section": "Tables",
    "appendix": "Appendixes", "supplementary": "Appendixes",
}


def standard_element(section_type: str) -> str:
    """Map a fine-grained type to the journal's standard element, or 'other'.

    Abstract subsections (abstract_introduction, ...) roll up to Abstract.
    Types outside the journal's standard list (keywords, highlights,
    running head, ORCID, word counts, data availability, ethics, unlabeled
    spans, ...) are flagged 'other' per the editorial requirement. Note:
    keywords/highlights are FOCUS journal elements but are not on the
    STANDARD MANUSCRIPT ELEMENTS list, so they roll to 'other' here.
    """
    if section_type.startswith("abstract_"):
        return "Abstract"
    return _STANDARD_ELEMENT_MAP.get(section_type, "other")
