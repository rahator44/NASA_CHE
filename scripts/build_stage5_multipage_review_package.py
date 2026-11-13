#!/usr/bin/env python3
"""
Build script for EARTH_PULSE_PROFESSIONAL_MULTIPAGE_UI_REVIEW.zip (Stage 5 Deliverable)
Packages all modern multi-page frontend source files, router, pages, components,
tests, configurations, and verification screenshots into the review archive.
"""

import hashlib
import os
import shutil
from pathlib import Path
import zipfile

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = REPO_ROOT.parent
UPLOAD_DIR = WORKSPACE_ROOT / 'EarthPulse-Upload-Ready'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

TARGET_ZIP_NAME = 'EARTH_PULSE_PROFESSIONAL_MULTIPAGE_UI_REVIEW.zip'
STAGE_ZIP_PATH = UPLOAD_DIR / TARGET_ZIP_NAME
STAGE_ROOT_ZIP_PATH = WORKSPACE_ROOT / TARGET_ZIP_NAME

INCLUDED_PREFIXES = [
    '.env.example',
    '.gitignore',
    'README.md',
    'requirements.txt',
    'docs/API_CONTRACT.md',
    'docs/DEPLOYMENT_GUIDE.md',
    'docs/MODEL_PROVENANCE.md',
    'docs/SCIENTIFIC_METHODOLOGY.md',
    'docs/screenshots/screenshot_2024_map.png',
    'docs/screenshots/screenshot_2025_map.png',
    'docs/screenshots/screenshot_2025_rf_probability.png',
    'docs/screenshots/screenshot_2025_xai.png',
    'docs/screenshots/screenshot_dashboard.png',
    'docs/screenshots/screenshot_explorer.png',
    'docs/screenshots/screenshot_desktop_map.png',
    'docs/screenshots/screenshot_comparison.png',
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
    'src/backend/',
    'tests/test_stage3_demo_readiness.py',
    'tests/test_scientific_visualization.py',
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
    parts = rel_path.split('/')
    for exc in EXCLUDE_PATTERNS:
        if exc in parts:
            return False
    for inc in INCLUDED_PREFIXES:
        if rel_path == inc or rel_path.startswith(inc):
            return True
    return False


def collect_files():
    files_to_pack = []
    for root, dirs, files in os.walk(REPO_ROOT):
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
        for full_path, arc_name in files_to_pack:
            zf.write(full_path, arcname=arc_name)

    # Mirror to workspace root
    shutil.copy2(STAGE_ZIP_PATH, STAGE_ROOT_ZIP_PATH)

    zip_bytes = STAGE_ZIP_PATH.read_bytes()
    zip_size_mb = len(zip_bytes) / (1024 * 1024)
    sha256 = hashlib.sha256(zip_bytes).hexdigest()

    print(f'\nArchive created successfully:')
    print(f'  Target: {STAGE_ZIP_PATH}')
    print(f'  Mirror: {STAGE_ROOT_ZIP_PATH}')
    print(f'  Size:   {zip_size_mb:.2f} MB ({len(zip_bytes):,} bytes)')
    print(f'  SHA256: {sha256}')


if __name__ == '__main__':
    main()
