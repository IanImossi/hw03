"""
hw03_earnings.py

Pulls the four most recent earnings press releases (8-K, Item 2.02
"Results of Operations and Financial Condition") for five companies from
SEC EDGAR, extracts headline figures with regex, and saves them to
earnings_history.csv in the hw03 folder.

Run from the hw03 folder (with the .venv active):
    python hw03_earnings.py

Uses only the Python standard library, so no extra installs are needed.
"""

import csv
import html
import json
import re
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# SEC requires a descriptive User-Agent on every request.
HEADERS = {"User-Agent": "MIS3060 Villanova iimossi@villanova.edu"}

# The five companies to pull: (company name, ticker, CIK).
# Look up any CIK at https://www.sec.gov/edgar/searchedgar/companysearch
COMPANIES = [
    ("Apple Inc.", "AAPL", "320193"),
    ("Microsoft Corporation", "MSFT", "789019"),
    ("NVIDIA Corporation", "NVDA", "1045810"),
    ("JPMorgan Chase & Co.", "JPM", "19617"),
    ("Walmart Inc.", "WMT", "104169"),
]

FILINGS_PER_COMPANY = 4
NOT_FOUND = "NOT_FOUND"
OUTPUT_CSV = Path(__file__).resolve().parent / "earnings_history.csv"
CSV_COLUMNS = [
    "company", "ticker", "cik", "filing_date", "period",
    "revenue_reported", "eps_diluted", "net_income",
]

# SEC's fair-access limit is 10 requests/second; stay well under it.
REQUEST_PAUSE_SECONDS = 0.2


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
            # 429 / 5xx: back off and retry. Anything else: give up.
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

def get_earnings_filings(cik, limit=FILINGS_PER_COMPANY):
    """Return the most recent 8-K filings whose items include 2.02."""
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    data = json.loads(http_get(url))
    recent = data["filings"]["recent"]

    filings = []
    for i, form in enumerate(recent["form"]):
        items = recent["items"][i] or ""
        if form == "8-K" and "2.02" in items.split(","):
            filings.append({
                "accession": recent["accessionNumber"][i],
                "filing_date": recent["filingDate"][i],
                "primary_doc": recent["primaryDocument"][i],
            })
        if len(filings) == limit:
            break
    # "recent" is already sorted newest first.
    return filings


def filing_index_url(cik, accession):
    """Build the human-readable filing index URL for an accession number."""
    folder = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{folder}/{accession}-index.htm"


def find_press_release_url(cik, accession, primary_doc):
    """
    Read the filing index page and return the URL of the earnings press
    release exhibit (an .htm document of type EX-99.x, preferring EX-99.1).
    """
    index_html = http_get(filing_index_url(cik, accession))
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"

    # Each document row: <td>seq</td><td>description</td><td><a href=...>name</a></td><td>type</td>
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", index_html, flags=re.S | re.I)
    candidates = []
    for row in rows:
        link = re.search(r'href="([^"]+\.html?)"', row, flags=re.I)
        cells = [strip_tags(c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S | re.I)]
        if not link or not cells:
            continue
        href = link.group(1)
        # Links look like /Archives/edgar/data/.../file.htm or /ix?doc=/Archives/...
        href = href.split("doc=")[-1]
        name = href.rsplit("/", 1)[-1]
        doc_type = cells[3].upper() if len(cells) > 3 else ""
        candidates.append((name, doc_type))

    # 1st choice: EX-99.1; 2nd: any EX-99.x; 3rd: an .htm file named like ex99.
    for name, doc_type in candidates:
        if doc_type.startswith("EX-99.1"):
            return base + name
    for name, doc_type in candidates:
        if doc_type.startswith("EX-99"):
            return base + name
    for name, _ in candidates:
        if re.search(r"ex-?99", name, flags=re.I) and name != primary_doc:
            return base + name
    return None


# ---------------------------------------------------------------------------
# HTML -> plain text
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    """Collect visible text, putting table rows and block elements on new lines."""

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
        elif tag == "td" or tag == "th":
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
    """Strip HTML to plain text: one table row / paragraph per line."""
    parser = _TextExtractor()
    parser.feed(raw_html)
    text = "".join(parser.parts)
    text = html.unescape(text).replace("\xa0", " ").replace("​", "")
    text = text.replace("’", "'").replace("—", "-").replace("–", "-")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def strip_tags(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment))


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

NUM = r"\(?\$?\s*([\d,]+(?:\.\d+)?)\)?"
SCALE = {"billion": 1000.0, "million": 1.0, "thousand": 0.001}


def _to_float(num_str):
    return float(num_str.replace(",", ""))


def _table_unit_scale(text):
    """Most financial tables state '(in millions...)' or '(in thousands...)'."""
    if re.search(r"in thousands", text, flags=re.I):
        return 0.001
    return 1.0  # default: millions


def extract_period(text):
    patterns = [
        # "fourth quarter fiscal 2024", "second quarter of fiscal year 2025", "third quarter 2024"
        r"\b(first|second|third|fourth)[\s-]+quarter(?:\s+of)?(?:\s+fiscal)?(?:\s+year)?\s+(?:FY\s*)?\d{4}",
        # "fiscal 2025 fourth quarter"
        r"\bfiscal(?:\s+year)?\s+\d{4}\s+(first|second|third|fourth)\s+quarter",
        # "Q3 2024", "Q4 FY25", "Q1 fiscal 2026"
        r"\bQ[1-4]\s*(?:fiscal\s*|FY\s*)?'?\d{2,4}\b",
        # "quarter ended September 28, 2024"
        r"\bquarter\s+ended\s+[A-Z][a-z]+\s+\d{1,2},\s+\d{4}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip()
    return NOT_FOUND


def extract_revenue(text):
    """Quarterly revenue in millions of USD."""
    flat = re.sub(r"\s+", " ", text)
    # Prose: "revenue of $94.9 billion", "net sales were $143.3 billion", "Revenue was $65.6 billion"
    prose = re.search(
        r"\b(?:total\s+|net\s+|quarterly\s+)?(?:revenues?|net sales|sales)\b[^$.]{0,80}?\$\s?([\d,]+(?:\.\d+)?)\s*(billion|million)",
        flat, flags=re.I,
    )
    if prose:
        return round(_to_float(prose.group(1)) * SCALE[prose.group(2).lower()], 2)

    # Table: "Total net sales $ 94,930 $ 85,777" -> first number is the current quarter.
    scale = _table_unit_scale(text)
    for label in (r"Total net sales", r"Total net revenues?", r"Total revenues?", r"Net sales", r"Net revenues?", r"Revenues?"):
        match = re.search(rf"^{label}\b[^\d\n]*?{NUM}", text, flags=re.I | re.M)
        if match:
            return round(_to_float(match.group(1)) * scale, 2)
    return NOT_FOUND


def extract_eps(text):
    """Diluted earnings per share in USD."""
    flat = re.sub(r"\s+", " ", text)
    prose_patterns = [
        r"diluted (?:earnings|net income|EPS)[^$]{0,80}?\$\s?(\(?\d+\.\d{2}\)?)",
        r"\$\s?(\(?\d+\.\d{2}\)?) per diluted share",
        r"earnings per diluted share[^$]{0,40}?\$\s?(\(?\d+\.\d{2}\)?)",
        # Banks / retailers often just say "EPS of $4.37" or "GAAP EPS of $0.56"
        r"\b(?:GAAP\s+)?EPS\s+(?:of|was)\s+\$\s?(\(?\d+\.\d{2}\)?)",
    ]
    for pattern in prose_patterns:
        match = re.search(pattern, flat, flags=re.I)
        if match:
            return _signed(match.group(1))

    # Table row labelled "Diluted" whose first value looks like a per-share amount.
    match = re.search(r"^Diluted\b[^\d\n]*?(\(?\d+\.\d{2}\)?)", text, flags=re.I | re.M)
    if match:
        return _signed(match.group(1))
    return NOT_FOUND


def extract_net_income(text):
    """Net income in millions of USD (negative for a net loss)."""
    flat = re.sub(r"\s+", " ", text)
    prose = re.search(
        r"\bnet income\b[^$.]{0,80}?\$\s?([\d,]+(?:\.\d+)?)\s*(billion|million)",
        flat, flags=re.I,
    )
    if prose:
        return round(_to_float(prose.group(1)) * SCALE[prose.group(2).lower()], 2)

    scale = _table_unit_scale(text)
    match = re.search(rf"^Net (?:income|earnings)(?: \(loss\))?\s*\$?\s*(\(?[\d,]+(?:\.\d+)?\)?)", text, flags=re.I | re.M)
    if match:
        value = _signed(match.group(1).replace(",", ""))
        return round(value * scale, 2)
    return NOT_FOUND


def _signed(num_str):
    """'(1.23)' -> -1.23, '1.23' -> 1.23"""
    negative = num_str.startswith("(")
    value = float(num_str.strip("()").replace(",", ""))
    return -value if negative else value


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def fmt_millions(value):
    if value == NOT_FOUND:
        return NOT_FOUND
    if abs(value) >= 1000:
        return f"${value / 1000:,.2f}B"
    return f"${value:,.1f}M"


def fmt_eps(value):
    return NOT_FOUND if value == NOT_FOUND else f"${value:.2f}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_company(company, ticker, cik):
    rows = []
    try:
        filings = get_earnings_filings(cik)
    except Exception as err:  # network / JSON errors shouldn't stop other companies
        print(f"[{ticker}] ERROR reading submissions: {err}")
        return rows

    if not filings:
        print(f"[{ticker}] No 8-K Item 2.02 filings found.")

    for filing in filings:
        row = {
            "company": company,
            "ticker": ticker,
            "cik": cik,
            "filing_date": filing["filing_date"],
            "period": NOT_FOUND,
            "revenue_reported": NOT_FOUND,
            "eps_diluted": NOT_FOUND,
            "net_income": NOT_FOUND,
        }
        try:
            exhibit_url = find_press_release_url(cik, filing["accession"], filing["primary_doc"])
            if exhibit_url:
                text = html_to_text(http_get(exhibit_url))
                row["period"] = extract_period(text)
                row["revenue_reported"] = extract_revenue(text)
                row["eps_diluted"] = extract_eps(text)
                row["net_income"] = extract_net_income(text)
            else:
                print(f"[{ticker}] No press release exhibit in {filing_index_url(cik, filing['accession'])}")
        except Exception as err:
            print(f"[{ticker}] ERROR processing {filing['accession']}: {err}")

        print(
            f"[{ticker}] | {row['period']} | Revenue: {fmt_millions(row['revenue_reported'])}"
            f" | EPS: {fmt_eps(row['eps_diluted'])} | Net Income: {fmt_millions(row['net_income'])}"
        )
        rows.append(row)
    return rows


def main():
    all_rows = []
    for company, ticker, cik in COMPANIES:
        all_rows.extend(process_company(company, ticker, cik))

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in all_rows:
            # Belt and braces: never write a blank cell.
            writer.writerow({k: (NOT_FOUND if row.get(k) in (None, "") else row[k]) for k in CSV_COLUMNS})

    print(f"\nSaved {len(all_rows)} rows to {OUTPUT_CSV}")
    print("Revenue and net income are in millions of USD; EPS is USD per diluted share.")


if __name__ == "__main__":
    main()
