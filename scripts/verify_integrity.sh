#!/usr/bin/env bash
# ==============================================================================
# Earth Pulse — Scientific Integrity & Asset Verification Suite
# NASA Space Apps Challenge 2026: Dancing with the SARs
# ==============================================================================
# Verifies cryptographic checksums for:
#   1. Canonical ESA SNAP XML graph
#   2. Frozen Random Forest AI model
#   3. Authoritative 2024 & 2025 scientific rasters, vectors, and manifests
#   4. Numerical scientific invariants (net floodwater changes)
# ==============================================================================

set -uo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
NC="\033[0m"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

echo -e "${BOLD}${CYAN}========================================================================${NC}"
echo -e "${BOLD}${CYAN}🔬  EARTH PULSE — SCIENTIFIC INTEGRITY & PROVENANCE AUDIT${NC}"
echo -e "${BOLD}${CYAN}========================================================================${NC}"

# Python check
PYTHON_BIN="python3"
if [ -d "${REPO_ROOT}/.venv" ] && [ -x "${REPO_ROOT}/.venv/bin/python3" ]; then
  PYTHON_BIN="${REPO_ROOT}/.venv/bin/python3"
fi

"${PYTHON_BIN}" -c "
import sys, json, hashlib
from pathlib import Path

repo_root = Path('${REPO_ROOT}').resolve()
errors = []

# ------------------------------------------------------------------------------
# 1. Canonical SNAP Graph Hash Verification
# ------------------------------------------------------------------------------
snap_path = repo_root / 'graphs' / 's1_grd_calibration_terrain_correction.xml'
EXPECTED_SNAP_SHA = 'c239c2691ebcf45b778e171553c1656f9ce4d4a1dded160d929fa8e73cf316a0'

print('\n[1/4] Canonical ESA SNAP Processing Graph Verification')
if not snap_path.exists():
    errors.append(f'Missing SNAP graph at: {snap_path}')
    print('  • Status: ❌ MISSING')
else:
    actual_snap_sha = hashlib.sha256(snap_path.read_bytes()).hexdigest()
    if actual_snap_sha == EXPECTED_SNAP_SHA:
        print(f'  • Path:   {snap_path.relative_to(repo_root)}')
        print(f'  • SHA256: {actual_snap_sha}')
        print('  • Status: ✅ VERIFIED MATCH')
    else:
        errors.append(f'SNAP graph hash mismatch: {actual_snap_sha} != {EXPECTED_SNAP_SHA}')
        print(f'  • Actual:   {actual_snap_sha}')
        print(f'  • Expected: {EXPECTED_SNAP_SHA}')
        print('  • Status:   ❌ CHECKSUM MISMATCH')

# ------------------------------------------------------------------------------
# 2. Frozen Random Forest Model Hash Verification
# ------------------------------------------------------------------------------
rf_path = repo_root / 'models' / 'phase7a' / 'phase7a_random_forest_model.joblib'
EXPECTED_RF_SHA = '85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad'

print('\n[2/4] Frozen AI Model Integrity Verification')
if not rf_path.exists():
    errors.append(f'Missing Random Forest model at: {rf_path}')
    print('  • Status: ❌ MISSING')
else:
    actual_rf_sha = hashlib.sha256(rf_path.read_bytes()).hexdigest()
    if actual_rf_sha == EXPECTED_RF_SHA:
        print(f'  • Path:   {rf_path.relative_to(repo_root)}')
        print(f'  • SHA256: {actual_rf_sha}')
        print('  • Status: ✅ VERIFIED MATCH')
    else:
        errors.append(f'Random Forest model hash mismatch: {actual_rf_sha} != {EXPECTED_RF_SHA}')
        print(f'  • Actual:   {actual_rf_sha}')
        print(f'  • Expected: {EXPECTED_RF_SHA}')
        print('  • Status:   ❌ CHECKSUM MISMATCH')

# ------------------------------------------------------------------------------
# 3. Demonstration Data Manifest Verification
# ------------------------------------------------------------------------------
manifest_path = repo_root / 'docs' / 'DEMO_DATA_MANIFEST.json'
print('\n[3/4] Demonstration Data Manifest & Byte-Level Verification')
if not manifest_path.exists():
    errors.append(f'Missing manifest file at: {manifest_path}')
    print('  • Status: ❌ MISSING DEMO_DATA_MANIFEST.json')
else:
    try:
        manifest = json.loads(manifest_path.read_text())
        total_checked = 0
        total_matched = 0

        for run_id, run_info in manifest.get('runs', {}).items():
            run_dir = repo_root / 'data' / 'runs' / run_id
            if not run_dir.exists():
                errors.append(f'Run directory missing: {run_dir}')
                print(f'  • {run_id}: ❌ DIRECTORY MISSING')
                continue

            run_files = run_info.get('files', [])
            run_matched = 0
            for item in run_files:
                fpath = run_dir / item['path']
                total_checked += 1
                if not fpath.exists():
                    errors.append(f'{run_id}: file missing: {item[\"path\"]}')
                    continue
                actual_sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
                if actual_sha == item['sha256']:
                    run_matched += 1
                    total_matched += 1
                else:
                    errors.append(f'{run_id}: checksum mismatch on {item[\"path\"]}')

            print(f'  • {run_id}: ✅ {run_matched}/{len(run_files)} files verified')

        print(f'  • Total verified: {total_matched}/{total_checked} files match cryptographic manifest')
    except Exception as e:
        errors.append(f'Manifest parsing failed: {e}')
        print(f'  • Error: ❌ {e}')

# ------------------------------------------------------------------------------
# 4. Scientific Metric Invariant Verification
# ------------------------------------------------------------------------------
print('\n[4/4] Scientific Invariant & Provenance Metrics Verification')

# 2024 Monsoon Check
summary_2024 = repo_root / 'data' / 'runs' / 'run_20261110_221732_1f2e94' / 'summary.json'
if summary_2024.exists():
    d24 = json.loads(summary_2024.read_text())
    net24 = d24.get('flood_transitions_km2', {}).get('net_candidate_water_change')
    if net24 == 5.8432:
        print(f'  • 2024 Monsoon Run:  ✅ Net water change: +{net24:.4f} km² (Exact scientific invariant)')
    else:
        errors.append(f'2024 Net change mismatch: {net24} != 5.8432')
        print(f'  • 2024 Monsoon Run:  ❌ {net24} != +5.8432 km²')
else:
    errors.append('Missing 2024 summary.json')

# 2025 Live SAR Check
summary_2025 = repo_root / 'data' / 'runs' / 'run_20261111_164348_f3c2b8' / 'summary.json'
if summary_2025.exists():
    d25 = json.loads(summary_2025.read_text())
    net25 = d25.get('flood_transitions_km2', {}).get('net_candidate_water_change')
    if net25 == 1.0440 or net25 == 1.044:
        print(f'  • 2025 Live SAR Run: ✅ Net water change: +{net25:.4f} km² (Exact scientific invariant)')
    else:
        errors.append(f'2025 Net change mismatch: {net25} != 1.0440')
        print(f'  • 2025 Live SAR Run: ❌ {net25} != +1.0440 km²')
else:
    errors.append('Missing 2025 summary.json')

# ------------------------------------------------------------------------------
# Exit Summary
# ------------------------------------------------------------------------------
print('\n========================================================================')
if not errors:
    print('✅ ALL SCIENTIFIC ASSETS AND INVARIANTS HAVE BEEN VERIFIED!')
    print('========================================================================\n')
    sys.exit(0)
else:
    print(f'❌ FAILED: Encountered {len(errors)} integrity error(s):')
    for err in errors:
        print(f'  • {err}')
    print('========================================================================\n')
    sys.exit(1)
"

