"""
Ground truth extraction pipeline for RQ2.

Collects flash loan attack incidents from three sources, merges and deduplicates
them, then extracts transaction hashes where possible with high confidence.
Incidents without tx hashes are left empty for manual lookup.

Pipeline:
  Step 1 — Collect incidents from SlowMist, DeFiLlama, DeFiHackLabs
  Step 2 — Merge and deduplicate on (protocol, month)
  Step 3 — Extract tx hashes from direct Etherscan source URLs
  Step 4 — Extract tx hashes via DeFiHackLabs fuzzy lookup (exact confidence only)
  Step 5 — Output flash_loan_attacks_v2.csv + manual_lookup.csv

Usage:
    python -m src.extraction.run_extraction
"""

import csv
import os
import re

from src.extraction import defihacklabs, defihacklabs_incidents, defillama, slowmist


OUTPUT_DIR = os.path.join("data", "ground_truth")

FIELDNAMES = [
    'date', 'protocol', 'loss_usd', 'technique',
    'tx_hash', 'block_number', 'tx_hash_source',
    'sources', 'source_url', 'dhl_source_file',
]

# Words stripped when normalising protocol names for deduplication
_NORM_STOPWORDS = re.compile(
    r'\b(v\d+|finance|protocol|defi|network|dao|swap|lending|capital|labs?|'
    r'project|app|pro|plus|one|the|frontier|elastic)\b'
)


def main():
    print("=" * 60)
    print("Flash Loan Ground Truth — Extraction Pipeline")
    print("=" * 60)
    print()

    # ── Step 1: Collect ──────────────────────────────────────────
    _header("STEP 1: Collect incidents from all sources")

    sm_incidents = slowmist.extract(ecosystem="ETH", flash_loans_only=True)
    dl_incidents = defillama.load()
    dhl_incidents = defihacklabs_incidents.load(repo_path="data/raw/DeFiHackLabs")
    print()

    # ── Step 2: Merge and deduplicate ────────────────────────────
    _header("STEP 2: Merge and deduplicate")

    merged = _merge(sm_incidents, dl_incidents, dhl_incidents)
    print(f"  Total unique incidents after merge: {len(merged)}")
    print()

    # ── Step 3: Etherscan URL extraction ─────────────────────────
    _header("STEP 3: Etherscan URL tx hash extraction")

    url_enriched = 0
    for inc in merged:
        if not inc.get('tx_hash') and inc.get('source_url'):
            match = re.search(r'etherscan\.io/tx/(0x[a-fA-F0-9]{64})', inc['source_url'])
            if match:
                inc['tx_hash'] = match.group(1)
                inc['tx_hash_source'] = 'etherscan_url'
                url_enriched += 1
    print(f"  tx hashes from Etherscan URLs: {url_enriched}")
    print()

    # ── Step 4: DeFiHackLabs fuzzy lookup (exact confidence only) ─
    _header("STEP 4: DeFiHackLabs fuzzy lookup (exact confidence only)")

    needs_hash = [inc for inc in merged if not inc.get('tx_hash')]
    print(f"  Incidents still missing tx hash: {len(needs_hash)}")

    if needs_hash and os.path.exists("data/raw/DeFiHackLabs"):
        enriched = defihacklabs.enrich(needs_hash, repo_path="data/raw/DeFiHackLabs")
        fuzzy_found = 0
        for inc in enriched:
            if inc.get('tx_hash') and inc.get('dhl_match_confidence') == 'exact':
                inc['tx_hash_source'] = 'defihacklabs_fuzzy_exact'
                fuzzy_found += 1
            elif inc.get('dhl_match_confidence') != 'exact':
                # Discard low-confidence matches
                inc['tx_hash'] = ''
                inc['block_number'] = ''
                inc['dhl_source_file'] = ''
                inc['tx_hash_source'] = ''
        print(f"  tx hashes accepted (exact confidence): {fuzzy_found}")
    else:
        print("  Skipped — DeFiHackLabs repo not found at data/raw/DeFiHackLabs")
    print()

    # ── Step 5: Output ───────────────────────────────────────────
    _header("STEP 5: Output")

    with_hash = sum(1 for inc in merged if inc.get('tx_hash'))
    without_hash = len(merged) - with_hash

    _write_csv(merged, "flash_loan_attacks_v2.csv")

    manual = [inc for inc in merged if not inc.get('tx_hash')]
    _write_csv(manual, "manual_lookup.csv")

    print()
    print(f"  Total incidents:       {len(merged)}")
    print(f"  With tx hash:          {with_hash}")
    print(f"  Needs manual lookup:   {without_hash}")
    print()
    print("=" * 60)
    print("DONE. Check data/ground_truth/ for output files.")
    print("=" * 60)


# ── Merge helpers ────────────────────────────────────────────────

def _merge(*source_lists):
    """
    Combine incident lists from multiple sources, deduplicating on
    (normalised protocol name, year-month).

    When two incidents match:
    - sources field is merged (e.g. "slowmist,defillama")
    - tx_hash, loss_usd, source_url filled from whichever has it
    """
    unified = []

    for incidents in source_lists:
        for inc in incidents:
            match = _find_duplicate(inc, unified)
            if match is None:
                unified.append(_copy(inc))
            else:
                _merge_into(match, inc)

    return unified


def _find_duplicate(inc, existing):
    """Return the existing incident that matches inc, or None."""
    norm_new = _normalize_name(inc.get('protocol', ''))
    month_new = inc.get('date', '')[:7]

    for ex in existing:
        norm_ex = _normalize_name(ex.get('protocol', ''))
        month_ex = ex.get('date', '')[:7]

        if month_new != month_ex:
            continue
        if not norm_new or not norm_ex:
            continue

        # Match if one normalised name contains the other
        if norm_new in norm_ex or norm_ex in norm_new:
            return ex

    return None


def _merge_into(existing, new):
    """Merge fields from new into existing, combining sources."""
    existing_sources = set(existing.get('sources', existing.get('source', '')).split(','))
    new_source = new.get('source', '')
    if new_source:
        existing_sources.add(new_source)
    existing['sources'] = ','.join(sorted(s for s in existing_sources if s))

    # Fill gaps from the new record
    for field in ('tx_hash', 'loss_usd', 'source_url', 'block_number',
                  'dhl_source_file', 'tx_hash_source', 'technique'):
        if not existing.get(field) and new.get(field):
            existing[field] = new[field]

    # Keep most specific date
    if len(new.get('date', '')) > len(existing.get('date', '')):
        existing['date'] = new['date']


def _copy(inc):
    """Return a copy of inc with the sources field set."""
    row = {k: inc.get(k, '') for k in FIELDNAMES}
    row['sources'] = inc.get('source', '')
    return row


def _normalize_name(name):
    """Lowercase, strip common DeFi words, keep only alphanumeric."""
    name = name.lower()
    name = _NORM_STOPWORDS.sub('', name)
    name = re.sub(r'[^a-z0-9]', '', name)
    return name.strip()


# ── Output helpers ───────────────────────────────────────────────

def _write_csv(data, filename):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(data)
    print(f"  -> {filepath} ({len(data)} rows)")


def _header(title):
    print("-" * 40)
    print(title)
    print("-" * 40)


if __name__ == "__main__":
    main()
