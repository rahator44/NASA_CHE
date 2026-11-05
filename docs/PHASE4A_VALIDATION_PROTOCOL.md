# Earth Pulse — Phase 4A: Independent Flood Validation Protocol
**NASA Space Apps Challenge 2026 — Dancing with the SARs**  
**Study Reach:** Jamuna River, Kazipur & Sirajganj Districts, Bangladesh  
**Target Study AOI:** `POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))`  
**Target Reference Grid:** EPSG:32645 (WGS 84 / UTM Zone 45N), $20.0\text{ m}$ pixel spacing, $1405 \times 1393$ cells  

---

## 1. Executive Summary & Scientific Purpose

The Earth Pulse processing chain through Phase 3B.1 produced rigorous, multi-temporal candidate surface-water change maps from Sentinel-1 SAR backscatter. However, in satellite remote sensing, **candidate classification is not confirmed physical ground truth**. 

Phase 4A establishes an **independent, defensible scientific validation framework** to quantitatively evaluate SAR-derived inundation masks against external evidence. Crucially, this protocol enforces strict scientific boundaries between different tiers of evidence to prevent false claims of validation.

---

## 2. Evidence Taxonomy: Distinguishing Degrees of Truth

Validation evidence is structured into four distinct hierarchical tiers. These forms of evidence are **not scientifically interchangeable**:

```
+-----------------------------------------------------------------------------------+
| TIER 1: FLOOD-EVENT DOCUMENTATION                                                 |
| NDRCC Disaster Reports, UN OCHA Situation Reports, NIRAPAD Assessments             |
| Role: Confirms regional occurrence of flooding; CANNOT validate pixel boundaries. |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| TIER 2: HYDROLOGICAL CORROBORATION                                                |
| BWDB/FFWC Daily River Stage Gauges (Sirajganj, Kazipur, Sariakandi)               |
| Role: Proves 1D hydraulic surcharge relative to Danger Level;                     |
|       CANNOT prove 2D spatial inundation across the 404 km² AOI.                   |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| TIER 3: PIXEL-LEVEL INDEPENDENT REFERENCE VALIDATION                              |
| Cloud-masked Sentinel-2 MSI / Landsat 8-9 OLI Water Reference Masks               |
| Role: Provides direct spatial truth for 2x2 confusion matrix, IoU, and F1-score.  |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| TIER 4: TERRAIN CONTEXTUAL ASSESSMENT                                             |
| Copernicus GLO-30 DEM, FABDEM, Height Above Nearest Drainage (HAND)               |
| Role: Provides physical plausibility constraints (depressions vs terraces);       |
|       NOT dynamic surface-water ground truth.                                     |
+-----------------------------------------------------------------------------------+
```

---

## 3. Strict Scientific Rules & Anti-Circular Validation

1. **Anti-Circular Validation Principle:**
   - SAR candidate masks must **never** be evaluated against other SAR candidate masks as ground truth.
   - Cross-filter comparisons (e.g., Lee 5×5 vs Lee 3×3) measure *methodological sensitivity*, not *accuracy*.
   - Any reference dataset whose file path or processing provenance derives from Sentinel-1 or backscatter thresholding is immediately rejected.
2. **Missing-Data Integrity Guard:**
   - Accuracy metrics (Precision, Recall, F1, IoU) are **never calculated or reported** in the absence of genuine independent reference labels.
   - If no reference data exists locally, the system status is formally set to:  
     $$\mathbf{BLOCKED\_REFERENCE\_DATA\_MISSING}$$
3. **No Uncalibrated Claims:**
   - Unsupervised candidate water changes must not be cited as "confirmed flood disaster boundaries" or "flood damage" without external ground calibration.

---

## 4. Optical Reference Ingestion Specification

### A. Sentinel-2 MSI (Level-2A Bottom-Of-Atmosphere)
- **Spectral Bands:**
  - $10\text{ m}$ visible/NIR: Band 2 (Blue), Band 3 (Green), Band 4 (Red), Band 8 (NIR).
  - $20\text{ m}$ SWIR: Band 11 (SWIR-1, $1.610\,\mu\text{m}$), Band 12 (SWIR-2, $2.190\,\mu\text{m}$).
  - $20\text{ m}$ Scene Classification Layer (SCL).
- **Cloud & Shadow Masking:**
  - Strict masking of SCL classes: `3` (Cloud Shadows), `7` (Low Proba Cloud), `8` (Medium Proba Cloud), `9` (High Proba Cloud), `10` (Thin Cirrus), `11` (Snow/Ice).
  - Masked optical pixels are assigned reference code `255` (Excluded / Uncertain) and excluded from the validation denominator.
- **Water Index Formulation:**
  - Modified Normalized Difference Water Index (MNDWI):
    $$\text{MNDWI} = \frac{\rho_{\text{Green}} - \rho_{\text{SWIR1}}}{\rho_{\text{Green}} + \rho_{\text{SWIR1}}} = \frac{B03 - B11}{B03 + B11}$$
  - Automated Water Extraction Index (no shadow, AWEInsh):
    $$\text{AWEI}_{\text{nsh}} = 4 \cdot (B03 - B11) - (0.25 \cdot B08 + 2.75 \cdot B12)$$
- **Spatial Alignment:**
  - Reproject to EPSG:32645 (WGS 84 / UTM Zone 45N).
  - Resample $10\text{ m}$ visible bands to $20\text{ m}$ using area-weighted pixel aggregation matching the reference grid.

### B. Landsat 8/9 OLI (Collection 2 Level-2 Surface Reflectance)
- **Spectral Bands:** Band 3 (Green), Band 5 (NIR), Band 6 (SWIR-1), `QA_PIXEL`.
- **Quality Bitmask:** Mask Bit 1 (Dilated Cloud), Bit 2 (Cirrus), Bit 3 (Cloud), Bit 4 (Cloud Shadow).
- **Resampling:** Reproject and resample from $30\text{ m}$ to $20\text{ m}$ matching the reference grid.

### C. Monsoon Cloud-Cover Limitation in Bangladesh
Optical validation during June–July in the Jamuna basin faces severe cloud obscuration ($> 85\%$ average monsoon cloudiness). A search window of $\pm 5$ days around June 10 and July 16 must be utilized to capture cloud-free slivers, or multi-day cloud-free composites must be compiled.

---

## 5. Hydrological River Gauge Ingestion Specification

### A. Gauge Station Network
The Bangladesh Water Development Board (BWDB) and Flood Forecasting and Warning Centre (FFWC) maintain primary hydrological stations along the Jamuna River reach:

| Station ID | Station Name | River | Latitude | Longitude | Danger Level (m PWD) | Recorded Flood Level 1988 (m PWD) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **SW46.9** | **Sirajganj** | Jamuna | $24.45^\circ\text{N}$ | $89.72^\circ\text{E}$ | **13.35 m** | 15.12 m |
| **SW46.9A** | **Kazipur** | Jamuna | $24.67^\circ\text{N}$ | $89.65^\circ\text{E}$ | **15.25 m** | 16.65 m |
| **SW46.8** | **Sariakandi** | Jamuna | $24.88^\circ\text{N}$ | $89.57^\circ\text{E}$ | **16.70 m** | 19.07 m |

### B. Vertical Datum & Measurement Semantics
- **Vertical Datum:** Public Works Department (PWD) Datum.
  $$\text{Elevation (PWD)} = \text{Elevation (MSL)} + 0.46\text{ m}$$
- **Hydraulic Threshold Semantics:**
  - $\text{Water Level} < \text{Danger Level}$: Within bankfull channel capacity; ordinary seasonal rise.
  - $\text{Water Level} \ge \text{Danger Level}$: Bankfull discharge exceeded; overtopping of natural riverbanks initiated.
  - $\text{Water Level} \ge \text{Danger Level} + 1.0\text{ m}$: Severe flood surge; risk of breach to the Brahmaputra Right Embankment (BRE).

### C. Gauge Surcharge vs Spatial Extent
A gauge station records a **1D point-measurement of water surface elevation**. While river stage exceeding the Danger Level corroborates regional inundation onset, it **cannot delineate 2D spatial flood boundaries**. Inundation patterns depend on polder dikes, road embankments, channel avulsions, and local micro-topography.

---

## 6. Terrain & Hydraulic Connectivity Protocol

### A. Recommended Datasets
- **Copernicus DEM GLO-30:** $30\text{ m}$ global elevation model (WGS84).
- **FABDEM:** $30\text{ m}$ bare-earth elevation model with tree and building bias removed.
- **Height Above Nearest Drainage (HAND):** Normalizes elevation relative to the local drainage network.

### B. Analytical Rules
1. **Plausibility Envelope:** Candidate inundation detected on elevated Pleistocene terraces (Barind Tract, elevations $> 25\text{ m}$) where no hydraulic connection exists must be tagged as false-positive agricultural ponding or soil moisture anomalies.
2. **Hydraulic Connectivity:** Floodwaters from river overtopping must exhibit continuous connectivity to the active drainage network ($\text{HAND} \le 3.0\text{ m}$).
3. **Radar Shadow & Layover:** While the Jamuna reach is a low-gradient braided floodplain, high road embankments, bridges (e.g. Bangabandhu Jamuna Bridge), and homestead tree groves create local micro-shadow and double-bounce artifacts.

---

## 7. Validation Metrics Engine Formulation

When independent reference labels $R \in \{0, 1\}$ are available for candidate pixels $C \in \{0, 1\}$, the validation engine computes:

### A. 2×2 Confusion Matrix
$$\begin{array}{c|cc}
& R = 1 \text{ (Reference Water)} & R = 0 \text{ (Reference Non-Water)} \\
\hline
C = 1 \text{ (Candidate Water)} & \text{True Positive (TP)} & \text{False Positive (FP)} \\
C = 0 \text{ (Candidate Non-Water)} & \text{False Negative (FN)} & \text{True Negative (TN)}
\end{array}$$

### B. Quantitative Statistical Metrics
1. **Precision (User's Accuracy for Water):**
   $$\text{Precision} = \frac{\text{TP}}{\text{TP} + \text{FP}}$$
2. **Recall / Sensitivity (Producer's Accuracy for Water):**
   $$\text{Recall} = \frac{\text{TP}}{\text{TP} + \text{FN}}$$
3. **F1-Score (Harmonic Mean):**
   $$\text{F1} = 2 \cdot \frac{\text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}} = \frac{2\text{TP}}{2\text{TP} + \text{FP} + \text{FN}}$$
4. **Intersection over Union (IoU / Jaccard Index):**
   $$\text{IoU} = \frac{\text{TP}}{\text{TP} + \text{FP} + \text{FN}}$$
5. **Specificity (True Negative Rate):**
   $$\text{Specificity} = \frac{\text{TN}}{\text{TN} + \text{FP}}$$
6. **Balanced Accuracy:**
   $$\text{Balanced Accuracy} = \frac{\text{Recall} + \text{Specificity}}{2}$$
7. **Overall Accuracy:**
   $$\text{Overall Accuracy} = \frac{\text{TP} + \text{TN}}{\text{TP} + \text{TN} + \text{FP} + \text{FN}}$$

### C. Mask Exclusion Rules
Pixels are excluded from evaluation if:
- Candidate pixel is NoData (`6`) or Indeterminate (`5`).
- Reference pixel is NoData (`255`) or Cloud/Shadow/Uncertain (`254`).
- Pixel lies outside the evaluated spatial domain (e.g. outside AOI).

---

## 8. Spatial Block Validation Protocol for Machine Learning

For future supervised or machine-learning models:
- **Problem:** Random pixel splitting causes extreme data leakage due to intense spatial autocorrelation in contiguous floodplains.
- **Protocol:** Spatial Block Cross-Validation (Spatial Checkerboard).
  - The study area is divided into $5\text{ km} \times 5\text{ km}$ spatial blocks.
  - Blocks are partitioned into independent training, validation, and testing folds.
  - A $500\text{ m}$ spatial buffer ("halo exclusion zone") is enforced between folds to prevent near-neighbor leakage.

---

## 9. Reference Data Directory Structure & Registry Schema

Reference datasets are organized into dedicated subdirectories under `data/reference/`:
- `data/reference/optical/`
- `data/reference/hydrology/`
- `data/reference/terrain/`
- `data/reference/event_documents/`

Every dataset must be registered in [`data/metadata/reference_data_registry.json`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/metadata/reference_data_registry.json) recording:
`dataset_name`, `category`, `provider`, `source_url_or_citation`, `acquisition_date_or_interval`, `spatial_extent_wkt`, `crs`, `resolution`, `processing_method`, `license_or_usage_conditions`, `intended_validation_purpose`, and `local_file_path`.

---

## 10. Current Validation Readiness Verdict

```
CURRENT STATUS: BLOCKED_REFERENCE_DATA_MISSING
```
- **Local Reference Count:** **0 independent datasets available locally**.
- **Reason:** In accordance with strict governance constraints, external downloads and browser automation were prohibited.
- **SAR Candidate Results:** Certified and locked at $+58.1432\text{ km}^2$ net candidate water expansion ($146,992\text{ px}$ gross expansion, $1,634\text{ px}$ receded water).
- **Next Operational Step:** Manual acquisition of BWDB daily river gauge CSVs and cloud-masked Sentinel-2 scenes for June 10 and July 16, 2024.

