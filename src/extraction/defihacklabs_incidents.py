"""
Load DeFiHackLabs Incident Explorer incidents.json.

Fetches the structured incident list from the DeFiHackLabs Incident Explorer,
filters for Ethereum flash loan attacks, and extracts tx hashes via the exact
Contract file path. No fuzzy matching — the Contract field gives the precise
.sol file path for each incident.

Requires: DeFiHackLabs repo cloned at data/raw/DeFiHackLabs
  git clone https://github.com/SunWeb3Sec/DeFiHackLabs.git data/raw/DeFiHackLabs
"""

import os
import re
import requests


INCIDENTS_URL = "https://raw.githubusercontent.com/SunWeb3Sec/DeFiHackLabs-Incident-Explorer/main/incidents.json"

# Type values that indicate a flash loan attack
FLASH_LOAN_TYPES = {'flash loan attack', 'flashloan'}


def load(repo_path="data/raw/DeFiHackLabs"):
    """
    Fetch incidents.json, filter to Ethereum flash loan incidents,
    extract tx hashes from exact .sol file paths.

    Returns: list of incident dicts
    """
    print("[DeFiHackLabs Incidents] Fetching incidents.json...")
    try:
        resp = requests.get(INCIDENTS_URL, timeout=30)
        resp.raise_for_status()
        all_incidents = resp.json()
    except Exception as e:
        print(f"[DeFiHackLabs Incidents] ERROR: {e}")
        return []

    eth_flash = [
        inc for inc in all_incidents
        if inc.get('chain') == 'Ethereum'
        and inc.get('type', '').lower() in FLASH_LOAN_TYPES
    ]
    print(f"[DeFiHackLabs Incidents] {len(eth_flash)} Ethereum flash loan incidents found")

    results = []
    for inc in eth_flash:
        date = _parse_date(inc.get('date', ''))
        contract_path = inc.get('Contract', '')

        tx_hash = ''
        block_number = ''
        if contract_path and os.path.exists(repo_path):
            full_path = os.path.join(repo_path, contract_path)
            tx_hash = _extract_tx_hash_from_file(full_path)
            block_number = _extract_block_number_from_file(full_path)

        lost = inc.get('Lost')

        results.append({
            'date': date,
            'protocol': inc.get('name', '').strip(),
            'loss_usd': str(lost) if lost is not None else '',
            'technique': inc.get('type', '').strip(),
            'source': 'DeFiHackLabs',
            'source_url': '',
            'tx_hash': tx_hash,
            'block_number': block_number,
            'dhl_source_file': contract_path,
            'tx_hash_source': 'defihacklabs_exact' if tx_hash else '',
        })

    found = sum(1 for r in results if r['tx_hash'])
    print(f"[DeFiHackLabs Incidents] tx hashes extracted: {found}/{len(results)}")
    return results


def _parse_date(date_str):
    """Convert '20230313' → '2023-03-13'."""
    s = str(date_str).strip()
    if re.match(r'^\d{8}$', s):
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


def _extract_tx_hash_from_file(filepath):
    if not os.path.exists(filepath):
        return ''
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return ''

    candidates = re.findall(r'0x[a-fA-F0-9]{64}', content)
    for tx in candidates:
        idx = content.find(tx)
        context = content[max(0, idx - 200):idx + 10].lower()
        if any(hint in context for hint in ['tx', 'transaction', 'attack', 'exploit', 'hack']):
            return tx
    return candidates[0] if candidates else ''


def _extract_block_number_from_file(filepath):
    if not os.path.exists(filepath):
        return ''
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return ''
    match = re.search(r'createSelectFork\([^)]*,\s*(\d{6,})\s*\)', content)
    return match.group(1) if match else ''
