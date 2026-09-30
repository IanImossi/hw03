"""
hw03_timeline.py

Lines up executive events (executive_events.csv) against earnings
announcements (earnings_history.csv) for each company and saves the
combined table to corporate_events_timeline.csv in the hw03 folder.

Run from the hw03 folder (with the .venv active), after running
hw03_earnings.py and hw03_executives.py:
    python hw03_timeline.py

Column notes
  days_to_nearest_earnings  absolute number of days between the executive
                            event's filing_date and the closest earnings
                            filing_date for the same company
  event_timing              'same week'       within 7 days of that earnings filing
                            'before earnings' more than 7 days before it
                            'after earnings'  more than 7 days after it
  earnings_filing_date,     columns from the matched (nearest) earnings row
  period, revenue_reported,
  eps_diluted, net_income
"""

from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
EARNINGS_CSV = HERE / "earnings_history.csv"
EVENTS_CSV = HERE / "executive_events.csv"
OUTPUT_CSV = HERE / "corporate_events_timeline.csv"

NOT_FOUND = "NOT_FOUND"
SAME_WEEK_DAYS = 7
KEY_COLUMNS = ["company", "ticker", "cik"]


def load_tables():
    # dtype=str keeps "NOT_FOUND" and CIKs exactly as written.
    earnings = pd.read_csv(EARNINGS_CSV, dtype=str, keep_default_na=False)
    events = pd.read_csv(EVENTS_CSV, dtype=str, keep_default_na=False)
    earnings["_date"] = pd.to_datetime(earnings["filing_date"], errors="coerce")
    events["_date"] = pd.to_datetime(events["filing_date"], errors="coerce")
    return earnings, events


def classify(event_date, earnings_date):
    """Return (days_between, timing) for one event vs. its nearest earnings date."""
    signed_days = (event_date - earnings_date).days  # negative -> event came first
    if abs(signed_days) <= SAME_WEEK_DAYS:
        timing = "same week"
    elif signed_days < 0:
        timing = "before earnings"
    else:
        timing = "after earnings"
    return abs(signed_days), timing


def build_timeline(earnings, events):
    earnings_cols = [c for c in earnings.columns if c not in KEY_COLUMNS + ["_date"]]
    rows = []

    for _, event in events.iterrows():
        row = event.drop(labels="_date").to_dict()
        company_earnings = earnings[(earnings["cik"] == event["cik"]) & earnings["_date"].notna()]

        if company_earnings.empty or pd.isna(event["_date"]):
            # Nothing to compare against: record that explicitly rather than leaving blanks.
            for col in earnings_cols:
                row["earnings_filing_date" if col == "filing_date" else col] = NOT_FOUND
            row["days_to_nearest_earnings"] = NOT_FOUND
            row["event_timing"] = NOT_FOUND
        else:
            gaps = (company_earnings["_date"] - event["_date"]).abs()
            nearest = company_earnings.loc[gaps.idxmin()]
            for col in earnings_cols:
                row["earnings_filing_date" if col == "filing_date" else col] = nearest[col]
            days, timing = classify(event["_date"], nearest["_date"])
            row["days_to_nearest_earnings"] = days
            row["event_timing"] = timing
        rows.append(row)

    event_cols = [c for c in events.columns if c != "_date"]
    matched_cols = ["earnings_filing_date" if c == "filing_date" else c for c in earnings_cols]
    columns = event_cols + matched_cols + ["days_to_nearest_earnings", "event_timing"]
    return pd.DataFrame(rows, columns=columns)


def print_summary(timeline, earnings, events):
    # Rows with event_type NOT_FOUND are Item 5.02 filings where no one joined or left
    # (e.g. pay approvals). They stay in the CSV but aren't counted as executive events.
    real = timeline[timeline["event_type"] != NOT_FOUND]
    skipped = len(timeline) - len(real)

    companies = (
        pd.concat([earnings[KEY_COLUMNS], events[KEY_COLUMNS]])
        .drop_duplicates(subset="ticker")
        .itertuples(index=False)
    )

    print("=" * 72)
    print("EXECUTIVE EVENTS VS. EARNINGS ANNOUNCEMENTS")
    print("=" * 72)
    for company, ticker, _ in companies:
        print(f"\n{company} ({ticker})")
        company_events = real[real["ticker"] == ticker]
        if company_events.empty:
            print("  No executive events in past 12 months")
            continue
        for _, e in company_events.sort_values("filing_date").iterrows():
            if e["event_timing"] == NOT_FOUND:
                where = "no earnings filing to compare against"
            elif e["event_timing"] == "same week":
                where = f"same week as earnings on {e['earnings_filing_date']} ({e['days_to_nearest_earnings']} days apart)"
            else:
                where = f"{e['days_to_nearest_earnings']} days {e['event_timing']} on {e['earnings_filing_date']}"
            print(f"  {e['filing_date']}  {e['event_type']:<11} {e['person_name']} ({e['title']})")
            print(f"              -> {where}")

    counts = real["event_timing"].value_counts()
    before = int(counts.get("before earnings", 0))
    after = int(counts.get("after earnings", 0))
    same_week = int(counts.get("same week", 0))

    print("\n" + "=" * 72)
    print("TOTALS ACROSS ALL COMPANIES")
    print("=" * 72)
    print(f"  Before an earnings announcement: {before}")
    print(f"  After an earnings announcement:  {after}")
    print(f"  Same week as earnings (±{SAME_WEEK_DAYS} days): {same_week}")
    print(f"  Total executive events:          {len(real)}")
    if skipped:
        print(f"\n  ({skipped} Item 5.02 filing(s) with no departure/appointment were left out of these counts.)")


def main():
    for path in (EARNINGS_CSV, EVENTS_CSV):
        if not path.exists():
            raise SystemExit(f"Missing {path.name}. Run hw03_earnings.py and hw03_executives.py first.")

    earnings, events = load_tables()
    timeline = build_timeline(earnings, events)
    timeline.to_csv(OUTPUT_CSV, index=False)

    print_summary(timeline, earnings, events)
    print(f"\nSaved {len(timeline)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
