"""Per-block role screening and heading-candidate detection.

Philosophy (precision-first):
1. Negative evidence first: captions, metadata counts, contact lines, ORCID
   lines, author bylines, affiliation lines, abbreviation-expansion lines are
   identified BEFORE heading detection and cannot become headings.
2. A lexicon match alone never makes a heading: structural evidence (style,
   bold coverage, caps, numbering, centering, standalone shortness) is
   required too. A word like "Introduction" inside a prose sentence never
   matches because matching is against the WHOLE block, normalized.
3. Non-lexicon headings are allowed only with strong structural evidence and
   become type "other_heading" (named), never a canonical type.
4. Sentence-terminal punctuation disqualifies non-lexicon candidates, but a
   trailing dotted abbreviation (U.S., U.S.A., e.g.) is recognized and does
   NOT count as sentence-terminal when formatting evidence is present.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from . import lexicon as lx
from .model import Block

STOPWORDS = {
    "a", "an", "and", "the", "of", "in", "on", "for", "to", "with", "by",
    "at", "or", "vs", "via", "from", "as", "its",
}


def title_case_ratio(text: str) -> float:
    words = [w for w in text.split() if any(c.isalpha() for c in w)]
    if not words:
        return 0.0
    content = [w for w in words if w.lower() not in STOPWORDS]
    if not content:
        return 0.0
    return sum(1 for w in content if w[0].isupper()) / len(content)


@dataclass
class Candidate:
    block_idx: int
    kind: str                    # 'standalone' | 'runin' | 'glued'
    section_type: Optional[str]  # canonical type or None (=> other_heading)
    name: str                    # literal heading text (prefix only if runin)
    level: int                   # 1/2/3 structural level guess
    strength: int                # 3 allcaps-standalone, 2 titlecase, 1 label
    signals: list = field(default_factory=list)
    lex: Optional[dict] = None
    prefix_len: int = 0          # for runin/glued: chars of heading prefix
    conf: float = 0.5


# ---------------------------------------------------------------- roles
def screen_roles(blocks: list[Block]) -> list[Optional[str]]:
    roles: list[Optional[str]] = [None] * len(blocks)
    for b in blocks:
        s = b.stripped
        if b.is_table:
            roles[b.idx] = "table"
            continue
        if not s:
            roles[b.idx] = "empty"
            continue
        if lx.CAPTION_RX.match(s):
            roles[b.idx] = "caption"
            continue
        if lx.METADATA_COUNT_RX.match(s):
            roles[b.idx] = "metadata_count"
            continue
        lexm = lx.match(s)
        if lexm:
            # lexicon labels are handled by candidate detection
            continue
        if lx.ORCID_RX.search(s) and b.n_words <= 10:
            roles[b.idx] = "orcid_line"
            continue
        if lx.CONTACT_RX.match(s) and len(s) <= 120:
            roles[b.idx] = "contact"
            continue
        if lx.CORRESPONDENCE_RX.match(s):
            roles[b.idx] = "correspondence"
            continue
        # street-address affiliation BEFORE the bare-email contact rule, so
        # "Madison, WI, USA name@uni.edu" is affiliation, not contact
        street0 = re.search(
            r"\b\d{2,5}\s+(?:[A-Z][A-Za-z.]*\s+){0,3}"
            r"(Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd|Lane|Ln|"
            r"Place|Pl|Box|Hwy|Suite)\b", s)
        if len(s) <= 250 and lx.EMAIL_RX.search(s) and \
                (street0 or
                 re.search(r",\s*(USA|United States|U\.S\.A?\.?)\b", s)):
            roles[b.idx] = "affiliation"
            continue
        if lx.EMAIL_RX.search(s) and len(s) <= 80 and b.n_words <= 10:
            roles[b.idx] = "contact"
            continue
        if lx.CORRESPONDENCE_RX.match(s):
            roles[b.idx] = "correspondence"
            continue
        has_tags = lx.COPYEDIT_TAG_RX.search(s)
        if (lx.AFFIL_START_RX.match(s) or has_tags) and \
                (has_tags or len(s) <= 700):
            roles[b.idx] = "affiliation"
            continue
        # letter/number-enumerated affiliation: "a. Nationwide Children's..."
        # or "1. Department of Psychiatry, University of ..."
        if re.match(r"^([a-z]|\d{1,2})[.)\]]{1,2}\s+\S", s) and \
                lx.AFFIL_KEYWORD_RX.search(s) and len(s) <= 400:
            roles[b.idx] = "affiliation"
            continue
        # street-address style affiliation line, possibly with email:
        # "Sharp Insight LLC. 4535 Everett Street, Kensington, MD, USA x@y.com"
        street = re.search(
            r"\b\d{2,5}\s+(?:[A-Z][A-Za-z.]*\s+){0,3}"
            r"(Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd|Lane|Ln|"
            r"Place|Pl|Box|Hwy|Suite)\b", s)
        present_addr = re.match(r"^\d{1,2}\s*[.)]?\s*Present address", s, re.I)
        if len(s) <= 250 and \
                (lx.AFFIL_KEYWORD_RX.search(s) or lx.EMAIL_RX.search(s)) and \
                (street or present_addr or
                 (lx.EMAIL_RX.search(s) and
                  re.search(r",\s*(USA|United States|U\.S\.A?\.?)\b", s))):
            roles[b.idx] = "affiliation"
            continue
        # institution-dense line: >=2 institution keywords, short, capitalized
        if len(s) <= 160 and s[:1].isupper() and \
                len(lx.AFFIL_KEYWORD_RX.findall(s)) >= 2:
            roles[b.idx] = "affiliation"
            continue
        deg_hits = lx.DEGREES_RX.findall(s)
        unambig = [d for d in deg_hits if d not in lx.AMBIGUOUS_DEGREES]
        # ambiguous tokens (MA/MS/MD... are also state codes) only count when
        # >=2 degree tokens co-occur or superscript digits are present
        deg_ok = bool(unambig) or len(deg_hits) >= 2 or \
            (deg_hits and re.search(r",\d", s))
        if deg_ok and s.count(",") >= 1 and b.n_words >= 4 \
                and len(s) <= 500 and not s.endswith(":"):
            letters_words = s.split()
            capw = sum(1 for w in letters_words
                       if w[:1].isupper() or w[:1].isdigit())
            if capw / len(letters_words) >= 0.6:
                roles[b.idx] = "byline"
                continue
        # person-name + CRediT taxonomy roles: content line, never a heading
        if lx.CREDIT_ROLE_RX.search(s) and ":" in s[:60] and \
                len(s.split(":", 1)[0].split()) <= 6:
            roles[b.idx] = "credit_line"
            continue
        if lx.ABBREV_EXPANSION_RX.match(s) and len(s) <= 90 and \
                ":" in s[:18]:
            prefix = s.split(":", 1)[0]
            pnorm, _ = lx.normalize(prefix)
            if pnorm not in lx._VARIANT_TO_TYPE:
                roles[b.idx] = "abbrev_line"
                continue
    return roles


# ------------------------------------------------------------- candidates
def _struct_signals(b: Block) -> list[str]:
    sig = []
    if b.style_heading_level:
        sig.append(f"style:{b.style or 'outline'}(H{b.style_heading_level})")
    if b.bold_ratio >= 0.6 and b.n_words <= 16:
        sig.append(f"bold({b.bold_ratio:.2f})")
    if b.caps_ratio >= 0.85 and b.n_letters >= 4:
        sig.append(f"allcaps({b.caps_ratio:.2f})")
    if b.jc == "center":
        sig.append("centered")
    if b.n_words <= 6 and len(b.stripped) <= 60:
        sig.append("short-standalone")
    if b.blank_before >= 1:
        sig.append("blank-before")
    return sig


def _ends_like_sentence(s: str) -> tuple[bool, str]:
    """Return (is_sentence_end, reason)."""
    if not s:
        return False, ""
    last = s.rstrip()[-1:]
    if last in ",;?!":
        return True, f"ends '{last}'"
    if last == ".":
        if lx.TRAILING_DOTTED_ABBREV_RX.search(s.rstrip()):
            return False, "trailing dotted abbreviation (e.g. U.S.) not treated as sentence end"
        return True, "ends '.'"
    return False, ""


def _leading_bold_prefix(b: Block) -> int:
    """Chars of the leading run of bold text (allowing bold whitespace)."""
    n = 0
    for r in b.runs:
        if r.bold or not r.text.strip():
            n += len(r.text)
        else:
            break
    return n


def detect_candidates(blocks: list[Block], roles: list,
                      text_mode: bool = False) -> list[Candidate]:
    cands: list[Candidate] = []
    for b in blocks:
        role = roles[b.idx]
        if role in ("table", "empty", "caption", "metadata_count", "contact",
                    "orcid_line", "byline", "abbrev_line", "credit_line"):
            continue
        s = b.stripped
        if not s:
            continue
        sig = _struct_signals(b)
        lexm = lx.match(s)
        if lexm is None and "(" in s:
            # retry with trailing parenthetical stripped: "Abstract (296/300 words)"
            import re as _re
            s2 = _re.sub(r"\s*\([^)]{0,40}\)\s*$", "", s)
            if s2 != s:
                lexm2 = lx.match(s2)
                if lexm2:
                    lexm = lexm2
                    sig.append("trailing-parenthetical-stripped")
        tc_ratio = title_case_ratio(s)
        sent_end, sent_reason = _ends_like_sentence(s)

        # ---------------- standalone heading (whole block) ----------------
        if lexm and len(s) <= 120 and b.n_words <= 16:
            has_struct = any(x.startswith(("style:", "bold", "allcaps",
                                           "centered")) for x in sig)
            has_weak = any(x.startswith("short-standalone") for x in sig) or \
                lexm.get("numbering") or text_mode
            if role == "correspondence" and lexm["type"] != "correspondence":
                has_struct = has_weak = False
            if has_struct or has_weak:
                strength = 3 if (b.caps_ratio >= 0.85 and b.n_letters >= 4) \
                    else (2 if b.bold_ratio >= 0.6 or b.style_heading_level
                          else 1)
                level = 1 if strength == 3 or b.style_heading_level == 1 else 2
                if lexm["type"] in lx.SUBSECTION_TYPES:
                    level = 2
                t = lexm["type"]
                if t == "_summary_ambiguous":
                    t = "summary"
                c = Candidate(
                    block_idx=b.idx, kind="standalone", section_type=t,
                    name=s, level=level, strength=strength,
                    signals=sig + [f"lexicon:'{lexm['variant']}'"], lex=lexm,
                )
                if lexm.get("numbering"):
                    c.signals.append(f"numbering:'{lexm['numbering']}'")
                if lexm.get("had_colon"):
                    c.signals.append("trailing-colon")
                c.conf = 0.9 if has_struct else 0.75
                cands.append(c)
                continue

        # -------- content labels with long tails: "Key Words: a; b; c" -----
        if ":" in s[:70] and not b.is_table:
            prefix, tail = s.split(":", 1)
            pm = lx.match(prefix)
            if pm and pm["type"] in ("keywords", "running_head", "orcid",
                                     "word_count_marker") and \
                    0 < len(tail.strip()) <= 300:
                cands.append(Candidate(
                    block_idx=b.idx, kind="runin", section_type=pm["type"],
                    name=prefix + ":", level=1, strength=1,
                    signals=sig + [f"content-label:'{prefix}:'",
                                   f"lexicon:'{pm['variant']}'"],
                    lex=pm, prefix_len=len(prefix) + 1,
                    conf=0.85,
                ))
                continue

        # -------- label with short inline tail: "Funding: None." ----------
        if ":" in s[:70] and len(s) <= 110 and not b.is_table:
            prefix, tail = s.split(":", 1)
            pm = lx.match(prefix)
            if pm and pm["type"] in (lx.RUN_IN_LABEL_TYPES |
                                     lx.BACK_MATTER_TYPES |
                                     {"title_page_marker"}) and \
                    0 < len(tail.strip()) <= 40:
                t = pm["type"]
                if t == "_summary_ambiguous":
                    t = "summary"
                cands.append(Candidate(
                    block_idx=b.idx, kind="standalone", section_type=t,
                    name=prefix + ":", level=2, strength=1,
                    signals=sig + [f"label-with-short-tail:'{s[:60]}'",
                                   f"lexicon:'{pm['variant']}'"],
                    lex=pm, conf=0.85 if (b.bold_ratio >= 0.3 or
                                          b.caps_ratio >= 0.5 or
                                          b.style_heading_level) else 0.7,
                ))
                continue

        # ---------------- run-in label: bold prefix + content -------------
        pl = _leading_bold_prefix(b)
        rest_len = len(s) - pl
        if 3 <= pl <= 80 and rest_len >= 25 and not text_mode:
            prefix = b.text[:pl].strip()
            pm = lx.match(prefix)
            if pm and pm["type"] in lx.RUN_IN_LABEL_TYPES:
                t = pm["type"]
                if t == "_summary_ambiguous":
                    t = "summary"
                cands.append(Candidate(
                    block_idx=b.idx, kind="runin", section_type=t,
                    name=prefix, level=3, strength=1,
                    signals=[f"bold-run-in-label:'{prefix}'",
                             f"lexicon:'{pm['variant']}'"],
                    lex=pm, prefix_len=pl, conf=0.85,
                ))
                continue
        # colon run-in without bold info (plain-text mode)
        if text_mode and ":" in s[:60]:
            prefix, rest = s.split(":", 1)
            if len(rest.strip()) >= 25:
                pm = lx.match(prefix)
                if pm and pm["type"] in lx.RUN_IN_LABEL_TYPES:
                    t = pm["type"]
                    if t == "_summary_ambiguous":
                        t = "summary"
                    cands.append(Candidate(
                        block_idx=b.idx, kind="runin", section_type=t,
                        name=prefix + ":", level=3, strength=1,
                        signals=[f"colon-run-in-label:'{prefix}:'",
                                 f"lexicon:'{pm['variant']}'"],
                        lex=pm, prefix_len=len(prefix) + 1, conf=0.7,
                    ))
                    continue

        # ---------------- glued label (merge artifact) --------------------
        if b.bold_ratio >= 0.5 and len(s) <= 120:
            gm = lx.match_glued_prefix(s)
            if gm:
                cands.append(Candidate(
                    block_idx=b.idx, kind="glued", section_type=gm["type"],
                    name=s[:gm["prefix_len"]], level=2, strength=1,
                    signals=[f"glued-label:'{s[:gm['prefix_len']]}' "
                             "(tracked-change paragraph-merge artifact)"],
                    lex=gm, prefix_len=gm["prefix_len"], conf=0.55,
                ))
                continue

        # ---------------- non-lexicon structural heading ------------------
        if role in ("correspondence", "affiliation"):
            continue
        if len(s) <= 90 and b.n_words <= 12 and b.n_letters >= 3:
            if sent_end:
                continue
            if s.rstrip().endswith(":"):
                # non-lexicon colon labels ("AID:") are never headings
                continue
            strong = (
                b.style_heading_level is not None
                or (b.bold_ratio >= 0.6 and (b.caps_ratio >= 0.85 or tc_ratio >= 0.8))
                or (b.caps_ratio >= 0.85 and b.n_letters >= 6)
                or (text_mode and b.caps_ratio >= 0.85 and b.n_letters >= 6)
            )
            if strong and not b.is_list:
                strength = 3 if b.caps_ratio >= 0.85 else 2
                level = 1 if (strength == 3 or b.style_heading_level == 1) else 2
                extra = []
                if s.rstrip().endswith(".") :
                    extra.append("terminal '.' accepted: dotted abbreviation")
                cands.append(Candidate(
                    block_idx=b.idx, kind="standalone", section_type=None,
                    name=s, level=level, strength=strength,
                    signals=sig + ["no-lexicon-match: structural evidence only"]
                    + extra,
                    conf=0.65,
                ))
    return cands
