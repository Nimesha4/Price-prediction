"""
Cinnamon Price Extractor
=========================
Scrapes weekly Producers' Prices reports from exagri.info (2016-2026),
extracts the CINNAMON table, and keeps only the requested grades
(Alba, C-5, C-4, H-2), producing one clean long-format CSV/Excel file:

    Date | Year | Month | Week | District | Grade | Highest_Price | Average_Price

Run:
    pip install -r requirements.txt
    python main.py
"""

import re
import time
import logging
import io
from datetime import datetime
from difflib import get_close_matches

import requests
from bs4 import BeautifulSoup
import pandas as pd

from config import (
    INDEX_URL,
    TARGET_GRADES,
    INCLUDE_NATIONAL_ROW,
    OUTPUT_DIR,
    OUTPUT_CSV,
    OUTPUT_XLSX,
    FAILED_URLS_FILE,
    LOG_FILE,
    REQUEST_DELAY_SECONDS,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

MONTHS_FULL = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


# --------------------------------------------------------------------------
# Step 1: get every (date, url) pair for weekly reports from the index page
# --------------------------------------------------------------------------

def closest_month(month_str: str):
    """Fuzzy-match month names to tolerate typos in the source (e.g. 'Augustr')."""
    matches = get_close_matches(month_str.lower(), MONTHS_FULL, n=1, cutoff=0.6)
    return MONTHS_FULL.index(matches[0]) + 1 if matches else None


def parse_date_from_text(text: str):
    """Parse dates like '07-July-2026', '16-may-2017', '05-November2019'."""
    text = text.strip()
    match = re.match(r"(\d{1,2})[.\-\s]*([A-Za-z]+)[.\-\s]*(\d{4})", text)
    if not match:
        return None
    day, month_str, year = match.groups()
    month = closest_month(month_str)
    if month is None:
        return None
    try:
        return datetime(int(year), month, int(day)).date()
    except ValueError:
        return None


def parse_date_from_url(url: str):
    """Fallback: try to pull a dd.mm.yyyy pattern out of the URL itself."""
    match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\.html", url)
    if match:
        day, month, year = match.groups()
        try:
            return datetime(int(year), int(month), int(day)).date()
        except ValueError:
            return None
    return None


def get_week_links(index_url: str):
    logger.info("Fetching index page: %s", index_url)
    resp = session.get(index_url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    links = []
    seen_urls = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.endswith(".html"):
            continue
        full_url = requests.compat.urljoin(index_url, href)
        if full_url in seen_urls:
            continue

        text = a.get_text(strip=True)
        date = parse_date_from_text(text) or parse_date_from_url(full_url)
        if date is None:
            logger.warning("Could not determine date for link text=%r url=%s -- skipped", text, full_url)
            continue

        seen_urls.add(full_url)
        links.append({"date": date, "url": full_url})

    links.sort(key=lambda d: d["date"])
    logger.info("Found %d weekly report links", len(links))
    return links


# --------------------------------------------------------------------------
# Step 2: extract the CINNAMON table from a single weekly page
# --------------------------------------------------------------------------

def extract_cinnamon_table(html: str, page_url: str):
    soup = BeautifulSoup(html, "html.parser")

    heading = None
    for tag in soup.find_all(["h3", "h4", "b", "strong", "th", "td"]):
        if tag.get_text(strip=True).upper() == "CINNAMON":
            heading = tag
            break
    if heading is None:
        logger.warning("No CINNAMON heading found on %s", page_url)
        return None

    table_tag = heading.find_next("table")
    if table_tag is None:
        logger.warning("No table found after CINNAMON heading on %s", page_url)
        return None

    try:
        df = pd.read_html(io.StringIO(str(table_tag)))[0]
    except ValueError:
        logger.warning("Could not parse CINNAMON table on %s", page_url)
        return None

    return df


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Turn either a MultiIndex header or a flat 'Alba (Highest Price)' style
    header into consistent 'Grade|Highest Price' / 'Grade|Average Price' names."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [f"{str(a).strip()}|{str(b).strip()}" for a, b in df.columns]
    else:
        new_cols = []
        for c in df.columns:
            m = re.match(r"(.+?)\s*\((Highest|Average)\s*Price\)", str(c))
            if m:
                new_cols.append(f"{m.group(1).strip()}|{m.group(2)} Price")
            else:
                new_cols.append(str(c).strip())
        df.columns = new_cols
    return df


def clean_price(value):
    s = str(value).strip()
    if s.lower() in ("-", "", "nan", "none") or "#REF" in s.upper():
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def melt_target_grades(df: pd.DataFrame, date, url: str) -> pd.DataFrame:
    df = normalize_columns(df)
    district_col = df.columns[0]
    df = df.rename(columns={district_col: "District"})

    records = []
    for grade in TARGET_GRADES:
        high_col = f"{grade}|Highest Price"
        avg_col = f"{grade}|Average Price"
        if high_col not in df.columns or avg_col not in df.columns:
            logger.warning("Grade '%s' columns missing on %s", grade, url)
            continue
        for _, row in df.iterrows():
            district = str(row["District"]).strip()
            if district.lower() == "national" and not INCLUDE_NATIONAL_ROW:
                continue
            if not district or district.lower() == "nan":
                continue
            records.append({
                "Date": date,
                "Year": date.year,
                "Month": date.month,
                "Week": date.isocalendar()[1],
                "District": district,
                "Grade": grade,
                "Highest_Price": clean_price(row[high_col]),
                "Average_Price": clean_price(row[avg_col]),
                "Source_URL": url,
            })
    return pd.DataFrame(records)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    weeks = get_week_links(INDEX_URL)

    all_rows = []
    failed = []

    for i, item in enumerate(weeks, 1):
        date, url = item["date"], item["url"]
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error("Failed to fetch %s: %s", url, e)
            failed.append(url)
            continue

        table = extract_cinnamon_table(resp.text, url)
        if table is None:
            failed.append(url)
            continue

        rows = melt_target_grades(table, date, url)
        if not rows.empty:
            all_rows.append(rows)

        if i % 25 == 0:
            logger.info("Processed %d/%d weekly pages...", i, len(weeks))

        time.sleep(REQUEST_DELAY_SECONDS)

    if all_rows:
        result = pd.concat(all_rows, ignore_index=True)
        result = result.sort_values(["Date", "District", "Grade"]).reset_index(drop=True)
        result.to_csv(OUTPUT_CSV, index=False)
        result.to_excel(OUTPUT_XLSX, index=False)
        logger.info("Saved %d rows -> %s and %s", len(result), OUTPUT_CSV, OUTPUT_XLSX)
    else:
        logger.warning("No data extracted at all -- check network access and site structure.")

    if failed:
        with open(FAILED_URLS_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(failed))
        logger.info("%d pages failed/skipped -- see %s", len(failed), FAILED_URLS_FILE)


if __name__ == "__main__":
    main()