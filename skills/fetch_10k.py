"""
fetch_10k.py
Skill: Download 10-K filings from SEC EDGAR for a given ticker or CIK.

Usage:
    uv run python skills/fetch_10k.py --ticker BA --years 3
    uv run python skills/fetch_10k.py --cik 0000719739 --label SIVB --years 5

Use --cik + --label for delisted tickers (SIVB, FRC, BBBY) that no longer
appear in EDGAR's active ticker→CIK map.

EDGAR is free and requires no API key, but you must send a User-Agent
header identifying yourself per SEC's fair access policy.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# SEC requires a descriptive User-Agent. Edit to your name + email.
HEADERS = {
    "User-Agent": "Shane Thakkar sjt200001@utdallas.edu",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov",
}
DATA_HEADERS = {**HEADERS, "Host": "data.sec.gov"}


def get_cik_for_ticker(ticker: str) -> str:
    """Look up the 10-digit zero-padded CIK for a ticker."""
    url = "https://www.sec.gov/files/company_tickers.json"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    ticker_upper = ticker.upper()
    for entry in data.values():
        if entry["ticker"] == ticker_upper:
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"Ticker {ticker} not found in EDGAR")


def _collect_10ks_from_block(block: dict, out: list) -> None:
    """Append 10-K entries from one EDGAR filings block (recent or historical)."""
    for i, form in enumerate(block["form"]):
        if form == "10-K":
            out.append(
                {
                    "accession": block["accessionNumber"][i].replace("-", ""),
                    "accession_dashed": block["accessionNumber"][i],
                    "filing_date": block["filingDate"][i],
                    "report_date": block["reportDate"][i],
                    "primary_doc": block["primaryDocument"][i],
                }
            )


def get_recent_10k_filings(cik: str, max_filings: int = 5) -> list:
    """Return list of recent 10-K accession numbers for a CIK.

    Walks the `recent` block first, then any older `files` chunks so that
    historical filings (e.g. Boeing FY2018) are reachable for heavy filers.
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    r = requests.get(url, headers=DATA_HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()

    filings: list = []
    _collect_10ks_from_block(data["filings"]["recent"], filings)

    for chunk in data["filings"].get("files", []):
        if len(filings) >= max_filings:
            break
        chunk_url = f"https://data.sec.gov/submissions/{chunk['name']}"
        cr = requests.get(chunk_url, headers=DATA_HEADERS, timeout=30)
        cr.raise_for_status()
        _collect_10ks_from_block(cr.json(), filings)
        time.sleep(0.2)

    filings.sort(key=lambda f: f["filing_date"], reverse=True)
    return filings[:max_filings]


def download_filing(cik: str, filing: dict, ticker: str) -> Path:
    """Download the primary 10-K document HTML to disk."""
    cik_int = int(cik)
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
        f"{filing['accession']}/{filing['primary_doc']}"
    )
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()

    fiscal_year = filing["report_date"][:4]
    out_path = RAW_DIR / f"{ticker.upper()}_10K_{fiscal_year}.html"
    out_path.write_text(r.text, encoding="utf-8")
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Stock ticker, e.g. BA (active issuers)")
    parser.add_argument("--cik", help="10-digit CIK (use for delisted tickers)")
    parser.add_argument("--label", help="Filename label when using --cik (e.g. SIVB)")
    parser.add_argument("--years", type=int, default=3, help="Number of recent 10-Ks to pull")
    args = parser.parse_args()

    if not args.ticker and not args.cik:
        parser.error("provide --ticker OR --cik")
    if args.cik and not args.label:
        parser.error("--label is required when using --cik")

    if args.ticker:
        ticker = args.ticker.upper()
        print(f"Looking up CIK for {ticker}...")
        cik = get_cik_for_ticker(ticker)
        print(f"  CIK: {cik}")
    else:
        ticker = args.label.upper()
        cik = args.cik.zfill(10)
        print(f"Using CIK {cik} with label {ticker}")

    print(f"Fetching {args.years} most recent 10-K filings...")
    filings = get_recent_10k_filings(cik, max_filings=args.years)

    if not filings:
        print(f"No 10-K filings found for {ticker}")
        sys.exit(1)

    manifest = []
    for f in filings:
        print(f"  Downloading FY{f['report_date'][:4]} (filed {f['filing_date']})...")
        path = download_filing(cik, f, ticker)
        manifest.append(
            {
                "ticker": ticker,
                "fiscal_year": f["report_date"][:4],
                "filing_date": f["filing_date"],
                "report_date": f["report_date"],
                "local_path": str(path),
                "accession": f["accession_dashed"],
            }
        )
        time.sleep(0.2)  # be polite to SEC servers

    manifest_path = RAW_DIR / f"{ticker}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f"\nDone. Downloaded {len(manifest)} filings.")
    print(f"Manifest: {manifest_path}")
    for m in manifest:
        size_kb = os.path.getsize(m["local_path"]) // 1024
        print(f"  {m['fiscal_year']}: {m['local_path']} ({size_kb} KB)")


if __name__ == "__main__":
    main()
