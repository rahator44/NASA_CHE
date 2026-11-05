# EARTH PULSE — SCIENTIFIC PROJECT HANDOFF & REVIEW DOSSIER (PHASE 8.4)

NASA Space Apps Challenge 2026 — Dancing with the SARs  
Project: EarthPulse-SAR  
Study Reach: Jamuna River, Kazipur / Sirajganj, Bangladesh  
Date: November 5, 2026  
Current Baseline: Phase 8.4 Verified & Sealed  

---

## 1. Project Overview & Repository State

EarthPulse-SAR is a scientific remote-sensing and machine-learning system designed for multi-temporal flood inundation detection, fluvial riverbank displacement tracking, and explainable AI along dynamic braided alluvial rivers.

- **Primary Study Area**: Jamuna River reach (Kazipur / Sirajganj, Bangladesh), UTM Zone 45N (`EPSG:32645`).
- **Core Observation Epochs**:
  - Baseline: June 10, 2024 (Pre-monsoon baseflow / exposed sandbars).
  - Flood Observation: July 16, 2024 (Monsoon flood-period observation / anabranch expansion).
- **Current Repository Status**:
  - Total Passing Tests: **330 passed** (0 failures, 0 warnings).
  - Python Environment: Python 3.14 / 3.13 / 3.12 compatible with GDAL 3.10+.
  - Machine-Learning Architecture: Pure-NumPy vectorized Random Forest with Saabas tree-path attribution.
  - Frozen Model Artifact: `models/phase7a/phase7a_random_forest_model.joblib` (SHA-256: `85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad`).
  - Model Operational Status: `RETAINED_AS_PROBABILITY_LAYER` (Test ROC-AUC: 0.6810, Threshold $\tau^* = 0.35$).
  - Primary Operational Flood Baseline: Adaptive Lee 5x5 Dual-AND Otsu (VV & VH).

---

## 2. Phase 8.4 Source-Backed Corrections Summary

Phase 8.4 reconciled all backend services with authoritative bundled CSV and JSON sources of truth:

1. **Flood Inundation Accounting**:
   - Common Valid Domain: **75,548.88 ha** (1,888,722 cells).
   - Persistent Water: **8,663.80 ha** (216,595 cells, 11.47%).
   - Newly Inundated Candidate: **5,879.68 ha** (146,992 cells, 7.78%).
   - Receded Water: **65.36 ha** (1,634 cells, 0.09%).
   - Persistent Non-Water: **60,940.04 ha** (1,523,501 cells, 80.66%).
   - Net Surface Water Expansion (Valid Domain): **+5,814.32 ha** (+145,358 cells).
   - Whole-Epoch Unmasked Delta: **6,452.24 ha** (161,306 cells).
   - Asymmetric Radar Mask Exclusion Gap: **637.92 ha** (15,948 cells).
2. **Fluvial Riverbank Transect Population**:
   - Total Evaluated Transects: **154** (from `phase6_1_transect_displacement_audit.csv`).
   - Valid Local Migration: **122** (79.22% valid fraction).
   - Outside Valid-Local: **32** (23 ambiguous edge effects, 5 anabranch activations, 4 major expansions).
   - Standard Field Name: `chainage_m`.
3. **Statistical Uncertainty & Confidence Intervals**:
   - Empirical percentiles (P10/P90) strictly segregated from bootstrap bounds.
   - 95% Spatial Block Bootstrap Confidence Intervals:
     - West Bank Median: **[20.0, 80.0] m** (mean: [59.84, 203.28] m).
     - East Bank Median: **[20.0, 150.0] m** (mean: [101.97, 222.79] m).
     - Channel Width Median: **[120.0, 320.0] m** (mean: [194.43, 378.03] m).
   - Provisional Scenario Detection Thresholds: 35.0 m (cut-bank), 60.0 m (nominal), 85.0 m (char fringe).
4. **General Fluvial Change Zones**:
   - Zone 2 (External Bank Expansion): **21.9400 km²** (2,194.00 ha, 54,850 cells).
   - Zone 3 (Internal Char Submergence): **23.2100 km²** (2,321.00 ha, 58,025 cells).
   - Zone 4 (Apparent Contraction / Accretion): **0.4148 km²** (41.48 ha, 1,037 cells).
   - Zone 6 (Disconnected Floodplain Inundation): **13.6468 km²** (1,364.68 ha, 34,117 cells).
5. **Raster & Vector Enhancements**:
   - 12-class geomorphic palette implemented for channel change zones.
   - Dynamic CRS extraction from raster dataset spatial reference.
   - NoData sentinels (`<= -9990.0`) rendered with 100% alpha transparency.
   - Vectors dynamically reprojected to RFC 7946 standard EPSG:4326 (`[lon, lat]`), preserving `native_crs: "EPSG:32645"`.
6. **Backend Robustness & Security**:
   - Strict 404 rejection for unknown `region_id` and `model_id`.
   - Streaming SHA-256 calculation for background dataset integrity audits.
   - Sanitized global exception handler preventing server traceback leaks.
   - Normalized system endpoints (`/health`, `/api/v1/system/status`, `/api/v1/system/capabilities`).

---

## 3. Authoritative Source Documents

All figures and models are certified by the following project artifacts:

| Domain | Authoritative Primary Source | Description |
|---|---|---|
| Model Weights | `models/phase7a/phase7a_random_forest_model.joblib` | Frozen pure-NumPy Random Forest model (40 trees, depth 6) |
| Model Metadata | `models/model_registry.json` | Registered model parameters, SHA-256, and promotion gate |
| Flood Transitions | `data/metadata/phase5_flood_change_report.json` | Dual-AND Otsu Common Valid Domain transition accounting |
| Flood Area Summary | `data/outputs/phase5/statistics/phase5_inundation_area_summary.csv` | Categorical cell counts and hectare distributions |
| Transect Audit | `data/outputs/phase6_1/statistics/phase6_1_transect_displacement_audit.csv` | 154 evaluated transects with chainage and status |
| Bootstrap CIs | `data/outputs/phase6_2/statistics/phase6_2_spatial_bootstrap_intervals.csv` | 95% spatial block bootstrap confidence intervals |
| General Zones | `data/outputs/phase6_1/statistics/phase6_1_area_reconciliation.csv` | 12-class channel change codebook and surface areas |
| Data Contracts | `src/backend/contracts.py` | Immutable programmatic contracts for all backend services |
| Issue Register | `data/outputs/phase8_4/issue_resolution_register.csv` | Itemized audit register of 22 resolved findings |

---

## 4. Verification Instructions for External Reviewers

To run the complete independent test verification suite:

```bash
cd /home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR
python3 -m pytest -v
```

Expected output:
```text
============================= 330 passed in 21.67s =============================
```

To run the dedicated Phase 8.4 backend corrections regression suite:

```bash
python3 -m pytest tests/test_phase8_4_backend_corrections.py -v
```

Expected output:
```text
============================== 15 passed in 3.07s ==============================
```

To verify the frozen Random Forest model SHA-256 integrity:

```bash
sha256sum models/phase7a/phase7a_random_forest_model.joblib
# Must output: 85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad
```
