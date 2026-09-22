"""
Scrape SlowMist Hacked database for Ethereum flash loan incidents.

Primary source for ground truth flash loan attack classification.
Filters for incidents where the 'Attack method' field mentions flash loans —
using the curated tag, not heuristic text scanning.
"""

import re
import time
import requests
from bs4 import BeautifulSoup


BASE_URL = "https://hacked.slowmist.io/"

FLASH_LOAN_METHOD_KEYWORDS = [
    'flash loan',
    'flashloan',
    'flash-loan',
]


def extract(ecosystem="ETH", flash_loans_only=True):
    """
    Scrape hacked.slowmist.io for flash loan incidents.

    Args:
        ecosystem:        Chain filter — "ETH", "BSC", "all", etc.
        flash_loans_only: If True (default), return only incidents where the
                          Attack method field mentions flash loans.

    Returns: list of incident dicts
    """
    results = []
    page = 1
    max_pages = None

    print(f"[SlowMist] Scraping {ecosystem} ecosystem...")

    while True:
        url = f"{BASE_URL}?c={ecosystem}&page={page}"

        try:
            headers = {'User-Agent': 'Mozilla/5.0 (academic research, flash loan thesis)'}
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print(f"[SlowMist] ERROR on page {page}: {e}")
            break

        soup = BeautifulSoup(resp.text, 'html.parser')

        # Parse total page count from pagination on first page
        if max_pages is None:
            max_pages = _parse_max_pages(soup)
            print(f"[SlowMist] Total pages: {max_pages}")

        if page > max_pages:
            break

        incidents = soup.find_all('li')

        total_on_page = 0
        flash_on_page = 0
        for incident in incidents:
            try:
                text = incident.get_text(separator='|', strip=True)
                if 'Hacked target' not in text and 'Amount of loss' not in text:
                    continue

                total_on_page += 1

                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
                target_match = re.search(r'Hacked target:\s*\|?\s*(.+?)(?:\||$)', text)
                amount_match = re.search(r'Amount of loss:\s*\$?\s*([\d,]+(?:\.\d+)?)', text)
                method_match = re.search(r'Attack method:\s*\|?\s*(.+?)(?:\||$)', text)

                attack_method = method_match.group(1).strip() if method_match else ''
                is_flash_loan = _is_flash_loan_attack(attack_method)

                ref_link = incident.find('a', href=True)

                row = {
                    'date': date_match.group(1) if date_match else '',
                    'protocol': target_match.group(1).strip() if target_match else '',
                    'loss_usd': amount_match.group(1).replace(',', '') if amount_match else '',
                    'attack_method': attack_method,
                    'is_flash_loan_attack': is_flash_loan,
                    'source': 'SlowMist Hacked',
                    'source_url': ref_link['href'] if ref_link else '',
                }

                if flash_loans_only and not is_flash_loan:
                    continue

                results.append(row)
                flash_on_page += 1

            except Exception:
                continue

        print(f"  Page {page}: {flash_on_page} flash loan / {total_on_page} total incidents")

        # Stop only when the page itself is empty (true end of data)
        if total_on_page == 0:
            break

        page += 1
        time.sleep(1)

    print(f"[SlowMist] Total flash loan incidents: {len(results)}")
    return results


def _is_flash_loan_attack(attack_method):
    """Return True if the attack method field identifies this as a flash loan attack."""
    method_lower = attack_method.lower()
    return any(kw in method_lower for kw in FLASH_LOAN_METHOD_KEYWORDS)


def _parse_max_pages(soup):
    """Extract total page count from pagination. Falls back to 30 if not found."""
    try:
        page_links = soup.select('a[href*="page="]')
        page_numbers = []
        for link in page_links:
            match = re.search(r'page=(\d+)', link.get('href', ''))
            if match:
                page_numbers.append(int(match.group(1)))
        if page_numbers:
            return max(page_numbers)
    except Exception:
        pass
    return 30  # safe fallback
