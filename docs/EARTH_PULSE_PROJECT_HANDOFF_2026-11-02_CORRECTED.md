# EARTH PULSE — MASTER PROJECT HANDOFF & SCIENTIFIC RECONCILIATION AUDIT (CORRECTED)
**Date:** 2026-11-02  
**Project:** NASA Space Apps Challenge 2026 — *"Dancing with the SARs"*  
**System:** Earth Pulse — Automated Satellite Radar Flood Inundation & Change Detection Engine  
**Target Study Area:** Jamuna River Reach, Kazipur & Sirajganj Districts, Bangladesh  
**Canonical Study AOI:** `POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))`  
**Target Raster Grid:** EPSG:32645 (UTM Zone 45N), $20.0\text{ m}$ pixel spacing, $1405 \times 1393$ cells ($1,957,165\text{ cells}$, $782.87\text{ km}^2$)  
**Current Milestone Completed:** Phase 4D.1 (Validation Metric Reconciliation & Scientific Correction)  
**Next Milestone Planned:** Phase 5 (Physics-Informed Machine Learning, Explainable AI / SHAP, FastAPI & Frontend)  
**Verified Test Baseline:** **174 passing unit tests (0 failures, 100% pass rate)**  

---

## 1. Executive Summary & Audit Resolution

Phase 4D.1 concludes a rigorous mathematical reconciliation and audit of the Phase 4D independent optical validation deliverables. Two apparent numerical discrepancies were independently investigated down to the individual raster pixel level:

1. **Resolution of Finding A (Non-Water Confusion Matrix Counts):**
   - The confusion matrix calculations in Python were verified as **$100\%$ mathematically correct**.
   - The reported $FP + TN$ totals ($349,040\text{ px}$ in June; $70,283\text{ px}$ in July) do **not** exceed the true SCL Class 5 bare ground populations ($353,793\text{ px}$ in June; $70,297\text{ px}$ in July).
   - The apparent conflict was caused solely by a transcription error in Table 2.4 of the earlier report, which erroneously copied Phase 4C.1 hybrid MNDWI-based water mask numbers ($256,636$ and $68,898$) and derived non-water figures ($296,959$ and $50,603$) rather than the true SCL raster histograms.
   - All mathematical conservation invariants ($N = \sum CM$, $TP+FN \le \text{SCL 6}$, $FP+TN \le \text{SCL 5}$) now pass verified runtime assertions.
2. **Resolution of Finding B (July Optical Water Discrepancy):**
   - In Phase 4C.1, `ref_water_mask` was generated via `clear_mask & ((mndwi > 0.0) | (scl == 6))`.
   - In July, the peak flood crest inundated char sandbars, causing **$49,899\text{ pixels}$ of SCL Class 5 (Bare ground)** and **$26\text{ pixels}$ of SCL Class 4 (Vegetation)** to exhibit positive MNDWI ($> 0.0$). Adding these to the raw SCL Class 6 water count ($49,206\text{ px}$) produced the Phase 4C.1 total of **$99,131\text{ pixels}$** ($49,206 + 49,899 + 26 = 99,131$).
   - In Phase 4D, strict optical validation required pure SCL Class 6 ($49,206\text{ px}$) to prevent waterlogged char sand from introducing optical reference false positives.
3. **Vegetation Sensitivity Clarification:**
   - Corrected the over-generalized claim that "SAR correctly classified 100% of vegetation pixels as non-water".
   - The finding is descriptive of model behavior: All evaluated SCL Class 4 pixels ($9,813$ in June; $30,215$ in July) received a candidate non-water prediction from SAR. Because optical vegetation canopy is not a definitive dry-land ground truth due to radar canopy penetration and sub-canopy inundation, this does not establish ground-truth classification correctness.
4. **Method Sensitivity Clarification:**
   - Lee $5\times 5$ Dual-AND remains the primary operational method. However, Unfiltered Dual-AND achieved slightly higher June specificity ($0.8117$ vs $0.8041$) and lower false positives ($65,728$ vs $68,382$) at the cost of lower recall ($0.4925$ vs $0.5141$). All metrics are now reported transparently.

---

## 2. Explicit Scientific Differentiation

| Evaluation Parameter | Historical Erroneous Figures (Report Only) | Verified Raster Measurements (Actual Data) | Corrected Scientific Calculation | Status |
| :--- | :--- | :--- | :--- | :--- |
| **June AOI SCL 5 (Bare)** | $296,959\text{ px}$ (Phase 4C.1 derived) | **$353,793\text{ px}$** | $353,793\text{ px}$ | **RECONCILED** |
| **June AOI SCL 6 (Water)** | $256,636\text{ px}$ (MNDWI hybrid) | **$199,802\text{ px}$** | $199,802\text{ px}$ | **RECONCILED** |
| **June Strict Non-Water** | Flagged as impossible ($349,040 > 296,959$) | $353,793 - 4,753\text{ (SAR excl)} = 349,040\text{ px}$ | $FP + TN = 349,040 \le 353,793$ | **VERIFIED CORRECT** |
| **July AOI SCL 5 (Bare)** | $50,603\text{ px}$ (Phase 4C.1 derived) | **$70,297\text{ px}$** | $70,297\text{ px}$ | **RECONCILED** |
| **July AOI SCL 6 (Water)** | $68,898\text{ px}$ (Subtracted hybrid) | **$49,206\text{ px}$** | $49,206\text{ px}$ | **RECONCILED** |
| **July Strict Non-Water** | Flagged as impossible ($70,283 > 50,603$) | $70,297 - 14\text{ (SAR excl)} = 70,283\text{ px}$ | $FP + TN = 70,283 \le 70,297$ | **VERIFIED CORRECT** |
| **July Phase 4C.1 Water** | $99,131\text{ px}$ (Reported in 4C.1) | $49,206\text{ (SCL 6)} + 49,899\text{ (SCL 5)} + 26\text{ (SCL 4)}$ | Exactly $99,131\text{ px}$ | **EXACT DECOMPOSITION** |

---

## 3. Verified Pixel Cross-Tabulation Inside Study AOI ($1,010,039\text{ cells}$)

### 3.1 June 07 Optical vs June 10 SAR
- **Total AOI cells:** $1,010,039$
- **SCL Class 3 (Shadow):** $3,356\text{ px}$ ($63\text{ excluded by SAR}$)
- **SCL Class 4 (Vegetation):** $9,813\text{ px}$ ($0\text{ excluded by SAR}$; in secondary mode, $0\text{ water}, 9,813\text{ non-water}$)
- **SCL Class 5 (Bare ground):** **$353,793\text{ px}$** ($4,753\text{ excluded by SAR}$; $349,040\text{ eligible}$; $68,382\text{ FP}, 280,658\text{ TN}$)
- **SCL Class 6 (Water bodies):** **$199,802\text{ px}$** ($7,600\text{ excluded by SAR}$; $192,202\text{ eligible}$; $98,808\text{ TP}, 93,394\text{ FN}$)
- **SCL Class 7 (Unclassified):** $78,082\text{ px}$ ($601\text{ excluded by SAR}$)
- **SCL Class 8 (Medium Cloud):** $158,958\text{ px}$ ($1,958\text{ excluded by SAR}$)
- **SCL Class 9 (High Cloud):** $205,545\text{ px}$ ($1,190\text{ excluded by SAR}$)
- **SCL Class 10 (Thin Cirrus):** $690\text{ px}$ ($1\text{ excluded by SAR}$)
- **Strict Evaluated Pixels:** $349,040 + 192,202 = \mathbf{541,242\text{ px}}$ ($53.59\%$ of AOI)
- **Secondary Evaluated Pixels:** $541,242 + 9,813 = \mathbf{551,055\text{ px}}$ ($54.56\%$ of AOI)

### 3.2 July 17 Optical vs July 16 SAR
- **Total AOI cells:** $1,010,039$
- **SCL Class 2 (Dark area):** $190\text{ px}$ ($0\text{ excluded by SAR}$)
- **SCL Class 3 (Shadow):** $1,912\text{ px}$ ($0\text{ excluded by SAR}$)
- **SCL Class 4 (Vegetation):** $30,215\text{ px}$ ($0\text{ excluded by SAR}$; in secondary mode, $0\text{ water}, 30,215\text{ non-water}$)
- **SCL Class 5 (Bare ground):** **$70,297\text{ px}$** ($14\text{ excluded by SAR}$; $70,283\text{ eligible}$; $40,309\text{ FP}, 29,974\text{ TN}$)
- **SCL Class 6 (Water bodies):** **$49,206\text{ px}$** ($11\text{ excluded by SAR}$; $49,195\text{ eligible}$; $38,454\text{ TP}, 10,741\text{ FN}$)
- **SCL Class 7 (Unclassified):** $15,478\text{ px}$ ($0\text{ excluded by SAR}$)
- **SCL Class 8 (Medium Cloud):** $408,496\text{ px}$ ($57\text{ excluded by SAR}$)
- **SCL Class 9 (High Cloud):** $243,758\text{ px}$ ($83\text{ excluded by SAR}$)
- **SCL Class 10 (Thin Cirrus):** $190,487\text{ px}$ ($30\text{ excluded by SAR}$)
- **Strict Evaluated Pixels:** $70,283 + 49,195 = \mathbf{119,478\text{ px}}$ ($11.83\%$ of AOI)
- **Secondary Evaluated Pixels:** $119,478 + 30,215 = \mathbf{149,693\text{ px}}$ ($14.82\%$ of AOI)

---

## 4. Reconciled Confusion Matrices & Optical-Reference Agreement

| Evaluation Metric | June Strict (SCL 6 vs 5) | June Secondary (SCL 6 vs 4+5) | July Strict (SCL 6 vs 5) | July Secondary (SCL 6 vs 4+5) |
| :--- | :--- | :--- | :--- | :--- |
| **Temporal Offset ($\Delta t$)** | 3 days | 3 days | 1 day | 1 day |
| **Evaluated Domain** | **$541,242\text{ px}$ ($216.50\text{ km}^2$, $53.59\%$)** | $551,055\text{ px}$ ($220.42\text{ km}^2$, $54.56\%$) | **$119,478\text{ px}$ ($47.79\text{ km}^2$, $11.83\%$)** | $149,693\text{ px}$ ($59.88\text{ km}^2$, $14.82\%$) |
| **True Positives ($TP$)** | 98,808 px | 98,808 px | 38,454 px | 38,454 px |
| **False Positives ($FP$)** | 68,382 px | 68,382 px | 40,309 px | 40,309 px |
| **True Negatives ($TN$)** | 280,658 px | 290,471 px ($+9,813\text{ px}$) | 29,974 px | 60,189 px ($+30,215\text{ px}$) |
| **False Negatives ($FN$)** | 93,394 px | 93,394 px | 10,741 px | 10,741 px |
| **Precision** | **0.5910** | 0.5910 | **0.4882** | 0.4882 |
| **Recall (Sensitivity)** | **0.5141** | 0.5141 | **0.7817** | 0.7817 |
| **F1-Score** | **0.5499** | 0.5499 | **0.6010** | 0.6010 |
| **IoU (Jaccard Index)** | **0.3792** | 0.3792 | **0.4296** | 0.4296 |
| **Specificity** | **0.8041** | 0.8094 | **0.4265** | 0.5989 |
| **Balanced Accuracy** | **0.6591** | 0.6618 | **0.6041** | 0.6903 |
| **Ref Water Prevalence** | $35.51\%$ ($76.88\text{ km}^2$) | $34.88\%$ ($76.88\text{ km}^2$) | $41.17\%$ ($19.68\text{ km}^2$) | $32.86\%$ ($19.68\text{ km}^2$) |
| **SAR Water Prevalence** | $30.89\%$ ($66.88\text{ km}^2$) | $30.34\%$ ($66.88\text{ km}^2$) | $65.92\%$ ($31.51\text{ km}^2$) | $52.62\%$ ($31.51\text{ km}^2$) |
| **Validation Status** | **`READY` / `REPRESENTATIVE`** | **`READY`** | **`PARTIALLY_EVALUABLE`** | **`PARTIALLY_EVALUABLE`** |

---

## 5. Recomputed 1 km Spatial Block Statistics & Uncertainty ($95\%\text{ CI}$)

Evaluated across $1\text{ km} \times 1\text{ km}$ ($50 \times 50\text{ px}$) blocks with 1,000 block-bootstrap iterations (seed 42):

| Metric | June Baseline ($241\text{ evaluable blocks}$, $53.44\%$) | July Flood Peak ($88\text{ evaluable blocks}$, $19.51\%$) | Scientific Meaning |
| :--- | :--- | :--- | :--- |
| **Precision ($95\%\text{ CI}$)** | $[0.5365, 0.6572]$ (width: 0.1207) | $[0.3982, 0.5888]$ (width: 0.1906) | Spatial variance across charlands |
| **Recall ($95\%\text{ CI}$)** | $[0.4419, 0.5616]$ (width: 0.1197) | $[0.7083, 0.8572]$ (width: 0.1489) | High flood sensitivity persists |
| **F1-Score ($95\%\text{ CI}$)** | $[0.4932, 0.5938]$ (width: 0.1006) | $[0.5207, 0.6891]$ (width: 0.1684) | Stable performance bounds |
| **IoU ($95\%\text{ CI}$)** | $[0.3273, 0.4223]$ (width: 0.0950) | $[0.3520, 0.5257]$ (width: 0.1737) | Spatial overlap interval |
| **Spatial Status** | **`REPRESENTATIVE`** | **`PARTIALLY_EVALUABLE`** | July restricted to cloud gaps |

---

## 6. Complete Milestone History & Test Suite Status

```text
Phase 0: Project & Dataset Read-Only Audit (Completed)
Phase 1: Raster Harmonization Engine (Completed, 10 tests)
Phase 2A: Radiometric Analysis & Backscatter Characterization (Completed, 9 tests)
Phase 2A.1: Quality Control & Noise Floor Investigation (Completed, 5 tests)
Phase 2A.2: Scientific Calibration Corrections (Completed, 5 tests)
Phase 2B: Adaptive Speckle Filtering Benchmark (Completed, 7 tests)
Phase 3A: Surface-Water Classification Benchmark (Completed, 9 tests)
Phase 3A.1: Classification QC & 4-Category Mask Fix (Completed, 7 tests)
Phase 3B: Multi-Temporal Flood-Change Detection (Completed, 8 tests)
Phase 3B.1: Transition Classification & NoData Fix (Completed, 8 tests)
Phase 4A: Independent Validation Protocol (Completed, 7 tests)
Phase 4A.1: Scientific Provenance Audit (Completed, 7 tests)
Phase 4B: Reference Ingestion Engine & Synthetic Tests (Completed, 18 tests)
Phase 4B.1: SCL Dark Area Correction (Completed, 13 tests)
Phase 4C.1: Sentinel-2 Real Data Ingestion (Completed, 48 tests)
Phase 4D: Independent Optical Validation & Agreement Assessment (Completed, 9 tests)
Phase 4D.1: Validation Metric Reconciliation & Scientific Correction (Completed, 12 tests)
---------------------------------------------------------------------------------------------------------
TOTAL REPOSITORY TEST SUITE: 174 PASSING UNIT TESTS (0 FAILURES, 100% PASS RATE)
```

---

## 7. Versioned Phase 4D.1 Deliverables

### Statistical Tables ([`data/outputs/phase4d1/statistics/`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase4d1/statistics/))
- [`phase4d1_confusion_matrices.csv`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase4d1/statistics/phase4d1_confusion_matrices.csv): Reconciled confusion matrix cell counts, populations, and invariant flags.
- [`phase4d1_agreement_metrics.csv`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase4d1/statistics/phase4d1_agreement_metrics.csv): Precision, Recall, F1, IoU, Specificity, Balanced Accuracy.
- [`phase4d1_scl_crosstabulation.csv`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase4d1/statistics/phase4d1_scl_crosstabulation.csv): Complete 12-class pixel cross-tabulation against SAR predictions.
- [`phase4d1_reference_coverage.csv`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase4d1/statistics/phase4d1_reference_coverage.csv): Pixel-level exclusion reasons.
- [`phase4d1_spatial_block_statistics.csv`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase4d1/statistics/phase4d1_spatial_block_statistics.csv): Block-by-block statistics for all 451 blocks across both epochs.
- [`phase4d1_uncertainty_statistics.csv`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase4d1/statistics/phase4d1_uncertainty_statistics.csv): 1,000-iteration block bootstrap 95% confidence intervals and width.
- [`phase4d1_method_sensitivity.csv`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase4d1/statistics/phase4d1_method_sensitivity.csv): Sensitivity benchmark across 7 SAR configurations.

### Cartographic Visualizations ([`data/outputs/phase4d1/maps/`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase4d1/maps/))
- [`phase4d1_june10_optical_agreement_map.png`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase4d1/maps/phase4d1_june10_optical_agreement_map.png) (300 DPI, 4 panels)
- [`phase4d1_july16_optical_agreement_map.png`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase4d1/maps/phase4d1_july16_optical_agreement_map.png) (300 DPI, 4 panels)

### Master Metadata & Reports
- [`data/metadata/phase4d1_reconciliation_report.json`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/metadata/phase4d1_reconciliation_report.json): Master reconciliation JSON.
- [`docs/PHASE4D1_METRIC_RECONCILIATION_REPORT.md`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/docs/PHASE4D1_METRIC_RECONCILIATION_REPORT.md): Publication-grade scientific report.
- [`data/metadata/earth_pulse_project_state.json`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/metadata/earth_pulse_project_state.json): Updated project state registry.

### Dedicated Test Suite
- [`tests/test_phase4d1_reconciliation.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase4d1_reconciliation.py): 12 dedicated tests enforcing all invariants and reconciliations.

---

## 8. Remaining Scientific Limitations & Transition to Phase 5

1. **Temporal Non-Simultaneity:** 3-day gap in June and 1-day gap in July. Dynamic channel shift on braided chars creates natural boundary divergence that is not algorithm error.
2. **Cloud Sampling Bias in Monsoon Flood:** July optical observations are restricted to $11.83\%$ clear sky. The designation **`PARTIALLY_EVALUABLE`** must remain attached to all July metrics.
3. **Vegetation Canopy Ambiguity:** SCL 4 is an imperfect dry-land reference. Sub-canopy inundation cannot be resolved with optical data alone.

**Phase 4D.1 is complete.** No Phase 5 activities (Random Forest, SHAP/XAI, FastAPI, or Frontend) have been started, preserving clean development boundaries.

