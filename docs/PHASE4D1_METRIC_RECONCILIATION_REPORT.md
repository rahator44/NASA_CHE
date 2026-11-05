# EARTH PULSE — PHASE 4D.1: VALIDATION METRIC RECONCILIATION & SCIENTIFIC CORRECTION REPORT
**NASA Space Apps Challenge 2026 — Dancing with the SARs**  
**Author:** Earth Pulse Geospatial Data Auditor & Remote Sensing Science Team  
**Date:** 2026-11-02  
**Study Area:** Jamuna River Reach, Kazipur & Sirajganj Districts, Bangladesh  
**Canonical Study AOI:** `POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))`  
**Target Reference Grid:** EPSG:32645 (UTM Zone 45N), $20.0\text{ m}$ pixel resolution, $1405 \times 1393$ cells ($1,957,165\text{ pixels}$, $782.87\text{ km}^2$)  
**Milestone Completed:** Phase 4D.1 — Metric Reconciliation & Scientific Correction  

---

## 1. Executive Summary

Phase 4D.1 provides an independent scientific audit and rigorous pixel-level reconciliation of the Phase 4D independent optical validation framework. Following a post-completion review that flagged apparent discrepancies between reported SCL populations, confusion matrix counts, and Phase 4C.1 optical water statistics, this audit inspected the underlying rasters directly.

### Key Audit Findings & Resolutions
1. **Finding A Resolution (Confusion Matrix Non-Water Populations):**
   - The reported confusion matrix counts ($FP + TN = 349,040$ in June; $70,283$ in July) were **mathematically correct and strictly computed from the source rasters**.
   - The discrepancy arose because the historical Phase 4D report table erroneously copied the hybrid Phase 4C.1 MNDWI-based water mask numbers ($256,636$ in June; $68,898$ in July) and derived non-water figures ($296,959$ and $50,603$) instead of reporting the true SCL raster histograms.
   - In the authentic Sentinel-2 SCL rasters inside the AOI, Class 5 (Bare ground) contains **$353,793\text{ pixels}$** in June and **$70,297\text{ pixels}$** in July. Consequently, $FP + TN \le \text{AOI SCL 5}$ holds strictly:
     - June Strict: $68,382 + 280,658 = 349,040\text{ px} \le 353,793\text{ px}$.
     - July Strict: $40,309 + 29,974 = 70,283\text{ px} \le 70,297\text{ px}$.
2. **Finding B Resolution (July Optical Water Discrepancy):**
   - In Phase 4C.1, `ref_water_mask` was generated using a spectral-hybrid condition: `clear_mask & ((mndwi > 0.0) | (scl == 6))`.
   - In July, the peak flood crest inundated and saturated sandbars, causing **$49,899\text{ pixels}$ of SCL Class 5 (Bare ground)** and **$26\text{ pixels}$ of SCL Class 4 (Vegetation)** to exhibit positive MNDWI ($> 0.0$). Adding these to the raw SCL Class 6 water count ($49,206\text{ px}$) produced the Phase 4C.1 total of **$99,131\text{ pixels}$** ($49,206 + 49,899 + 26 = 99,131$).
   - In Phase 4D, strict optical validation required pure SCL Class 6 ($49,206\text{ px}$) to prevent waterlogged char sand from introducing optical reference false positives.
3. **Vegetation Sensitivity Correction:**
   - The previous statement that "SAR correctly classified 100% of vegetation pixels as non-water" was scientifically misleading.
   - While all evaluated SCL Class 4 pixels ($9,813$ in June; $30,215$ in July) received a candidate non-water prediction from SAR, optical vegetation canopy is not a definitive dry-land ground truth due to radar canopy penetration and sub-canopy inundation. The finding is descriptive of model behavior, not proof of correctness.
4. **Method Sensitivity Correction:**
   - Lee $5\times 5$ Dual-AND remains the primary operational configuration. However, Unfiltered Dual-AND achieved slightly higher June specificity ($0.8117$ vs $0.8041$) and lower false positives ($65,728$ vs $68,382$) at the cost of lower recall ($0.4925$ vs $0.5141$). All metrics are now reported transparently.
5. **Verified Test Suite:**
   - A dedicated 12-test suite ([`tests/test_phase4d1_reconciliation.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase4d1_reconciliation.py)) was implemented.
   - The full test suite expanded from 162 to **174 passing unit tests (0 failures)**.

---

## 2. Root Cause Investigation & Audit Evidence

### 2.1 Investigation of Finding A: Confusion Matrix Non-Water Populations
The Phase 4D report text presented an apparent mathematical impossibility:
- June Strict Non-Water in CM: $FP + TN = 68,382 + 280,658 = 349,040\text{ px}$.
- Reported AOI Bare Ground in Table 2.4: $296,959\text{ px}$.
- Apparent Deficit: $349,040 > 296,959$ ($+52,081\text{ px}$).

**Pixel-Level Investigation:**
Extracting the raw pixel histogram directly from [`data/processed/reference/optical/sentinel2/june_2024/s2_june07_aligned_scl.tif`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/processed/reference/optical/sentinel2/june_2024/s2_june07_aligned_scl.tif) masked by the canonical AOI revealed:

$$\text{AOI SCL Class 5 (Bare Ground)} = 353,793\text{ pixels}$$
$$\text{AOI SCL Class 6 (Water)} = 199,802\text{ pixels}$$

The number $296,959$ in the report was not derived from the SCL raster! It was computed in Phase 4C.1 by subtracting vegetation from the clear non-water mask ($306,772 - 9,813 = 296,959$). 

When intersecting the authentic SCL Class 5 raster ($353,793\text{ px}$) with valid SAR pixels (excluding $4,753\text{ pixels}$ of SAR clipping floor and NoData):

$$\text{Eligible Strict Non-Water} = 353,793 - 4,753 = 349,040\text{ pixels}$$

Among these $349,040$ pixels:
- SAR predicted water (Category 1) $\rightarrow FP = 68,382\text{ px}$
- SAR predicted non-water (Category 0) $\rightarrow TN = 280,658\text{ px}$
- $FP + TN = 68,382 + 280,658 = 349,040\text{ px} \le 353,793\text{ px}$

Similarly for July SCL:
$$\text{AOI SCL Class 5 (Bare Ground)} = 70,297\text{ pixels}$$
$$\text{AOI SCL Class 6 (Water)} = 49,206\text{ pixels}$$

Intersecting with valid SAR pixels (excluding $14\text{ pixels}$):
$$\text{Eligible Strict Non-Water} = 70,297 - 14 = 70,283\text{ pixels}$$
- $FP = 40,309\text{ px}$, $TN = 29,974\text{ px}$
- $FP + TN = 40,309 + 29,974 = 70,283\text{ px} \le 70,297\text{ px}$

**Conclusion:** The confusion matrix calculations in Python were completely correct. The historical report contained typographical and cross-referencing errors from Phase 4C.1.

---

### 2.2 Investigation of Finding B: July Optical Water Count Discrepancy
The review flagged a discrepancy between the Phase 4C.1 reported clear water count ($99,131\text{ px}$) and the Phase 4D raw SCL Class 6 count ($49,206\text{ px}$, previously reported as $68,898\text{ px}$).

**Pixel-Level Investigation:**
Inspection of line 482 of [`scripts/ingest_sentinel2_real.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/ingest_sentinel2_real.py) showed:
```python
clear_water = scl_result.clear_mask & ((mndwi > 0.0) | (scl_arr == 6))
```
During the massive monsoon crest of July 17, 2024:
1. Pure SCL Class 6 (Water) inside AOI: **$49,206\text{ pixels}$**.
2. SCL Class 5 (Bare Ground) with $\text{MNDWI} > 0.0$ inside AOI: **$49,899\text{ pixels}$**.
3. SCL Class 4 (Vegetation) with $\text{MNDWI} > 0.0$ inside AOI: **$26\text{ pixels}$**.

Summing these components:
$$49,206 + 49,899 + 26 = 99,131\text{ pixels}$$

This accounts for the entire Phase 4C.1 water count ($99,131\text{ px}$) with zero remainder.

**Scientific Rationale for Phase 4D Strictness:**
In the braided Jamuna River, char sandbars during peak monsoon floods are saturated with moisture. The Modified Normalized Difference Water Index (MNDWI) detects surface wetness ($> 0.0$), labeling wet sand as water. In Phase 4D, strict optical validation required pure SCL Class 6 ($49,206\text{ px}$) to prevent saturated sandbars from being mislabeled as open water reference.

---

## 3. Pixel-Wise SCL Cross-Tabulation Inside the Study AOI

Below is the verified pixel cross-tabulation across all 12 SCL classes, comparing the raw AOI SCL population, SAR quality exclusions, eligible validation populations, and SAR predictions.

### 3.1 June 07 Optical vs June 10 SAR Cross-Tabulation ($1,010,039\text{ cells}$)

| SCL Class Description | AOI Pixels | Area ($\text{km}^2$) | AOI Pct | SAR Excl | Strict Px | Sec Px | SAR Water (Cat 1) | SAR Non-Water (Cat 0) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **0: NoData** | 0 | 0.0000 | 0.00% | 0 | 0 | 0 | 0 | 0 |
| **1: Defective / Saturated** | 0 | 0.0000 | 0.00% | 0 | 0 | 0 | 0 | 0 |
| **2: Dark Area Pixels** | 0 | 0.0000 | 0.00% | 0 | 0 | 0 | 0 | 0 |
| **3: Cloud Shadows** | 3,356 | 1.3424 | 0.33% | 63 | 0 | 0 | 0 | 0 |
| **4: Vegetation** | 9,813 | 3.9252 | 0.97% | 0 | 0 | **9,813** | **0** | **9,813** |
| **5: Bare Ground** | 353,793 | 141.5172 | 35.03% | 4,753 | **349,040** | **349,040** | **68,382 (FP)** | **280,658 (TN)** |
| **6: Water Bodies** | 199,802 | 79.9208 | 19.78% | 7,600 | **192,202** | **192,202** | **98,808 (TP)** | **93,394 (FN)** |
| **7: Unclassified** | 78,082 | 31.2328 | 7.73% | 601 | 0 | 0 | 0 | 0 |
| **8: Medium Cloud** | 158,958 | 63.5832 | 15.74% | 1,958 | 0 | 0 | 0 | 0 |
| **9: High Cloud** | 205,545 | 82.2180 | 20.35% | 1,190 | 0 | 0 | 0 | 0 |
| **10: Thin Cirrus** | 690 | 0.2760 | 0.07% | 1 | 0 | 0 | 0 | 0 |
| **11: Snow / Ice** | 0 | 0.0000 | 0.00% | 0 | 0 | 0 | 0 | 0 |
| **TOTAL** | **1,010,039** | **404.0156** | **100.00%** | **16,166** | **541,242** | **551,055** | **167,190** | **383,865** |

*SAR Exclusions in June:* $16,105\text{ clipping-floor indeterminate (Cat 2)} + 61\text{ source NoData (Cat 3)} = 16,166\text{ pixels}$.

---

### 3.2 July 17 Optical vs July 16 SAR Cross-Tabulation ($1,010,039\text{ cells}$)

| SCL Class Description | AOI Pixels | Area ($\text{km}^2$) | AOI Pct | SAR Excl | Strict Px | Sec Px | SAR Water (Cat 1) | SAR Non-Water (Cat 0) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **0: NoData** | 0 | 0.0000 | 0.00% | 0 | 0 | 0 | 0 | 0 |
| **1: Defective / Saturated** | 0 | 0.0000 | 0.00% | 0 | 0 | 0 | 0 | 0 |
| **2: Dark Area Pixels** | 190 | 0.0760 | 0.02% | 0 | 0 | 0 | 0 | 0 |
| **3: Cloud Shadows** | 1,912 | 0.7648 | 0.19% | 0 | 0 | 0 | 0 | 0 |
| **4: Vegetation** | 30,215 | 12.0860 | 2.99% | 0 | 0 | **30,215** | **0** | **30,215** |
| **5: Bare Ground** | 70,297 | 28.1188 | 6.96% | 14 | **70,283** | **70,283** | **40,309 (FP)** | **29,974 (TN)** |
| **6: Water Bodies** | 49,206 | 19.6824 | 4.87% | 11 | **49,195** | **49,195** | **38,454 (TP)** | **10,741 (FN)** |
| **7: Unclassified** | 15,478 | 6.1912 | 1.53% | 0 | 0 | 0 | 0 | 0 |
| **8: Medium Cloud** | 408,496 | 163.3984 | 40.44% | 57 | 0 | 0 | 0 | 0 |
| **9: High Cloud** | 243,758 | 97.5032 | 24.13% | 83 | 0 | 0 | 0 | 0 |
| **10: Thin Cirrus** | 190,487 | 76.1948 | 18.86% | 30 | 0 | 0 | 0 | 0 |
| **11: Snow / Ice** | 0 | 0.0000 | 0.00% | 0 | 0 | 0 | 0 | 0 |
| **TOTAL** | **1,010,039** | **404.0156** | **100.00%** | **195** | **119,478** | **149,693** | **78,763** | **70,930** |

*SAR Exclusions in July:* $145\text{ clipping-floor indeterminate (Cat 2)} + 50\text{ source NoData (Cat 3)} = 195\text{ pixels}$.

---

## 4. Reconciled Confusion Matrices & Agreement Metrics

### 4.1 Reconciled Confusion Matrices & Mathematical Conservation Invariants

All four confusion matrices satisfy every mathematical invariant:

| Metric / Attribute | June 10 vs June 07 (Strict) | June 10 vs June 07 (Secondary) | July 16 vs July 17 (Strict) | July 16 vs July 17 (Secondary) |
| :--- | :--- | :--- | :--- | :--- |
| **Evaluation Mode** | Primary Strict (SCL 6 vs 5) | Secondary (SCL 6 vs 4+5) | Primary Strict (SCL 6 vs 5) | Secondary (SCL 6 vs 4+5) |
| **Temporal Gap ($\Delta t$)** | 3 days | 3 days | 1 day | 1 day |
| **True Positives ($TP$)** | 98,808 px | 98,808 px | 38,454 px | 38,454 px |
| **False Positives ($FP$)** | 68,382 px | 68,382 px | 40,309 px | 40,309 px |
| **True Negatives ($TN$)** | 280,658 px | 290,471 px ($+9,813\text{ px}$) | 29,974 px | 60,189 px ($+30,215\text{ px}$) |
| **False Negatives ($FN$)** | 93,394 px | 93,394 px | 10,741 px | 10,741 px |
| **Evaluated Pixels ($N$)** | **541,242 px** | **551,055 px** | **119,478 px** | **149,693 px** |
| **Evaluated Area** | $216.50\text{ km}^2$ ($53.59\%$) | $220.42\text{ km}^2$ ($54.56\%$) | $47.79\text{ km}^2$ ($11.83\%$) | $59.88\text{ km}^2$ ($14.82\%$) |
| **Ref Water ($TP+FN$)** | $192,202\text{ px} \le 199,802$ | $192,202\text{ px} \le 199,802$ | $49,195\text{ px} \le 49,206$ | $49,195\text{ px} \le 49,206$ |
| **Ref Non-Water ($FP+TN$)** | $349,040\text{ px} \le 353,793$ | $358,853\text{ px} \le 363,606$ | $70,283\text{ px} \le 70,297$ | $100,498\text{ px} \le 100,512$ |
| **SAR Water ($TP+FP$)** | 167,190 px | 167,190 px | 78,763 px | 78,763 px |
| **SAR Non-Water ($TN+FN$)** | 374,052 px | 383,865 px | 40,715 px | 70,930 px |
| **Conservation ($N = \sum CM$)** | **VERIFIED (Exact)** | **VERIFIED (Exact)** | **VERIFIED (Exact)** | **VERIFIED (Exact)** |
| **Population Bounds** | **PASSED ($\le \text{SCL 5, 6}$)** | **PASSED ($\le \text{SCL 4, 5, 6}$)** | **PASSED ($\le \text{SCL 5, 6}$)** | **PASSED ($\le \text{SCL 4, 5, 6}$)** |

---

### 4.2 Reconciled Optical-Reference Agreement Metrics

All figures are reported under the standardized terminology **"optical-reference agreement"**:

| Agreement Metric | June Strict (SCL 6 vs 5) | June Secondary (SCL 6 vs 4+5) | July Strict (SCL 6 vs 5) | July Secondary (SCL 6 vs 4+5) |
| :--- | :--- | :--- | :--- | :--- |
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

## 5. Scientific Interpretation Corrections

### 5.1 Corrected Vegetation Sensitivity Interpretation
The earlier report stated: *"SAR correctly classified 100% of these vegetation pixels as non-water."*

**Scientific Correction:**
All evaluated SCL Class 4 pixels ($9,813$ in June; $30,215$ in July) received a candidate non-water prediction from the SAR classifier. Because dense floodplain vegetation and crop canopies are not definitive dry-land references (due to radar attenuation and sub-canopy inundation), this result is descriptive of model behavior and does not establish classification correctness over vegetated charland.

In both epochs:
- When SCL 4 was introduced as non-water in Secondary mode, True Negatives ($TN$) increased by exactly the number of vegetation pixels ($+9,813$ in June; $+30,215$ in July).
- True Positives ($TP$) and False Positives ($FP$) remained strictly identical ($98,808$ and $68,382$ in June; $38,454$ and $40,309$ in July).
- This confirms that the SAR classifier assigned Category 0 (non-water) to $100\%$ of the SCL Class 4 pixels in both epochs, producing zero false water alarms over vegetated char surfaces.

---

### 5.2 Corrected Method Sensitivity Interpretation
The earlier report claimed that Lee $5\times 5$ Dual-AND achieved the lowest false alarm rate. 

**Scientific Correction:**
Among the 7 evaluated SAR configurations:
- **Lee 5x5 Dual-AND (Primary):** Achieves high precision ($0.5910$ in June; $0.4882$ in July) and balanced performance across both epochs.
- **Unfiltered Dual-AND:** Achieved slightly higher specificity in June ($0.8117$ vs $0.8041$) and fewer false positives ($65,728$ vs $68,382$), but suffered lower recall ($0.4925$ vs $0.5141$) due to speckle-induced dropouts in water channels.
- **Dual-OR & 2D Otsu:** Produced higher raw recall ($0.8288$ and $0.8242$ in July) at the expense of lower specificity ($0.3736$ and $0.3884$) and substantially elevated false alarms over wet soils.
- Lee $5\times 5$ Dual-AND remains the scientifically defensible primary method due to its balance between noise suppression, channel continuity, and spatial coherence.

---

## 6. Spatial Block Statistics & Bootstrapping ($95\%\text{ CI}$)

Evaluated across $1\text{ km} \times 1\text{ km}$ ($50 \times 50\text{ px}$) blocks with 1,000 block-bootstrap iterations (seed 42):

| Metric | June 10 Baseline (241 evaluable blocks, 53.44%) | July 16 Flood Peak (88 evaluable blocks, 19.51%) | Interpretation |
| :--- | :--- | :--- | :--- |
| **Precision (95% CI)** | $[0.5365, 0.6572]$ (width: 0.1207) | $[0.3982, 0.5888]$ (width: 0.1906) | Spatial variance across charlands |
| **Recall (95% CI)** | $[0.4419, 0.5616]$ (width: 0.1197) | $[0.7083, 0.8572]$ (width: 0.1489) | High flood sensitivity persists |
| **F1-Score (95% CI)** | $[0.4932, 0.5938]$ (width: 0.1006) | $[0.5207, 0.6891]$ (width: 0.1684) | Stable performance bounds |
| **IoU (95% CI)** | $[0.3273, 0.4223]$ (width: 0.0950) | $[0.3520, 0.5257]$ (width: 0.1737) | Spatial overlap interval |
| **Spatial Status** | **`REPRESENTATIVE`** | **`PARTIALLY_EVALUABLE`** | July restricted to cloud gaps |

---

## 7. Versioned Phase 4D.1 Deliverables Inventory

All corrected deliverables have been generated in dedicated versioned directories:

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

### Master Metadata
- [`data/metadata/phase4d1_reconciliation_report.json`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/metadata/phase4d1_reconciliation_report.json): Complete machine-readable reconciliation results.

### Dedicated Test Suite
- [`tests/test_phase4d1_reconciliation.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase4d1_reconciliation.py): 12 dedicated tests enforcing all invariants and reconciliations.
- Full repository test suite: **174 passing unit tests (0 failures)**.

