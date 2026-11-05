# Phase 8.3 — Automated GitHub & Google Drive Project Handoff
### NASA Space Apps Challenge 2026 — Dancing with the SARs

**Project Root:** `/home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR`  
**GitHub Destination:** `https://github.com/rahator44/NASA_CHE`  
**Google Drive Destination:** `pillior44@gmail.com`  
**Target Reviewer:** External AI / Independent Reviewer (e.g., ChatGPT)  
**Baseline Test Suite:** 315 passing tests, 0 warnings (15.48s execution time)  
**Date:** November 5, 2026

---

## 1. Executive Summary

Phase 8.3 establishes the automated, reproducible repository handoff for Earth Pulse. The system (~5.67 GB total data volume across 652 files) has been cryptographically cataloged, partitioned, staged, and verified for dual-destination distribution:

1. **Lightweight GitHub Codebase (~89.1 MB, 360 files):**
   Houses all source code (`src/`), unit and integration tests (`tests/`), YAML configurations (`configs/`), technical documentation (`docs/`), vector GeoJSONs, metadata JSONs, output CSVs, and the serialized Phase 7A Random Forest model artifact (104 KB). No file exceeds 10 MB.
2. **Standardized Google Drive Scientific Archive (~5.59 GB, 231 files):**
   Organized into an 8-folder hierarchy on Google Drive (`EarthPulse-SAR-Scientific-Data`) preserving original Sentinel-1 GRD SAR archives, Sentinel-2 optical SAFE bundles, calibrated Sigma0 GeoTIFFs, and automated restore utilities.
3. **Automated Verification & Restoration Engine (`tools/restore_earthpulse_data.py`):**
   Enables one-command restoration and SHA-256 integrity verification across all 651 tracked files with zero errors.

---

## 2. Storage Partition & File Transfer Inventory

The repository inventory has been strictly partitioned across the 10 standard categories:

| Category | Description | Destination | File Count | Data Volume |
| :--- | :--- | :--- | :--- | :--- |
| **A: Core Source Code** | Python modules in `src/`, `tools/`, `scripts/` | GitHub | 104 files | ~1.8 MB |
| **B: Configuration** | YAML configs in `configs/`, `pyrightconfig.json` | GitHub | 15 files | ~24 KB |
| **C: Test Suite** | Test fixtures and test scripts in `tests/` | GitHub | 28 files | ~480 KB |
| **D: Documentation** | Phase reports in `docs/`, `README.md`, Review Guide | GitHub | 40 files | ~1.2 MB |
| **E: Small Vector Data** | GeoJSON shorelines, transects, inundation zones | GitHub | 166 files | ~75.4 MB |
| **F: Small Model Artifacts** | Phase 7A Random Forest model (.joblib) | GitHub & Drive | 1 file | 104 KB |
| **G: Raw Satellite Data** | Sentinel-1 GRD archives & Sentinel-2 MSI SAFE bundles | Google Drive | 18 files | 5.29 GB |
| **H: Processed Rasters** | Calibrated GeoTIFFs, DIM, IMG, and HDR rasters | Google Drive | 173 files | ~329 MB |
| **I: Build & Caches** | Python `__pycache__`, `.pytest_cache`, logs | Excluded | 100 files | ~2.4 MB |
| **J: Sensitive Files** | Environment secrets, keys, private tokens | Excluded | 0 files | 0 bytes |

### Phase 8.3 Output CSV Deliverables
All manifests are generated and preserved in `data/outputs/phase8_3/`:
- `file_transfer_manifest.csv` — Full 651-file classification database with destination routing.
- `github_upload_inventory.csv` — 360 files staged for GitHub publication (89.16 MB).
- `drive_upload_inventory.csv` — 231 files staged for Google Drive backup (5.59 GB).
- `checksum_verification.csv` — Authoritative SHA-256 database validating repository integrity.

---

## 3. Security, Credential & Sensitive Data Audit

Prior to staging, an exhaustive security audit was executed across all 645 files:
- **Scan Report:** `data/metadata/phase8_3_security_audit.json`
- **Result:** **PASSED (0 findings)**
- **Checked Patterns:** API keys, AWS credentials, Bearer tokens, GitHub personal access tokens (`ghp_`, `github_pat_`), RSA/SSH private keys.
- **Sensitive Extensions Checked:** `.env`, `.key`, `.pem`, `.token`, `.p12`, `.pfx`, `credentials.json`, `service_account.json`.
- **Verdict:** No sensitive tokens or secrets are present in the repository. All test fixtures rely on synthetic, mock, or relative references.

---

## 4. GitHub Repository Configuration & Visibility Notice

### Remote Details
- **Target Repository:** `https://github.com/rahator44/NASA_CHE`
- **SSH URL:** `git@github.com:rahator44/NASA_CHE.git`
- **Authentication:** Verified via SSH public key (`rahator44`).

> [!WARNING]
> **Repository Visibility Requirement:**
> The repository `rahator44/NASA_CHE` is currently configured as **PUBLIC** on GitHub (`"private": false`).
> To protect project materials and conform to Space Apps guidelines before release, the repository visibility should be toggled to **PRIVATE** in the GitHub repository Settings (`Settings -> Danger Zone -> Change repository visibility -> Make private`).

### Git Commit Specification
- **Working Tree:** Fully configured with `.gitignore` excluding all large binaries and caches.
- **Staged File Count:** 360 files.
- **Total Payload Size:** ~89.16 MB (individual files $\le 9.58$ MB).
- **Commit Message:**
  ```text
  Earth Pulse - Phase 8.1 verified scientific backend handoff
  ```

---

## 5. Google Drive Scientific Data Staging

The complete ~5.59 GB scientific dataset has been staged into the standardized 8-folder directory structure at:
`/home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR-Scientific-Data/`

### Subfolder Organization
```text
EarthPulse-SAR-Scientific-Data/
├── 01_Sentinel1_Raw/            # 2 files, 2.59 GB (June 10 & July 16, 2024 GRDH archives)
├── 02_Sentinel2_Raw/            # 16 files, 2.70 GB (Sentinel-2 MSI Level-2A SAFE & JP2s)
├── 03_Processed_GeoTIFF/        # 173 files, 329 MB (Calibrated Sigma0, Otsu masks, filters)
├── 04_Reference_Data/           # Hydrology and terrain rasters
├── 05_Model_Artifacts/          # 1 file, 104 KB (Random Forest joblib model)
├── 06_Large_Scientific_Outputs/ # 1 file, 10 MB (High-res backscatter delta map)
├── 07_Manifests_and_Checksums/  # 35 files (Transfer manifests, metadata, SQLite state)
└── 08_Backup_and_Restore/       # 3 files (restore script, instructions, SHA-256 hashes)
```

Staged using hardlinks on the local NVMe filesystem, utilizing 0 bytes of extra disk space while providing complete files for upload tools (e.g., `rclone` or web browser).

### Uploading to Google Drive (`pillior44@gmail.com`)
To push the staged directory to Google Drive via `rclone`:
```bash
# Example rclone configuration command:
rclone copy /home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR-Scientific-Data/ gdrive:EarthPulse-SAR-Scientific-Data -P --transfers 4
```

---

## 6. Scientific Data Restoration & Integrity Tool

The standalone tool [`tools/restore_earthpulse_data.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tools/restore_earthpulse_data.py) provides verification and restoration:

### Usage Instructions
```bash
# 1. Verify integrity of all local repository files
python3 tools/restore_earthpulse_data.py --verify-only

# 2. Dry run restore from downloaded Google Drive folder
python3 tools/restore_earthpulse_data.py --source-dir /path/to/EarthPulse-SAR-Scientific-Data --dry-run

# 3. Perform full restoration into EarthPulse-SAR data directories
python3 tools/restore_earthpulse_data.py --source-dir /path/to/EarthPulse-SAR-Scientific-Data --mode copy
```

### Verification Benchmark
```text
======================================================================
EARTH PULSE — SCIENTIFIC DATA RESTORATION & VERIFICATION
Repository Root: /home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR
Checksum File:   data/outputs/phase8_3/checksum_verification.csv
======================================================================
[+] Loaded 651 entries from checksum database.
[*] Verifying existing repository files against 651 recorded checksums...
----------------------------------------------------------------------
VERIFICATION SUMMARY:
  Intact & Verified: 651
  Mismatched:        0
  Missing:           0
  Total Checked:     651
----------------------------------------------------------------------
```

---

## 7. Reviewer Handoff Documentation

The independent code review package is authored and committed at the repository root:
[`EARTH_PULSE_INDEPENDENT_REVIEW.md`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/EARTH_PULSE_INDEPENDENT_REVIEW.md)

It contains complete instructions for an external reviewer (e.g., ChatGPT) to:
1. Re-run and verify the 315-test baseline.
2. Spin up the FastAPI backend service (`uvicorn src.backend.main:app`).
3. Audit the Random Forest model and custom NumPy tree-path attribution mathematical axioms.
4. Review the 8 non-blocking items from the Phase 8.1 Issue Register.
5. Inspect the fluvial geomorphology transects and flood inundation accounts.

---

## 8. Cryptographic Hash Invariants

The pre-upload invariant hashes have remained untouched and identical throughout Phase 8.3:

| Critical File | Expected SHA-256 Hash | Status |
| :--- | :--- | :--- |
| `models/phase7a/phase7a_random_forest_model.joblib` | `85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad` | Verified Intact |
| `src/backend/main.py` | `8d2cbebb4b6cf2a0515a3736ba95ce7dc3fec13134e64ad2feb5bdb34f35e1ff` | Verified Intact |
| `src/ml/random_forest.py` | `adbe913332ec601bd138f20d3d10a48a4b19353e763265fd3e2f0afc4deb9411` | Verified Intact |
| `src/ml/explainability.py` | `82f593755259d779f575eff920a3af6c0230fc6bb6ae7c935302d6d12ecec0ea` | Verified Intact |

*Phase 8.3 is completed, verified, and ready for reviewer dispatch.*
