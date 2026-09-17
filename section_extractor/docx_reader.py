"""DOCX (OOXML) reader.

Reads word/document.xml directly (python-docx is NOT used for text extraction
because its ``paragraph.text`` does not include runs inside tracked-change
<w:ins> elements and cannot resolve tracked paragraph-mark deletions).

Tracked-changes semantics implemented:
- mode="accept" (default): text inside <w:ins> kept, <w:del>/<w:delText>
  dropped, <w:moveTo> kept, <w:moveFrom> dropped. A paragraph whose paragraph
  MARK is deleted (<w:pPr><w:rPr><w:del/>) merges directly with the following
  paragraph (Word joins them with no separator).
- mode="reject": the inverse.

Excluded streams (headers, footers, footnotes, endnotes, comments) are
extracted separately with provenance and never mixed into body text.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import replace
from lxml import etree

from .model import Block, Run

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def _q(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _local(elem) -> str:
    return etree.QName(elem).localname


def _bool_attr(elem) -> bool:
    """OOXML toggle property: absent val means on; '0'/'false'/'none' off."""
    if elem is None:
        return False
    val = elem.get(_q("val"))
    return val is None or val.lower() not in ("0", "false", "none")


_RICH_KEYS = ("font", "size", "u", "strike", "color", "highlight",
              "valign")


def _rpr_rich(rpr, theme: dict | None = None) -> dict:
    """Rich run properties out of one <w:rPr> (style checks, v0.5).
    None = not set at this level. Font resolves w:ascii -> w:hAnsi ->
    theme reference."""
    out = {k: None for k in _RICH_KEYS}
    if rpr is None:
        return out
    rf = rpr.find(f"{_q('rFonts')}")
    if rf is not None:
        f = rf.get(_q("ascii")) or rf.get(_q("hAnsi"))
        if not f and theme:
            ref = rf.get(_q("asciiTheme")) or rf.get(_q("hAnsiTheme")) or ""
            f = theme.get("minor" if ref.startswith("minor") else
                          "major" if ref.startswith("major") else "")
        out["font"] = f or None
    sz = rpr.find(f"{_q('sz')}")
    if sz is not None:
        try:
            out["size"] = int(sz.get(_q("val"))) / 2.0
        except (TypeError, ValueError):
            pass
    u = rpr.find(f"{_q('u')}")
    if u is not None:
        v = u.get(_q("val")) or "single"
        out["u"] = None if v == "none" else v
    st = rpr.find(f"{_q('strike')}")
    if st is not None:
        out["strike"] = _bool_attr(st)
    col = rpr.find(f"{_q('color')}")
    if col is not None:
        v = col.get(_q("val"))
        out["color"] = None if not v or v == "auto" else v
    hl = rpr.find(f"{_q('highlight')}")
    if hl is not None:
        v = hl.get(_q("val"))
        out["highlight"] = None if not v or v == "none" else v
    va = rpr.find(f"{_q('vertAlign')}")
    if va is not None:
        v = va.get(_q("val"))
        out["valign"] = None if not v or v == "baseline" else v
    return out


class _Styles:
    """Minimal style-sheet resolution: bold/italic/caps + outline level,
    plus (v0.5) rich run properties with docDefaults / default-style
    fallback for style checks."""

    def __init__(self, styles_xml: bytes | None, theme: dict | None = None):
        self.by_id: dict[str, dict] = {}
        self.theme = theme or {}
        self.defaults = {k: None for k in _RICH_KEYS}
        self.default_para = ""
        if not styles_xml:
            return
        try:
            root = etree.fromstring(styles_xml)
        except etree.XMLSyntaxError:
            return
        dd = root.find(f"{_q('docDefaults')}")
        if dd is not None:
            rprd = dd.find(f"{_q('rPrDefault')}")
            if rprd is not None:
                self.defaults = _rpr_rich(rprd.find(f"{_q('rPr')}"),
                                          self.theme)
        for st in root.findall(f"{_q('style')}"):
            sid = st.get(_q("styleId")) or ""
            if st.get(_q("default")) == "1" and \
                    st.get(_q("type")) == "paragraph":
                self.default_para = sid
            name_el = st.find(f"{_q('name')}")
            based_el = st.find(f"{_q('basedOn')}")
            rpr = st.find(f"{_q('rPr')}")
            ppr = st.find(f"{_q('pPr')}")
            info = {
                "name": name_el.get(_q("val")) if name_el is not None else sid,
                "basedOn": based_el.get(_q("val")) if based_el is not None else None,
                "bold": None, "italic": None, "caps": None, "outline": None,
            }
            info.update(_rpr_rich(rpr, self.theme))
            if rpr is not None:
                b = rpr.find(f"{_q('b')}")
                i = rpr.find(f"{_q('i')}")
                c = rpr.find(f"{_q('caps')}")
                if b is not None:
                    info["bold"] = _bool_attr(b)
                if i is not None:
                    info["italic"] = _bool_attr(i)
                if c is not None:
                    info["caps"] = _bool_attr(c)
            if ppr is not None:
                ol = ppr.find(f"{_q('outlineLvl')}")
                if ol is not None:
                    try:
                        info["outline"] = int(ol.get(_q("val")))
                    except (TypeError, ValueError):
                        pass
            self.by_id[sid] = info

    def _resolve(self, sid: str, key: str):
        seen = set()
        while sid and sid not in seen:
            seen.add(sid)
            info = self.by_id.get(sid)
            if info is None:
                return None
            if info[key] is not None:
                return info[key]
            sid = info["basedOn"]
        return None

    def rich(self, sid, key): return self._resolve(sid, key)

    def bold(self, sid): return self._resolve(sid, "bold")
    def italic(self, sid): return self._resolve(sid, "italic")
    def caps(self, sid): return self._resolve(sid, "caps")
    def outline(self, sid): return self._resolve(sid, "outline")
    def name(self, sid):
        info = self.by_id.get(sid)
        return info["name"] if info else sid


# Containers that are transparent for run collection.
_TRANSPARENT = {"hyperlink", "smartTag", "fldSimple", "sdtContent", "dir",
                "bdo", "customXml"}
_SKIP = {"pPr", "bookmarkStart", "bookmarkEnd", "proofErr",
         "commentRangeStart", "commentRangeEnd", "commentReference",
         "moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart",
         "moveToRangeEnd", "permStart", "permEnd", "ins_placeholder",
         "del_placeholder", "oMath", "oMathPara"}


class DocxReader:
    def __init__(self, path: str, mode: str = "accept"):
        assert mode in ("accept", "reject")
        self.path = path
        self.mode = mode
        self.warnings: list[str] = []

    # ------------------------------------------------------------------ runs
    def _run_props(self, r, para_style: str) -> tuple[bool, bool, bool]:
        rpr = r.find(f"{_q('rPr')}")
        bold = italic = caps = None
        rstyle = None
        if rpr is not None:
            b = rpr.find(f"{_q('b')}")
            i = rpr.find(f"{_q('i')}")
            c = rpr.find(f"{_q('caps')}")
            rs = rpr.find(f"{_q('rStyle')}")
            if b is not None:
                bold = _bool_attr(b)
            if i is not None:
                italic = _bool_attr(i)
            if c is not None:
                caps = _bool_attr(c)
            if rs is not None:
                rstyle = rs.get(_q("val"))
        if bold is None and rstyle:
            bold = self.styles.bold(rstyle)
        if bold is None and para_style:
            bold = self.styles.bold(para_style)
        if italic is None and rstyle:
            italic = self.styles.italic(rstyle)
        if italic is None and para_style:
            italic = self.styles.italic(para_style)
        if caps is None and rstyle:
            caps = self.styles.caps(rstyle)
        if caps is None and para_style:
            caps = self.styles.caps(para_style)
        return bool(bold), bool(italic), bool(caps)

    def _run_rich(self, r, para_style: str) -> dict:
        """Resolve the rich styling of one <w:r> for style checks:
        direct rPr -> run style chain -> paragraph style chain (falling
        back to the document default paragraph style) -> docDefaults."""
        rpr = r.find(f"{_q('rPr')}")
        direct = _rpr_rich(rpr, self.styles.theme)
        rstyle = None
        if rpr is not None:
            rs = rpr.find(f"{_q('rStyle')}")
            if rs is not None:
                rstyle = rs.get(_q("val"))
        pstyle = para_style or self.styles.default_para
        out = {}
        for k in _RICH_KEYS:
            v = direct[k]
            if v is None and rstyle:
                v = self.styles.rich(rstyle, k)
            if v is None and pstyle:
                v = self.styles.rich(pstyle, k)
            if v is None:
                v = self.styles.defaults[k]
            out[k] = v
        return out

    def _run_text(self, r, in_del: bool) -> tuple[str, bool]:
        """Extract text of one <w:r>. Returns (text, saw_page_break)."""
        parts = []
        page_break = False
        for ch in r:
            tag = _local(ch)
            if tag == "t":
                parts.append(ch.text or "")
            elif tag == "delText":
                if in_del and self.mode == "reject":
                    parts.append(ch.text or "")
                # in accept mode deleted text is dropped
            elif tag == "instrText" or tag == "delInstrText":
                continue  # field instruction codes are not document text
            elif tag == "tab":
                parts.append("\t")
            elif tag in ("br", "cr"):
                if ch.get(_q("type")) == "page":
                    page_break = True
                parts.append("\n")
            elif tag == "noBreakHyphen":
                parts.append("-")
            elif tag == "softHyphen":
                continue
            elif tag == "lastRenderedPageBreak":
                page_break = True
            elif tag in ("sym", "drawing", "pict", "object",
                         "footnoteReference", "endnoteReference",
                         "footnoteRef", "endnoteRef", "fldChar",
                         "commentReference", "ruby"):
                continue
        return "".join(parts), page_break

    def _collect_runs(self, elem, para_style: str, in_ins: bool, in_del: bool,
                      out: list, state: dict) -> None:
        for ch in elem:
            tag = _local(ch)
            if tag == "r":
                if self.mode == "accept" and in_del:
                    # still scan for page breaks in deleted content? no.
                    continue
                if self.mode == "reject" and in_ins:
                    continue
                text, pb = self._run_text(ch, in_del)
                if pb:
                    state["page_break"] = True
                if text:
                    b, i, c = self._run_props(ch, para_style)
                    rich = self._run_rich(ch, para_style)
                    out.append(Run(
                        text=text, bold=b, italic=i, caps=c,
                        font_name=rich["font"], font_size=rich["size"],
                        underline=rich["u"], strike=bool(rich["strike"]),
                        color=rich["color"], highlight=rich["highlight"],
                        vert_align=rich["valign"]))
            elif tag == "ins" or tag == "moveTo":
                self._collect_runs(ch, para_style, True, in_del, out, state)
            elif tag == "del" or tag == "moveFrom":
                self._collect_runs(ch, para_style, in_ins, True, out, state)
            elif tag == "sdt":
                content = ch.find(f"{_q('sdtContent')}")
                if content is not None:
                    self._collect_runs(content, para_style, in_ins, in_del,
                                       out, state)
            elif tag in _TRANSPARENT:
                self._collect_runs(ch, para_style, in_ins, in_del, out, state)
            elif tag in _SKIP:
                continue
            # anything else: ignore silently but note once
            elif tag not in ("sectPr",):
                key = f"unhandled:{tag}"
                if key not in state["seen_unhandled"]:
                    state["seen_unhandled"].add(key)

    # ------------------------------------------------------------ paragraphs
    def _para(self, p, state: dict) -> dict:
        """Extract one paragraph into a dict (not yet a Block)."""
        ppr = p.find(f"{_q('pPr')}")
        style = ""
        jc = ""
        outline = None
        page_break_before = False
        is_list = False
        mark_deleted = False
        mark_inserted = False
        if ppr is not None:
            ps = ppr.find(f"{_q('pStyle')}")
            if ps is not None:
                style = ps.get(_q("val")) or ""
            jc_el = ppr.find(f"{_q('jc')}")
            if jc_el is not None:
                jc = jc_el.get(_q("val")) or ""
            ol = ppr.find(f"{_q('outlineLvl')}")
            if ol is not None:
                try:
                    outline = int(ol.get(_q("val")))
                except (TypeError, ValueError):
                    pass
            if ppr.find(f"{_q('pageBreakBefore')}") is not None:
                page_break_before = True
            if ppr.find(f"{_q('numPr')}") is not None:
                is_list = True
            mrpr = ppr.find(f"{_q('rPr')}")
            if mrpr is not None:
                if mrpr.find(f"{_q('del')}") is not None:
                    mark_deleted = True
                if mrpr.find(f"{_q('ins')}") is not None:
                    mark_inserted = True
        if outline is None and style:
            outline = self.styles.outline(style)
        runs: list[Run] = []
        pstate = {"page_break": False, "seen_unhandled": state["seen_unhandled"]}
        self._collect_runs(p, style, False, False, runs, pstate)
        # merge-with-next decision by mode
        merge_next = (mark_deleted if self.mode == "accept" else mark_inserted)
        return {
            "runs": runs, "style": style, "jc": jc, "outline": outline,
            "page_break_before": page_break_before or pstate["page_break"],
            "is_list": is_list, "merge_next": merge_next,
        }

    def _table_text(self, tbl, state: dict) -> str:
        rows = []
        for tr in tbl.iter(f"{_q('tr')}"):
            cells = []
            for tc in tr.findall(f"{_q('tc')}"):
                cell_paras = []
                for p in tc.iter(f"{_q('p')}"):
                    d = self._para(p, state)
                    t = "".join(r.text for r in d["runs"])
                    if t.strip():
                        cell_paras.append(t.strip())
                cells.append(" ".join(cell_paras))
            rows.append("\t".join(cells))
        return "\n".join(rows)

    # ------------------------------------------------------------------ body
    def _iter_body_items(self, container):
        for ch in container:
            tag = _local(ch)
            if tag in ("p", "tbl"):
                yield ch
            elif tag == "sdt":
                content = ch.find(f"{_q('sdtContent')}")
                if content is not None:
                    yield from self._iter_body_items(content)
            # sectPr / bookmarks etc: skip

    def read(self):
        with zipfile.ZipFile(self.path) as z:
            names = set(z.namelist())
            doc_xml = z.read("word/document.xml")
            styles_xml = z.read("word/styles.xml") if "word/styles.xml" in names else None
            theme_xml = z.read("word/theme/theme1.xml") \
                if "word/theme/theme1.xml" in names else None
            excluded: dict[str, list] = {"headers": [], "footers": [],
                                         "footnotes": [], "endnotes": [],
                                         "comments": []}
            for n in sorted(names):
                m = re.match(r"word/(header|footer)(\d+)\.xml$", n)
                if m:
                    txt = self._flat_text(z.read(n))
                    if txt.strip():
                        excluded[m.group(1) + "s"].append(
                            {"part": n, "text": txt.strip()})
            for part, key in (("word/footnotes.xml", "footnotes"),
                              ("word/endnotes.xml", "endnotes"),
                              ("word/comments.xml", "comments")):
                if part in names:
                    txt = self._flat_text(z.read(part))
                    if txt.strip():
                        excluded[key].append({"part": part, "text": txt.strip()})
        theme = {}
        if theme_xml:
            try:
                troot = etree.fromstring(theme_xml)
                A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
                for kind in ("minor", "major"):
                    el = troot.find(f".//{A}{kind}Font/{A}latin")
                    if el is not None and el.get("typeface"):
                        theme[kind] = el.get("typeface")
            except etree.XMLSyntaxError:
                pass
        self.styles = _Styles(styles_xml, theme)
        root = etree.fromstring(doc_xml)
        body = root.find(f"{_q('body')}")
        if body is None:
            raise ValueError("no w:body in document.xml")

        state = {"seen_unhandled": set()}
        blocks: list[Block] = []
        blank_count = 0
        page_break_pending = False
        pending_runs: list[Run] = []
        pending_props: dict | None = None
        pending_merged = 0

        def split_lines(runs: list[Run]) -> list[list[Run]]:
            """Split runs at '\n' (soft line breaks) into visual lines."""
            lines: list[list[Run]] = [[]]
            for r in runs:
                parts = r.text.split("\n")
                for k, part in enumerate(parts):
                    if k > 0:
                        lines.append([])
                    if part:
                        lines[-1].append(replace(r, text=part))
            return lines

        def flush(props: dict, runs: list[Run], merged: int):
            nonlocal blank_count, page_break_pending
            text = "".join(r.text for r in runs)
            if not text.strip():
                blank_count += 1
                if props["page_break_before"]:
                    page_break_pending = True
                return
            # a soft line break (w:br) separates visually distinct lines --
            # treat each as its own block (headings often share a paragraph
            # with following text via soft breaks)
            first = True
            for line_runs in split_lines(runs):
                ltext = "".join(r.text for r in line_runs)
                if not ltext.strip():
                    blank_count += 1
                    continue
                b = Block(
                    idx=len(blocks), text=ltext, runs=line_runs,
                    style=props["style"],
                    style_name=self.styles.name(props["style"])
                    if props["style"] else "",
                    outline=props["outline"], jc=props["jc"],
                    blank_before=blank_count,
                    page_break_before=(props["page_break_before"] or
                                       page_break_pending) if first else False,
                    is_table=False, is_list=props["is_list"],
                    merged_from=merged,
                )
                blocks.append(b)
                blank_count = 0
                page_break_pending = False
                first = False

        for item in self._iter_body_items(body):
            if _local(item) == "tbl":
                # a pending merge cannot cross a table; flush it first
                if pending_props is not None:
                    flush(pending_props, pending_runs, pending_merged)
                    pending_runs, pending_props, pending_merged = [], None, 0
                ttext = self._table_text(item, state)
                if ttext.strip():
                    b = Block(idx=len(blocks), text=ttext, runs=[],
                              is_table=True, blank_before=blank_count,
                              page_break_before=page_break_pending)
                    blocks.append(b)
                    blank_count = 0
                    page_break_pending = False
                continue
            d = self._para(item, state)
            if pending_props is not None:
                # previous paragraph's mark was removed: join directly
                pending_runs.extend(d["runs"])
                pending_merged += 1
                pending_props["page_break_before"] = (
                    pending_props["page_break_before"] or d["page_break_before"])
                if d["merge_next"]:
                    continue
                flush(pending_props, pending_runs, pending_merged)
                pending_runs, pending_props, pending_merged = [], None, 0
            elif d["merge_next"]:
                pending_runs = list(d["runs"])
                pending_props = d
                pending_merged = 1
            else:
                flush(d, d["runs"], 1)
        if pending_props is not None:
            flush(pending_props, pending_runs, pending_merged)

        if state["seen_unhandled"]:
            self.warnings.append(
                "unhandled OOXML elements ignored: "
                + ", ".join(sorted(state["seen_unhandled"])))

        # char spans into canonical text
        pos = 0
        for b in blocks:
            b.start = pos
            b.end = pos + len(b.text)
            pos = b.end + 1  # '\n' separator
            b.featurize()
        full_text = "\n".join(b.text for b in blocks)
        return blocks, full_text, excluded, self.warnings

    def _flat_text(self, xml: bytes) -> str:
        try:
            root = etree.fromstring(xml)
        except etree.XMLSyntaxError:
            return ""
        parts = []
        for t in root.iter(f"{_q('t')}"):
            anc = {_local(a) for a in t.iterancestors()}
            if "del" in anc and self.mode == "accept":
                continue
            parts.append(t.text or "")
        return " ".join(p for p in parts if p)


def read_docx(path: str, mode: str = "accept"):
    return DocxReader(path, mode=mode).read()
