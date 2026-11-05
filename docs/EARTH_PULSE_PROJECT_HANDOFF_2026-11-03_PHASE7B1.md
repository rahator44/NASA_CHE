# EARTH PULSE — PROJECT HANDOFF DOCUMENT (PHASE 7B.1)

**NASA Space Apps Challenge 2026:** Dancing with the SARs  
**Project:** Earth Pulse — SAR Remote Sensing, Riverbank Migration & Explainable AI Engine  
**Study Area:** Jamuna River Reach, Kazipur / Sirajganj, Bangladesh (AOI: EPSG:32645, 1405 × 1393 pixels, 20 m spacing)  
**Date of Handoff:** November 3, 2026  
**Current Milestone Completed:** Phase 7B.1 (Tree Explainability Mathematical Verification & Random Forest Model Integrity Audit)  
**Next Milestone Planned:** Phase 8 (Backend API & Data Service Development)  
**Test Suite Status:** **291 passing tests, 0 warnings, 0 failures**  
**Frozen Model Artifact:** `models/phase7a/phase7a_random_forest_model.joblib` (SHA-256: `85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad`)  
**Primary Operational Baseline:** Adaptive Lee 5×5 Dual-AND Otsu Classifier  

---

## 1. EXECUTIVE STATUS & CONTEXT

Phase 7B.1 concludes the rigorous mathematical and scientific audit of the machine-learning and explainability systems developed in Phase 7A and Phase 7B. The audit confirmed the mathematical integrity of the pure-NumPy Random Forest, resolved conceptual terminology overstatements regarding out-of-bag prediction, independently verified the additive single-path mechanics of `TreePathExplainer`, formally downgraded terminology from exact Shapley to path-dependent tree attribution, quantified feature redundancy clipping, reconciled the 6,124-sample confusion matrix, and clarified the scientific epistemology of false-positive microwave scattering.

All 291 unit and integration tests are passing with zero warnings under Linux CPU-only execution.

---

## 2. AUDIT SUMMARY BY WORK PACKAGE

### Work Package A: Random Forest Architectural Principles (Task A)
- **Status:** **VERIFIED COMPLIANT**
- The custom implementation in [src/ml/random_forest.py](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/src/ml/random_forest.py) adheres to Breiman (2001) principles:
  - Bootstrap sampling with replacement (`replace=True`).
  - $75.0\%$ sub-bagging ratio ($N_{sub} = 14,118$) for variance reduction and CPU speed.
  - Random feature subset selection ($\lfloor\sqrt{6}\rfloor = 2$ features per split).
  - Vectorized candidate threshold evaluation over 10 linear intervals.
  - Leaf node probability calculation from weighted class-1 sample proportions.
  - Ensemble soft voting arithmetic mean over 40 independent, deterministically seeded trees (`random_state=42`).
- Deliverable: [phase7b1_random_forest_integrity.csv](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b1/audit/phase7b1_random_forest_integrity.csv).

### Work Package B: Out-of-Bag Terminology Correction (Task B)
- **Status:** **RECONCILED & CORRECTED**
- The Phase 7B narrative description of model probability as an "out-of-bag ensemble soft vote" was audited and corrected:
  - **Held-Out Test Predictions:** Evaluates all 40 ensemble trees across $6,124$ independent observations that had zero training exposure.
  - **True Out-of-Bag (OOB) Predictions:** Applicable strictly to training samples, averaging only across bootstrap-omitted trees (simulated mean of $18.89$ trees per training sample).
- Deliverable: [phase7b1_oob_prediction_audit.csv](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b1/audit/phase7b1_oob_prediction_audit.csv).

### Work Package C: Mathematical Verification of Custom Tree Explainability (Task C)
- **Status:** **MATHEMATICALLY VERIFIED & DOWNGRADED TO PATH ATTRIBUTION**
- An independent brute-force Shapley reference algorithm evaluating all $2^D$ feature coalitions was implemented and compared against `TreePathExplainer` across 6 controlled tree fixtures:
  - **Exact Additivity (Efficiency):** Confirmed across all fixtures and samples:
    $$\phi_0 + \sum_{j=1}^D \phi_j = f(x) \quad (\text{error } < 10^{-8})$$
  - **Single-Split Trees:** Saabas and exact Shapley produce analytically identical attributions.
  - **Multi-Depth Trees:** Saabas allocates the stepwise delta $(P_{\text{child}} - P_{\text{parent}})$ to the feature evaluated at that node along the single traversed branch. Exact Shapley averages across all $2^D$ feature coalitions.
  - **Terminology Downgrade:** To uphold strict scientific standards, the implementation is formally described as **"Pure-NumPy Path-Dependent Tree Attribution (Saabas Formulation)"** rather than exact Shapley attribution.
- Deliverable: [phase7b1_shap_bruteforce_verification.csv](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b1/audit/phase7b1_shap_bruteforce_verification.csv).

### Work Package D: Feature Redundancy & 20 dB Clipping (Task D)
- **Status:** **QUANTIFIED & MITIGATED VIA GROUPED ATTRIBUTION**
- The relationship $\text{cross\_pol\_ratio} = \min(10^{\Delta/10}, 100.0)$ was audited across all splits:
  - Below $20.0\text{ dB}$, the exact logarithmic inversion $\Delta = 10 \log_{10}(\text{cross\_pol\_ratio})$ holds with rank correlation $\text{Spearman } r = 1.0000$.
  - In the held-out test split, $99.48\%$ ($6,092$ samples) are unclipped; $0.52\%$ ($32$ samples) are hard-clipped at $100.0$.
  - Credit splitting between `vv_minus_vh_db` and `cross_pol_ratio` is resolved by Grouped Polarization Attribution ($10.67\%$ joint contribution).
- Deliverable: [phase7b1_feature_redundancy_audit.csv](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b1/audit/phase7b1_feature_redundancy_audit.csv).

### Work Package E: Local Additivity Across Representative Cases (Task E)
- **Status:** **ALL 8 CASES VERIFIED (PASS)**
- All 8 local cases published in Phase 7B pass exact additivity verification with error $< 10^{-8}$. Global base value across all 40 estimators is $\phi_0 = 0.3905$.
- Deliverable: [phase7b1_local_additivity_audit.csv](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b1/audit/phase7b1_local_additivity_audit.csv).

### Work Package F: Probability Calibration & Uncertainty Terminology (Task F)
- **Status:** **RECONCILED & AUDITED**
- Predictive certainty terminology was clarified:
  - $|P - 0.5|$ is an **empirical decision margin / distance to threshold**, not a calibrated posterior probability.
  - Brier score: $0.2270$; Expected Calibration Error (ECE): $0.0959$.
- Deliverable: [phase7b1_probability_calibration_audit.csv](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b1/audit/phase7b1_probability_calibration_audit.csv).

### Work Package G: False-Positive Physical Scattering Epistemology (Task G)
- **Status:** **RECONCILED TO HYPOTHESIS**
- Confusion matrix sample counts reconciled exactly ($N = 6,124$: $\text{TP}=2,239$, $\text{TN}=932$, $\text{FP}=2,762$, $\text{FN}=191$).
- The specular scattering explanation for low backscatter on moist char sandbars is formally characterized as a **scientifically supported physical hypothesis**, rather than an in-situ proven causal certainty, due to the lack of ground-truth moisture profilometry during overpasses.
- Deliverable: [phase7b1_false_positive_physics_audit.csv](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b1/audit/phase7b1_false_positive_physics_audit.csv).

### Work Package H: Deterministic Baseline Reconciliation (Task H)
- **Status:** **RECONCILED TO HISTORICAL PHASE 3A METADATA**
- Verified the historical Phase 3A adaptive Lee 5×5 Dual-AND Otsu thresholds:
  - June 10, 2020: $\text{VV} = -12.457\text{ dB}$, $\text{VH} = -21.697\text{ dB}$.
  - July 16, 2020: $\text{VV} = -14.960\text{ dB}$, $\text{VH} = -21.828\text{ dB}$.
- Contrast with illustrative static heuristic ($-16.0$ / $-23.5\text{ dB}$): adaptive Otsu achieves $53.89\%$ agreement with RF and identifies $2,177$ water pixels, closely tracking the optical reference ($2,430$ water pixels).
- Deliverable: [phase7b1_baseline_threshold_audit.csv](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b1/audit/phase7b1_baseline_threshold_audit.csv).

### Work Package I: Multi-Region Framework Readiness (Task I)
- **Status:** **VERIFIED EXTENSIBLE**
- Validated `ExplainabilityBatchBuffer` and `explain_prediction_records()`. Dynamic region decoupling confirmed. November 12–13 intake protocol strictly preserved.

---

## 3. ARTIFACT INVENTORY & CHECKSUMS

### Core Model & Code Files:
- [src/ml/random_forest.py](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/src/ml/random_forest.py): Vectorized Pure-NumPy Random Forest.
- [src/ml/explainability.py](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/src/ml/explainability.py): Tree-path attribution, brute-force Shapley, calibration, grouped decomposition.
- [scripts/run_phase7b1_audit.py](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/scripts/run_phase7b1_audit.py): Audit execution script.
- [tests/test_phase7b1_integrity.py](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase7b1_integrity.py): 16 unit and integration test fixtures.
- [models/phase7a/phase7a_random_forest_model.joblib](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/models/phase7a/phase7a_random_forest_model.joblib): Frozen model artifact (SHA-256: `85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad`).

### Audit Reports & Output Tables:
- [data/metadata/phase7b1_integrity_audit.json](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/metadata/phase7b1_integrity_audit.json): Comprehensive audit metadata.
- [docs/PHASE7B1_MODEL_AND_EXPLAINABILITY_AUDIT.md](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/docs/PHASE7B1_MODEL_AND_EXPLAINABILITY_AUDIT.md): Detailed scientific audit report.
- 8 Audit CSV Tables:
  1. `data/outputs/phase7b1/audit/phase7b1_random_forest_integrity.csv`
  2. `data/outputs/phase7b1/audit/phase7b1_oob_prediction_audit.csv`
  3. `data/outputs/phase7b1/audit/phase7b1_shap_bruteforce_verification.csv`
  4. `data/outputs/phase7b1/audit/phase7b1_feature_redundancy_audit.csv`
  5. `data/outputs/phase7b1/audit/phase7b1_local_additivity_audit.csv`
  6. `data/outputs/phase7b1/audit/phase7b1_probability_calibration_audit.csv`
  7. `data/outputs/phase7b1/audit/phase7b1_false_positive_physics_audit.csv`
  8. `data/outputs/phase7b1/audit/phase7b1_baseline_threshold_audit.csv`

---

## 4. SCIENTIFIC GOVERNANCE & PHASE 8 HANDOFF DIRECTIVES

Before beginning **Phase 8 (Backend API & Data Service Development)**, the following architectural boundaries are formally established:

1. **Model Promotion Ban:** The Random Forest model (`phase7a_rf_jamuna_v1`) must remain registered under status `RETAINED_AS_PROBABILITY_LAYER`. It shall not replace the deterministic Lee 5×5 Dual-AND Otsu baseline as the primary water classifier.
2. **Threshold Immutability:** The decision threshold $\tau^* = 0.35$ remains frozen.
3. **Probability Recalibration:** In Phase 8 backend endpoints, raw ensemble probabilities should undergo post-hoc calibration (e.g., Platt scaling or isotonic regression) before serving continuous risk indices.
4. **Data Intake Gate:** Any future satellite acquisitions (e.g., November 12–13, 2026) must pass through the documented intake protocol in [DATA_INTAKE_PROCEDURE.md](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/docs/DATA_INTAKE_PROCEDURE.md) without automated online re-training.
5. **Phase 8 Scope:** Proceed to develop FastAPI backend services, spatial tiling, and explainability endpoints, referencing the verified scientific artifacts.

