#!/usr/bin/env python3
"""
Build script for EARTH_PULSE_FRONTEND_FINAL_POLISH_REVIEW.zip
Packages all polished frontend files, responsive test suites, screenshots,
documentation, and backend core files into the final review zip.
"""

import hashlib
import os
from pathlib import Path
import zipfile

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = REPO_ROOT.parent
UPLOAD_DIR = WORKSPACE_ROOT / 'EarthPulse-Upload-Ready'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

TARGET_ZIP_NAME = 'EARTH_PULSE_FRONTEND_FINAL_POLISH_REVIEW.zip'
STAGE_ZIP_PATH = WORKSPACE_ROOT / TARGET_ZIP_NAME
MIRROR_ZIP_PATH = UPLOAD_DIR / TARGET_ZIP_NAME

INCLUDED_PREFIXES = [
    '.env.example',
    '.gitignore',
    'README.md',
    'requirements.txt',
    'docs/API_CONTRACT.md',
    'docs/DEPLOYMENT_GUIDE.md',
    'docs/FRONTEND_FINAL_POLISH_REPORT.md',
    'docs/FRONTEND_FOUNDATION_VERIFICATION.md',
    'docs/FRONTEND_SCIENTIFIC_UI_VERIFICATION.md',
    'docs/LIVE_SATELLITE_VALIDATION_2025.md',
    'docs/MAP_AND_XAI_REMEDIATION_REPORT.md',
    'docs/MODEL_PROVENANCE.md',
    'docs/SCIENTIFIC_METHODOLOGY.md',
    'docs/screenshots/screenshot_2024_map.png',
    'docs/screenshots/screenshot_2025_map.png',
    'docs/screenshots/screenshot_2025_rf_probability.png',
    'docs/screenshots/screenshot_2025_xai.png',
    'docs/screenshots/screenshot_desktop_map.png',
    'docs/screenshots/screenshot_tablet_map.png',
    'docs/screenshots/screenshot_mobile_map.png',
    'frontend/index.html',
    'frontend/package.json',
    'frontend/package-lock.json',
    'frontend/tsconfig.json',
    'frontend/tsconfig.node.json',
    'frontend/vite.config.ts',
    'frontend/scripts/browser_smoke_test.py',
    'frontend/scripts/run-tests.mjs',
    'frontend/src/',
    'src/',
    'tests/test_deployment_safety_gates.py',
    'tests/test_frontend_api_handoff_contract.py',
]

EXCLUDE_PATTERNS = [
    '__pycache__',
    'node_modules',
    'dist',
    '.test_build',
    '.vite',
    '.pytest_cache',
    '.git',
    '.DS_Store',
]


def should_include(rel_path: str) -> bool:
    for exc in EXCLUDE_PATTERNS:
        if exc in rel_path.split('/'):
            return False
    for inc in INCLUDED_PREFIXES:
        if rel_path == inc or rel_path.startswith(inc):
            return True
    return False


def collect_files():
    files_to_pack = []
    for root, dirs, files in os.walk(REPO_ROOT):
        # Skip excluded dirs in traversal
        dirs[:] = [d for d in dirs if d not in EXCLUDE_PATTERNS]
        for f in files:
            full_path = Path(root) / f
            rel_path = full_path.relative_to(REPO_ROOT).as_posix()
            if should_include(rel_path):
                files_to_pack.append((full_path, f'EarthPulse-SAR/{rel_path}'))
    return sorted(files_to_pack, key=lambda x: x[1])


def main():
    print(f'Building {TARGET_ZIP_NAME}...')
    files_to_pack = collect_files()
    print(f'Total files selected: {len(files_to_pack)}')

    if STAGE_ZIP_PATH.exists():
        STAGE_ZIP_PATH.unlink()

    with zipfile.ZipFile(STAGE_ZIP_PATH, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for full_path, arcname in files_to_pack:
            zf.write(full_path, arcname=arcname)

    # Test ZIP integrity
    with zipfile.ZipFile(STAGE_ZIP_PATH, 'r') as zf:
        bad_file = zf.testzip()
        if bad_file:
            raise RuntimeError(f'Corrupted file in ZIP: {bad_file}')
        entries = zf.namelist()
        total_size = sum(info.file_size for info in zf.infolist())
        compressed_size = sum(info.compress_size for info in zf.infolist())

    # Mirror to Upload-Ready directory
    import shutil
    shutil.copy2(STAGE_ZIP_PATH, MIRROR_ZIP_PATH)

    # Compute SHA-256
    h = hashlib.sha256()
    with open(STAGE_ZIP_PATH, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    sha256_hex = h.hexdigest()

    file_bytes = STAGE_ZIP_PATH.stat().st_size
    print('\n========================================================================')
    print(f'Archive created: {STAGE_ZIP_PATH}')
    print(f'Mirrored to:     {MIRROR_ZIP_PATH}')
    print(f'Total Entries:   {len(entries)}')
    print(f'Uncompressed:    {total_size:,} bytes ({total_size / (1024*1024):.2f} MB)')
    print(f'Compressed Size: {file_bytes:,} bytes ({file_bytes / (1024*1024):.2f} MB)')
    print(f'SHA-256 Digest:  {sha256_hex}')
    print('========================================================================')


if __name__ == '__main__':
    main()

