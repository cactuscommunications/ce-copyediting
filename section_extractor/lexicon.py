"""Section-name vocabulary, normalization, and numbering handling.

Every variant listed here was either observed in the AMEPRE/FOCUS development
corpus or is a widely used academic section name. Matching is done on a
normalized form (numbering prefix stripped, trailing punctuation stripped,
case-folded) so that "1. INTRODUCTION:", "I. Introduction", and
"introduction" all resolve to the same canonical type. The presence of a
lexicon match NEVER suffices on its own to declare a heading \u2014 structural
evidence is required as well (see headings.py).
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Canonical vocabulary. canonical_type -> variants (normalized form).
# ---------------------------------------------------------------------------
VOCAB: dict[str, set] = {
    "abstract": {
        "abstract", "structured abstract", "graphical abstract",
        "abstract and keywords",
    },
    # "summary" is ambiguous (abstract at front, conclusions at tail);
    # resolved positionally in assemble.py.
    "_summary_ambiguous": {"summary", "lay summary", "plain language summary"},
    "keywords": {"keywords", "key words", "index terms", "key terms"},
    "highlights": {"highlights", "ajpm focus highlights", "research highlights"},
    "introduction": {
        "introduction", "background", "introduction and background",
        "background and objectives", "background and aims",
        "background and significance", "intro",
    },
    "objectives": {
        "objectives", "objective", "aims", "aim", "purpose",
        "aims and objectives", "study objectives", "research questions",
        "hypothesis", "hypotheses", "rationale",
    },
    "methods": {
        "methods", "method", "methodology", "materials and methods",
        "methods and materials", "material and methods",
        "patients and methods", "subjects and methods", "data and methods",
        "study design and methods", "experimental methods",
        "experimental section", "research design and methods",
        "methods and procedures", "study methods", "research methods",
        "design and methods", "materials & methods",
    },
    "results": {"results", "findings", "results and findings"},
    "results_and_discussion": {"results and discussion"},
    "discussion": {"discussion", "comment", "general discussion"},
    "limitations": {
        "limitations", "strengths and limitations", "limitations and strengths",
        "study limitations", "strengths and weaknesses",
    },
    "conclusions": {
        "conclusions", "conclusion", "concluding remarks",
        "summary and conclusions", "conclusions and implications",
        "conclusions and future directions", "conclusions and recommendations",
        "final remarks", "discussion and conclusions", "discussion and conclusion",
    },
    "implications": {
        "implications", "implications for practice", "practical implications",
        "public health implications", "policy implications",
        "clinical implications", "implications for research and practice",
    },
    "recommendations": {"recommendations", "recommendation"},
    "future_work": {
        "future directions", "future work", "future research",
        "directions for future research",
    },
    "related_work": {
        "related work", "literature review", "review of the literature",
        "prior work", "related literature", "theoretical background",
    },
    "acknowledgments": {
        "acknowledgments", "acknowledgment", "acknowledgements",
        "acknowledgement", "general acknowledgments",
    },
    "funding": {
        "funding", "funding sources", "sources of funding", "funding source",
        "funding statement", "financial support", "funding declaration",
        "role of the funding source", "supported by", "funding/support",
        "grant support", "sources of support", "funding/acknowledgements",
        "funding/acknowledgments", "funding and acknowledgements",
        "funding and acknowledgments", "role of the funder/sponsor",
        "role of the funder", "role of the sponsor", "funding/support",
    },
    "declaration_of_interest": {
        "declaration of interest", "declarations of interest",
        "declaration of interests", "declaration of competing interest",
        "declaration of competing interests", "conflicts of interest",
        "conflict of interest", "competing interests", "competing interest",
        "disclosures", "disclosure", "disclosure statement",
        "financial disclosure", "financial disclosures",
        "declaration of interest statement", "conflict of interest statement",
        "declaration of interests statement", "conflicts of interest statement",
        "conflicts of interest and financial disclosure",
    },
    "disclaimer": {"disclaimer", "disclaimers"},
    "presented_at": {
        "presented at", "previous presentations", "previous presentation",
        "prior presentations", "prior presentation",
    },
    "data_availability": {
        "data availability", "data availability statement",
        "data sharing statement", "availability of data and materials",
        "data access", "data statement", "data and code availability",
        "code availability", "access to data",
    },
    "ethics": {
        "ethics approval", "ethical approval", "ethics statement",
        "ethical considerations", "ethical consideration", "irb approval",
        "ethics approval and consent to participate", "ethics",
        "informed consent statement", "informed consent",
        "human subjects", "patient consent",
    },
    "credit_statement": {
        "credit author statement", "credit authorship statement",
        "credit authorship contribution statement", "credit statement",
        "author contributions", "author contribution", "authors contributions",
        "contribution statement", "authorship contributions",
        "author contribution statement", "credit", "authorship statement",
        "statement of authorship", "credit authorship contribution",
        "credit author contribution",
        "authors contribution", "author contributions credit",
        "author contribution credit", "contributors",
    },
    "references": {
        "references", "reference", "bibliography", "works cited",
        "literature cited", "references cited", "reference list",
    },
    "figure_legends": {
        "figure legends", "figure captions", "legends", "figure legend",
        "list of figures", "figure titles and legends", "figure",
        "figures",
    },
    "tables_section": {"tables", "list of tables", "table"},
    "appendix": {
        "appendix", "appendices", "appendixes", "supplementary appendix",
        "appendix materials", "appendix material",
    },
    "supplementary": {
        "supplementary material", "supplemental material",
        "supplementary materials", "supplemental materials",
        "supporting information", "supplementary information",
        "online supplement", "supplement", "online supplementary material",
        "supplementary data", "supplemental digital content",
    },
    "abbreviations": {
        "abbreviations", "list of abbreviations", "glossary",
        "abbreviations and acronyms", "abbreviation list",
    },
    "correspondence": {
        "corresponding author", "address correspondence to", "correspondence",
        "corresponding author address", "corresponding author email address",
        "correspondence to", "corresponding authors", "contact information",
        "address reprint requests to",
    },
    "affiliations": {
        "affiliations", "author affiliations", "affiliation",
        "authors affiliations",
    },
    "orcid": {"orcid", "orcid of authors", "orcids", "orcid ids"},
    "running_head": {"running head", "running title", "short title"},
    "title_page_marker": {
        "title page", "ajpm submission", "original article",
        "original research", "research article", "original investigation",
        "brief report", "research brief", "review article",
        "journal for submission", "manuscript", "main document",
        "article type",
        "cover page", "full title page", "complete title page",
        "manuscript title", "title", "research letter",
    },
    "authors_marker": {
        "authors", "author names", "author list", "authors and affiliations",
        "email address of authors", "email addresses of authors",
    },
    "word_count_marker": {
        "word count", "wordcount of main text", "word count of main text",
        "manuscript word count", "abstract word count", "current word count",
        "allowed word count", "manuscript information",
    },
}

# Types that may appear as an abstract's internal structured labels.
IMRAD_LABEL_TYPES = {
    "introduction", "objectives", "methods", "results", "discussion",
    "conclusions", "limitations", "results_and_discussion",
}

# Types that make sense as run-in labels ("Funding: text ...").
RUN_IN_LABEL_TYPES = {
    "abstract", "keywords", "highlights", "funding", "declaration_of_interest",
    "disclaimer", "presented_at", "data_availability", "ethics",
    "credit_statement", "correspondence", "affiliations", "running_head",
    "acknowledgments", "references",
} | IMRAD_LABEL_TYPES

# Types that normally begin the body of the article.
BODY_TYPES = {
    "introduction", "objectives", "methods", "results",
    "results_and_discussion", "discussion", "limitations", "conclusions",
    "implications", "recommendations", "future_work", "related_work",
}

# Back-matter statement types.
BACK_MATTER_TYPES = {
    "acknowledgments", "funding", "declaration_of_interest", "disclaimer",
    "presented_at", "data_availability", "ethics", "credit_statement",
    "abbreviations",
}

# Tail (post-references) types.
TAIL_TYPES = {
    "figure_legends", "tables_section", "appendix", "supplementary",
}

FRONT_TYPES = {
    "title_page_marker", "authors_marker", "word_count_marker", "orcid",
    "running_head", "correspondence", "affiliations", "title", "authors",
    "front_metadata", "front_other",
}

# Known Methods/Results/Discussion subsection names (typed subsections).
SUBSECTION_VOCAB: dict[str, set] = {
    "study_sample": {
        "study sample", "study population", "population", "participants",
        "sample", "setting", "study design and participants",
        "data and sample", "study design", "participants and setting",
        "study setting", "subjects", "study participants", "data source",
        "data sources", "data collection", "study cohort", "cohort",
        "survey sample",
    },
    "measures": {
        "measures", "measurements", "variables", "outcomes", "exposures",
        "covariates", "outcome measures", "measures and outcomes",
        "dependent variables", "independent variables", "instruments",
    },
    "statistical_analysis": {
        "statistical analysis", "statistical analyses", "analysis", "analyses",
        "data analysis", "data analyses", "statistical methods",
        "sensitivity analysis", "sensitivity analyses",
    },
    "framework": {
        "theoretical framework", "conceptual framework", "current study",
        "the current study", "present study", "the present study",
    },
    "procedures": {"procedures", "procedure", "intervention", "interventions"},
}

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
_WS_CHARS = "\u00a0\u200b\u200c\u200d\ufeff\u2007\u202f"

# Numbering prefixes. Bare numbers without punctuation are NOT stripped here
# (too risky: "2020 Rural-urban ...", street addresses); see match() which
# retries a bare-number strip only when the remainder is an exact match.
_NUM_DOTTED = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})[.):\]]?\s+")
_NUM_ROMAN = re.compile(r"^\s*([IVXLivxl]{1,7})[.):\]]\s+")
_NUM_ALPHA = re.compile(r"^\s*([A-Z])[.)]\s+")
_NUM_PAREN = re.compile(r"^\s*\((\d{1,2}|[a-z])\)\s+")
_NUM_BARE = re.compile(r"^\s*(\d{1,2})\s+")

_TRAIL_PUNCT = re.compile(r"[\s:;.\u2013\u2014-]+$")
_MD_WRAP = re.compile(r"^[*_#\s]+|[*_\s]+$")


def clean_ws(s: str) -> str:
    for ch in _WS_CHARS:
        s = s.replace(ch, " ")
    return s


def strip_numbering(s: str):
    """Return (rest, prefix) where prefix is a detected numbering prefix."""
    for rx in (_NUM_DOTTED, _NUM_ROMAN, _NUM_ALPHA, _NUM_PAREN):
        m = rx.match(s)
        if m:
            return s[m.end():], m.group(1)
    return s, ""


def normalize(s: str, strip_number: bool = True):
    """Normalize a potential heading. Returns (normalized, info dict)."""
    info = {"numbering": "", "had_colon": False, "had_period": False}
    s = clean_ws(unicodedata.normalize("NFKC", s)).strip()
    s = _MD_WRAP.sub("", s)
    if strip_number:
        s, info["numbering"] = strip_numbering(s)
    body = s.rstrip()
    if body.endswith(":"):
        info["had_colon"] = True
    elif body.endswith("."):
        info["had_period"] = True
    s = _TRAIL_PUNCT.sub("", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    s = s.replace("&", "and")
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("'", "")
    s = re.sub(r"[\"\u201c\u201d]", "", s)
    # unify hyphen spacing:  "e- mail" artifacts
    s = re.sub(r"\s*-\s*", "-", s)
    return s, info


# Reverse index: normalized variant -> canonical type. Longest-first for
# glued-prefix matching.
_VARIANT_TO_TYPE: dict[str, str] = {}
for _t, _vars in list(VOCAB.items()) + list(SUBSECTION_VOCAB.items()):
    for _v in _vars:
        # subsection vocab must not override major vocab on collision
        _VARIANT_TO_TYPE.setdefault(_v, _t)
_VARIANTS_BY_LEN = sorted(_VARIANT_TO_TYPE, key=len, reverse=True)

SUBSECTION_TYPES = set(SUBSECTION_VOCAB.keys())


def match(text: str):
    """Match text against the vocabulary.

    Returns dict(type, variant, method, numbering, had_colon) or None.
    method: 'exact' | 'exact_bare_number'
    """
    norm, info = normalize(text)
    if not norm:
        return None
    if norm in _VARIANT_TO_TYPE:
        return {
            "type": _VARIANT_TO_TYPE[norm], "variant": norm, "method": "exact",
            **info,
        }
    # bare-number numbering ("1 Introduction") accepted only on exact remainder
    m = _NUM_BARE.match(clean_ws(text).strip())
    if m:
        rest = clean_ws(text).strip()[m.end():]
        norm2, info2 = normalize(rest, strip_number=False)
        if norm2 in _VARIANT_TO_TYPE:
            info2["numbering"] = m.group(1)
            return {
                "type": _VARIANT_TO_TYPE[norm2], "variant": norm2,
                "method": "exact_bare_number", **info2,
            }
    return None


def match_glued_prefix(text: str):
    """Detect a vocabulary label glued to following content, an artifact of
    tracked-changes paragraph merging, e.g. 'FundingNone.' or
    'Declaration of interestNone.'.

    Requires: the variant is a prefix of the normalized text AND the original
    text continues with an uppercase letter, digit or ':' right after the
    matched prefix (no space), AND remainder is short-ish or starts a new
    sentence-like chunk. Returns dict or None. Deliberately conservative.
    """
    raw = clean_ws(unicodedata.normalize("NFKC", text)).strip()
    low = raw.lower().replace("&", "and")
    for variant in _VARIANTS_BY_LEN:
        if len(variant) < 5:
            continue  # too short to trust for glued matching
        if low.startswith(variant):
            nxt = raw[len(variant):len(variant) + 1]
            if nxt and (nxt.isupper() or nxt.isdigit() or nxt == ":"):
                t = _VARIANT_TO_TYPE[variant]
                if t in RUN_IN_LABEL_TYPES or t in BACK_MATTER_TYPES:
                    return {
                        "type": t, "variant": variant, "method": "glued",
                        "numbering": "", "had_colon": False,
                        "prefix_len": len(variant),
                    }
    return None


# ---------------------------------------------------------------------------
# Negative-evidence patterns (things that look like headings but are not)
# ---------------------------------------------------------------------------
CAPTION_RX = re.compile(
    r"^\s*(supplementa(?:l|ry)\s+)?(appendix\s+)?(online\s+)?"
    r"(table|figure|fig|scheme|box|exhibit|chart)\b\.?\s*"
    r"([0-9]{1,3}|[IVXivx]{1,5}|[A-Za-z])(?![A-Za-z])\s*[.:]",
    re.I,
)
METADATA_COUNT_RX = re.compile(
    r"^\s*(abstract word count|manuscript word count|"
    r"word ?count(?: of main text)?(?:\s*\([^)]{0,25}\))?|"
    r"current word count|allowed word count|total word count|"
    r"references|tables?|figures?|supplemental tables?|supplementary tables?|"
    r"appendices|tables?\s*/\s*figures?|number of (tables|figures|references))"
    r"\s*[:=\u2013\u2014-]?\s*[\d,]+\s*(words?)?\s*(\([^)]{0,60}\))?\s*$",
    re.I,
)
CONTACT_RX = re.compile(
    r"^\s*(phone|fax|tel|telephone|e-?mail(?:\s+address(?:es)?(?:\s+of\s+authors)?)?)\b",
    re.I,
)
EMAIL_RX = re.compile(r"\S+@\S+\.\S+")
ORCID_RX = re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dXx]\b")
DEGREES_RX = re.compile(
    r"\b(MD|PhD|MPH|MSPH|MS|MSc|MSN|MA|MBA|MBBS|MBChB|RN|BSN|DrPH|ScD|ScM|DO|DDS|"
    r"DMD|PharmD|DPhil|EdD|JD|BS|BA|BSc|FSA|FAAP|FACP|FRCP|CPH|MSW|MHS|MHSc|OTR|"
    r"PA-C|NP|DVM|MPA|MPP)(?=\d|\b)"  # allow glued superscript digits: "PhD2"
)
AFFIL_START_RX = re.compile(
    r"^\s*(from\s+the\b|from\s+<organization>|\d{1,2}\s*(?=[A-Z<])|<organization>)",
    re.I,
)
AFFIL_KEYWORD_RX = re.compile(
    r"\b(university|department|school|institute|institution|center|centre|"
    r"hospital|college|faculty|division|laboratory|clinic|foundation|ministry|"
    r"agency|inc\.?|llc)\b",
    re.I,
)
CORRESPONDENCE_RX = re.compile(
    r"^\s*[*\u2020\u2021]?\s*(address\s+correspondence|correspond(?:ing|ence)\b|"
    r"address\s+reprint)",
    re.I,
)
COPYEDIT_TAG_RX = re.compile(r"<(organization|city|state|country|zip)>", re.I)
REF_ENTRY_RX = re.compile(r"^\s*\[?\d{1,3}\s*[.)\]]\s*\S")
YEAR_RX = re.compile(r"\b(19|20)\d{2}\b")
DOI_URL_RX = re.compile(r"(doi|https?://|www\.)", re.I)
# Trailing abbreviation like "U.S.", "U.S.A.", "e.g." at end of a heading --
# a terminal period that does NOT indicate a sentence.
TRAILING_DOTTED_ABBREV_RX = re.compile(r"(?:\b[A-Za-z]\.){2,}$")
ABBREV_EXPANSION_RX = re.compile(
    r"^\s*[A-Za-z][A-Za-z0-9\-()/+]{0,14}\s*[:,]\s+\S"
)
# degree tokens that are also U.S. state codes / common words -- ambiguous
AMBIGUOUS_DEGREES = {"MA", "MS", "MD", "DO", "PA", "BS", "BA", "RN"}
# CRediT taxonomy roles after a "Name:" prefix
CREDIT_ROLE_RX = re.compile(
    r":.*\b(Conceptualization|Methodology|Investigation|Data [Cc]uration|"
    r"Writing|Supervision|Visualization|Validation|Formal [Aa]nalysis|"
    r"Funding [Aa]cquisition|Project [Aa]dministration|Resources|Software)\b")
