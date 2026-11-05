# EARTH PULSE — PHASE 7B.1 ERRATA & BACKEND METADATA CORRECTIONS

**Project:** NASA Space Apps Challenge 2026 — Dancing with the SARs  
**System:** Earth Pulse Backend Data Services  
**Study Area:** Jamuna River Reach, Kazipur / Sirajganj, Bangladesh  
**Date of Erratum:** November 4, 2026  
**Status:** RECONCILED & DOCUMENTED FOR BACKEND SERVICES  

---

## 1. PURPOSE OF THIS ERRATUM

Prior to exposing machine-learning, flood-classification, and change-detection outputs through the FastAPI backend API in Phase 8, three metadata discrepancies were investigated, audited against raw source rasters and code, and reconciled.

Historical Phase 1–7B.1 reports are preserved without retroactive overwriting; this document and its companion JSON metadata establish the authoritative backend-facing truth.

---

## 2. RECONCILIATION SUMMARY

### Erratum B1: Global Explanation Base Value ($\phi_0$)

- **Discrepancy:** Phase 7B narrative reported $\phi_0 = 0.4905$, whereas the Phase 7B.1 specification text mentioned $\phi_0 = 0.3905$.
- **Audit Findings:**
  1. $\mathbb{E}_{x \sim X_{\text{train}}}[f(x)] = 0.490460 \approx 0.4905$: This is the empirical mean predicted probability of candidate water evaluated across the $18,825$ background training samples.
  2. $\frac{1}{T}\sum_{t=1}^{40} \text{root.prob}_t = 0.499450 \approx 0.4995$: This is the unweighted mean root-node probability across the 40 individual estimators in `phase7a_random_forest_model.joblib`.
  3. The value $0.3905$ cited in the Phase 7B.1 prompt text was a typographical error (an offset of exactly $0.1000$ from $0.4905$).
- **Backend Resolution:**
  - The authoritative global training background base value is **$0.4905$** ($0.490460$).
  - When explaining individual instances via local tree-path decomposition, the ensemble root base value is **$0.4995$** ($0.499450$).
  - Both values are clearly distinguished and documented in the backend API schemas.

---

### Erratum B2: Acquisition Year Correction (2024 vs. 2020)

- **Discrepancy:** Some historical text fragments in Phase 3A and Phase 7B.1 baseline summaries referenced "June 10, 2020" and "July 16, 2020".
- **Audit Findings:**
  1. The raw Sentinel-1 GRD archives are:
     - `S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69.zip`
     - `S1A_IW_GRDH_1SDV_20240716T120507_20240716T120532_054786_06ABD2_6511.zip`
  2. The Sentinel-2 optical validation scenes are:
     - `S2A_MSIL2A_20240607T043711_N0510_R033_T45RYJ_20240607T081358.SAFE`
     - `S2A_MSIL2A_20240717T043701_N0510_R033_T45RYJ_20240717T081329.SAFE`
  3. The acquisition year is unequivocally **2024**.
- **Backend Resolution:**
  - All Phase 8 backend endpoints, dataset registries, and metadata models strictly serve **2024-06-10** (Pre-Monsoon Low Flow) and **2024-07-16** (Monsoon Crest Observation).

---

### Erratum B3: Adaptive Baseline Agreement & Pixel Accounting

- **Discrepancy:** Clarification of the exact derivation of $53.89\%$ adaptive Otsu vs. Random Forest agreement, $2,177$ water predictions, and $2,430$ optical-reference water pixels.
- **Audit Findings (Evaluated on $N = 6,124$ Held-Out Test Samples):**
  1. **Adaptive Otsu Water Predictions:** **$2,177$ pixels** ($35.55\%$). Derived via scene-specific Lee 5×5 Dual-AND thresholds (June: $\text{VV} \le -12.457\text{ dB}$, $\text{VH} \le -21.697\text{ dB}$; July: $\text{VV} \le -14.960\text{ dB}$, $\text{VH} \le -21.828\text{ dB}$).
  2. **Optical Reference Water Labels:** **$2,430$ pixels** ($39.68\%$). Independent Sentinel-2 SCL water class (`SCL == 6`).
  3. **Random Forest Water Predictions ($\tau^* = 0.35$):** **$5,001$ pixels** ($81.66\%$).
  4. **Coincidence & Agreement Matrix between Adaptive Otsu and RF:**
     - Both predict Water: **$2,177$ pixels**
     - Both predict Non-Water: **$1,123$ pixels**
     - Otsu-only Water: **$0$ pixels** (every pixel identified by Otsu is also captured by RF at 0.35)
     - RF-only Water: **$2,824$ pixels** (RF overpredicts water on moist soils)
     - **Overall Spatial Agreement Percentage:**
       $$\text{Agreement} = \frac{2,177 + 1,123}{6,124} = \frac{3,300}{6,124} \times 100\% = 53.8863\% \approx \mathbf{53.89\%}$$
  5. **Coincidence between Adaptive Otsu and Optical Reference:**
     - True Positive (Both Water): $1,222$ pixels
     - True Negative (Both Land): $2,739$ pixels
     - False Positive (Otsu Water, Optical Land): $955$ pixels
     - False Negative (Otsu Land, Optical Water): $1,208$ pixels
     - Overall Otsu Accuracy vs. Optical: **$64.68\%$** (significantly higher precision than RF).
- **Backend Resolution:**
  - The backend distinguishes:
    - `spatial_agreement_pct` ($53.89\%$)
    - `baseline_water_count` ($2,177$)
    - `rf_water_count` ($5,001$)
    - `optical_reference_water_count` ($2,430$)
    - `overlapping_water_count` ($2,177$)
  - These distinct quantities are exposed under explicit, unambiguous field names in API schemas.

---

## 3. CHECKSUMS & ARTIFACT RECORD

- Companion JSON metadata: `data/metadata/phase7b1_backend_errata.json`
- Frozen model artifact: `models/phase7a/phase7a_random_forest_model.joblib` (SHA-256: `85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad`)

