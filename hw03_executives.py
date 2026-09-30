"""
hw03_executives.py

Finds executive / director changes (8-K Item 5.02, "Departure of Directors
or Certain Officers; Election of Directors; Appointment of Certain
Officers") filed in the past 12 months for five companies, extracts each
event with regex, and saves them to executive_events.csv in the hw03 folder.

Run from the hw03 folder (with the .venv active):
    python hw03_executives.py

Uses only the Python standard library.
"""

import csv
import html
import json
import re
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# SEC requires a descriptive User-Agent on every request (same as hw03_earnings.py).
HEADERS = {"User-Agent": "MIS3060 Villanova iimossi@villanova.edu"}

# (company name, ticker, CIK)
COMPANIES = [
    ("Apple Inc.", "AAPL", "320193"),
    ("Microsoft Corporation", "MSFT", "789019"),
    ("NVIDIA Corporation", "NVDA", "1045810"),
    ("JPMorgan Chase & Co.", "JPM", "19617"),
    ("Walmart Inc.", "WMT", "104169"),
]

LOOKBACK_DAYS = 365
NOT_FOUND = "NOT_FOUND"
OUTPUT_CSV = Path(__file__).resolve().parent / "executive_events.csv"
CSV_COLUMNS = [
    "company", "ticker", "cik", "filing_date", "event_type",
    "person_name", "title", "effective_date",
]
REQUEST_PAUSE_SECONDS = 0.2  # SEC fair-access limit is 10 requests/second


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def http_get(url, retries=3):
    """GET a URL with the SEC User-Agent header and return the body as text."""
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
            time.sleep(REQUEST_PAUSE_SECONDS)
            return body.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as err:
            if err.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 * attempt)
                continue
            raise
        except urllib.error.URLError:
            if attempt < retries:
                time.sleep(2 * attempt)
                continue
            raise


# ---------------------------------------------------------------------------
# EDGAR lookups
# ---------------------------------------------------------------------------

def get_502_filings(cik, since):
    """Return 8-K filings with Item 5.02 filed on or after `since` (a date)."""
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    recent = json.loads(http_get(url))["filings"]["recent"]

    filings = []
    for i, form in enumerate(recent["form"]):
        filed = date.fromisoformat(recent["filingDate"][i])
        if filed < since:
            break  # list is newest first, so everything after is older
        items = (recent["items"][i] or "").split(",")
        if form == "8-K" and "5.02" in items:
            filings.append({
                "accession": recent["accessionNumber"][i],
                "filing_date": recent["filingDate"][i],
                "report_date": recent["reportDate"][i] or "",
                "primary_doc": recent["primaryDocument"][i],
            })
    return filings


def filing_document_url(cik, accession, document):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{document}"


# ---------------------------------------------------------------------------
# HTML -> plain text
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    BLOCK_TAGS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table"}
    SKIP_TAGS = {"script", "style", "head", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(raw_html):
    parser = _TextExtractor()
    parser.feed(raw_html)
    text = html.unescape("".join(parser.parts))
    for bad, good in {"\xa0": " ", "​": "", "’": "'", "“": '"',
                      "”": '"', "—": "-", "–": "-"}.items():
        text = text.replace(bad, good)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

MONTHS = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
DATE_RE = rf"{MONTHS}\s+\d{{1,2}},\s+\d{{4}}"

DEPARTURE_RE = re.compile(
    r"\b(resign(?:s|ed|ing|ation)?|retire(?:s|d|ment)?|retiring|depart(?:s|ed|ure)?|"
    r"step(?:s|ped)? down|stepping down|terminat(?:e|ed|ion)|separat(?:e|ed|ion)|"
    r"will not stand for re-?election|not to stand for re-?election|"
    r"cease(?:s|d)? to serve|leav(?:e|es|ing) the Company|transition(?:ing)? out)\b",
    re.I,
)
APPOINTMENT_RE = re.compile(
    r"\b(appoint(?:s|ed|ing|ment)?|elect(?:s|ed|ion)?|named|promot(?:e|ed|ion)|"
    r"hired|will join|joined|to serve as|will serve as|will become|has been designated)\b",
    re.I,
)
SUCCEEDING_RE = re.compile(
    r"\b(?:succeed(?:s|ing)?|replac(?:e|es|ing)|in place of)\s+"
    r"(?:(?:Mr|Ms|Mrs|Dr)\.\s+)?([A-Z][A-Za-z'\-]+(?:\s+[A-Z]\.)?(?:\s+[A-Z][A-Za-z'\-]+)?)"
)

TITLE_UNIT = (
    r"(?:(?:Senior|Executive|Group|Corporate|Lead|Independent)\s+)*"
    r"(?:Vice\s+Chair(?:man)?|Vice\s+President|President|"
    r"Chief\s+(?:[A-Z][a-z]+\s+){1,3}Officer|"
    r"Chair(?:man|woman)?(?:\s+of\s+the\s+Board)?|Treasurer|Controller|Corporate\s+Secretary|Secretary|"
    r"General\s+Counsel|Principal\s+(?:Accounting|Financial|Executive|Operating)\s+Officer|"
    r"(?:member\s+of\s+the\s+)?Board\s+of\s+Directors|[Dd]irector)"
)
TITLE_RE = re.compile(
    rf"{TITLE_UNIT}(?:\s*(?:,|and|&)\s*(?:the\s+)?{TITLE_UNIT})*"
    r"(?:\s*(?:,\s*)?of\s+(?:the\s+)?[A-Z][A-Za-z&]+(?:\s+[A-Z][A-Za-z&]+)*)?"
)

# Capitalised words that look like names but aren't.
NOT_NAME_WORDS = {
    "The", "Company", "Company's", "Board", "Directors", "Director", "Inc", "Corporation", "Corp",
    "Chief", "Officer", "Executive", "Financial", "Operating", "Accounting", "Legal", "People",
    "President", "Vice", "Senior", "Chair", "Chairman", "Committee", "Compensation", "Audit",
    "Nominating", "Governance", "Item", "Form", "Section", "Exhibit", "Agreement", "Plan",
    "Securities", "Exchange", "Act", "Commission", "Stock", "Annual", "Meeting", "Shareholders",
    "Stockholders", "General", "Counsel", "Secretary", "Treasurer", "Controller", "Principal",
    "On", "In", "As", "Effective", "Following", "Pursuant", "Upon", "There", "No", "Mr", "Ms",
    "Mrs", "Dr", "Apple", "Microsoft", "NVIDIA", "Nvidia", "JPMorgan", "Chase", "Walmart", "Bank",
    "America", "United", "States", "Delaware", "New", "York", "California", "Arkansas", "Washington",
    "Departure", "Election", "Appointment", "Certain", "Officers", "Compensatory", "Arrangements",
    "Interim", "Global", "Group", "Operations", "Technology", "Information", "Human", "Resources",
    *(m for m in MONTHS.strip("(?:)").split("|")),
}
NAME_RE = re.compile(
    r"\b(?:(?:Mr|Ms|Mrs|Dr)\.\s+)?"
    r"([A-Z][a-z][A-Za-z'\-]+(?:\s+[A-Z]\.)?(?:\s+[A-Z][a-z][A-Za-z'\-]+){1,2}(?:,?\s+(?:Jr|Sr|III|II)\.?)?)"
)
HONORIFIC_SURNAME_RE = re.compile(r"\b(?:Mr|Ms|Mrs|Dr)\.\s+([A-Z][A-Za-z'\-]+)")


def item_502_section(text):
    """Return the text of Item 5.02 up to the next Item heading or signature block."""
    start = re.search(r"Item\s*5\.02", text, flags=re.I)
    if not start:
        return text
    rest = text[start.end():]
    end = re.search(r"\n\s*Item\s*\d\.\d{2}|\nSIGNATURES?\b", rest, flags=re.I)
    return rest[: end.start()] if end else rest


def split_sentences(section):
    flat = re.sub(r"\s+", " ", section)
    # Protect abbreviations so we don't split on them.
    protected = re.sub(r"\b(Mr|Ms|Mrs|Dr|Jr|Sr|Inc|Co|Corp|No|St)\.", r"\1<DOT>", flat)
    protected = re.sub(r"\b([A-Z])\.(?=\s+[A-Z])", r"\1<DOT>", protected)  # middle initials
    parts = re.split(r"(?<=[.;])\s+(?=[A-Z\"(])", protected)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


def is_name(candidate):
    words = re.findall(r"[A-Za-z'\-]+", candidate)
    return len(words) >= 2 and not any(w in NOT_NAME_WORDS for w in words)


def names_in(sentence, known):
    """Full names in a sentence, in order. 'Mr. Smith' resolves to a known full name."""
    found = []
    for match in NAME_RE.finditer(sentence):
        name = match.group(1).strip().rstrip(",")
        if is_name(name):
            found.append((match.start(), name))
            known.setdefault(name.split()[-1].rstrip(".,"), name)
    for match in HONORIFIC_SURNAME_RE.finditer(sentence):
        full = known.get(match.group(1))
        if full and all(full != n for _, n in found):
            found.append((match.start(), full))
    return [name for _, name in sorted(found)]


def title_in(sentence):
    # Prefer the role the sentence assigns: "as (the Company's) Chief Financial Officer",
    # "to the role of Vice Chair". Fall back to the first title anywhere in the sentence.
    lead_in = re.search(
        r"\b(?:as|to the (?:role|position) of)\s+(?:a\s+|an\s+|the\s+|its\s+|the\s+Company's\s+)?(?=[A-Za-z])",
        sentence,
    )
    match = None
    if lead_in:
        match = TITLE_RE.match(sentence, lead_in.end())
    match = match or TITLE_RE.search(sentence)
    if not match:
        return None
    title = re.sub(r"\s+", " ", match.group(0)).strip(" ,")
    return title[0].upper() + title[1:]


def effective_date_in(sentence, report_date):
    match = re.search(rf"effective\s+(?:as\s+of\s+|on\s+)?({DATE_RE})", sentence, flags=re.I)
    if match:
        return _iso(match.group(1))
    if re.search(r"effective\s+immediately", sentence, flags=re.I) and report_date:
        return report_date
    match = re.search(rf"\b(?:on|as of)\s+({DATE_RE})", sentence)
    if match:
        return _iso(match.group(1))
    return None


def _iso(date_text):
    from datetime import datetime
    try:
        return datetime.strptime(re.sub(r"\s+", " ", date_text), "%B %d, %Y").date().isoformat()
    except ValueError:
        return date_text


def extract_events(text, report_date):
    """
    Return a list of events: {event_type, person_name, title, effective_date}.
    One event per person; a person who both leaves one role and takes another
    in the same filing is recorded as "both".
    """
    section = item_502_section(text)
    known_surnames = {}
    people = {}  # name -> {"departure": bool, "appointment": bool, "title": str, "date": str}

    def record(name, kind, sentence):
        info = people.setdefault(name, {"departure": False, "appointment": False, "title": None, "date": None})
        info[kind] = True
        info["title"] = info["title"] or title_in(sentence)
        info["date"] = info["date"] or effective_date_in(sentence, report_date)

    for sentence in split_sentences(section):
        departing = bool(DEPARTURE_RE.search(sentence))
        appointing = bool(APPOINTMENT_RE.search(sentence))
        if not (departing or appointing):
            continue
        names = names_in(sentence, known_surnames)
        if not names:
            continue

        # "... appointed Jane Doe as CFO, succeeding John Smith" -> Smith departs.
        successor_target = SUCCEEDING_RE.search(sentence)
        replaced = None
        if successor_target:
            target = successor_target.group(1)
            replaced = known_surnames.get(target.split()[-1], target) if is_name(target) or target in known_surnames else None
            if replaced:
                record(replaced, "departure", sentence)

        subject = next((n for n in names if n != replaced), None)
        if not subject:
            continue
        if departing and not (appointing and replaced):
            record(subject, "departure", sentence)
        if appointing:
            record(subject, "appointment", sentence)

    events = []
    for name, info in people.items():
        if info["departure"] and info["appointment"]:
            event_type = "both"
        elif info["departure"]:
            event_type = "departure"
        else:
            event_type = "appointment"
        events.append({
            "event_type": event_type,
            "person_name": name,
            "title": info["title"] or NOT_FOUND,
            "effective_date": info["date"] or NOT_FOUND,
        })
    return events


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_company(company, ticker, cik, since):
    rows = []
    try:
        filings = get_502_filings(cik, since)
    except Exception as err:
        print(f"[{ticker}] ERROR reading submissions: {err}")
        return rows

    if not filings:
        print(f"[{ticker}]: No executive events in past 12 months")
        return rows

    for filing in filings:
        base = {"company": company, "ticker": ticker, "cik": cik, "filing_date": filing["filing_date"]}
        try:
            url = filing_document_url(cik, filing["accession"], filing["primary_doc"])
            events = extract_events(html_to_text(http_get(url)), filing["report_date"])
        except Exception as err:
            print(f"[{ticker}] ERROR processing {filing['accession']}: {err}")
            events = []

        if not events:
            # Item 5.02 is also used for pay/plan changes with no one joining or leaving.
            # Keep a row so the filing is still accounted for.
            events = [{"event_type": NOT_FOUND, "person_name": NOT_FOUND,
                       "title": NOT_FOUND, "effective_date": NOT_FOUND}]

        for event in events:
            row = {**base, **event}
            print(f"[{ticker}] | {row['filing_date']} | {row['event_type']} | {row['person_name']} | {row['title']}")
            rows.append(row)
    return rows


def main():
    since = date.today() - timedelta(days=LOOKBACK_DAYS)
    print(f"Looking for 8-K Item 5.02 filings since {since.isoformat()}\n")

    all_rows = []
    for company, ticker, cik in COMPANIES:
        all_rows.extend(process_company(company, ticker, cik, since))

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({k: (NOT_FOUND if row.get(k) in (None, "") else row[k]) for k in CSV_COLUMNS})

    print(f"\nSaved {len(all_rows)} events to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
