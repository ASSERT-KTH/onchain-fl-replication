"""
DeFiHackLabs lookup tool.

Given a list of known incidents (protocol name + date from SlowMist/DeFiLlama),
finds the matching PoC file and extracts the attack transaction hash.

NOT a scanner. Does not infer which exploits used flash loans from source code.
Flash loan classification comes from curated databases (SlowMist, DeFiLlama).
This module only enriches known incidents with transaction hashes.

Requires: DeFiHackLabs cloned into data/raw/DeFiHackLabs/
  git clone https://github.com/SunWeb3Sec/DeFiHackLabs.git data/raw/DeFiHackLabs
"""

import os
import re
import glob


def enrich(incidents, repo_path="data/raw/DeFiHackLabs"):
    """
    Enrich a list of incidents with tx hashes from DeFiHackLabs PoC files.

    Args:
        incidents: list of dicts, each with 'protocol' (str) and 'date' (str YYYY-MM-DD or YYYY-MM)
        repo_path: path to cloned DeFiHackLabs repo

    Returns: same list, each dict enriched with:
        'tx_hash'              — attack tx hash (or "" if not found)
        'block_number'         — fork block number from PoC (or "")
        'dhl_source_file'      — relative path to matched .sol file (or "")
        'dhl_match_confidence' — "exact", "partial", or "none"
    """
    sol_files = _index_repo(repo_path)
    if not sol_files:
        print(f"[DeFiHackLabs] ERROR: Repo not found at {repo_path}")
        print(f"  Clone: git clone https://github.com/SunWeb3Sec/DeFiHackLabs.git {repo_path}")
        for inc in incidents:
            inc.setdefault('tx_hash', '')
            inc.setdefault('block_number', '')
            inc.setdefault('dhl_source_file', '')
            inc.setdefault('dhl_match_confidence', 'none')
        return incidents

    print(f"[DeFiHackLabs] Enriching {len(incidents)} incidents from {len(sol_files)} PoC files...")

    enriched = 0
    for inc in incidents:
        result = _lookup(inc.get('protocol', ''), inc.get('date', ''), sol_files, repo_path)
        inc['tx_hash'] = result['tx_hash']
        inc['block_number'] = result['block_number']
        inc['dhl_source_file'] = result['source_file']
        inc['dhl_match_confidence'] = result['confidence']
        if result['tx_hash']:
            enriched += 1

    print(f"[DeFiHackLabs] tx hashes found: {enriched}/{len(incidents)}")
    return incidents


def _lookup(protocol, date_str, sol_files, repo_path):
    """
    Find the PoC file for a given protocol + date and extract tx hash.

    Matching strategy:
      - "exact":   filename contains both the full date (YYYYMMDD) and protocol name
      - "partial": filename contains year-month (YYYYMM) + protocol, or exact date + tokens
      - "none":    no match found
    """
    date_compact = re.sub(r'[^0-9]', '', date_str)[:8]  # "20230313" or "202303"
    date_ym = date_compact[:6]                            # "202303" for loose matching

    protocol_norm = _normalize(protocol)
    protocol_slug = protocol_norm.replace(' ', '')
    protocol_tokens = [t for t in protocol_norm.split() if len(t) > 2 and t not in _STOPWORDS]

    best_file = None
    best_confidence = 'none'

    for filepath, fname_lower in sol_files:
        fname_slug = re.sub(r'[^a-z0-9]', '', fname_lower)

        has_exact_date = bool(date_compact) and date_compact in fname_slug
        has_ym = bool(date_ym) and date_ym in fname_slug
        has_protocol = bool(protocol_slug) and protocol_slug in fname_slug
        has_tokens = any(t in fname_slug for t in protocol_tokens)
        # Prefix match: catches truncated names e.g. "ZoomerCoin"→"Zoomer", "Makinafi"→"makina"
        has_prefix = len(protocol_slug) > 5 and any(
            protocol_slug[:n] in fname_slug for n in range(5, len(protocol_slug))
        )

        if not has_exact_date and not has_ym:
            continue

        if has_exact_date and has_protocol:
            best_file = filepath
            best_confidence = 'exact'
            break
        elif (has_exact_date and has_tokens) or (has_ym and has_protocol):
            if best_confidence != 'exact':
                best_file = filepath
                best_confidence = 'partial'
        elif has_ym and (has_tokens or has_prefix) and best_confidence == 'none':
            best_file = filepath
            best_confidence = 'partial'

    if best_file is None:
        return {'tx_hash': '', 'block_number': '', 'source_file': '', 'confidence': 'none'}

    try:
        with open(best_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return {'tx_hash': '', 'block_number': '', 'source_file': best_file, 'confidence': best_confidence}

    rel_path = os.path.relpath(best_file, repo_path)
    return {
        'tx_hash': _extract_tx_hash(content),
        'block_number': _extract_block_number(content),
        'source_file': rel_path,
        'confidence': best_confidence,
    }


def _index_repo(repo_path):
    """Return list of (filepath, filename_lower) for all .sol files in the repo."""
    if not os.path.exists(repo_path):
        return []

    files = []
    for search_dir in ['src/test', 'past']:
        full_dir = os.path.join(repo_path, search_dir)
        if os.path.exists(full_dir):
            for fp in glob.glob(os.path.join(full_dir, '**', '*.sol'), recursive=True):
                # Include parent directory name so date-in-directory files are matched
                # e.g. "2023-03/Euler_exp.sol" instead of just "Euler_exp.sol"
                parent = os.path.basename(os.path.dirname(fp))
                fname = os.path.basename(fp)
                files.append((fp, os.path.join(parent, fname).lower()))

    return files


_STOPWORDS = {
    'finance', 'protocol', 'token', 'swap', 'dao', 'defi', 'network',
    'exchange', 'pool', 'vault', 'farm', 'yield', 'money', 'cash',
    'capital', 'fund', 'bank', 'credit', 'lend', 'borrow', 'pay',
    'lab', 'labs', 'project', 'app', 'pro', 'plus', 'one', 'the',
}


def _normalize(name):
    """Lowercase, strip special chars, collapse whitespace."""
    name = name.lower()
    name = re.sub(r'[^a-z0-9 ]', ' ', name)
    return re.sub(r'\s+', ' ', name).strip()


def _extract_tx_hash(content):
    """Extract the most likely attack tx hash from a PoC file."""
    candidates = re.findall(r'0x[a-fA-F0-9]{64}', content)
    for tx in candidates:
        idx = content.find(tx)
        context = content[max(0, idx - 200):idx + 10].lower()
        if any(hint in context for hint in ['tx', 'transaction', 'attack', 'exploit', 'hack']):
            return tx
    return candidates[0] if candidates else ''


def _extract_block_number(content):
    match = re.search(r'createSelectFork\([^)]*,\s*(\d{6,})\s*\)', content)
    return match.group(1) if match else ''
