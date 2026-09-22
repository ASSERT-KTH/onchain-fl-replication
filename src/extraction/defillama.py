"""
Load DeFiLlama flash loan attacks from pre-downloaded CSV.

Input:  data/ground_truth/defillama_flashloan_attacks.csv
Output: list of normalised incident dicts
"""

import csv
from datetime import datetime


def load(filepath="data/ground_truth/defillama_flashloan_attacks.csv"):
    """
    Parse DeFiLlama hacks CSV, filter to Ethereum incidents only.

    Returns: list of incident dicts
    """
    results = []

    with open(filepath, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            chains = [c.strip() for c in row.get('Chains', '').split(',')]
            if 'Ethereum' not in chains:
                continue

            date = _parse_date(row.get('Date', ''))
            if not date:
                continue

            results.append({
                'date': date,
                'protocol': row['Name'].strip(),
                'loss_usd': str(row.get('Amount Lost (USD)', '')),
                'technique': row.get('Technique', '').strip(),
                'source': 'DeFiLlama',
                'source_url': row.get('Link', '').strip(),
                'tx_hash': '',
                'block_number': '',
                'dhl_source_file': '',
                'tx_hash_source': '',
            })

    print(f"[DeFiLlama] Loaded {len(results)} Ethereum flash loan incidents")
    return results


def _parse_date(date_str):
    """Convert '28 Feb 2026' → '2026-02-28'."""
    date_str = date_str.strip()
    for fmt in ('%d %b %Y', '%d %B %Y'):
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return ''
