# Earth Pulse — Phase 8.6: Independent Scientific Review Reconciliation Report

**Project:** EarthPulse-SAR  
**Challenge:** NASA Space Apps Challenge 2026 — *Dancing with the SARs*  
**Study Area:** Jamuna River reach (Kazipur / Sirajganj, Bangladesh)  
**Authors:** Senior Scientific Software Architect, Remote-Sensing Specialist, Machine-Learning Auditor  
**Date:** November 2026  
**Test Baseline:** 337 passing unit, integration, and mathematical verification tests (0 warnings, 0 deprecations)  

---

## 1. Executive Summary & Purpose

Following the external independent review of the Earth Pulse remote-sensing backend and verification packages, Phase 8.6 was executed as a focused scientific reconciliation and quality-assurance phase. The objective was to eliminate any remaining discrepancies between backend API contracts, metadata manifests, documentation, and the authoritative raster and vector products generated across Phases 1 through 7B.1.

Strict rules were maintained:
1. **No Project Rebuild:** Original Sentinel-1 and Sentinel-2 satellite archives, authoritative GeoTIFF rasters, and historical phase outputs were strictly preserved.
2. **Frozen Model Integrity:** The trained Random Forest model artifact (`models/phase7a/phase7a_random_forest_model.joblib`) was kept completely frozen with cryptographic hash `85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad`.
3. **No Retraining or Extra Dependencies:** Zero external package installations or data redownloads.
4. **Physical Baseline Primacy:** The dual-polarization Lee 5×5 filtered Otsu thresholding engine remains the authoritative primary flood detection standard, while the Random Forest classifier is retained strictly as an auxiliary probability layer (`RETAINED_AS_PROBABILITY_LAYER`, $\tau^* = 0.35$).

---

## 2. Issue Reconciliation Register & Mathematical Details

| Issue ID | Component | Summary | Root Cause | Reconciliation Action |
|:---|:---|:---|:---|:---|
| **ISSUE-01** | `contracts/flood` | Flood Transition Accounting Domain Divergence | Phase 8.4 reported the full raster bounding box ($1,888,722$ cells) instead of the authoritative Jamuna Study AOI ($993,736$ valid cells). | Reconciled common valid domain to $993,736$ cells ($397.49\text{ km}^2$), persistent non-water to $628,515$ cells ($251.41\text{ km}^2$), added indeterminate noise floor ($16,242$ cells) and boundary NoData ($61$ cells). Enforced closed identities. |
| **ISSUE-02** | `riverbank/geomorphology` | Riverbank Lateral Displacement Statistics Divergence | Reported numbers conflated all transects with the 122 valid local migration transects, and omitted explicit medians. | Reconciled empirical stats from 122 valid rows: West (mean=$130.00\text{ m}$, med=$40.0\text{ m}$), East (mean=$160.66\text{ m}$, med=$90.0\text{ m}$), Channel Width (mean=$290.66\text{ m}$, med=$180.0\text{ m}$). Confirmed 95% spatial block bootstrap CIs. |
| **ISSUE-03** | `ml/explainability` | Explainable AI Node Traversal Precision Divergence | Node traversal evaluated features in `float64` while decision tree splits evaluated in `float32` during inference, causing boundary path divergences (residuals up to $0.0093$). | Cast input features to `np.float32` inference representation, reducing max additivity residual to $1.15 \times 10^{-7} < 10^{-5}$ across all test instances and boundary conditions. Supported both `ensemble_root` and `background` baselines. |
| **ISSUE-04** | `backend/raster_service` | Out-of-AOI Flood Map Display in Web Tiles | GDAL Warp rendered the raw raster extent ($1,957,165$ cells), rendering unvalidated classifications outside the study AOI. | Added GDAL cutline masking (`/vsimem/study_area_aoi.geojson`) with `dstNodata=255.0` for categorical rasters, ensuring all pixels outside the study AOI render 100% transparent. |
| **ISSUE-05** | `documentation` | Algorithmic Terminology Alignment | Outdated narrative text referenced Lee 7×7, 100 m transects, peak crest, async queue, and generic SHAP. | Corrected `README.md` and documentation: Lee 5×5 window, 200 m transects (154 evaluated), mid-monsoon flood observation (July 16), synchronous job execution, and Saabas-style pure-NumPy tree attribution. |
| **ISSUE-06** | `ml/random_forest` | Random Forest Model Specifications | Reviewers assumed default 100-tree scikit-learn model rather than pure-NumPy 40-tree architecture. | Verified 40 trees, max depth 6; verified held-out test metrics (ROC-AUC $0.6810$, Precision $0.4477$, Recall $0.9214$, Accuracy $0.5178$); confirmed rationale for auxiliary probability status. |
| **ISSUE-07** | `devops/hygiene` | Repository and Packaging Cleanliness | Development database backup files could inadvertently leak into public distribution archives. | Added explicit file filters in packaging scripts to exclude `.local_backup` and `.pre_phase8_4_backup` artifacts. |

---

## 3. Mathematical Accounting Identities

### 3.1 Flood Inundation Mass Balance

The authoritative surface water classification across the Jamuna Study AOI ($404.0156\text{ km}^2$, $1,010,039$ cells at $20\text{ m} \times 20\text{ m}$) is governed by exact conservation laws:

$$\text{Common Valid Domain} = C_1 + C_2 + C_3 + C_4 = 216,595 + 146,992 + 1,634 + 628,515 = 993,736\text{ cells}\quad (39,749.44\text{ ha})$$

$$\text{Total Study AOI} = \text{Common Valid Domain} + \text{Indeterminate} + \text{NoData} = 993,736 + 16,242 + 61 = 1,010,039\text{ cells}\quad (40,401.56\text{ ha})$$

$$\text{Net Candidate Water Change} = C_2 - C_3 = 146,992 - 1,634 = 145,358\text{ cells}\quad (5,814.32\text{ ha})$$

$$\text{Asymmetric Exclusion Gap} = \Delta_{\text{whole-epoch}} - \Delta_{\text{valid-domain}} = 6,452.24\text{ ha} - 5,814.32\text{ ha} = 637.92\text{ ha}\quad (15,948\text{ cells})$$

### 3.2 Riverbank Displacement Population Structure

Out of the 154 evaluated transects normal to the Jamuna braid-belt centerline:
- **122 Valid Local Migration Transects ($79.22\%$):** True morphological bank movement.
  - West Bank (Right/Mainland): $\text{Mean} = 130.00\text{ m}$, $\text{Median} = 40.0\text{ m}$, $\text{IQR} = 200.0\text{ m}$, $95\%\text{ Bootstrap CI} = [20.0, 80.0]\text{ m}$
  - East Bank (Left/Chars): $\text{Mean} = 160.66\text{ m}$, $\text{Median} = 90.0\text{ m}$, $\text{IQR} = 275.0\text{ m}$, $95\%\text{ Bootstrap CI} = [20.0, 150.0]\text{ m}$
  - Channel Width: $\text{Mean} = 290.66\text{ m}$, $\text{Median} = 180.0\text{ m}$, $\text{IQR} = 360.0\text{ m}$, $95\%\text{ Bootstrap CI} = [120.0, 320.0]\text{ m}$
- **32 Outside Valid-Local Transects ($20.78\%$):**
  - 23 Ambiguous Edge Effects
  - 5 Anabranch Activations
  - 4 Major Channel Expansions

---

## 4. Verification Tools & Test Coverage

Four standalone verification scripts are provided under `tools/verification/` for direct, independent execution:
1. `tools/verification/verify_flood_counts.py`: Confirms Phase 5 raster pixel counts, area conversions, and dual-domain reconciliation.
2. `tools/verification/verify_riverbank_statistics.py`: Confirms 154-transect audit population, 122 valid rows empirical statistics, and 95% spatial bootstrap intervals.
3. `tools/verification/verify_model_metrics.py`: Confirms frozen model SHA-256 hash, 40-tree architecture, 31,522 dataset samples, and held-out test split evaluation metrics at $\tau^* = 0.35$.
4. `tools/verification/verify_explanation_additivity.py`: Confirms float32 inference representation, sub-microsecond local tree-path additivity ($|residual| < 10^{-5}$), and global specular backscatter feature dominance.

All 337 tests across unit, integration, regression, and reconciliation test modules pass with zero failures and zero warnings under Python 3.10+:
```bash
python3 -m pytest tests/ -q
# Output: 337 passed in 38.92s
```
