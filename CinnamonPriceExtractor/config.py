"""
Configuration for the cinnamon price extractor.

Source: exagri.info publishes one HTML page per week (Producers' Prices,
Department of Export Agriculture, Sri Lanka). We scrape directly from the
site instead of parsing screenshots/PDFs -- the HTML tables are clean and
far more reliable than OCR.
"""

from pathlib import Path

# The master index page listing every weekly report since 2016
INDEX_URL = "https://exagri.info/mkt/index.html"

# Only these cinnamon grades will be extracted (matches your highlighted columns)
# NOTE: source table also has "C-5 Sp" -- we deliberately exclude it, it is
# NOT the same as "C-5".
TARGET_GRADES = ["Alba", "C-5", "C-4", "H-2"]

# Districts are kept as-is from the source, including the "National" summary row.
# Set to False if you only want individual districts, not the National row.
INCLUDE_NATIONAL_ROW = True

OUTPUT_DIR = Path("output")
OUTPUT_CSV = OUTPUT_DIR / "cinnamon_prices_2016_2026.csv"
OUTPUT_XLSX = OUTPUT_DIR / "cinnamon_prices_2016_2026.xlsx"
FAILED_URLS_FILE = OUTPUT_DIR / "failed_urls.txt"
LOG_FILE = OUTPUT_DIR / "extraction.log"

# Be polite to the source server
REQUEST_DELAY_SECONDS = 1.0
REQUEST_TIMEOUT = 30

USER_AGENT = (
    "Mozilla/5.0 (compatible; CinnamonPriceResearchBot/1.0; "
    "academic research use)"
)