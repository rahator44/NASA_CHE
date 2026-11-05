# Earth Pulse — Phase 4A.1: Scientific Provenance & Validation Assumption Audit
**NASA Space Apps Challenge 2026 — Dancing with the SARs**  
**Study Reach:** Jamuna River Reach, Kazipur / Sirajganj Districts, Bangladesh  
**Target Study AOI:** `POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))`  
**Audit Purpose:** Comprehensive scrutiny of all scientific assumptions, hydrological constants, and external references in the Phase 4A validation framework prior to operational execution.

---

## 1. Executive Summary & Audit Objective

In Phase 4A, an independent validation framework was established to prepare Earth Pulse for external evaluation against optical imagery, river stage observations, and terrain models. 

Phase 4A.1 conducts a **rigorous scientific code-and-documentation audit** to identify every geographical constant, hydraulic threshold, and terrain assumption introduced into the system. This audit enforces scientific integrity by verifying that:
1. No unverified constant or assumption is used in automatic operational decision-making.
2. Unverified figures are formally quarantined and classified.
3. Zero-division edge cases in validation metrics are fully documented and do not conceal missing validation classes.
4. Anti-circular validation guards strictly prevent SAR candidate masks from self-validating.
5. All completed SAR analytical calculations (Phases 1 through 3B.1) remain 100% intact and untouched.

---

## 2. Part 1 — Hydrological Constants Audit

Every hydrological parameter cited in Phase 4A was audited against local repository holdings. Because **no raw BWDB bulletins or survey benchmark files exist locally**, these parameters are classified as follows:

| Parameter | Cited Value | Local Source Citation Present | Classification | Operational Decision / Restriction |
| :--- | :---: | :---: | :---: | :--- |
| **Sirajganj Gauge SW46.9** | Lat $24.45^\circ\text{N}$, Lon $89.72^\circ\text{E}$ | **No** | **UNVERIFIED** | Prohibited from automatic operational execution. Retained as preliminary reference station ID only. |
| **Sirajganj Danger Level** | $13.35\text{ m PWD}$ | **No** | **UNVERIFIED** | Prohibited from automated thresholding. Requires official BWDB/FFWC annual bulletin. |
| **Kazipur Gauge SW46.9A** | Lat $24.67^\circ\text{N}$, Lon $89.65^\circ\text{E}$ | **No** | **UNVERIFIED** | Prohibited from automatic operational execution. Requires official BWDB station bulletin. |
| **Kazipur Danger Level** | $15.25\text{ m PWD}$ | **No** | **UNVERIFIED** | Prohibited from automated thresholding. Requires official BWDB/FFWC annual bulletin. |
| **Sariakandi Gauge SW46.8** | Lat $24.88^\circ\text{N}$, Lon $89.57^\circ\text{E}$ | **No** | **UNVERIFIED** | Located north of target AOI; preliminary literature reference only. |
| **Sariakandi Danger Level** | $16.70\text{ m PWD}$ | **No** | **UNVERIFIED** | Prohibited from automated thresholding. Requires official BWDB bulletin. |
| **PWD Vertical Datum** | National Hydrological Datum | **No** | **UNVERIFIED** | Standard national datum in Bangladesh, but unverified by local geodetic benchmark citation. |
| **PWD-to-MSL Offset** | $\text{PWD} = \text{MSL} - 0.46\text{ m}$ | **No** | **ASSUMPTION** | Standard regional approximation ($\sim 0.46\text{ m}$); geodetic offset varies locally. Prohibited from quantitative datum conversion without local survey monument. |

### Governance Action Applied:
All hardcoded station records in `scripts/validate_reference_data.py` have been marked as `UNVERIFIED_PRELIMINARY_HYPOTHESIS`. An automated gatekeeper function (`validate_gauge_reading_input`) was implemented to reject any gauge observation record that lacks verified provider authentication or official citations.

---

## 3. Part 2 — Terrain Assumptions Audit

Terrain parameters proposed in Phase 4A were evaluated to separate preliminary hypotheses from verified empirical data:

| Terrain Parameter / Hypothesis | Cited Value / Model | Local Data Present | Classification | Scientific Assessment & Operational Rule |
| :--- | :---: | :---: | :---: | :--- |
| **Floodplain Elevation Range** | $11.0 - 18.0\text{ m PWD}$ | **No** | **ASSUMPTION** | Preliminary rule-of-thumb. Prohibited from automated elevation clipping without local calibrated DEM. |
| **HAND Connectivity Threshold** | $3.0\text{ m}$ | **No** | **ASSUMPTION** | Hydraulic rule-of-thumb. Requires hydrodynamic drainage network calibration. |
| **Barind Tract Elevation** | $> 25.0\text{ m}$ | **No** | **ASSUMPTION** | Regional geomorphological context. No local DEM exists in workspace to verify terrace boundary. |
| **Radar Shadow / Layover** | Micro-shadow along embankments | **No** | **ASSUMPTION** | Qualitative physical hypothesis. Quantitative illumination masking requires high-res DSM. |
| **Copernicus GLO-30 & FABDEM** | $30\text{ m}$ Global Rasters | **No** | **UNVERIFIED** | Recommended external elevation models; neither dataset exists locally in the workspace. |

### Fundamental Scientific Principle:
**DEM/HAND models provide topographic plausibility checks (water cannot flow uphill without impoundment), NOT independent dynamic flood ground truth.** They can confirm whether a detected water body is topographically viable, but cannot determine whether surface water was physically present on July 16, 2024.

An automated gatekeeper (`validate_terrain_threshold_input`) was implemented to reject applying uncalibrated elevation or HAND cutoffs automatically.

---

## 4. Part 3 — Optical Validation Protocol Audit

The optical ingestion specification for Sentinel-2 MSI Level-2A and Landsat 8/9 Level-2 was reviewed:

- **Band Selections:**
  - Sentinel-2: B03 (Green, 10m), B08 (NIR, 10m), B11 (SWIR1, 20m), B12 (SWIR2, 20m), SCL (Scene Classification, 20m). **Verified sound.**
  - Landsat 8/9: Band 3 (Green, 30m), Band 5 (NIR, 30m), Band 6 (SWIR1, 30m), QA_PIXEL (30m). **Verified sound.**
- **Cloud & Shadow Masking:**
  - SCL classes `3` (Cloud Shadow), `7`, `8`, `9` (Cloud probabilities), `10` (Cirrus), `11` (Snow/Ice) are mapped to reference code `255` (Excluded / Uncertain). **Verified sound.**
- **Water Indices:**
  - Modified Normalized Difference Water Index (MNDWI) and Automated Water Extraction Index ($\text{AWEI}_{\text{nsh}}$). **Verified sound.**
- **Spatial Alignment:**
  - Area-weighted aggregation of 10m bands to the 20m EPSG:32645 reference grid. **Verified sound.**
- **Monsoon Cloud Cover Reality:**
  - In Bangladesh, cloud cover during June–July exceeds $85\%$. The protocol explicitly documents that cloud-free optical ground truth **cannot be assumed to exist** concurrently with SAR overpasses.

---

## 5. Part 4 — Validation Metrics Engine Audit

The validation engine in [`scripts/validate_reference_data.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/validate_reference_data.py) was audited for mathematical rigor:

### Mathematical Implementation:
- Confusion Matrix: True Positive (TP), False Positive (FP), True Negative (TN), False Negative (FN).
- Precision: $\frac{\text{TP}}{\text{TP} + \text{FP}}$
- Recall: $\frac{\text{TP}}{\text{TP} + \text{FN}}$
- F1-Score: $\frac{2\text{TP}}{2\text{TP} + \text{FP} + \text{FN}}$
- Intersection over Union (IoU): $\frac{\text{TP}}{\text{TP} + \text{FP} + \text{FN}}$
- Specificity: $\frac{\text{TN}}{\text{TN} + \text{FP}}$
- Balanced Accuracy: $\frac{\text{Recall} + \text{Specificity}}{2}$
- Overall Accuracy: $\frac{\text{TP} + \text{TN}}{\text{TP} + \text{TN} + \text{FP} + \text{FN}}$

### Zero-Division Handling Audit:
Previously, zero-division returned `0.0` silently. While computationally safe, returning `recall = 0.0` when reference data contains zero water pixels ($TP+FN=0$) can mislead users into believing the model failed, when in reality the positive class was entirely absent.
**Audit Remediation:**
The engine now emits explicit `class_distribution_flags`:
- `positive_predictions_count`, `positive_reference_count`
- `precision_undefined`: `bool(TP+FP == 0)`
- `recall_undefined`: `bool(TP+FN == 0)`
- `specificity_undefined`: `bool(TN+FP == 0)`
- `class_coverage_complete`: `bool(...)`
- Detailed explanatory `notes` annotating every undefined metric.

### Spatial Block Validation for Machine Learning:
To prevent spatial autocorrelation data leakage in future ML models, a $5\text{ km} \times 5\text{ km}$ spatial block cross-validation protocol with $500\text{ m}$ buffer halo exclusion zones was verified and documented.

---

## 6. Part 5 — Reference Data Registry Audit

The registry file [`data/metadata/reference_data_registry.json`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/metadata/reference_data_registry.json) was audited:
- **Required Fields Enforced:**
  `dataset_name`, `category`, `provider`, `source_identifier`, `source_url_or_citation`, `original_acquisition_date`, `spatial_extent_wkt`, `crs`, `resolution`, `processing_history`, `license_or_usage_conditions`, `intended_validation_purpose`, `local_file_path`, and `quality_information`.
- **Registry Count:** Exactly **0 registered datasets** (no fabricated entries; reflects true local state).

---

## 7. Part 6 — Anti-Circular Validation Guard

The framework strictly enforces the **Anti-Circular Validation Principle**:
- Candidate SAR water masks cannot validate candidate SAR water masks.
- `validate_reference_dataset_provenance()` inspects file paths, dataset names, and processing history, immediately raising:  
  $$\mathbf{CIRCULAR\_VALIDATION\_ERROR}$$  
  if any reference file derives from Sentinel-1 backscatter, Otsu thresholding, or Lee filtering.

---

## 8. Part 7 — Automated Testing Suite

A dedicated regression test suite was developed in [`tests/test_phase4a_provenance.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase4a_provenance.py) containing **8 automated unit tests**:
1. `test_rejection_of_unverified_gauge_values`: Asserts rejection of gauge records lacking provider verification or citations.
2. `test_rejection_of_unverified_danger_levels`: Asserts rejection of danger levels lacking official citations.
3. `test_rejection_of_unsupported_elevation_thresholds`: Asserts rejection of uncalibrated elevation/HAND thresholds without calibrated DEM.
4. `test_reference_provenance_requirements`: Asserts enforcement of all required metadata fields, including quality information.
5. `test_optical_uncertainty_masking`: Asserts code 254 (uncertain cloud/shadow) and 255 (NoData) are strictly excluded from metrics.
6. `test_anti_circular_validation_guard`: Asserts SAR masks are rejected with `CIRCULAR_VALIDATION_ERROR`.
7. `test_missing_reference_data_status`: Asserts `BLOCKED_REFERENCE_DATA_MISSING` status when workspace is empty.
8. `test_validation_metrics_incomplete_class_coverage`: Asserts explicit zero-division flags when positive reference or prediction pixels are absent.

**Test Run Results:**
- `tests/test_phase4a_provenance.py`: **8 passed in 0.55s**
- `tests/test_phase4a_validation.py`: **12 passed in 0.58s**
- **Full Repository Suite:** **114 passed in 10.95s** across all phases (Phase 1 through Phase 4A.1).

---

## 9. Part 8 — Summary of Corrections & Remediations Applied

1. **Hydrological Constants Quarantined:** Gauge station coordinates, danger levels, and datum offsets are labeled `UNVERIFIED_PRELIMINARY_HYPOTHESIS` and prohibited from automatic operational execution.
2. **Terrain Assumptions Quarantined:** Elevation ranges (11-18m) and HAND cutoffs (3m) are classified as `ASSUMPTION` and barred from automated filtering without verified local DEMs.
3. **Zero-Division Handling Enhanced:** Validation metrics now report `class_distribution_flags` that clearly explain when validation classes are absent.
4. **Registry Schema Updated:** `quality_information` and `source_identifier` added to required registry fields.
5. **No Modifications to Analytical Results:** All previously computed SAR rasters, thresholds, and change metrics (Phases 1 through 3B.1) remain 100% verified and intact.

---

## 10. Current Validation Status & Manual Data Requirements

$$\mathbf{CURRENT \quad VALIDATION \quad STATUS: \quad BLOCKED\_REFERENCE\_DATA\_MISSING}$$

To operationalize validation, the following external datasets must be manually acquired out-of-band:
1. **BWDB Hydrology:** Verified daily water level records for Sirajganj (SW46.9) and Kazipur (SW46.9A) for June–July 2024.
2. **Sentinel-2 MSI Level-2A:** Cloud-masked scenes covering the Kazipur reach for early/mid June and mid/late July 2024.
3. **Copernicus GLO-30 DEM:** Tile `N24_E089` for topographic plausibility filtering.

