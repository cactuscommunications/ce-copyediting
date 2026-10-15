# import re


# def format_authors(authors: list[str]) -> str:
#     """
#     Format author names as:
#         Surname Initials

#     Rules:
#     - Up to 6 authors: include all
#     - More than 6 authors: include first 3 + "et al."
    
#     Examples:
#         ["Alan H Hirai", "Wendy M Sappenfield", "Michael D Kogan"]
#         -> "Hirai AH, Sappenfield WM, Kogan MD"

#         > 6 authors
#         -> "Hirai AH, Sappenfield WM, Kogan MD, et al."
#     """

#     if not authors:
#         return ""

#     # Normalize and remove empty names
#     authors = [a.strip() for a in authors if a and a.strip()]

#     # Format each author
#     formatted = [_format_author_name(author) for author in authors]

#     if len(formatted) > 6:
#         return ", ".join(formatted[:3]) + ", et al."

#     return ", ".join(formatted) + '.'


# def _format_author_name(author: str) -> str:
#     """
#     Convert an author name into:
#         Surname Initials

#     Handles:
#         Alan H Hirai
#         Hirai AH
#         Hirai, Alan H
#         Hirai, AH
#         Alan H. Hirai
#         Alan Hirai
#     """

#     author = re.sub(r"\s+", " ", author.strip())

#     # ---------------------------------------------------------
#     # Format: Surname, Given Middle
#     # ---------------------------------------------------------
#     if "," in author:
#         surname, given = [x.strip() for x in author.split(",", 1)]

#         initials = _get_initials(given)

#         return f"{surname} {initials}".strip()

#     # ---------------------------------------------------------
#     # Format: Given Middle Surname
#     # Assume last token is surname
#     # ---------------------------------------------------------
#     parts = author.split()

#     if len(parts) == 1:
#         return parts[0]

#     surname = parts[-1]
#     given_names = parts[:-1]

#     initials = _get_initials(" ".join(given_names))

#     return f"{surname} {initials}".strip()


# def _get_initials(name: str) -> str:
#     """
#     Extract initials from given/middle names.

#     Examples:
#         'Alan H'       -> 'AH'
#         'Alan Henry'   -> 'AH'
#         'A. H.'        -> 'AH'
#         'Alan H.'      -> 'AH'
#     """

#     ACCEPTED_SURNAMES = ['de', 'da']
#     # Remove periods
#     name = name.replace(".", "")

#     parts = name.split()

#     initials = []

#     for part in parts:
#         if part in ACCEPTED_SURNAMES:
#             initials.append(f' {part} ')
#             continue
#         # Handle hyphenated names: Jean-Pierre -> JP
#         elif "-" in part:
#             initials.extend(
#                 p[0].upper()
#                 for p in part.split("-")
#                 if p
#             )
#         elif part:
#             initials.append(part[0].upper())

#     return "".join(initials)


import re


def format_authors(authors: list[str]) -> str:
    """
    Format authors as:

        Surname Initials

    Up to 6 authors:
        Author 1, Author 2, ...

    More than 6 authors:
        Author 1, Author 2, Author 3, et al.

    Examples:
        Rafael de Morais Cury
            -> Cury R de M

        Taynara da Silva
            -> da Silva T

        Fernando Cezar‐dos‐Santos
            -> Cezar-dos-Santos F
    """

    if not authors:
        return ""

    authors = [
        re.sub(r"\s+", " ", author.strip())
        for author in authors
        if author and author.strip()
    ]

    # Normalize Unicode hyphens
    authors = [
        re.sub(r"[‐-‒–—]", "-", author)
        for author in authors
    ]

    formatted = [_format_author(author) for author in authors]

    if len(formatted) > 6:
        return ", ".join(formatted[:3]) + ", et al."

    return ", ".join(formatted) + "."


def _format_author(author: str) -> str:
    """
    Convert:

        Rafael de Morais Cury
        -> Cury R de M

        Taynara da Silva
        -> da Silva T

        Fernando Cezar-dos-Santos
        -> Cezar-dos-Santos F
    """

    parts = author.split()

    if not parts:
        return ""

    # Handle explicit "Surname, Given Names" format
    if "," in author:
        surname, given = [
            x.strip()
            for x in author.split(",", 1)
        ]

        initials = _extract_initials(given)

        return f"{surname} {initials}".strip()

    # ---------------------------------------------------------
    # Find surname
    #
    # A lowercase-starting component belongs with the surname.
    #
    # Rafael de Morais Cury
    #   Rafael  -> given name
    #   de      -> surname particle
    #   Morais  -> given/middle name
    #   Cury    -> surname
    #
    # Taynara da Silva
    #   Taynara -> given name
    #   da      -> surname particle
    #   Silva   -> surname
    # ---------------------------------------------------------

    surname_index = _find_surname_index(parts)

    surname_parts = parts[surname_index:]

    given_parts = parts[:surname_index]

    # Lowercase particles immediately before the surname are
    # part of the surname.
    #
    # For "Rafael de Morais Cury":
    # surname_index = 3
    # surname = Cury
    # given = Rafael de Morais
    #
    # But "de" should remain after the initials:
    # Cury R de M

    surname = " ".join(surname_parts)

    initials = _format_given_names(given_parts)

    return f"{surname} {initials}".strip()


def _find_surname_index(parts: list[str]) -> int:
    """
    Determine where the surname begins.

    Rules:
    - Last component is always part of surname.
    - Lowercase components immediately preceding the final
      uppercase component are surname particles.
    - For:
          Taynara da Silva
      surname = "da Silva"

    - For:
          Rafael de Morais Cury
      surname = "Cury"
    """

    if len(parts) <= 1:
        return 0

    # The final component is the core surname.
    surname_index = len(parts) - 1

    # Include lowercase particles directly before the final
    # surname, e.g. "da Silva", "van Gogh".
    while surname_index > 0:
        previous = parts[surname_index - 1]

        if _starts_lowercase(previous):
            surname_index -= 1
        else:
            break

    return surname_index


def _format_given_names(parts: list[str]) -> str:
    """
    Convert given/middle names while preserving lowercase
    particles in their original position.

    Rafael de Morais
        -> R de M

    Fernando John
        -> FJ
    """

    result = []

    for part in parts:
        if _starts_lowercase(part):
            # Preserve lowercase particles exactly
            result.append(part)
        else:
            # Generate initial from uppercase-starting component
            result.append(part[0].upper())

    return "".join(result)


def _extract_initials(name: str) -> str:
    """
    Used for explicit surname-first format:

        Cury, Rafael de Morais
            -> R de M
    """

    parts = name.split()
    result = []

    for part in parts:
        if _starts_lowercase(part):
            result.append(part)
        else:
            result.append(part[0].upper())

    return " ".join(result)


def _starts_lowercase(value: str) -> bool:
    """
    Check whether the first alphabetic character is lowercase.
    """

    for char in value:
        if char.isalpha():
            return char.islower()

    return False