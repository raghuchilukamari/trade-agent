#!/usr/bin/env python3
"""
edgar_fetcher.py — SEC EDGAR data fetcher using the public REST API.

No API key required. Uses data.sec.gov (official SEC API).

Functions:
    get_cik(ticker)                  -> str (zero-padded 10-digit CIK)
    get_recent_filings(cik, form, n) -> list[dict] filing metadata
    get_filing_text(cik, accession)  -> str
    get_form4_transactions(ticker, days) -> list[InsiderTransaction]
    get_financial_facts(ticker)      -> list[QuarterlyData]
"""

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional

import requests

# ── direct-execution import ──────────────────────────────────────────────────
try:
    from scripts.insider_analysis import InsiderTransaction, TransactionCode
    from scripts.dso_analysis import QuarterlyData
except ImportError:
    _dir = os.path.dirname(os.path.abspath(__file__))
    import importlib.util as _ilu

    def _load(name):
        spec = _ilu.spec_from_file_location(name, os.path.join(_dir, f"{name}.py"))
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    _ia = _load("insider_analysis")
    _da = _load("dso_analysis")
    InsiderTransaction = _ia.InsiderTransaction
    TransactionCode = _ia.TransactionCode
    QuarterlyData = _da.QuarterlyData

# ─────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "trading-agent research@trading.local",
    "Accept-Encoding": "gzip, deflate",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

_last_request = 0.0
_MIN_DELAY = 0.12   # SEC rate limit: 10 req/s


def _get(url: str, **kwargs) -> requests.Response:
    global _last_request
    elapsed = time.time() - _last_request
    if elapsed < _MIN_DELAY:
        time.sleep(_MIN_DELAY - elapsed)
    for attempt in range(4):
        resp = SESSION.get(url, timeout=20, **kwargs)
        _last_request = time.time()
        if resp.status_code == 429:
            wait = 2 ** attempt  # 1s, 2s, 4s, 8s
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()  # raise after final attempt
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# CIK resolution
# ─────────────────────────────────────────────────────────────────────────────

_TICKERS_CACHE_PATH = Path("/tmp/sec_company_tickers.json")
_TICKERS_CACHE_TTL = 86400  # 24 hours


def _load_company_tickers() -> dict:
    """Load company tickers JSON, using a disk cache to avoid parallel-process 429s."""
    if _TICKERS_CACHE_PATH.exists():
        age = time.time() - _TICKERS_CACHE_PATH.stat().st_mtime
        if age < _TICKERS_CACHE_TTL:
            return json.loads(_TICKERS_CACHE_PATH.read_text())
    resp = _get("https://www.sec.gov/files/company_tickers.json")
    data = resp.json()
    _TICKERS_CACHE_PATH.write_text(json.dumps(data))
    return data


@lru_cache(maxsize=512)
def get_cik(ticker: str) -> str:
    """Return zero-padded 10-digit CIK for a ticker symbol."""
    ticker = ticker.upper().strip()
    data = _load_company_tickers()
    for entry in data.values():
        if entry.get("ticker", "").upper() == ticker:
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"CIK not found for ticker '{ticker}'")


# ─────────────────────────────────────────────────────────────────────────────
# Filing index
# ─────────────────────────────────────────────────────────────────────────────

def get_recent_filings(cik: str, form_type: str, n: int = 10) -> list[dict]:
    """
    Return the n most-recent filings of a given form type.

    Each dict has: accession, form, filed, primary_doc, primary_doc_url
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    data = _get(url).json()

    recent = data.get("filings", {}).get("recent", {})
    forms  = recent.get("form", [])
    dates  = recent.get("filingDate", [])
    accs   = recent.get("accessionNumber", [])
    docs   = recent.get("primaryDocument", [])

    results = []
    for form, date, acc, doc in zip(forms, dates, accs, docs):
        if form_type and form.upper() != form_type.upper():
            continue
        acc_clean = acc.replace("-", "")
        doc_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}"
            f"/{acc_clean}/{doc}"
        )
        results.append({
            "accession": acc,
            "form": form,
            "filed": date,
            "primary_doc": doc,
            "primary_doc_url": doc_url,
        })
        if len(results) >= n:
            break

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Filing text
# ─────────────────────────────────────────────────────────────────────────────

def get_filing_text(cik: str, accession: str, doc: Optional[str] = None) -> str:
    """Download full text of a filing document."""
    acc_clean = accession.replace("-", "")
    cik_int = int(cik)

    if doc:
        url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{doc}"
        return _get(url).text

    # Fetch filing index to find the primary document
    index_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}"
        f"/{acc_clean}/{accession}-index.htm"
    )
    try:
        text = _get(index_url).text
        # Extract primary document link
        match = re.search(r'href="([^"]+\.htm)"', text, re.IGNORECASE)
        if match:
            doc_url = f"https://www.sec.gov{match.group(1)}"
            return _get(doc_url).text
    except Exception:
        pass

    # Fallback: try .txt full submission
    txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{accession}.txt"
    return _get(txt_url).text


# ─────────────────────────────────────────────────────────────────────────────
# Form 4 — insider transactions
# ─────────────────────────────────────────────────────────────────────────────

def _parse_form4_xml(xml_text: str) -> list[InsiderTransaction]:
    """Parse Form 4 XML and return a list of InsiderTransaction objects."""
    txns: list[InsiderTransaction] = []

    try:
        # Strip any HTML wrapper
        xml_match = re.search(r"<ownershipDocument.*?</ownershipDocument>", xml_text, re.DOTALL)
        if not xml_match:
            return txns
        root = ET.fromstring(xml_match.group(0))
    except ET.ParseError:
        return txns

    # Reporting owner
    owner_name = ""
    owner_title = ""
    owner_el = root.find(".//reportingOwner")
    if owner_el is not None:
        name_el = owner_el.find(".//rptOwnerName")
        title_el = owner_el.find(".//officerTitle")
        if name_el is not None:
            owner_name = name_el.text or ""
        if title_el is not None:
            owner_title = title_el.text or ""

    # Non-derivative transactions (open-market buys/sells)
    for txn_el in root.findall(".//nonDerivativeTransaction"):
        try:
            date_el = txn_el.find(".//transactionDate/value")
            code_el = txn_el.find(".//transactionCode")
            shares_el = txn_el.find(".//transactionShares/value")
            price_el = txn_el.find(".//transactionPricePerShare/value")
            plan_el = txn_el.find(".//equitySwapInvolved")  # rough 10b5-1 proxy

            date = date_el.text.strip() if date_el is not None and date_el.text else ""
            code_str = code_el.text.strip() if code_el is not None and code_el.text else ""
            shares = float(shares_el.text) if shares_el is not None and shares_el.text else 0.0
            price = float(price_el.text) if price_el is not None and price_el.text else 0.0

            # Infer 10b5-1 from footnotes (not perfect but practical)
            footnotes = " ".join(
                (f.text or "") for f in txn_el.findall(".//footnote")
            )
            is_10b5 = "10b5-1" in footnotes.lower() or "10b5" in footnotes.lower()

            # Store as string (InsiderTransaction.transaction_code: str)
            try:
                code_name = TransactionCode[code_str].name
            except KeyError:
                code_name = code_str if code_str else "J"

            txn = InsiderTransaction(
                date=date,
                insider_name=owner_name,
                insider_title=owner_title,
                transaction_code=code_name,
                shares=shares,
                price=price,
                value=shares * price,
                is_10b5_1=is_10b5,
                direct_indirect="D",
            )
            txns.append(txn)
        except Exception:
            continue

    return txns


def get_form4_transactions(
    ticker: str,
    days: int = 90,
) -> list[InsiderTransaction]:
    """
    Fetch and parse recent Form 4 filings for a ticker.
    Returns a flat list of InsiderTransaction objects within the last `days` days.
    """
    cik = get_cik(ticker)
    filings = get_recent_filings(cik, "4", n=100)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    all_txns: list[InsiderTransaction] = []

    for filing in filings:
        if filing["filed"] < cutoff:
            break
        try:
            # Form 4 primary doc is usually an XML file
            acc_clean = filing["accession"].replace("-", "")
            cik_int = int(cik)

            # primary_doc is often XSLT-rendered HTML (xslF345X06/foo.xml).
            # Strip the XSL folder prefix to get the raw XML with
            # <ownershipDocument> that our parser needs.
            raw_doc = re.sub(r'^xsl\w+/', '', filing['primary_doc'])
            xml_url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik_int}"
                f"/{acc_clean}/{raw_doc}"
            )
            xml_text = _get(xml_url).text
            txns = _parse_form4_xml(xml_text)
            all_txns.extend(txns)
        except Exception:
            continue

    return all_txns


# ─────────────────────────────────────────────────────────────────────────────
# XBRL facts — quarterly AR + Revenue for DSO
# ─────────────────────────────────────────────────────────────────────────────

_AR_CONCEPTS = [
    "AccountsReceivableNetCurrent",
    "ReceivablesNetCurrent",
    "AccountsReceivableNet",
]
_REV_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueGoodsNet",
]


def _extract_quarterly_series(facts: dict, concepts: list[str]) -> dict[str, float]:
    """Return period→value mapping for the first matching concept (quarterly)."""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for concept in concepts:
        data = us_gaap.get(concept, {}).get("units", {}).get("USD", [])
        if not data:
            continue
        quarterly = {
            item["end"]: item["val"]
            for item in data
            if item.get("form") in ("10-Q", "10-K") and item.get("fp") != "FY"
        }
        if quarterly:
            return quarterly
    return {}


def get_financial_facts(ticker: str, quarters: int = 8) -> list[QuarterlyData]:
    """
    Fetch quarterly AR and revenue from EDGAR XBRL facts.
    Returns a list of QuarterlyData objects sorted oldest-first.
    """
    cik = get_cik(ticker)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    facts = _get(url).json()

    ar_series = _extract_quarterly_series(facts, _AR_CONCEPTS)
    rev_series = _extract_quarterly_series(facts, _REV_CONCEPTS)

    # Intersect periods
    common_periods = sorted(set(ar_series) & set(rev_series))[-quarters:]

    result: list[QuarterlyData] = []
    for period in common_periods:
        month = int(period[5:7])
        quarter = (month - 1) // 3 + 1
        label = f"Q{quarter} {period[:4]}"
        result.append(QuarterlyData(
            period=label,
            date=period,
            accounts_receivable=ar_series[period],
            revenue=rev_series[period],
        ))

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: recent 8-K / 10-K / 10-Q text for red flag scanning
# ─────────────────────────────────────────────────────────────────────────────

def get_filings_text(
    ticker: str,
    form_types: list[str] = None,
    n_per_type: int = 5,
) -> list[dict]:
    """
    Return list of {form, filed, text} dicts for red flag scanning.
    form_types defaults to ["8-K", "10-K", "10-Q"].
    """
    if form_types is None:
        form_types = ["8-K", "10-K", "10-Q"]

    cik = get_cik(ticker)
    results = []

    for form_type in form_types:
        filings = get_recent_filings(cik, form_type, n=n_per_type)
        for filing in filings:
            try:
                text = get_filing_text(cik, filing["accession"], filing["primary_doc"])
                results.append({
                    "form": filing["form"],
                    "filed": filing["filed"],
                    "accession": filing["accession"],
                    "text": text,
                })
            except Exception as e:
                print(f"  Warning: could not fetch {form_type} {filing['accession']}: {e}",
                      file=sys.stderr)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# CLI test mode
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test EDGAR fetcher")
    parser.add_argument("--test", metavar="TICKER", help="Run a quick fetch test")
    parser.add_argument("--cik", metavar="TICKER", help="Resolve CIK only")
    args = parser.parse_args()

    if args.cik:
        cik = get_cik(args.cik)
        print(f"{args.cik} → CIK {cik}")

    elif args.test:
        ticker = args.test.upper()
        print(f"\n--- Testing EDGAR fetcher for {ticker} ---\n")

        cik = get_cik(ticker)
        print(f"CIK: {cik}")

        print("\nRecent 8-K filings:")
        filings = get_recent_filings(cik, "8-K", n=3)
        for f in filings:
            print(f"  {f['filed']}  {f['accession']}")

        print("\nRecent Form 4 filings:")
        form4_filings = get_recent_filings(cik, "4", n=3)
        for f in form4_filings:
            print(f"  {f['filed']}  {f['accession']}")

        print("\nInsider transactions (last 90 days):")
        txns = get_form4_transactions(ticker, days=90)
        for t in txns[:5]:
            print(f"  {t.date}  {t.insider_name}  {t.transaction_code.name}  "
                  f"{t.shares:,.0f} shares @ ${t.price:.2f}")

        print("\nQuarterly financial facts (last 4 quarters):")
        quarters = get_financial_facts(ticker, quarters=4)
        for q in quarters:
            print(f"  {q.period}  AR=${q.accounts_receivable/1e6:.1f}M  "
                  f"Rev=${q.revenue/1e6:.1f}M  DSO={q.dso:.1f}d")
    else:
        parser.print_help()