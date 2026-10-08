"""Readable names from QuickBooks' all-caps habit.

QuickBooks stores whatever the user typed, and decades of typing in caps is
common. FlowBooks can present ``ACME TOOLING, INC.`` as ``ACME Tooling, Inc.``
without damaging names that are already correct. The IIF import does it only
when the person importing asks (its "Change ALL-CAPS names" box), because the
word lists below cannot know every initialism a business uses.

Two rules keep this safe:

* Only a name with **no lowercase letter at all** is rewritten; in a
  ``Parent:Child`` name each side is judged on its own. Anything already
  mixed-case (``Contoso``, ``Model-X42``, ``illycaffè``) is returned
  untouched, because we cannot tell an intentional casing from a typo and
  guessing would corrupt it.
* Words that are acronyms or legal/entity forms keep their own casing, because
  ``.capitalize()`` would turn ``INC.`` into ``inc.`` and ``NYC`` into ``Nyc``.

Every other all-caps word becomes first-letter-upper, rest-lower, so
``ACME TOOLING, INC.`` reads ``ACME Tooling, Inc.`` — the initialism keeps its
caps, the ordinary words are retitled, and ``INC.`` keeps its legal casing.
"""

from __future__ import annotations

import re

# Legal and entity forms. These keep their own casing rather than being
# lower-cased, because ".capitalize()" would turn "INC." into "inc.". They are
# title-cased like ordinary words unless the firm writes them in caps.
LEGAL_FORMS_CAPS = {
    "LLC",
    "LLP",
    "L.L.C.",
    "L.L.P.",
    "DBA",
    "D/B/A",
    "PLLC",
    "PCLP",
    "LP",
    "L.P.",
    "PC",
    "P.C.",
}
LEGAL_FORMS_TITLE = {
    "INC": "Inc",
    "INC.": "Inc.",
    "CORP": "Corp",
    "CORP.": "Corp.",
    "CO": "Co",
    "CO.": "Co.",
    "LTD": "Ltd",
    "LTD.": "Ltd.",
    "LIMITED": "Limited",
    "COMPANY": "Company",
}

# Short function words that are legitimately upper-case in an all-caps name but
# are ordinary words, not acronyms. Without this, "OF" and "IN" survive as
# capitals and read as noise.
_CONNECTIVES = {
    "OF",
    "THE",
    "AND",
    "FOR",
    "TO",
    "IN",
    "ON",
    "AT",
    "BY",
    "OR",
    "A",
    "AN",
}

# Acronyms that are read as letters, not words. Anything here keeps its caps.
ACRONYMS = {
    "AT&T",
    "IBM",
    "NYC",
    "NYS",
    "USA",
    "US",
    "UK",
    "EU",
    "UN",
    "FBI",
    "IRS",
    "DMV",
    "FDNY",
    "NYPD",
    "MTA",
    "BART",
    "LIPA",
    "CUNY",
    "SUNY",
    "ACH",
    "PACS",
    "HDFC",
    "II",
    "III",
    "IV",
    "VI",
    "VII",
    "VIII",
    # Banks and card issuers whose names are conventionally written in caps.
    # Words that are also ordinary words in business names (BANK, WELLS,
    # FARGO, SHELL, CHEVRON, YORK, DOT) are not here: "BANK OF AMERICA" read
    # "BANK of America" and "NEW YORK LIFE" read "New YORK Life".
    "HSBC",
    "AMEX",
    "NA",  # National Association: "WELLS FARGO BANK NA"
    "USAA",
    "UPS",
    "USPS",
    "DHL",
    # Short product/model codes where a capital letter is the product name.
    "TC",
    "QSC",
    "MSC",
    "DSC",
    "MFP",
    "HP",
    "LG",
    "AC",
    "DC",
    # Initialisms that form part of a trading name. "JBC INTERNATIONAL, INC."
    # must read as "JBC International, Inc.", not "Jbc International, Inc.".
    "JBC",
    "GHP",
    "BMW",
    "KIA",
    "AOL",
    "SAP",
    "JPM",
    "AXA",
    "BNY",
    "PNC",
    "TD",
    "AXP",
    "BOFA",
    "ACME",
    # Common trading names and initialisms in US books.
    "AAA",
    "AARP",
    "ABC",
    "ADP",
    "ATM",
    "BP",
    "CBS",
    "CVS",
    "ESPN",
    "GE",
    "GM",
    "GNC",
    "HBO",
    "HR",
    "HVAC",
    "IHOP",
    "KFC",
    "NBC",
    "PTA",
    "TV",
    "YMCA",
    "YWCA",
    # Professional letters after a name: "SMITH DDS" -> "Smith DDS".
    "CPA",
    "DDS",
    "DMD",
    "DVM",
    "MD",
    "RN",
    # Payroll and ledger initialisms in account names: "TAXES:FICA".
    "AP",
    "AR",
    "COGS",
    "EFT",
    "FICA",
    "FSA",
    "FUTA",
    "HSA",
    "IRA",
    "PPP",
    "PTO",
    "SBA",
    "SDI",
    "SUI",
    "SUTA",
    "YTD",
    # State codes after a name ("ABC PLUMBING NJ"). Codes that are also words
    # or name parts (IN, OR, ME, HI, OH, OK, CO, DE, AL, MI, MO, MS, MT, PA) are
    # left out.
    "AK",
    "AZ",
    "CT",
    "FL",
    "GA",
    "IA",
    "IL",
    "KS",
    "KY",
    "MN",
    "NC",
    "ND",
    "NH",
    "NJ",
    "NM",
    "NV",
    "NY",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "VA",
    "VT",
    "WA",
    "WI",
    "WV",
    "WY",
    # A domain's leading label: "WWW.EXAMPLE.COM" reads as "WWW.Example.com",
    # not "Www.Example.com".
    "WWW",
}

# Names whose owners write them their own way.
BRANDS = {
    "FEDEX": "FedEx",
    "PAYPAL": "PayPal",
    "EBAY": "eBay",
    "LINKEDIN": "LinkedIn",
    "YOUTUBE": "YouTube",
    "QUICKBOOKS": "QuickBooks",
}

# A word is a run of letters/digits plus any of these internal marks.
_WORD_RE = re.compile(r"[A-Za-z0-9&'’./\\-]*")
_LITERAL_ESCAPE_RE = re.compile(r"\\n|\\r|\\t")


def _has_lowercase(text: str) -> bool:
    return any(c.islower() for c in text)


def _looks_like_code(word: str) -> bool:
    """True for product/model codes that must not be re-cased.

    ``MSC-3800`` and ``22QT`` are identifiers, not prose: lower-casing them
    (``Msc-3800``, ``22qt``) breaks the way a person would search for them.

    A digit in the word is the signal. An earlier version also froze any
    all-caps run of three or fewer letters, which wrongly caught ordinary words
    (``OF``, ``CO``, ``THE``) and real names (``CHASE``), so short initialisms
    are listed explicitly in ``ACRONYMS`` instead.
    """
    if not word:
        return False
    return any(c.isalpha() for c in word) and any(c.isdigit() for c in word)


def _smart_cap(core: str) -> str:
    """Capitalise the first letter of each apostrophe-delimited part, lower the rest.

    ``O'BRIEN`` becomes ``O'Brien``, not ``O'brien`` — a lower-cased surname
    particle reads as a typo. Words that should stay lower mid-name (``OF`` in
    ``DEPARTMENT OF FINANCE``) are handled by the caller before this is reached.

    A trailing ``'s`` is a possessive, not a name: ``SMITH'S`` becomes
    ``Smith's``, because a single letter after the apostrophe is a suffix. An
    apostrophe with nothing before it is an elision, not a possessive, so
    ``O'BRIEN`` still reads ``O'Brien``.
    """
    parts = re.split(r"(['’])", core)
    out: list[str] = []
    # True when the previous part was an apostrophe preceded by letters, so a
    # lone letter here is a possessive suffix. Applies to one part only.
    after_apostrophe = False
    for part in parts:
        if part in {"'", "’"}:
            out.append(part)
            after_apostrophe = bool(out[:-1])
            continue
        if not part:
            continue
        if after_apostrophe and len(part) == 1 and part.isalpha():
            # "SMITH'S" -> "Smith's", "O'BRIEN'S PUB" -> "O'Brien's Pub".
            out.append(part.lower())
        elif not out and len(part) >= 4 and part[:2].upper() == "MC" and part.isalpha():
            # "MCDONALD'S" -> "McDonald's", not "Mcdonald's".
            out.append("Mc" + part[2].upper() + part[3:].lower())
        else:
            # Every other part title-cases, which is what turns the elision in
            # "O'BRIEN" into "O'Brien".
            out.append(part[:1].upper() + part[1:].lower())
        after_apostrophe = False
    return "".join(out)


# Top-level domains. A domain's last label is never title-cased: "Amazon.com",
# never "Amazon.Com".
TLDS = {
    "COM",
    "NET",
    "ORG",
    "CO",
    "UK",
    "DE",
    "FR",
    "NL",
    "EU",
    "US",
    "CA",
    "INFO",
    "BIZ",
    "IO",
    "APP",
    "DEV",
}


def _retitle_host(token: str) -> str:
    """Case a dotted name the way a domain is written.

    ``AMAZON.COM`` -> ``Amazon.com``: the leading label is title-cased, interior
    labels are too, and the top-level domain is lower-cased. Known acronyms keep
    their caps, so ``WWW.EXAMPLE.COM`` -> ``WWW.Example.com`` and a label with a
    digit is an identifier and is left alone.
    """
    labels = token.split(".")
    if len(labels) < 2:
        return token

    def case(label: str, *, last: bool) -> str:
        if label.upper() in ACRONYMS or label.upper() in LEGAL_FORMS_CAPS:
            return label.upper()
        if any(c.isdigit() for c in label):
            return label  # "1AND1" is an identifier
        if last and label.upper() in TLDS:
            return label.lower()
        return _smart_cap(label)

    out = [case(labels[0], last=False)]
    out.extend(
        case(label, last=(i == len(labels) - 1))
        for i, label in enumerate(labels[1:], start=1)
    )
    return ".".join(out)


def _title_word(word: str, *, first_word: bool) -> str:
    """Title-case a single word unless it is an acronym or a legal form."""
    if not word:
        return word

    # A word glued to others by punctuation ("SMITH," "RANDALL") is split by the
    # caller; here we only need the leading run of characters that carries case.
    match = re.match(r"[^\W_]+(?:['’][^\W_]+)*", word, re.UNICODE)
    if not match:
        return word
    core = match.group(0)

    upper_core = core.upper()
    if upper_core in BRANDS:
        return BRANDS[upper_core] + word[match.end() :]
    if upper_core in ACRONYMS or upper_core in LEGAL_FORMS_CAPS:
        return word
    if _looks_like_code(core):
        return word
    if upper_core in _CONNECTIVES:
        # Ordinary words shouted by the caps habit. Mid-name they stay lower
        # ("DEPARTMENT OF FINANCE" -> "Department of Finance"); leading, they
        # are capitalised like any other first word.
        if first_word:
            return _smart_cap(core) + word[match.end() :]
        return core.lower() + word[match.end() :]
    if upper_core in LEGAL_FORMS_TITLE:
        return LEGAL_FORMS_TITLE[upper_core] + word[match.end() :]

    return _smart_cap(core) + word[match.end() :]


def _retitle_segment(segment: str) -> str:
    """Title-case each word of a segment, preserving every separator.

    A "word" here is a run of letters/digits with optional internal apostrophes.
    Anything else — spaces, slashes, hyphens, ampersands, commas, parentheses —
    is a separator and is copied through untouched, so ``JUDITH/RANDALL`` and
    ``ROOMS & RENT`` are cased word by word without disturbing the punctuation.
    """
    tokens = re.findall(r"[^\W_]+(?:['’][^\W_]+)*|[^\w\s]+|\s+", segment, re.UNICODE)
    out: list[str] = []
    word_index = 0
    for i, token in enumerate(tokens):
        if not token[0].isalnum():
            out.append(token)  # separator: space, slash, hyphen, comma, ...
            continue
        before = tokens[i - 1] if i else ""
        after = tokens[i + 1] if i + 1 < len(tokens) else ""
        if _is_initial(token, before, after):
            out.append(token)
        else:
            out.append(_title_word(token, first_word=(word_index == 0)))
        word_index += 1
    return "".join(out)


def _is_initial(word: str, before: str, after: str) -> bool:
    """Letters that stand for words keep their caps.

    A single letter beside a full stop is an initial (``N.A.``, ``S.I.``,
    ``J. SMITH``), and a short run joined to another by ``&`` or ``/`` with
    no space is an abbreviation (``AT&T``, ``H&R``, ``A/R``, ``C/O``,
    ``D/B/A``). Without this, the "A" of "N.A." and "A/R" and the "AT" of
    "AT&T" were taken for the ordinary words "a" and "at".
    """
    if not word.isalpha():
        return False
    if len(word) == 1 and (after.startswith(".") or before.endswith(".")):
        return True
    glued = after[:1] in {"&", "/"} or before[-1:] in {"&", "/"}
    return len(word) <= 3 and glued


def normalize_name(name: str | None) -> str | None:
    """Return ``name`` in readable case, or unchanged when it already is.

    >>> normalize_name("ACME TOOLING, INC.")
    'ACME Tooling, Inc.'
    >>> normalize_name("160 PARKING CORP")
    '160 Parking Corp'
    >>> normalize_name("Contoso")
    'Contoso'
    >>> normalize_name("AUTOMOBILE EXPENSE:GASOLINE")
    'Automobile Expense:Gasoline'
    """
    if not name:
        return name

    # A leading "=", "+", "-" or "@" marks a spreadsheet formula or a handle, not
    # prose. Re-casing those would both corrupt the guard the importer strips
    # ("'=HYPERLINK(1)" -> "=Hyperlink(1)") and can make a sheet treat the cell
    # as a formula, so they are returned untouched.
    if name[0] in "=+-@":
        return name

    # QuickBooks sometimes stores a literal two-character escape rather than a
    # real newline. That is a data defect, not a casing choice, so drop it
    # before deciding on case.
    cleaned = _LITERAL_ESCAPE_RE.sub("", name).strip()
    if not cleaned:
        return cleaned

    # Sub-accounts and jobs are "Parent:Child", and each side is a name of its
    # own, decided on its own: "BOB JONES:Kitchen" reads "Bob Jones:Kitchen",
    # the same "Bob Jones" the customer's own row "BOB JONES" becomes, so the
    # job still finds its customer.
    return ":".join(_normalize_part(part) for part in cleaned.split(":"))


def _normalize_part(cleaned: str) -> str:
    # Already mixed-case: leave it exactly as the user typed it.
    if _has_lowercase(cleaned):
        return cleaned

    # A whole name that is one dotted run is a domain. An apostrophe rules that
    # out — no real host contains one — so "ACME'S.COM" is a company name that
    # happens to end in a suffix, and is cased as words.
    if (
        "." in cleaned
        and "'" not in cleaned
        and "’" not in cleaned
        and not any(c.isspace() for c in cleaned)
    ):
        return _retitle_host(cleaned)

    return _retitle_segment(cleaned)
