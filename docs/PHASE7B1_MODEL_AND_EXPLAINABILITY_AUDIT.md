# EARTH PULSE — PHASE 7B.1: TREE EXPLAINABILITY MATHEMATICAL VERIFICATION & RANDOM FOREST MODEL INTEGRITY AUDIT

**Project:** NASA Space Apps Challenge 2026 — Dancing with the SARs  
**System:** Earth Pulse — Explainable SAR Water Classification & Change Engine  
**Study Area:** Jamuna River Reach (Kazipur / Sirajganj, Bangladesh)  
**Date of Audit:** November 3, 2026  
**Auditor Roles:** Senior Machine-Learning Scientist, Explainable-AI Researcher, Statistical Auditor, SAR Remote-Sensing Engineer  
**Baseline Test Suite:** 291 passing tests (275 inherited + 16 new Phase 7B.1 integrity tests, 0 warnings)  

---

## 1. EXECUTIVE SUMMARY & AUDIT OBJECTIVES

Phase 7B.1 provides an independent mathematical, statistical, and architectural audit of the machine-learning pipeline deployed in Phase 7A and explained in Phase 7B. The audit was conducted under strict scientific governance: **no model retraining, no hyperparameter modification, no threshold adjustment ($\tau^* = 0.35$ maintained), no promotion of the Random Forest above the primary deterministic baseline, and zero external package installations** (preserving the environment audit finding `BLOCKED_DEPENDENCY_MISSING` for third-party `shap` and `scikit-learn`).

### Summary of Core Audit Outcomes:
1. **Random Forest Implementation (Task A):** Verified as a genuine, mathematically sound pure-NumPy Random Forest adhering to Breiman (2001) principles. It implements bootstrap sampling with replacement (`replace=True`), $75.0\%$ sub-bagging for diversity/speed, random feature subsets per split ($\lfloor\sqrt{6}\rfloor = 2$ features), vectorized Gini impurity gain, and 40-tree ensemble soft voting with deterministic reproducibility (`random_state=42`).
2. **OOB Terminology Reconciliation (Task B):** Identified and corrected a terminology overstatement in the Phase 7B narrative. Model evaluation on the test set ($N=6,124$) is strictly **ordinary ensemble soft voting across all 40 trees**, not out-of-bag prediction. True out-of-bag predictions only apply to training samples evaluated exclusively by bootstrap-omitted trees (averaging $18.89$ trees per training sample).
3. **Tree Explainability Mathematical Verification (Task C):** Evaluated `TreePathExplainer` against an independent brute-force Shapley reference calculator over all $2^D$ feature coalitions. Demonstrated that `TreePathExplainer` implements the **Saabas (2014) single-path attribution algorithm**. While it satisfies exact efficiency/additivity ($\phi_0 + \sum_{j=1}^6 \phi_j = f(x)$ with error $< 10^{-5}$), it is path-dependent and diverges from coalition-averaged Shapley values on multi-depth branches due to split ordering. Terminology is formally downgraded to **Pure-NumPy Path-Dependent Tree Attribution (Saabas Formulation)** to prevent unsupported exact-SHAP claims.
4. **Feature Redundancy & 20 dB Clipping (Task D):** Formally quantified the analytical relation $\text{cross\_pol\_ratio} = \min(10^{\Delta/10}, 100.0)$. The exact logarithmic inversion $\Delta = 10 \log_{10}(\text{cross\_pol\_ratio})$ holds strictly for $\Delta < 20.0\text{ dB}$. In the held-out test set, $99.48\%$ ($6,092$ samples) are unclipped ($\text{Spearman } r = 1.0000$), while $0.52\%$ ($32$ samples) are clipped at $100.0$. In tree ensembles, this causes credit-splitting along identical monotonic sample orderings, fully validating the **Grouped Polarization Attribution** ($10.67\%$ combined impact).
5. **Local Additivity Audit (Task E):** Audited all 8 representative local explanation cases across deep water, floodplains, char sandbars, and settlements. All 8 cases passed exact additivity verification with error $< 10^{-8}$.
6. **Probability & Decision Margin Terminology (Task F):** Reconciled predictive uncertainty terminology. The heuristic metric $|P - 0.5|$ represents an **empirical classification decision margin / uncertainty proxy**, not a calibrated posterior probability. The uncalibrated ensemble achieves a Brier score of $0.2270$ and Expected Calibration Error (ECE) of $0.0959$.
7. **False-Positive Physical Epistemology (Task G):** Reconciled the held-out confusion matrix ($N=6,124$: $\text{TP}=2,239$, $\text{TN}=932$, $\text{FP}=2,762$, $\text{FN}=191$). The low backscatter observed over moist char sandbars and waterlogged topsoil ($\text{VV}_{mean} = -12.57\text{ dB}$) is classified as a **scientifically supported physical hypothesis consistent with forward specular scattering**, but **not an in-situ proven causal certainty** due to the absence of synchronous ground-truth soil moisture measurements.
8. **Deterministic Baseline Reconciliation (Task H):** Reconciled the historical Phase 3A Lee 5×5 Dual-AND Otsu thresholds (June 10: $\text{VV} = -12.457\text{ dB}$, $\text{VH} = -21.697\text{ dB}$; July 16: $\text{VV} = -14.960\text{ dB}$, $\text{VH} = -21.828\text{ dB}$) against the illustrative static heuristic ($-16.0\text{ dB}$ / $-23.5\text{ dB}$). Demonstrated that adaptive scene-specific thresholds account for seasonal hydrological dynamics and achieve $53.89\%$ spatial agreement with the Random Forest on test samples (identifying $2,177$ water pixels, closely tracking the optical reference count of $2,430$).
9. **Multi-Region Framework Readiness (Task I):** Validated that `PredictionRecord` batch buffering and attribution generation function correctly, preserving geographical decoupling for future regional datasets while maintaining the strict freeze on the unconfirmed November 12–13, 2026 intake protocol.

---

## 2. TASK A: RANDOM FOREST IMPLEMENTATION & ARCHITECTURAL PRINCIPLES AUDIT

The repository's pure-NumPy Random Forest implementation (`src/ml/random_forest.py`) was audited line-by-line to verify compliance with core machine-learning principles:

| Subsystem | Configured Parameter | Implementation Line | Verified Behavior | Compliance Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **Bootstrap Sampling** | `replace=True` | `src/ml/random_forest.py:287` | Samples indices with replacement from master training pool | **COMPLIANT** |
| **Subsample Ratio** | `sample_size = 0.75 * N` | `src/ml/random_forest.py:286` | Draws $14,118$ samples ($75\%$) per tree (sub-bagging) | **COMPLIANT (OPTIMIZATION)** |
| **Random Feature Subsampling** | `max_features = 'sqrt'` | `src/ml/random_forest.py:126` | $\lfloor\sqrt{6}\rfloor = 2$ random features chosen per split | **COMPLIANT** |
| **Split Criterion** | Gini Impurity Gain | `src/ml/random_forest.py:89,175` | $\Delta \text{Gini} = I_{\text{parent}} - (w_L I_L + w_R I_R) / w_{\text{tot}}$ | **COMPLIANT** |
| **Threshold Search** | `n_thresholds = 10` | `src/ml/random_forest.py:152` | 10 linear candidate thresholds evaluated via 2D broadcasting | **COMPLIANT (CPU SPEEDUP)** |
| **Stopping Conditions** | `max_depth=6, min_leaf=10` | `src/ml/random_forest.py:112` | Depth ceiling, minimum leaf occupancy, pure impurity threshold | **COMPLIANT** |
| **Leaf Probability** | Empirical Frequency | `src/ml/random_forest.py:108` | $P(\text{water}) = \sum w_1 / \sum w_{\text{leaf}}$ | **COMPLIANT** |
| **Ensemble Aggregation** | Soft Voting | `src/ml/random_forest.py:322` | Mean posterior across all 40 independent trees | **COMPLIANT** |
| **Reproducibility** | Master Seed 42 | `src/ml/random_forest.py:282` | Master RNG derives unique seeds per tree deterministically | **COMPLIANT** |
| **Artifact Integrity** | Joblib Serialization | `models/phase7a/*.joblib` | 103,922 bytes payload, verified SHA-256 hash | **COMPLIANT** |

### Scientific Findings:
- The custom implementation genuinely constitutes a Random Forest in the sense of Breiman (2001).
- The use of $75\%$ sub-bagging with replacement (m-out-of-n bootstrap) is a well-established variance-reduction technique that reduces tree correlation while maintaining high execution speed on CPU.
- The vectorized threshold search over 10 linear candidates balances split optimality with high CPU throughput, avoiding costly full-sort evaluations across $18,825$ continuous backscatter values.

---

## 3. TASK B: OUT-OF-BAG (OOB) TERMINOLOGY AUDIT & PROBABILITY CALCULATION

In the Phase 7B report narrative, model probability was occasionally termed an "out-of-bag ensemble soft vote". This audit examined the underlying prediction mechanics to eliminate ambiguity:

```
+----------------------------------------------------------------------------------------------------+
|                                    PREDICTION PARADIGM COMPARISON                                  |
+------------------------------------+--------------------------------+------------------------------+
| Dimension                          | Ordinary Ensemble Prediction   | True Out-of-Bag (OOB)        |
+------------------------------------+--------------------------------+------------------------------+
| Tree Scope                         | All 40 trees evaluated         | Only trees omitting sample i |
| Sample Type                        | Held-out test / live raster    | Training samples only        |
| Mean Trees Evaluated               | 40.0 trees (100.0%)            | 18.89 trees (47.2%)          |
| In-Bag Exposure                    | None (samples held out)        | Zero (strictly excluded)     |
| Purpose                            | Inference & Generalization     | Unbiased Training Diagnostic |
+------------------------------------+--------------------------------+------------------------------+
```

### Numerical OOB Simulation:
Under $75.0\%$ bootstrap sampling with replacement from $N = 18,825$, the theoretical probability that a sample is omitted from a single tree is:
$$P(\text{omitted}) = \left(1 - \frac{1}{N}\right)^{0.75 N} \approx e^{-0.75} \approx 0.4724 \quad (47.24\%)$$
Across an ensemble of $T = 40$ trees:
- Theoretical mean OOB trees per training sample: $40 \times 0.4724 = 18.90$ trees.
- Simulated empirical mean OOB trees per sample: $18.89$ trees.
- Proportion of training samples with at least one OOB tree: $100.00\%$ ($18,825 / 18,825$).

### Reconciled Terminology:
1. The test set predictions ($N = 6,124$) generated in Phase 7B are **Held-Out Test Ensemble Soft Voting Predictions**.
2. They evaluate all 40 trees because the test samples were entirely disjoint from the training set.
3. The phrase "out-of-bag ensemble soft vote" is formally corrected in all reporting to **"Ensemble Soft Voting / Mean Tree Probability"**.

---

## 4. TASK C: MATHEMATICAL VERIFICATION OF CUSTOM TREE EXPLAINABILITY

### The Theoretical Distinction: Saabas (2014) vs. Exact Shapley (1953) / TreeSHAP (2020)
In cooperative game theory, the exact Shapley value for feature $i$ across feature set $F$ ($|F| = D$) is:
$$\phi_i^{\text{Shapley}} = \sum_{S \subseteq F \setminus \{i\}} \frac{|S|!(|F| - |S| - 1)!}{|F|!} \Big[ v(S \cup \{i\}) - v(S) \Big]$$
where $v(S) = \mathbb{E}[f(x) \mid x_S]$ evaluates the expected prediction given feature subset $S$.

In contrast, `TreePathExplainer` executes Saabas-style single-path attribution:
Along the single decision branch traversed by sample $x$:
$$\phi_{f_k}^{\text{Saabas}} = \sum_{k \in \text{splits on } f_k} \Big( P(\text{child}_k) - P(\text{parent}_k) \Big)$$

### Mathematical Comparison on Controlled Fixtures:

```
+-----------------------------------------------------------------------------------------------------------------+
|                                 BRUTE-FORCE SHAPLEY vs. SAABAS TREE-PATH AUDIT                                  |
+------------------------------+--------------------+---------------------+--------------------+------------------+
| Fixture ID                   | Saabas Attr (f0,f1)| Exact Shapley (f0,f1)| Additivity Error  | Max Divergence   |
+------------------------------+--------------------+---------------------+--------------------+------------------+
| FIXTURE_1_SINGLE_SPLIT       | [0.2400, 0.0000]   | [0.2400, 0.0000]    | < 1e-8 (Exact)     | 0.0000 (Identical|
| FIXTURE_2_TWO_SPLIT_SEQ      | [0.3000, 0.4000]   | [0.4000, 0.3000]    | < 1e-8 (Exact)     | 0.1000 (Shift)   |
| FIXTURE_3_REPEATED_SPLIT     | [0.4400, 0.0000]   | [0.4400, 0.0000]    | < 1e-8 (Exact)     | 0.0000 (Identical|
| FIXTURE_4_THREE_TREE_ENSEMBLE| [0.0200, 0.1800]   | [0.0933, 0.1067]    | < 1e-8 (Exact)     | 0.0733 (Shift)   |
| FIXTURE_5_UNUSED_FEATURE     | [0.30, 0.40, 0.00] | [0.40, 0.30, 0.00]  | < 1e-8 (Exact)     | 0.1000 (Shift)   |
| FIXTURE_6_CLASS_SYMMETRY     | [-0.3000, 0.0000]  | [-0.2000, -0.1000]  | < 1e-8 (Exact)     | 0.1000 (Shift)   |
+------------------------------+--------------------+---------------------+--------------------+------------------+
```

### Scientific Verification Takeaways:
1. **Efficiency / Additivity:** Both Saabas and exact Shapley satisfy efficiency:
   $$\phi_0 + \sum_{j=1}^D \phi_j = f(x)$$
   Across all test fixtures and local cases, the additivity error is $< 10^{-8}$.
2. **Path Dependency & Symmetry Violation:** Saabas single-path attribution allocates the marginal shift $(P_{\text{child}} - P_{\text{parent}})$ to the feature evaluated at that step. A feature tested near the root captures the gross population shift, whereas downstream features receive shifts conditioned on upstream splits. Exact Shapley averages across all $2^D$ entry orders.
3. **Null Player Property:** Both methods strictly assign $0.0000$ attribution to unreferenced features (Fixture 5).
4. **Terminology Governance:** Because `TreePathExplainer` does not average over all feature permutations, it is formally labeled **"Pure-NumPy Path-Dependent Tree Attribution (Saabas Formulation)"** rather than exact Shapley attribution.

---

## 5. TASK D: FEATURE REDUNDANCY & NON-INVERTIBILITY CLIPPING AUDIT

The operational feature schema incorporates both logarithmic difference and linear cross-polarization ratio:
$$\text{vv\_minus\_vh\_db} = \sigma^0_{\text{VV, dB}} - \sigma^0_{\text{VH, dB}}$$
$$\text{cross\_pol\_ratio} = \min\left(10^{\frac{\text{vv\_minus\_vh\_db}}{10}}, 100.0\right)$$

### Invertibility Domain & Clipping Audit:
- **Exact Inversion Formula:** $\text{vv\_minus\_vh\_db} = 10 \log_{10}(\text{cross\_pol\_ratio})$ holds strictly when $\text{cross\_pol\_ratio} < 100.0$ ($\text{vv\_minus\_vh\_db} < 20.0\text{ dB}$).
- **Non-Invertibility Range:** When $\text{vv\_minus\_vh\_db} \ge 20.0\text{ dB}$, `cross_pol_ratio` is hard-clipped to $100.0$.
- **Population Clipping Statistics:**
  - Full Dataset ($N=31,522$): $151$ clipped samples ($0.48\%$), $31,371$ unclipped ($99.52\%$). Pearson $r = 0.8558$, Spearman $r = 1.0000$.
  - Training Split ($N=18,825$): $76$ clipped samples ($0.40\%$), $18,749$ unclipped ($99.60\%$).
  - Held-Out Test Split ($N=6,124$): $32$ clipped samples ($0.52\%$), $6,092$ unclipped ($99.48\%$). Pearson $r = 0.8647$, Spearman $r = 1.0000$.

### Impact on Tree Split Pathways & Attribution:
Because the transformation is strictly monotonic over $99.5\%$ of the domain, any decision tree split on `cross_pol_ratio` at threshold $\theta$ is functionally equivalent to a split on `vv_minus_vh_db` at $10 \log_{10}(\theta)$. In random forest training with feature subsampling ($\lfloor\sqrt{6}\rfloor = 2$), some trees pick `vv_minus_vh_db` while others pick `cross_pol_ratio`, splitting attribution credit between them:
- `vv_minus_vh_db`: Mean |SHAP| = $0.0077$ (Rank 5)
- `cross_pol_ratio`: Mean |SHAP| = $0.0074$ (Rank 6)

Combining them into the **Polarization Ratio Group** recovers their true collective importance ($10.67\%$ total attribution), resolving the credit-splitting artifact without modifying the frozen model architecture.

---

## 6. TASK E: LOCAL ADDITIVITY AUDIT (REPRESENTATIVE CASES)

All 8 representative local explanation cases published in Phase 7B were re-audited using the frozen Random Forest and verified for exact efficiency ($\phi_0 + \sum \phi_j = P(\text{water})$):

| Case ID | Category | Epoch | Reference Label | RF Prob | Base Val $\phi_0$ | $\sum \phi_j$ | Reconstructed | Additivity Error | Pass Status | Primary Driver |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **CASE_01** | TRUE_POSITIVE | June | 1 | 0.9996 | 0.3905 | +0.6091 | 0.9996 | 0.00000000 | **PASS** | `vv_db` (+0.2520) |
| **CASE_02** | TRUE_POSITIVE | July | 1 | 0.9997 | 0.3905 | +0.6092 | 0.9997 | 0.00000000 | **PASS** | `vh_db` (+0.2646) |
| **CASE_03** | TRUE_NEGATIVE | June | 0 | 0.0000 | 0.3905 | -0.3905 | 0.0000 | 0.00000000 | **PASS** | `vv_db` (-0.2104) |
| **CASE_04** | TRUE_NEGATIVE | July | 0 | 0.0000 | 0.3905 | -0.3905 | 0.0000 | 0.00000000 | **PASS** | `vh_db` (-0.1982) |
| **CASE_05** | OPTICAL_DISAGREEMENT_FP | June | 0 | 0.9950 | 0.3905 | +0.6045 | 0.9950 | 0.00000000 | **PASS** | `vv_db` (+0.2485) |
| **CASE_06** | OPTICAL_DISAGREEMENT_FP | July | 0 | 0.9950 | 0.3905 | +0.6045 | 0.9950 | 0.00000000 | **PASS** | `vv_db` (+0.2485) |
| **CASE_07** | OPTICAL_DISAGREEMENT_FN | June | 1 | 0.1600 | 0.3905 | -0.2305 | 0.1600 | 0.00000000 | **PASS** | `vv_db` (-0.1250) |
| **CASE_08** | OPTICAL_DISAGREEMENT_FN | July | 1 | 0.2250 | 0.3905 | -0.1655 | 0.2250 | 0.00000000 | **PASS** | `texture_vh` (-0.0820) |

The global base value across all 40 trees is verified at $\phi_0 = 0.3905$ (corresponding to the mean root probability across the ensemble).

---

## 7. TASK F: PROBABILITY CALIBRATION & DECISION MARGIN AUDIT

The Phase 7B report utilized the quantity $|P - 0.5|$ as a measure of classification certainty. This audit clarifies the distinction between heuristic decision margin and calibrated posterior probability:

### Reliability Diagram & Brier Decomposition ($N = 6,124$):
- **Overall Brier Score:** $0.2270$
- **Expected Calibration Error (ECE):** $0.0959$ ($9.59\%$)
- **Bin Statistics:**
  - In extreme bins ($P \in [0.0, 0.1]$ and $P \in [0.9, 1.0]$), the ensemble shows moderate alignment, but overpredicts water in intermediate bins ($P \in [0.3, 0.7]$) where the calibration gap reaches $0.15$ to $0.28$.

### Scientific Reclassification:
1. $|P - 0.5|$ is an **empirical decision margin / distance to threshold**, indicating how far an observation lies from the ambiguous midpoint.
2. It is **NOT a calibrated Bayesian probability** of true physical presence.
3. Uncalibrated Random Forest tree posteriors tend to push probabilities toward $0$ and $1$ due to Gini purity incentives at leaf nodes.
4. For Phase 8 production serving, post-hoc calibration (Platt scaling or isotonic regression on the validation split) is recommended before exposing continuous probabilities to downstream hydrological risk engines.

---

## 8. TASK G: FALSE-POSITIVE PHYSICAL INTERPRETATION & CONFUSION MATRIX AUDIT

### Sample Count Reconciliation:
The held-out evaluation set ($N = 6,124$) at threshold $\tau^* = 0.35$ reconciles exactly:
$$\text{Total Test Observations} = \text{TP} (2,239) + \text{TN} (932) + \text{FP} (2,762) + \text{FN} (191) = 6,124$$

- **June 10 Pre-Monsoon ($N=4,522$):** $\text{TP}=1,573$, $\text{TN}=849$, $\text{FP}=1,918$, $\text{FN}=182$.
- **July 16 Monsoon Peak ($N=1,602$):** $\text{TP}=666$, $\text{TN}=83$, $\text{FP}=844$, $\text{FN}=9$.

### Mean Feature Distributions by Classification Group:
```
+------------------------------------+-------+----------+----------+------------+------------+
| Group                              | Count | VV (dB)  | VH (dB)  | Ratio (dB) | Texture VV |
+------------------------------------+-------+----------+----------+------------+------------+
| True Positive (TP - Water)         | 2,239 | -14.3511 | -21.9320 | +7.5809    | 0.4421     |
| True Negative (TN - Land)          |   932 |  -6.0464 | -14.3712 | +8.3248    | 1.3410     |
| False Positive (FP - Disagreement) | 2,762 | -12.5702 | -20.4126 | +7.8424    | 0.6120     |
| False Negative (FN - Disagreement) |   191 | -11.0210 | -19.2010 | +8.1800    | 0.8210     |
+------------------------------------+-------+----------+----------+------------+------------+
```

### Physical Scattering Epistemology:
- **Observation:** False positive pixels exhibit low backscatter ($\text{VV} = -12.57\text{ dB}$, $\text{VH} = -20.41\text{ dB}$), much closer to calm water ($-14.35\text{ dB}$) than dry mainland soils ($-6.05\text{ dB}$).
- **Literature-Supported Hypothesis:** Smooth, waterlogged sediments (e.g., exposed char sandbars after river recession, saturated alluvial soils) exhibit high dielectric permittivity and low micro-scale surface roughness, causing forward specular reflection of C-band SAR pulses away from the monostatic satellite receiver.
- **Scientific Audit Correction:** Because synchronous in-situ dielectric probe readings and surface roughness profilometry were not collected during the Sentinel-1 overpasses, this physical mechanism must be stated as a **physically supported hypothesis consistent with microwave scattering theory**, rather than an in-situ proven causal certainty.

---

## 9. TASK H: DETERMINISTIC BASELINE RECONCILIATION (OTSU THRESHOLDS)

The Phase 7B prose cited illustrative fixed thresholds of $-16.0\text{ dB}$ (VV) and $-23.5\text{ dB}$ (VH). This audit compared these against the actual Phase 3A adaptive Lee 5×5 Dual-AND Otsu baseline:

```
+---------------------------------------------------------------------------------------------------------------+
|                                      DETERMINISTIC BASELINE RECONCILIATION                                    |
+------------------------------------+---------------+---------------+--------------------+---------------------+
| Baseline Implementation            | VV Thresh(dB) | VH Thresh(dB) | Test Water Pct     | RF Spatial Agreement|
+------------------------------------+---------------+---------------+--------------------+---------------------+
| Phase 3A June 10 Adaptive Otsu     | -12.4571      | -21.6972      | 25.08% (1,134 pix) | 51.20%              |
| Phase 3A July 16 Adaptive Otsu     | -14.9599      | -21.8279      | 65.11% (1,043 pix) | 61.49%              |
| Phase 3A Combined Adaptive Baseline| Epoch-Adaptive| Epoch-Adaptive| 35.55% (2,177 pix) | 53.89%              |
| Phase 7B Illustrative Fixed Heurist| -16.0000      | -23.5000      | 29.21% (1,789 pix) | 47.55%              |
+------------------------------------+---------------+---------------+--------------------+---------------------+
```

### Scientific Reconciliation:
1. The fixed threshold pair ($-16.0\text{ dB}$ / $-23.5\text{ dB}$) used in Phase 7B was a conservative static heuristic. It under-detects water during the monsoon crest by enforcing a threshold lower than the natural low-backscatter flood water mode.
2. The true operational baseline remains the **Epoch-Adaptive Lee 5×5 Dual-AND Otsu Classifier** derived in Phase 3A. It adapts to seasonal backscatter distributions, identifying $2,177$ water pixels ($35.55\%$), which closely tracks the independent optical reference ($2,430$ water pixels, $39.68\%$) far better than the over-predicting Random Forest ($5,001$ pixels, $81.66\%$).
3. The deterministic baseline remains the primary operational system for Earth Pulse inundation accounting.

---

## 10. TASK I: MULTI-REGION & FUTURE DATA READINESS

The explainability interface was extended to accept standardized `PredictionRecord` batches:
- `explain_prediction_records()` verifies region identifier (`region_id`), model version (`model_version`), and schema alignment prior to attribution generation.
- Decoupling verified: no hardcoded regional bounding boxes or coordinate transforms exist inside `TreePathExplainer`.
- Strict Intake Protocol: The upcoming November 12–13, 2026 acquisition window remains unconfirmed. In accordance with project governance, no live ingestion, online weight adaptation, or synthetic regional datasets were introduced.

---

## 11. TASK J & K: AUDIT DELIVERABLES & TEST VERIFICATION

### Versioned CSV Artifacts Generated:
1. `data/outputs/phase7b1/audit/phase7b1_random_forest_integrity.csv`
2. `data/outputs/phase7b1/audit/phase7b1_oob_prediction_audit.csv`
3. `data/outputs/phase7b1/audit/phase7b1_shap_bruteforce_verification.csv`
4. `data/outputs/phase7b1/audit/phase7b1_feature_redundancy_audit.csv`
5. `data/outputs/phase7b1/audit/phase7b1_local_additivity_audit.csv`
6. `data/outputs/phase7b1/audit/phase7b1_probability_calibration_audit.csv`
7. `data/outputs/phase7b1/audit/phase7b1_false_positive_physics_audit.csv`
8. `data/outputs/phase7b1/audit/phase7b1_baseline_threshold_audit.csv`
9. `data/metadata/phase7b1_integrity_audit.json`

### Test Suite Execution:
- Test File: `tests/test_phase7b1_integrity.py` (16 new unit and integration tests).
- Total Test Suite Status: **291 passed in 12.52s, 0 warnings, 0 failures**.

---

## 12. TASK L: LIMITATIONS & RECOMMENDATIONS BEFORE PHASE 8

### Remaining Model Limitations:
1. **Uncalibrated Output Distribution:** The Random Forest probabilities remain uncalibrated raw ensemble soft votes, exhibiting an Expected Calibration Error of $9.59\%$.
2. **Path-Dependent Explainability:** The pure-NumPy explainer implements Saabas tree-path attribution, which satisfies additivity along observed branches but violates coalition symmetry.
3. **High False-Positive Volume:** At threshold $\tau^* = 0.35$, the model generates $2,762$ false positive pixels over moist bare sediments, resulting in an optical precision of $44.77\%$.

### Phase 8 Backend Architectural Recommendations:
1. **Model Governance:** Expose `phase7a_rf_jamuna_v1` strictly as an auxiliary uncertainty/probability layer; do not replace the deterministic Lee 5×5 Dual-AND Otsu baseline.
2. **Calibration Layer:** Implement post-hoc Platt scaling or isotonic regression in the backend inference service before exposing continuous probabilities to frontend map tiles.
3. **Multi-Region Endpoints:** Design FastAPI endpoints to accept `region_id` and route dynamically to region-specific config files without hardcoding coordinates.
4. **Data Intake Gate:** Retain the manual validation gate in `DATA_INTAKE_PROCEDURE.md` for any future satellite scenes.

