# EARTH PULSE — MASTER PROJECT HANDOFF & SCIENTIFIC AUDIT (PHASE 7B)
**Date:** 2026-11-03  
**Project:** NASA Space Apps Challenge 2026 — *"Dancing with the SARs"*  
**System:** Earth Pulse — Automated Satellite Radar Flood Inundation, Change Detection & Fluvial Geomorphology Engine  
**Target Study Area:** Jamuna River Reach, Kazipur & Sirajganj Districts, Bangladesh  
**Canonical Study AOI:** `POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))`  
**Target Raster Grid:** EPSG:32645 (UTM Zone 45N), $20.0\text{ m}$ pixel spacing, $1405 \times 1393$ raster dimensions ($1,010,039\text{ valid AOI cells}$, $404.0156\text{ km}^2$)  
**Current Milestone Completed:** Phase 7B (Explainable AI, SHAP Attribution & SAR Model Interpretability)  
**Next Milestone Planned:** Phase 8 (Backend API & Data Service Development)  
**Verified Test Baseline:** **275 passing unit tests (100% pass rate, 0 warnings)**  

---

## 1. Executive Summary & Phase 7B Milestones

Phase 7B completes the explainability, feature attribution, and diagnostic interpretability milestone of Earth Pulse. Operating under strict scientific governance guidelines without retraining, parameter modification, or package additions, Phase 7B investigated the internal decision pathways of the existing 40-tree Random Forest model (`phase7a_rf_jamuna_v1`), decomposed feature contributions, evaluated mathematical redundancy between polarization features, diagnosed the geophysical root causes of the high false-alarm rate, and benchmarked model predictions against the operational deterministic baseline (**Lee 5x5 Dual-AND Otsu**).

### 1.1 Key Achievements in Phase 7B:
1. **Explainability Environment Audit (Task A):**
   - Verified that third-party `shap` and `scikit-learn` packages are absent. Formally logged `SHAP_STATUS: BLOCKED_DEPENDENCY_MISSING` in strict adherence to environment policy.
   - Built an exact mathematical pure-NumPy `TreePathExplainer` implementing path-dependent Shapley decomposition directly on the ensemble with verified additivity ($\sum \phi_j = f(x) - \phi_0$).
   - Resolved the historical GDAL `FutureWarning` by adding `gdal.UseExceptions()`, achieving **0 warnings** across the test suite.
2. **Feature Redundancy Audit (Task B):**
   - Proven that `vv_minus_vh_db` and `cross_pol_ratio` share **strict monotonic mathematical redundancy** ($\text{cross\_pol\_ratio} = \min(10^{\text{vv\_minus\_vh\_db}/10}, 100.0)$), yielding Pearson $r = 0.8558$ and Spearman rank $r_s = \mathbf{1.0000}$ ($p=0.0$).
   - Demonstrated that tree splits on either feature partition data identically, causing credit-splitting.
3. **Global Tree-Path Feature Attribution & Grouped Attributions (Task C):**
   - Computed global base probability $\phi_0 = 0.4905$.
   - Ranked individual feature impacts: `vv_db` ($0.0508$) $\to$ `vh_db` ($0.0503$) $\to$ `texture_vh` ($0.0292$) $\to$ `texture_vv` ($0.0090$) $\to$ `vv_minus_vh_db` ($0.0077$) $\to$ `cross_pol_ratio` ($0.0074$).
   - Grouped into functional physical categories:
     - **Radiometric Backscatter (`vv_db` + `vh_db`):** $67.38\%$ of total attribution.
     - **Spatial Texture (`texture_vv` + `texture_vh`):** $21.94\%$ of total attribution.
     - **Polarization Ratio Group (`vv_minus_vh_db` + `cross_pol_ratio`):** $10.67\%$ of total attribution.
4. **Local Prediction Explanations for Representative Cases (Task D):**
   - Extracted and visualized 8 representative held-out cases across True Positives, True Negatives, Optical Disagreement False Positives, and Optical Disagreement False Negatives.
   - Preserved exact spatial coordinates, optical ground-truth SCL labels, probabilities, and waterfall breakdowns.
5. **Geophysical False-Positive Error Investigation (Task E):**
   - Uncovered why the model generates 2,762 false alarms:
     - Mean VV for False Positives is $-12.57\text{ dB}$, only $1.78\text{ dB}$ higher than True Water ($-14.35\text{ dB}$) and far lower than True Mainland ($-6.05\text{ dB}$).
     - Saturated fine-grained alluvium on sandbars (chars) and monsoon agricultural fields produces specular forward scattering at C-band, mimicking open water.
     - Low texture on sandbars ($\le 1.0\text{ dB}$) fails to trigger canopy roughness penalties.
6. **Deterministic Baseline Explanation & Side-by-Side Comparison (Task F):**
   - Deconstructed the Lee 5x5 Dual-AND Otsu baseline rule: $(\sigma^0_{VV} < -16.0\text{ dB}) \land (\sigma^0_{VH} < -23.5\text{ dB})$.
   - Identified that in $3,212\text{ pixels}$ ($52.45\%$ of test samples), Random Forest predicts water while the Otsu baseline rejects it. Otsu's simultaneous dual-threshold requirement successfully eliminates false alarms on wet sand.
7. **Probability Calibration & Uncertainty Interpretation (Task G):**
   - Evaluated 10-bin reliability diagram: Brier score $= 0.2270$, Expected Calibration Error (ECE) $= 0.0959$.
   - Established strict disambiguation between model probability, SHAP attribution, classification confidence, optical-reference agreement, and physical certainty.
8. **Visualization Outputs (Task I):**
   - Generated 9 publication-grade figures (300 DPI) covering global beeswarm, feature ranking, polarization dependence, texture dependence, local waterfalls, FP/FN comparisons, spatial disagreement mapping, and reliability curves.
9. **Testing & Verification (Task L):**
   - Implemented 15 tests in `tests/test_phase7b_explainability.py`. Full test suite passes: **275 / 275 tests passing, 0 warnings**.

---

## 2. Updated Earth Pulse Development Roadmap

| Milestone | Phase Name | Status | Key Deliverables & Achievements |
| :---: | :--- | :---: | :--- |
| **Phase 4D.1** | Optical-Reference Validation Reconciliation | **COMPLETE** | S2A cloud masking ($83.4\%$ cloud), pixel confusion matrices, F1 score reconciliation. |
| **Phase 5** | SAR Flood-Change Engine & Inundation Accounting | **COMPLETE** | $58.7968\text{ km}^2$ newly inundated area, zero-residual cell conservation ($1,010,039\text{ px}$). |
| **Phase 6** | Riverbank Migration & Channel-Margin Displacement | **COMPLETE** | Bank/floodplain separation, 154 orthogonal transects, channel belt extraction ($+30.07\text{ km}^2$). |
| **Phase 6.1** | Riverbank Geometry Audit & Cross-Phase Reconciliation | **COMPLETE** | Resolved 5.6 km boundary entry anomaly and 3.5 km anabranch anomaly; restored Indeterminate class. |
| **Phase 6.2** | Final Displacement Uncertainty & Statistical Audit | **COMPLETE** | Epistemic uncertainty audit, spatial block bootstrap, threshold range ($35\text{--}85\text{ m}$). |
| **Phase 7A** | SAR-Based Random Forest Development & Multi-Region Config | **COMPLETE** | Pure-NumPy RF classifier, 6 SAR features, 1 km spatial split, baseline comparison, 8 GeoTIFFs, 2 maps. |
| **Phase 7B** | Explainable AI (XAI) & Model Interpretability | **COMPLETE** | **CURRENT MILESTONE:** Native TreePathExplainer, feature redundancy proof, grouped attribution, local waterfalls, 9 maps, 275 tests. |
| **Phase 8** | Backend API & Data Service | **PLANNED** | FastAPI REST endpoints, tile serving, raster caching, spatial query engine. |
| **Phase 9** | Frontend & Interactive Web GIS Development | **PLANNED** | MapLibre / Leaflet interface, multi-temporal swipe comparison, transect profile charts. |
| **Phase 10** | Final Integration, Optimization & Space Apps Demonstration | **PLANNED** | End-to-end containerization, pitch video packaging, challenge submission documentation. |

---

## 3. Phase 7B Deliverables Inventory & Cryptographic Checksums

All Phase 7B deliverables are persisted and cryptographically verified:

### 3.1 Metadata & Statistical Tables
| File Path | Size (Bytes) | SHA-256 Checksum | Description |
| :--- | :---: | :---: | :--- |
| `data/metadata/phase7b_explainability_report.json` | 5,690 | `e0426e39e3126669ca0270c6aa8832eaa14b66182254cdf7abea051056125f57` | Master Phase 7B explainability metadata report. |
| `data/outputs/phase7b/shap/phase7b_feature_correlation.csv` | 373 | `07c4e37bdf92bee90c061e34565d1e570f79929b769c684136dffb5dfb3ae3b5` | Pearson and Spearman feature correlation matrix. |
| `data/outputs/phase7b/shap/phase7b_global_shap_importance.csv` | 386 | `9f970cc66e1001fef733e64c820de58939278c697fab0ca6195f0e1147f04a3d` | Global Mean Absolute SHAP feature importance ranking. |
| `data/outputs/phase7b/shap/phase7b_grouped_feature_attribution.csv` | 364 | `edc5e9507c3ce9ddfb5e6d65d64dffc732f22449b40e0bf8a6f96b4e93d7cfd7` | Grouped attributions for backscatter, texture, and ratio. |
| `data/outputs/phase7b/local_explanations/phase7b_local_prediction_explanations.csv` | 2,303 | `73ebcb72174493c0f2a5ce561e15a19d53ced5b47eb140e3ba5a40add2719c83` | 8 representative local prediction case explanations. |
| `data/outputs/phase7b/diagnostics/phase7b_false_positive_analysis.csv` | 1,722 | `725417a0d1cd7676ef939887e609bb896705f00bb2baa1c0b35800c8a689f0d1` | Feature distribution statistics for False Positives. |
| `data/outputs/phase7b/diagnostics/phase7b_false_negative_analysis.csv` | 1,193 | `d77c4957e62120248af23e2d42fc75d02698565fb4a3bbf445de41c9206f9117` | Feature distribution statistics for False Negatives. |
| `data/outputs/phase7b/diagnostics/phase7b_model_disagreement_summary.csv` | 315 | `82b437533b7797d3620c305ef2286998f002661bf6e965d67366c874462f8d8a` | Spatial agreement/disagreement breakdown vs. Otsu baseline. |
| `data/outputs/phase7b/diagnostics/phase7b_probability_diagnostics.csv` | 487 | `4dda0a6ec20037b5fc4e0b68c5155806195ee2f05b7f8cc674e1d9e1f532934f` | 10-bin reliability diagram calibration table. |

### 3.2 Publication Visualizations (300 DPI)
| Figure File Path | Size (Bytes) | SHA-256 Checksum | Description |
| :--- | :---: | :---: | :--- |
| `data/outputs/phase7b/maps/phase7b_global_shap_beeswarm.png` | 758,435 | `1c86e9a93a65b4b077e067bd01b386599b4252e4b0d7ecef4703b137e6157631` | Global SHAP beeswarm distribution across held-out test set. |
| `data/outputs/phase7b/maps/phase7b_global_feature_importance.png` | 131,005 | `2b0cf41c3737727e32e15493895abb16a8f057e878accdf3bc379f5721e31ff0` | Global mean absolute feature importance ranking bar chart. |
| `data/outputs/phase7b/maps/phase7b_polarization_dependence.png` | 747,045 | `e0688990d19667bb2f68e8e8b435150e2d90b6bf755985b7f600f83a1fd6a55f` | Two-panel dependence plot for VV and VH backscatter. |
| `data/outputs/phase7b/maps/phase7b_texture_dependence.png` | 617,361 | `9a1d42284d877a35f75f8f43182924b6b12708500b83874a162c804b975f63bd` | Two-panel dependence plot for local spatial texture features. |
| `data/outputs/phase7b/maps/phase7b_local_waterfall_examples.png` | 352,694 | `d1e0af5b2b361de9cb9d4c0fa144214b01851db95bfc95c8ef395602ab139de7` | Four-panel waterfall breakdown of representative cases. |
| `data/outputs/phase7b/maps/phase7b_false_positive_comparison.png` | 163,702 | `29dc07abd873f40ad86a7c6ba9af7c736d3b4fd92325be35cbec823381cbc7ac` | Histograms showing False Positive overlap with Water. |
| `data/outputs/phase7b/maps/phase7b_false_negative_comparison.png` | 161,939 | `234b6c149250a801185c3fd71996766a50d5e509e56af32cc726505034502291` | Boxplots of missed water backscatter and texture. |
| `data/outputs/phase7b/maps/phase7b_rf_vs_otsu_disagreement_map.png` | 927,985 | `cee4efa1fc0a3214fa85b99fb9a08240b7042f7d48d8300dd373bf36354429c0` | Spatial agreement/disagreement map along the Jamuna River. |
| `data/outputs/phase7b/maps/phase7b_probability_uncertainty_map.png` | 273,111 | `567b8769c25b8861e8d14908dd027addd4748f4d89b9431bdf0c744b0a2a56ca` | Reliability curve and uncertainty distribution histogram. |

---

## 4. Scientific Governance & Operational Decision Framework

1. **Model Promotion Rejected:**
   The Random Forest model `phase7a_rf_jamuna_v1` is maintained with status **`RETAINED_AS_PROBABILITY_LAYER`**. Its poor specificity ($0.2523$) and high false-positive rate on moist sandbars ($2,762\text{ false alarms}$) prevent it from replacing the primary operational baseline.
2. **Deterministic Baseline Confirmed:**
   The deterministic **Lee 5x5 Dual-AND Otsu classifier** remains the official primary baseline for all Earth Pulse operational flood-extent and riverbank migration products.
3. **Role of Machine Learning in Future Phases:**
   The Random Forest model provides continuous probability and uncertainty estimation layers that enhance user decision support, but will not be used as an uncalibrated crisp flood mask.

---

## 5. Transition & Readiness for Phase 8 (Backend Development)

The scientific core of Earth Pulse (Phases 1 through 7B) is complete, validated, and frozen:
- **Phase 8 Objectives:**
  1. Build a high-performance **FastAPI** backend application (`src/backend/`).
  2. Implement REST endpoints for multi-temporal flood classification, change detection, riverbank migration transects, and uncertainty rasters.
  3. Implement efficient Cloud Optimized GeoTIFF (COG) window reading and tile serving for the upcoming Phase 9 Web GIS frontend.
  4. Serve explainability records and feature attribution breakdowns via API.

---

## 6. Verification Status

```bash
$ python3 -m pytest -q tests/
275 passed in 10.15s
```
**All 275 repository unit tests pass with zero failures and zero warnings.** Phase 7B is complete, documented, and ready for handoff to Phase 8.

