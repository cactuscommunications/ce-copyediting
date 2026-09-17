"""Section assembly: contextual disambiguation of heading candidates into a
section tree with confidence, evidence, duplicate flags and full coverage.

Key contextual rules (each grounded in observed failure modes, see report):
- Structured-abstract label clusters ("Introduction:", "Methods", ...) are
  recognized and kept INSIDE the abstract instead of being mistaken for body
  sections. Evidence routes: an explicit Abstract heading (labels after it are
  abstract subsections, including formatting-free colon labels), or >=2
  IMRaD-family labels that each re-appear later with strictly stronger
  formatting (the real body headings).
- Keywords/Highlights sections are bounded by their own content extent
  (bullets / short lines), so unheaded body text after them is NOT swallowed;
  it becomes an explicit "unlabeled" section instead.
- Front matter is classified over all pre-body blocks not claimed by other
  sections \u2014 submission title pages may appear AFTER highlights.
- The references section is anchored by a references heading followed by
  reference-shaped content; its END is computed from where reference-shaped
  content stops, so trailing figure legends / tables are not swallowed.
- Nothing is ever deleted: duplicates are flagged, not removed; unclassifiable
  text becomes explicit "unlabeled"/"front_other" sections; leaf sections tile
  the document.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Optional

from . import lexicon as lx
from .headings import Candidate, detect_candidates, screen_roles, \
    title_case_ratio
from .model import Block, Section

BODY_SET = lx.BODY_TYPES
BACK_SET = lx.BACK_MATTER_TYPES
TAIL_SET = lx.TAIL_TYPES

_norm_ws = re.compile(r"\s+")

TITLE_LABEL_RX = re.compile(
    r"^\s*(full\s+|manuscript\s+|article\s+|paper\s+)?title\s*[:.]\s*(\S.{8,})",
    re.I,
)

# formatting-free abstract labels ("Introduction:" / "Introduction" alone)
_ABS_LABEL_WORDS = {
    "introduction": "introduction", "background": "introduction",
    "rationale": "objectives",
    "objective": "objectives", "objectives": "objectives",
    "purpose": "objectives", "aim": "objectives", "aims": "objectives",
    "method": "methods", "methods": "methods",
    "materials and methods": "methods",
    "result": "results", "results": "results", "findings": "results",
    "discussion": "discussion",
    "conclusion": "conclusions", "conclusions": "conclusions",
    "limitations": "limitations",
}
_ABS_WORDS_RX = (
    r"(introduction|background|rationale|objectives?|purpose|aims?|methods?|"
    r"materials and methods|results?|findings|discussion|conclusions?|"
    r"limitations)"
)
_ABS_LABEL_RX = re.compile(rf"^\s*{_ABS_WORDS_RX}\s*(:|$)", re.I)
# glued/period/space variants seen in submissions, ONLY matched in the
# constrained context of abstract-label scanning: "IntroductionThis study",
# "Results. On average", "Methods A questionnaire", "Rationale If and what"
_ABS_LABEL_GLUED_RX = re.compile(
    rf"^\s*{_ABS_WORDS_RX}(?=[A-Z]|[.:\u2013\u2014-]\s|\s+[A-Z])", re.I,
)


def _norm_for_sim(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[-\u2013\u2014\u2022\u2022\t]", " ", s)
    return _norm_ws.sub(" ", s).strip()


@dataclass
class Mark:
    idx: int
    section_type: str
    name: str
    level: int
    conf: float
    evidence: list = field(default_factory=list)
    flags: dict = field(default_factory=dict)
    uncertain: bool = False


class Assembler:
    def __init__(self, blocks: list[Block], full_text: str,
                 text_mode: bool = False):
        self.blocks = blocks
        self.full_text = full_text
        self.text_mode = text_mode
        self.roles = screen_roles(blocks)
        self.cands = detect_candidates(blocks, self.roles, text_mode=text_mode)
        self.cand_by_idx: dict[int, Candidate] = {}
        for c in self.cands:
            self.cand_by_idx.setdefault(c.block_idx, c)
        self.warnings: list[str] = []
        self.marks: list[Mark] = []
        self.extents: list[tuple] = []   # (start, end) content extents

    # ------------------------------------------------------------------ util
    def _add_mark(self, m: Mark):
        # one mark per (block, level); a parent (level 1) and a child
        # (level 2) may legitimately start on the same block
        for existing in self.marks:
            if existing.idx == m.idx and existing.level == m.level:
                if m.conf > existing.conf:
                    existing.section_type = m.section_type
                    existing.name = m.name
                    existing.evidence = m.evidence + existing.evidence
                    existing.conf = m.conf
                    existing.flags.update(m.flags)
                return
        self.marks.append(m)

    def _add_mark_exists(self, idx: int) -> bool:
        return any(m.idx == idx for m in self.marks)

    def _is_ref_entry(self, b: Block) -> bool:
        if "reference" in (b.style or "").lower() or \
                "bibliograph" in (b.style or "").lower():
            return True
        s = b.stripped
        if lx.REF_ENTRY_RX.match(s) and (
                lx.YEAR_RX.search(s) or lx.DOI_URL_RX.search(s) or len(s) > 80):
            return True
        # bare-number entries: "9 Deng S, Hager K, ..." (no dot)
        if re.match(r"^\d{1,3}\s+[A-Z]", s) and (
                lx.YEAR_RX.search(s) or lx.DOI_URL_RX.search(s) or
                len(s) > 80):
            return True
        if lx.DOI_URL_RX.search(s) and len(s) <= 200 and not b.is_table:
            return True
        return False

    # ----------------------------------------------------------- references
    def find_references(self):
        ref_cands = [c for c in self.cands if c.section_type == "references"]
        best = None
        for c in reversed(ref_cands):
            content = sum(
                1 for b in self.blocks[c.block_idx + 1: c.block_idx + 8]
                if self._is_ref_entry(b))
            if content >= 2:
                best = (c, content)
                break
        if best is None and ref_cands:
            best = (ref_cands[-1], 0)
        if best is None:
            run_start, run_len = None, 0
            i, n = 0, len(self.blocks)
            while i < n:
                if self._is_ref_entry(self.blocks[i]) and \
                        not self.blocks[i].is_table:
                    j = i
                    while j < n and self._is_ref_entry(self.blocks[j]):
                        j += 1
                    if j - i > run_len:
                        run_start, run_len = i, j - i
                    i = j
                else:
                    i += 1
            if run_start is not None and run_len >= 5 and \
                    run_start > len(self.blocks) * 0.4:
                m = Mark(run_start, "references", "", 1, 0.6,
                         ["no references heading found; "
                          f"{run_len} consecutive reference-shaped blocks "
                          f"start at block {run_start}"], uncertain=True)
                return run_start, self._refs_end(run_start - 1), m
            return None, None, None
        c, content = best
        ev = list(c.signals)
        if content:
            ev.append(f"followed by {content} reference-shaped blocks "
                      "(numbered entries / Reference style / DOI-URL)")
            conf, unc = min(0.95, c.conf + 0.05), False
        else:
            ev.append("references heading with no reference-shaped content "
                      "after it")
            conf, unc = min(c.conf, 0.6), True
            self.warnings.append(
                f"references heading at block {c.block_idx} has no "
                "reference-shaped content after it")
        m = Mark(c.block_idx, "references", c.name, 1, conf, ev, uncertain=unc)
        return c.block_idx, self._refs_end(c.block_idx), m

    def _refs_end(self, start_idx: int) -> int:
        n = len(self.blocks)
        last = start_idx
        i = start_idx + 1
        gap = 0
        while i < n:
            b = self.blocks[i]
            cand = self.cand_by_idx.get(i)
            if cand and cand.section_type in (TAIL_SET | {"abbreviations"}):
                break
            if self.roles[i] == "caption" or b.is_table:
                break
            if self._is_ref_entry(b):
                last = i
                gap = 0
            elif self.roles[i] in ("affiliation", "contact", "byline"):
                # stray duplicated front-matter junk inside the reference
                # region: tolerate without ending the section
                gap += 1
                if gap > 2:
                    break
            else:
                gap += 1
                if gap > 1:
                    break
            i += 1
        return last

    # ------------------------------------------------------------- abstract
    def _scan_label_blocks(self, start: int, limit: int,
                           max_span: int = 40):
        """Scan blocks for formatting-free structured-abstract labels
        (colon, standalone, glued or spaced forms). Returns
        (found=[(idx, family)...], content_end) where content_end is the last
        block of trailing wrapped continuation prose after the final label.
        A run ends at bullets, roles, candidates or unrelated short lines.
        """
        i = start
        content_allow = 0
        found: list[tuple] = []
        seen: set = set()
        last_content = start - 1
        while i < min(limit, start + max_span, len(self.blocks)):
            if i in self.cand_by_idx and found:
                break
            if self.roles[i] not in (None,):
                break
            s = self.blocks[i].stripped
            if s[:1] in "-\u2022\u00b7*" or (len(s) > 2 and s[1] == "-"):
                break  # bullet list (e.g. highlights) ends the abstract
            m = _ABS_LABEL_RX.match(s)
            glued = None if m else _ABS_LABEL_GLUED_RX.match(s)
            standalone = m and len(s) <= 40
            runin = (m and m.group(2) == ":" and len(s) > 40) or \
                (glued and len(s) > 40)
            word = (m or glued).group(1).lower() if (m or glued) else None
            fam = _ABS_LABEL_WORDS.get(word) if word else None
            if (standalone or runin) and fam and fam not in seen:
                found.append((i, fam))
                seen.add(fam)
                content_allow = 1 if standalone else 0
                last_content = i
            elif found and (content_allow or
                            (len(s) >= 25 and not s[:1].isdigit())):
                # wrapped continuation prose of the previous label
                content_allow = max(0, content_allow - 1)
                last_content = i
            elif not found:
                break
            else:
                break
            i += 1
        return found, last_content

    def resolve_abstract(self, refs_start):
        """Returns (abstract_mark, child_marks, last_child_idx, body_start)."""
        limit = refs_start if refs_start is not None else len(self.blocks)
        cands = [c for c in self.cands if c.block_idx < limit]

        fam_occ: dict[str, list[Candidate]] = {}
        for c in cands:
            if c.section_type in lx.IMRAD_LABEL_TYPES:
                fam_occ.setdefault(c.section_type, []).append(c)

        def stronger_later(c: Candidate) -> bool:
            return any(o.block_idx > c.block_idx and o.strength > c.strength
                       for o in fam_occ.get(c.section_type, []))

        abs_cands = [c for c in cands if c.section_type == "abstract"
                     and c.block_idx < len(self.blocks) * 0.7]
        child_marks: list[Mark] = []
        abstract_mark = None
        abs_idx = None
        last_child_idx = None

        if abs_cands:
            a = abs_cands[0]
            abs_idx = a.block_idx
            ev = list(a.signals)
            if a.kind == "runin":
                ev.append("abstract content run-in after label")
            abstract_mark = Mark(abs_idx, "abstract", a.name, 1,
                                 max(a.conf, 0.85), ev)
            # (1) candidate children (formatted labels)
            seen_fams: set = set()
            for c in cands:
                if c.block_idx <= abs_idx:
                    continue
                if c.section_type in lx.IMRAD_LABEL_TYPES and \
                        c.strength <= 2 and c.section_type not in seen_fams:
                    between = [x for x in cands
                               if abs_idx < x.block_idx < c.block_idx
                               and x.section_type not in lx.IMRAD_LABEL_TYPES]
                    if between:
                        break
                    seen_fams.add(c.section_type)
                    child_marks.append(Mark(
                        c.block_idx, "abstract_" + c.section_type, c.name, 2,
                        c.conf,
                        c.signals + ["inside abstract: structured-abstract "
                                     "label"]))
                    last_child_idx = c.block_idx
                else:
                    break
            # (2) formatting-free colon/standalone labels after the Abstract
            # heading (or after the last formatted label child, when only
            # some labels are formatted)
            scan_from = (last_child_idx + 1) if last_child_idx is not None \
                else abs_idx + 1
            next_cand = min((c.block_idx for c in cands
                             if c.block_idx >= scan_from),
                            default=len(self.blocks))
            found, content_end = self._scan_label_blocks(
                scan_from, min(next_cand, len(self.blocks)))
            have_fams = {m.section_type.replace("abstract_", "")
                         for m in child_marks}
            found = [(bi, t) for bi, t in found if t not in have_fams]
            fams = {t for _, t in found}
            if len(fams) >= 2 or (found and child_marks):
                for bi, t in found:
                    child_marks.append(Mark(
                        bi, "abstract_" + t,
                        self.blocks[bi].stripped[:40], 2, 0.8,
                        ["formatting-free structured-abstract label after "
                         "explicit Abstract heading"]))
                    last_child_idx = bi
                if content_end > (last_child_idx or 0):
                    last_child_idx = content_end
        else:
            # cluster without explicit heading
            imrad = [c for c in cands
                     if c.section_type in lx.IMRAD_LABEL_TYPES
                     and c.strength <= 2]
            run: list[Candidate] = []
            for c in imrad:
                if not run:
                    run = [c]
                    continue
                between = [x for x in cands
                           if run[-1].block_idx < x.block_idx < c.block_idx
                           and x not in run
                           and x.section_type not in lx.IMRAD_LABEL_TYPES]
                fams = {r.section_type for r in run}
                if between or c.section_type in fams:
                    if len(run) >= 2:
                        break
                    run = [c]
                    continue
                run.append(c)
            if len(run) >= 2:
                superseded = [c for c in run if stronger_later(c)]
                if len(superseded) >= 2:
                    c0 = run[0]
                    abs_idx = c0.block_idx
                    # structured abstracts open with background prose; if the
                    # cluster starts at a non-opening family, extend start
                    # over up to 2 preceding unlabeled prose blocks
                    ext_ev = []
                    if c0.section_type not in ("introduction", "objectives"):
                        k = abs_idx
                        steps = 0
                        while k - 1 >= 0 and steps < 2:
                            pb = self.blocks[k - 1]
                            if (k - 1) in self.cand_by_idx or \
                                    self.roles[k - 1] is not None or \
                                    len(pb.stripped) < 150 or \
                                    pb.bold_ratio > 0.3:
                                break
                            k -= 1
                            steps += 1
                        if k < abs_idx:
                            ext_ev.append(
                                f"abstract start extended {abs_idx - k} "
                                "block(s) earlier over unlabeled opening "
                                "prose (cluster began at "
                                f"'{c0.name.strip()}', not an opening "
                                "family) \u2014 extension is uncertain")
                            abs_idx = k
                    abstract_mark = Mark(
                        abs_idx, "abstract", "", 1,
                        0.7 if ext_ev else 0.85, ext_ev +
                        ["structured abstract cluster without explicit "
                         f"'Abstract' heading: labels "
                         f"{[r.name.strip() for r in run]} at blocks "
                         f"{[r.block_idx for r in run]}",
                         f"{len(superseded)} of these families re-appear "
                         "later with stronger formatting (the body "
                         "headings), so these labels are abstract "
                         "subsections, not body sections"])
                    for c in run:
                        child_marks.append(Mark(
                            c.block_idx, "abstract_" + c.section_type,
                            c.name, 2, c.conf,
                            c.signals + ["inside abstract: structured-"
                                         "abstract label"]))
                        last_child_idx = c.block_idx

        # fallback: formatting-free label cluster with NO abstract heading and
        # NO formatted label candidates (heavily damaged submissions)
        if abstract_mark is None and not abs_cands:
            limit2 = min(
                [c.block_idx for c in cands
                 if c.section_type in BODY_SET and c.strength >= 2] or
                [refs_start if refs_start is not None else len(self.blocks)])
            j = 0
            while j < limit2:
                s = self.blocks[j].stripped
                if (j not in self.cand_by_idx and self.roles[j] is None and
                        (_ABS_LABEL_RX.match(s) or
                         _ABS_LABEL_GLUED_RX.match(s))):
                    found, content_end = self._scan_label_blocks(j, limit2)
                    fams = {t for _, t in found}
                    if len(fams) >= 3 and any(
                            c.section_type in BODY_SET and
                            c.block_idx > content_end for c in cands):
                        # look back <=4 blocks for an opening label glued
                        # mid-block by a paragraph-merge artifact, e.g.
                        # "...no conflictIntroduction: The aim..."
                        first_fam = found[0][1]
                        if first_fam not in ("introduction", "objectives"):
                            rx_mid = re.compile(
                                r"[a-z0-9](Introduction|Background|"
                                r"Rationale|Objectives?|Purpose|Aims?)"
                                r"\s*:\s+\S")
                            k = found[0][0] - 1
                            steps = 0
                            while k >= 0 and steps < 4:
                                if k in self.cand_by_idx or \
                                        self.roles[k] is not None:
                                    break
                                mm = rx_mid.search(self.blocks[k].stripped)
                                if mm:
                                    w = mm.group(1).lower()
                                    found.insert(0, (
                                        k, _ABS_LABEL_WORDS.get(
                                            w, "introduction")))
                                    break
                                k -= 1
                                steps += 1
                        abs_idx = found[0][0]
                        abstract_mark = Mark(
                            abs_idx, "abstract", "", 1, 0.7,
                            ["formatting-free structured-abstract label "
                             f"cluster with no 'Abstract' heading: "
                             f"{len(fams)} families at blocks "
                             f"{[i for i, _ in found]}; stronger body "
                             "sections follow \u2014 boundary uncertain"],
                            uncertain=True)
                        for bi, t in found:
                            child_marks.append(Mark(
                                bi, "abstract_" + t,
                                self.blocks[bi].stripped[:40], 2, 0.7,
                                ["formatting-free label in headingless "
                                 "abstract cluster"]))
                        last_child_idx = max(content_end, found[-1][0])
                        break
                j += 1

        # additional Abstract headings (duplicated title-page abstracts):
        # emit marks + their contiguous run-in label children
        for extra in abs_cands[1:]:
            self._add_mark(Mark(
                extra.block_idx, "abstract", extra.name, 1, extra.conf,
                extra.signals + ["additional abstract heading (duplicate "
                                 "candidate; resolved in duplicate pass)"]))
            seen2: set = set()
            last2 = extra.block_idx
            for c in (x for x in cands if x.block_idx > extra.block_idx):
                if c.section_type in lx.IMRAD_LABEL_TYPES and \
                        c.strength <= 2 and c.section_type not in seen2 and \
                        c.block_idx <= extra.block_idx + len(seen2) + 2:
                    seen2.add(c.section_type)
                    last2 = c.block_idx
                    child_marks.append(Mark(
                        c.block_idx, "abstract_" + c.section_type, c.name, 2,
                        c.conf, c.signals + ["label inside duplicated "
                                             "abstract"]))
                else:
                    break
            # formatting-free labels inside the duplicated abstract
            nc = min((x.block_idx for x in cands if x.block_idx > last2),
                     default=len(self.blocks))
            found2, _ = self._scan_label_blocks(last2 + 1, nc)
            found2 = [(bi, t) for bi, t in found2 if t not in seen2]
            if len({t for _, t in found2}) >= 2 or (found2 and seen2):
                for bi, t in found2:
                    child_marks.append(Mark(
                        bi, "abstract_" + t,
                        self.blocks[bi].stripped[:40], 2, 0.7,
                        ["formatting-free label inside duplicated abstract"]))

        after = last_child_idx if last_child_idx is not None else (
            abs_idx if abs_idx is not None else -1)
        child_idxs = {m.idx for m in child_marks}
        body_cands = [c for c in cands
                      if c.block_idx > after
                      and c.section_type in BODY_SET
                      and c.block_idx not in child_idxs]
        strong = [c for c in body_cands if c.strength >= 2]
        pick = strong[0] if strong else (body_cands[0] if body_cands else None)
        body_start = pick.block_idx if pick is not None else None
        return abstract_mark, child_marks, last_child_idx, body_start

    # ------------------------------------------------- keywords / highlights
    def _content_extent(self, start_idx: int, kind: str) -> int:
        n = len(self.blocks)
        # does the content use list formatting? if so, bound by it strictly
        has_list = any(self.blocks[j].is_list or
                       self.blocks[j].stripped[:1] in "-\u2022\u00b7*"
                       for j in range(start_idx + 1,
                                      min(start_idx + 3, n)))
        i, last = start_idx + 1, start_idx
        while i < n and i - start_idx <= 14:
            if i in self.cand_by_idx:
                break
            b = self.blocks[i]
            s = b.stripped
            if not s:
                i += 1
                continue
            if self.roles[i] in ("byline", "metadata_count", "contact",
                                 "correspondence", "affiliation",
                                 "orcid_line", "table") or \
                    TITLE_LABEL_RX.match(s):
                break
            bullet = b.is_list or s[:1] in "-\u2022\u00b7*"
            if kind == "highlights":
                # plain-line bullets: short single sentences in sentence case
                # (body prose is multi-sentence/longer; a repeated Title-Case
                # title line is excluded by the title-case guard)
                plain_ok = (len(s) <= 300 and s.count(". ") < 2 and
                            title_case_ratio(s) < 0.6)
                ok = bullet or plain_ok
            else:
                kw_list = (len(s) <= 220 and
                           s.count(",") + s.count(";") >= 3)
                ok = bullet if has_list else (
                    ((len(s) <= 100 or kw_list) and
                     not lx.EMAIL_RX.search(s)) or bullet)
            if not ok:
                break
            last = i
            i += 1
        return last

    def kw_hl_marks(self, refs_start):
        limit = refs_start if refs_start is not None else len(self.blocks)
        for c in self.cands:
            if c.block_idx >= limit:
                continue
            if c.section_type in ("keywords", "highlights"):
                self._add_mark(Mark(c.block_idx, c.section_type, c.name, 1,
                                    c.conf, c.signals,
                                    uncertain=c.conf < 0.7))
                if c.kind == "runin":
                    ext = c.block_idx
                else:
                    ext = self._content_extent(c.block_idx, c.section_type)
                self.extents.append((c.block_idx, ext))

    # ---------------------------------------------------------- body marks
    def body_marks(self, body_start, refs_start, child_idxs: set):
        if body_start is None:
            return
        limit = refs_start if refs_start is not None else len(self.blocks)
        used_l1_families: set = set()
        last_l1_type = None
        last_l1_idx = None
        core = {"introduction", "methods", "results", "discussion",
                "conclusions", "results_and_discussion"}
        max_core_strength = max(
            (c.strength for c in self.cands
             if body_start <= c.block_idx < limit
             and c.section_type in core), default=0)
        for c in self.cands:
            if c.block_idx < body_start or c.block_idx >= limit:
                continue
            if c.block_idx in child_idxs:
                continue
            t = c.section_type
            ev = list(c.signals)
            flags = {}
            conf = c.conf
            if t is None:
                t = "other_heading"
                lvl = 1 if c.strength >= 3 else 2
            elif t in lx.SUBSECTION_TYPES:
                lvl = 2
            elif t in ("limitations", "implications") and \
                    c.strength < max_core_strength:
                # visually subordinate to the surrounding core headings:
                # a Discussion subheading per journal convention
                lvl = 2
                ev.append("limitations formatted weaker than core body "
                          "headings \u2014 nested as subsection")
            elif t == "acknowledgments" and c.kind == "standalone" and \
                    c.strength >= 2:
                lvl = 1  # acknowledgments is a container, never nested
            elif t == "credit_statement" and c.kind == "standalone" and \
                    c.strength >= 2 and last_l1_type != t:
                lvl = 1  # a credit statement is its own section
            elif t in BACK_SET and (c.kind in ("runin", "glued")
                                    or c.strength <= 2):
                # statement stems nest under an Acknowledgments container, or
                # under a same-type container when in weak label form AND
                # immediately adjacent (a stem line, not a duplicated section)
                near_same = (last_l1_type == t and
                             last_l1_idx is not None and
                             c.block_idx - last_l1_idx == 1)
                if t == "credit_statement":
                    # a credit statement is its own section, never an
                    # acknowledgments stem
                    lvl = 2 if near_same else 1
                else:
                    lvl = 2 if (last_l1_type == "acknowledgments" or
                                near_same) else 1
            elif t in lx.IMRAD_LABEL_TYPES and c.strength == 1:
                stronger = [o for o in self.cands
                            if o.section_type == t and
                            o.block_idx > c.block_idx and
                            o.strength > c.strength and o.block_idx < limit]
                if stronger:
                    self.warnings.append(
                        f"weak '{c.name.strip()}' label at block "
                        f"{c.block_idx} ignored (stronger occurrence later)")
                    continue
                lvl = 1
            elif t == "summary":
                fam = "conclusions" if last_l1_type in (
                    "discussion", "results", "limitations",
                    "conclusions") else "abstract"
                flags["ambiguous_family"] = fam
                ev.append(f"'summary' resolved positionally toward {fam}")
                lvl = 1
            else:
                lvl = 1
            if lvl == 1 and t in BODY_SET:
                if t in used_l1_families:
                    flags["repeated_type"] = True
                    conf -= 0.15
                    ev.append(f"repeated body section type '{t}' \u2014 kept and "
                              "flagged, resolved in duplicate pass")
                used_l1_families.add(t)
                last_l1_type = t
                last_l1_idx = c.block_idx
            elif lvl == 1:
                last_l1_type = t
                last_l1_idx = c.block_idx
            if c.kind == "glued":
                flags["glued_label"] = True
            self._add_mark(Mark(c.block_idx, t, c.name, lvl, conf, ev, flags,
                                uncertain=conf < 0.7))

    # ------------------------------------------------------------ tail marks
    def tail_marks(self, refs_end):
        if refs_end is None:
            return
        n = len(self.blocks)
        open_kind = None
        i = refs_end + 1
        while i < n:
            b = self.blocks[i]
            cand = self.cand_by_idx.get(i)
            role = self.roles[i]
            if cand and cand.section_type in (
                    TAIL_SET | BACK_SET | {"abbreviations", "other_heading",
                                           None}):
                t = cand.section_type or "other_heading"
                conf = cand.conf
                ev = list(cand.signals)
                if t == "other_heading":
                    # mangled tail headings ("ist of Figures"): fuzzy-match
                    # against tail vocabulary with a high threshold
                    try:
                        from rapidfuzz import fuzz
                        norm, _ = lx.normalize(cand.name)
                        best = (0, None)
                        for tt in TAIL_SET:
                            for v in lx.VOCAB[tt]:
                                r = fuzz.ratio(norm, v)
                                if r > best[0]:
                                    best = (r, tt)
                        if best[0] >= 88:
                            t = best[1]
                            conf = min(conf, 0.7)
                            ev.append(
                                f"fuzzy tail-heading match: '{cand.name}' ~ "
                                f"{best[1]} (score {best[0]:.0f}/100, likely "
                                "character-loss artifact)")
                    except ImportError:
                        pass
                self._add_mark(Mark(i, t, cand.name, 1, conf, ev,
                                    uncertain=conf < 0.7))
                open_kind = t
            elif b.is_table and open_kind is None:
                self._add_mark(Mark(
                    i, "tables_section", "", 1, 0.7,
                    ["table content after references with no caption "
                     "heading"]))
                open_kind = "tables_section"
            elif role == "caption":
                s = b.stripped.lower()
                if s.startswith(("appendix", "supplement", "online")):
                    kind = "appendix"
                elif s.startswith("table"):
                    kind = "tables_section"
                else:
                    kind = "figure_legends"
                if kind != open_kind:
                    # a short unrecognized line right before the captions may
                    # be a mangled group heading ("ist of Figures")
                    converted = False
                    for m in self.marks:
                        if m.idx == i - 1 and m.section_type == "unlabeled" \
                                and len(self.blocks[i - 1].stripped) <= 40:
                            try:
                                from rapidfuzz import fuzz
                                norm, _ = lx.normalize(
                                    self.blocks[i - 1].stripped)
                                best = max(
                                    (fuzz.ratio(norm, v)
                                     for v in lx.VOCAB[kind]), default=0)
                                if best >= 85:
                                    m.section_type = kind
                                    m.evidence.append(
                                        "fuzzy match to mangled group "
                                        f"heading '{self.blocks[i-1].stripped}'"
                                        f" (score {best:.0f}/100)")
                                    m.conf = 0.7
                                    converted = True
                            except ImportError:
                                pass
                            break
                    if not converted:
                        self._add_mark(Mark(
                            i, kind, "", 1, 0.75,
                            [f"grouped by caption pattern: "
                             f"'{b.stripped[:40]}' (no explicit heading)"]))
                    open_kind = kind
            elif open_kind in ("tables_section", "figure_legends") and \
                    re.match(r"^(Journal|Title|Author List|Manuscript|"
                             r"Running head)\s*:", b.stripped):
                # submission-form field lines after tables/figures are not
                # part of the table/figure group
                self._add_mark(Mark(i, "unlabeled", "", 1, 0.3,
                                    ["submission-form field lines after "
                                     "tables/figures"], uncertain=True))
                open_kind = "unlabeled"
            elif b.is_table or role in ("abbrev_line",) or \
                    (open_kind and len(b.stripped) < 400):
                pass
            elif open_kind is None:
                self._add_mark(Mark(i, "unlabeled", "", 1, 0.3,
                                    ["post-references content with no "
                                     "recognizable structure"],
                                    uncertain=True))
                open_kind = "unlabeled"
            i += 1

    # ---------------------------------------------------------- front matter
    def front_marks(self, eligible: list[int]):
        if not eligible:
            return
        FRONT_LABELS = {
            "title_page_marker", "authors_marker", "word_count_marker",
            "running_head", "orcid", "affiliations", "correspondence",
            "abbreviations",
        }
        assigned: dict[int, tuple] = {}
        seen_prose = False   # long unheaded prose encountered so far
        consumed_until = -1  # content absorbed by a back-matter statement
        front_limit_hint = eligible[-1] + 1
        for i in eligible:
            cand = self.cand_by_idx.get(i)
            role = self.roles[i]
            b = self.blocks[i]
            s = b.stripped
            if i <= consumed_until and not cand:
                continue  # content of a front back-matter statement
            if len(s) >= 180 and b.bold_ratio < 0.3 and role is None \
                    and not cand:
                seen_prose = True
            tl = TITLE_LABEL_RX.match(s)
            if tl and b.n_words >= 4:
                assigned[i] = ("title", 0.9,
                               [f"explicit title label: '{s[:40]}...'"])
                continue
            if cand and (cand.section_type in lx.SUBSECTION_TYPES or
                         cand.section_type is None) and seen_prose:
                # subsection-style heading in an unheaded body region:
                # emit as a level-2 mark under the surrounding unlabeled span.
                # guarded by seen_prose so a bold title block is never
                # mistaken for a subsection heading
                self._add_mark(Mark(
                    i, cand.section_type or "other_heading", cand.name, 2,
                    cand.conf,
                    cand.signals + ["subsection-style heading inside an "
                                    "unheaded body region"],
                    uncertain=cand.conf < 0.7))
                continue
            if cand and cand.section_type in BACK_SET | {"references"} and \
                    cand.section_type != "references":
                # back-matter statements legitimately appear on title pages
                self._add_mark(Mark(
                    i, cand.section_type, cand.name, 1, cand.conf,
                    cand.signals + ["back-matter statement in front matter"],
                    uncertain=cand.conf < 0.7))
                # absorb following content until the next candidate or mark
                j = i + 1
                while j < front_limit_hint and j not in self.cand_by_idx \
                        and not self._add_mark_exists(j) and \
                        self.roles[j] in (None, "abbrev_line",
                                          "credit_line") and j - i <= 6:
                    j += 1
                consumed_until = j - 1
                continue
            if cand and cand.section_type in FRONT_LABELS:
                t = cand.section_type
                if t == "word_count_marker":
                    t = "front_metadata"
                assigned[i] = (t, cand.conf, cand.signals)
            elif role == "byline":
                assigned[i] = ("authors", 0.85,
                               ["author byline: capitalized names with "
                                "academic degrees/superscripts"])
            elif role == "affiliation":
                assigned[i] = ("affiliations", 0.85,
                               ["affiliation pattern: 'From the'/enumerated "
                                "institution line"])
            elif role in ("correspondence", "contact"):
                assigned[i] = ("correspondence", 0.8,
                               ["correspondence/contact pattern"])
            elif role == "orcid_line":
                assigned[i] = ("orcid", 0.85, ["ORCID identifier pattern"])
            elif role == "metadata_count":
                assigned[i] = ("front_metadata", 0.85,
                               ["manuscript metadata count line"])
        # positional title: first unassigned block with title evidence,
        # only if no explicit title label was found
        have_title = any(t == "title" for t, _, _ in assigned.values())
        if not have_title:
            for i in eligible:
                if i in assigned:
                    continue
                b = self.blocks[i]
                if b.is_table or self.roles[i] == "caption":
                    continue
                if b.n_words >= 3 and len(b.stripped) >= 15:
                    sigs = []
                    if b.bold_ratio >= 0.5:
                        sigs.append(f"bold({b.bold_ratio:.2f})")
                    if b.caps_ratio >= 0.85:
                        sigs.append("allcaps")
                    if b.jc == "center":
                        sigs.append("centered")
                    tcr = title_case_ratio(b.stripped)
                    if tcr >= 0.7:
                        sigs.append(f"title-case({tcr:.2f})")
                    if sigs or i == eligible[0]:
                        conf = 0.85 if (b.bold_ratio >= 0.5 or
                                        b.caps_ratio >= 0.85 or
                                        b.jc == "center") else 0.6
                        ev = ["first substantive front-matter block"] + sigs
                        if not sigs:
                            ev.append("no formatting evidence \u2014 positional "
                                      "only")
                        assigned[i] = ("title", conf, ev)
                        break
        # repeated-title detection: a later front block nearly identical to
        # the chosen title is typed 'title' too (duplicate pass flags it)
        title_txt = None
        for i in eligible:
            if i in assigned and assigned[i][0] == "title":
                title_txt = _norm_for_sim(self.blocks[i].stripped)
                title_i = i
                break
        if title_txt:
            for i in eligible:
                if i in assigned or i <= title_i:
                    continue
                s = self.blocks[i].stripped
                if len(s) >= 15:
                    r = difflib.SequenceMatcher(
                        None, title_txt, _norm_for_sim(s)).ratio()
                    if r >= 0.8:
                        assigned[i] = ("title", 0.8,
                                       [f"repeated title text "
                                        f"(similarity {r:.2f} to title at "
                                        f"block {title_i})"])
        if not any(t == "title" for t, _, _ in assigned.values()):
            self.warnings.append(
                "title could not be identified with confidence; "
                "no title section emitted")
        # correspondence continuation absorption + unlabeled long prose
        prev_type = None
        prev_el = None
        for i in eligible:
            b = self.blocks[i]
            s = b.stripped
            if prev_el is not None and i != prev_el + 1:
                prev_type = None  # protected span between: chain broken
            prev_el = i
            if i in assigned:
                t = assigned[i][0]
                # a lone name line under "Corresponding Author:" is part of
                # the correspondence block, not a second authors byline
                if t == "authors" and prev_type == "correspondence" and \
                        b.n_words <= 8:
                    assigned[i] = ("correspondence", 0.75,
                                   ["single name line under correspondence "
                                    "label"])
                # contact lines directly under an authors/orcid list label
                # belong to that list, not to correspondence
                elif t == "correspondence" and \
                        prev_type in ("authors_marker", "orcid") and \
                        self.roles[i] in ("contact", "orcid_line"):
                    assigned[i] = (prev_type, 0.75,
                                   [f"continuation line under '{prev_type}' "
                                    "label"])
                # a single institution line directly under a correspondence
                # label is the corresponding author's address
                elif t == "affiliations" and prev_type == "correspondence" \
                        and len(b.stripped) <= 160:
                    assigned[i] = ("correspondence", 0.7,
                                   ["institution line under correspondence "
                                    "label (corresponding author's address)"])
                prev_type = assigned[i][0]
                continue
            if self._add_mark_exists(i):
                prev_type = None
                continue
            if prev_type == "correspondence" and len(s) <= 200 and \
                    not b.is_table:
                assigned[i] = ("correspondence", 0.7,
                               ["correspondence continuation line "
                                "(name/address under correspondence label)"])
                continue
            if len(s) >= 180 and b.bold_ratio < 0.3:
                assigned[i] = ("unlabeled", 0.3,
                               ["body-like prose without a section heading \u2014 "
                                "left unlabeled rather than guessed"])
            else:
                assigned[i] = ("front_other", 0.4,
                               ["front-matter block with no recognized "
                                "pattern"])
            prev_type = assigned[i][0]
        # group consecutive same-type (within eligibility continuity)
        prev_type = None
        prev_i = None
        for i in eligible:
            if i not in assigned:
                prev_type, prev_i = None, i
                continue
            t, conf, ev = assigned[i]
            force_break = prev_i is None or i != prev_i + 1
            if t != prev_type or t == "title" or force_break:
                self._add_mark(Mark(
                    i, t,
                    self.blocks[i].stripped[:80]
                    if t in ("title_page_marker", "running_head",
                             "word_count_marker") else "",
                    1, conf, list(ev), uncertain=conf < 0.7))
            prev_type, prev_i = t, i

    # ------------------------------------------------------------- assembly
    def assemble(self) -> tuple[list[Section], list[str]]:
        refs_start, refs_end, refs_mark = self.find_references()
        abstract_mark, child_marks, last_child_idx, body_start = \
            self.resolve_abstract(refs_start)

        if abstract_mark is not None:
            self._add_mark(abstract_mark)
            for m in child_marks:
                self._add_mark(m)
        self.kw_hl_marks(refs_start)
        self.body_marks(body_start, refs_start, {m.idx for m in child_marks})
        if refs_mark is not None:
            self._add_mark(refs_mark)
            self.tail_marks(refs_end)
        else:
            self.warnings.append("no references section identified")

        # ----- front matter over uncovered pre-body blocks -----
        protected: set = set()
        for m in self.marks:
            protected.add(m.idx)
        for (a, b) in self.extents:
            protected.update(range(a, b + 1))
        # every abstract-typed mark protects its content up to the next mark
        for am in [m for m in self.marks if m.section_type == "abstract"]:
            nxt = min((m.idx for m in self.marks
                       if m.idx > am.idx and m.level == 1),
                      default=len(self.blocks))
            hi = nxt
            if abstract_mark is not None and am.idx == abstract_mark.idx \
                    and last_child_idx is not None:
                hi = max(nxt, last_child_idx + 1)
            protected.update(range(am.idx, hi))
        front_limit = body_start if body_start is not None else (
            refs_start if refs_start is not None else len(self.blocks))
        eligible = [i for i in range(front_limit) if i not in protected]
        self.front_marks(eligible)

        self._credit_signature_pass()

        if not self.marks:
            self._add_mark(Mark(0, "unlabeled", "", 1, 0.3,
                                ["no recognizable structure in document"],
                                uncertain=True))
        elif min(m.idx for m in self.marks) > 0:
            self._add_mark(Mark(0, "unlabeled", "", 1, 0.3,
                                ["document start before first recognized "
                                 "structure"], uncertain=True))
        # gap after keyword/highlight extents (when body follows directly)
        covered = {m.idx for m in self.marks}
        for (a, b) in self.extents:
            j = b + 1
            if j < len(self.blocks) and j not in covered and \
                    all(not (m.idx <= j <= m.idx for m in self.marks)):
                pass  # handled below by generic gap fill
        # generic gap fill: any block not reachable will be covered by the
        # sweep (sections extend to the next mark), except blocks after an
        # extent-bounded section whose next mark is far -- insert unlabeled
        marks_sorted = sorted(self.marks, key=lambda m: (m.idx, m.level))
        for (a, b) in self.extents:
            nxt = min((m.idx for m in marks_sorted if m.idx > a),
                      default=len(self.blocks))
            if b + 1 < nxt:
                self._add_mark(Mark(
                    b + 1, "unlabeled", "", 1, 0.3,
                    ["text after keywords/highlights content with no "
                     "section heading \u2014 left unlabeled rather than guessed"],
                    uncertain=True))

        marks = sorted(self.marks, key=lambda m: (m.idx, m.level))

        # sweep with a stack -> section tree
        sections: list[Section] = []
        stack: list[tuple[Mark, Section]] = []
        counter = [0]

        def close(sec: Section, end_block: int, reason: str):
            end_block = max(end_block, sec.start_block)
            sec.end_block = end_block
            sec.end = self.blocks[end_block].end
            sec.text = self.full_text[sec.start:sec.end]
            sec.evidence.append(f"end: {reason}")

        def open_mark(m: Mark, parent: Optional[Section]) -> Section:
            counter[0] += 1
            sec = Section(
                id=counter[0], section_type=m.section_type, name=m.name,
                level=m.level, start_block=m.idx, end_block=m.idx,
                start=self.blocks[m.idx].start, end=self.blocks[m.idx].end,
                text="", confidence=max(0.15, min(0.97, m.conf)),
                uncertain=m.uncertain or m.conf < 0.7,
                evidence=[f"start: block {m.idx}"] + list(m.evidence),
                parent_id=parent.id if parent else None,
                flags=dict(m.flags),
            )
            sections.append(sec)
            return sec

        for m in marks:
            while stack and stack[-1][0].level >= m.level:
                _, top_s = stack.pop()
                close(top_s, m.idx - 1,
                      f"next section '{m.section_type}' starts at block "
                      f"{m.idx}")
            parent = stack[-1][1] if stack else None
            sec = open_mark(m, parent)
            stack.append((m, sec))
        last = len(self.blocks) - 1
        while stack:
            _, top_s = stack.pop()
            close(top_s, last, "document end")

        if refs_start is not None:
            for s in sections:
                if s.section_type == "references" and \
                        s.start_block == refs_start:
                    s.evidence.append(
                        f"reference-shaped content spans blocks "
                        f"{refs_start}..{refs_end}")

        self._sequence_bonus(sections)
        self._duplicate_pass(sections)

        for s in sections:
            s.confidence = max(0.15, min(0.97, s.confidence))
            s.uncertain = s.confidence < 0.7
        n_unlabeled = sum(1 for s in sections if s.section_type in
                          ("unlabeled", "front_other"))
        if n_unlabeled:
            self.warnings.append(
                f"{n_unlabeled} span(s) left explicitly unlabeled/front_other "
                "rather than guessed")
        return sections, self.warnings

    _CREDIT_ROLE_RX = lx.CREDIT_ROLE_RX

    def _credit_signature_pass(self):
        """An unheaded CRediT block: >=3 consecutive 'Name: Role, Role' lines
        using the fixed CRediT taxonomy vocabulary."""
        credit_idx = {m.idx for m in self.marks
                      if m.section_type == "credit_statement"}
        n = len(self.blocks)
        i = 0
        while i < n:
            if self._add_mark_exists(i) or self.blocks[i].is_table:
                i += 1
                continue
            j = i
            while j < n and not self.blocks[j].is_table and \
                    len(self.blocks[j].stripped) <= 220 and \
                    self._CREDIT_ROLE_RX.search(self.blocks[j].stripped) and \
                    not (j > i and self._add_mark_exists(j)):
                j += 1
            if j - i >= 3:
                # skip if a credit heading opens within the 3 blocks before
                if not any(k in credit_idx for k in range(max(0, i - 3), i)):
                    self._add_mark(Mark(
                        i, "credit_statement", "", 1, 0.7,
                        [f"unheaded CRediT block: {j - i} consecutive "
                         "'Name: Role' lines using CRediT taxonomy terms"],
                        uncertain=False))
                i = j
            else:
                i += 1

    # ----------------------------------------------------------- sequencing
    def _sequence_bonus(self, sections: list[Section]):
        order = {"introduction": 0, "objectives": 1, "methods": 2,
                 "results": 3, "results_and_discussion": 3.5,
                 "discussion": 4, "limitations": 5, "conclusions": 6}
        seq = [s for s in sections if s.level == 1 and
               s.section_type in order]
        vals = [order[s.section_type] for s in seq]
        if len(vals) >= 3 and vals == sorted(vals):
            for s in seq:
                s.confidence = min(0.97, s.confidence + 0.05)
                s.evidence.append(
                    "sequence-consistent with canonical IMRaD order "
                    f"({' -> '.join(x.section_type for x in seq)})")

    # ------------------------------------------------------------ duplicates
    DUP_TYPES = {
        "abstract", "keywords", "highlights", "credit_statement", "funding",
        "declaration_of_interest", "front_metadata", "affiliations",
        "correspondence", "orcid", "running_head", "authors",
        "title_page_marker", "title", "disclaimer", "data_availability",
        "acknowledgments",
    } | BODY_SET

    # types a genuine manuscript states at most once; a second occurrence
    # with DIFFERENT wording (text similarity cannot catch it) is a
    # restatement of the same element - in this corpus, the journal's
    # submission form (checkbox declaration-of-interest,
    # statement-of-authorship) appended after the tables
    SINGLETON_TYPES = {
        "declaration_of_interest", "credit_statement", "acknowledgments",
        "funding", "data_availability", "ethics",
    }
    _CHECKBOX_CHARS = "\u2610\u2611\u2612"

    def _duplicate_pass(self, sections: list[Section]):
        by_type: dict[str, list[Section]] = {}
        for s in sections:
            if s.section_type in self.DUP_TYPES:
                by_type.setdefault(s.section_type, []).append(s)
        for t, group in by_type.items():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    if a.flags.get("duplicate_of") or \
                            b.flags.get("duplicate_of"):
                        continue
                    ta = _norm_for_sim(a.text)[:2500]
                    tb = _norm_for_sim(b.text)[:2500]
                    if len(ta) < 12 or len(tb) < 12:
                        continue
                    ratio = difflib.SequenceMatcher(None, ta, tb).ratio()
                    contained = (ta in tb) or (tb in ta)
                    short = len(ta) < 25 or len(tb) < 25
                    # tiny sections need near-identical text to count as dup
                    if (ratio >= 0.9 if short else
                            (ratio >= 0.65 or contained)):
                        if len(tb) >= 1.3 * len(ta):
                            primary, dup = b, a
                        else:
                            primary, dup = a, b
                        dup.flags["duplicate_of"] = primary.id
                        dup.confidence -= 0.15
                        dup.uncertain = True
                        dup.evidence.append(
                            f"near-duplicate of section id={primary.id} "
                            f"(same type '{t}', similarity={ratio:.2f}"
                            f"{', containment' if contained else ''}); "
                            "kept but flagged \u2014 primary chosen by "
                            "completeness/position")
                        primary.evidence.append(
                            f"section id={dup.id} is a near-duplicate of "
                            f"this one (similarity={ratio:.2f}); this "
                            "occurrence kept as primary")
        self._singleton_restatement_pass(sections)
        # duplicates may chain (A dup-of B, B dup-of C); re-point each
        # flag at the ultimate primary so downstream consumers never have
        # to walk the chain themselves
        by_id = {s.id: s for s in sections}
        for s in sections:
            tgt = s.flags.get("duplicate_of")
            seen = set()
            while tgt in by_id and by_id[tgt].flags.get("duplicate_of") \
                    and tgt not in seen:
                seen.add(tgt)
                tgt = by_id[tgt].flags["duplicate_of"]
            if tgt is not None and tgt != s.flags.get("duplicate_of"):
                s.flags["duplicate_of"] = tgt

    def _singleton_restatement_pass(self, sections: list[Section]):
        """Flag a SECOND occurrence of a singleton statement type even when
        its wording differs (so the similarity pass above cannot see it).
        The evidence is the canonical type itself recurring: a manuscript
        states its declaration of interest / authorship / funding once, and
        the extra copy observed in this corpus is the journal's submission
        form appended after the tables. Flag-only, never deleted: the text
        stays available with both spans."""
        for t in sorted(self.SINGLETON_TYPES):
            group = [s for s in sections if s.section_type == t
                     and not s.flags.get("duplicate_of")]
            if len(group) < 2:
                continue

            def boxes(s: Section) -> int:
                return sum(s.text.count(c) for c in self._CHECKBOX_CHARS)

            # primary = the in-paper occurrence: no form checkboxes, then
            # nested under a parent section (e.g. inside acknowledgments),
            # then the fuller text, then the earlier position
            primary = min(group, key=lambda s: (
                boxes(s), 0 if s.parent_id is not None else 1,
                -len(s.text), s.start))
            for dup in group:
                if dup is primary:
                    continue
                # adjacent same-type siblings (e.g. 'Funding' next to
                # 'Role of the Funder/Sponsor') are DIFFERENT statements
                # sharing one canonical type - never flag those. A true
                # restatement is far away in the document, carries form
                # checkbox marks, or is a bare heading stub.
                gap = max(dup.start - primary.end,
                          primary.start - dup.end, 0)
                nb = boxes(dup)
                stub = len(_norm_for_sim(dup.text)) < 40
                if gap < 2000 and nb == 0 and not stub:
                    continue
                ratio = difflib.SequenceMatcher(
                    None, _norm_for_sim(primary.text)[:2500],
                    _norm_for_sim(dup.text)[:2500]).ratio()
                why = []
                if gap >= 2000:
                    why.append(f"{gap} chars away from the primary")
                if nb:
                    why.append(f"{nb} form checkbox mark(s) present")
                if stub:
                    why.append("bare heading stub")
                dup.flags["duplicate_of"] = primary.id
                dup.confidence -= 0.15
                dup.uncertain = True
                dup.evidence.append(
                    f"second occurrence of singleton type '{t}' "
                    f"(similarity={ratio:.2f} - different wording, same "
                    f"element, likely a submission-form restatement: "
                    f"{'; '.join(why)}); kept but flagged, primary is the "
                    f"in-paper occurrence id={primary.id}")
                primary.evidence.append(
                    f"section id={dup.id} restates this element (same "
                    f"singleton type '{t}', similarity={ratio:.2f}); this "
                    "occurrence kept as primary")


def assemble(blocks: list[Block], full_text: str, text_mode: bool = False):
    return Assembler(blocks, full_text, text_mode=text_mode).assemble()
