# Earth Pulse — Phase 7B: Explainable AI, SHAP Attribution & SAR Model Interpretability

**Project:** NASA Space Apps Challenge 2026 — Dancing with the SARs  
**Study Area:** Jamuna River reach (Kazipur / Sirajganj, Bangladesh)  
**System:** Earth Pulse Fluvial Geomorphology & SAR Change Engine  
**Hardware & Environment:** Linux, Intel Core i7-1255U (10 Cores), 16 GB RAM, CPU-Only  
**Date:** November 3, 2026  
**Status:** **OPERATIONAL & SCIENTIFICALLY BENCHMARKED (275 / 275 TESTS PASSING, 0 WARNINGS)**  

---

## 1. Executive Summary & Model Governance Status

Phase 7B delivers a rigorous Explainable AI (XAI) and model interpretability framework for the supervised Random Forest water classifier developed in Phase 7A (`phase7a_rf_jamuna_v1`). Operating under strict scientific governance guidelines without retraining, parameter modification, or package additions, Phase 7B investigates the internal decision pathways of the 40-tree ensemble, decomposes feature contributions, quantifies mathematical redundancy between polarization features, investigates the geophysical causes of the high false-alarm rate (low precision and specificity), and contrasts model predictions against the deterministic physical baseline (**Lee 5x5 Dual-AND Otsu**).

### Core Scientific Findings:
1. **Explainability Environment Audit (Task A):**
   - The Python 3.14 execution environment lacks the third-party `shap` and `scikit-learn` packages.
   - In strict compliance with environment governance ("Do not install packages; do not claim SHAP package was implemented; mark SHAP package execution as BLOCKED"), third-party library execution is formally logged as:
     $$\text{SHAP Package Status: } \mathbf{BLOCKED\_DEPENDENCY\_MISSING}$$
   - Exact mathematical Shapley feature attributions were computed using a native pure-NumPy **`TreePathExplainer`** implementing the exact path-dependent tree attribution formulation (Lundberg et al., 2020; Saabas, 2014) with machine-precision additivity:
     $$\phi_0 + \sum_{j=1}^D \phi_j(x) = f(x) = P(\text{Water} \mid x)$$
2. **Feature Redundancy & Redundant Polarization Attribution (Task B):**
   - Analysis of `vv_minus_vh_db` versus `cross_pol_ratio` confirms **strict monotonic mathematical redundancy**:
     $$\text{cross\_pol\_ratio} = \min\left(10^{\frac{\sigma^0_{VV} - \sigma^0_{VH}}{10}}, 100.0\right) \iff \text{vv\_minus\_vh\_db} = 10 \log_{10}(\text{cross\_pol\_ratio})$$
   - Pearson correlation is $r = \mathbf{0.8558}$, and Spearman rank correlation is **$r_s = \mathbf{1.0000}$** ($p = 0.0$). In decision tree splits, monotonic transformations partition sample spaces along identical rankings, causing **credit-splitting** in individual attributions.
   - When grouped into physically motivated categories:
     - **Radiometric Backscatter (`vv_db` + `vh_db`):** $\mathbf{67.38\%}$ of total attribution ($\text{Mean}|\text{SHAP}| = 0.0877$).
     - **Spatial Texture (`texture_vv` + `texture_vh`):** $\mathbf{21.94\%}$ of total attribution ($\text{Mean}|\text{SHAP}| = 0.0286$).
     - **Polarization Ratio (`vv_minus_vh_db` + `cross_pol_ratio`):** $\mathbf{10.67\%}$ of total attribution ($\text{Mean}|\text{SHAP}| = 0.0139$).
3. **Geophysical Root Cause of False Alarms (Task E):**
   - The Random Forest model's low precision ($0.4477$) and low specificity ($0.2523$) generate $2,762\text{ false alarms}$ on the held-out test set ($1,918$ in June, $844$ in July).
   - **Physical Mechanism:** On fine-grained saturated sands (chars) and moist agricultural soil, smooth surface conditions produce specular forward scattering at C-band, causing backscatter to drop into the water regime:
     - Mean VV for False Positives: $\mathbf{-12.57\text{ dB}}$ (closely overlapping True Water at $\mathbf{-14.35\text{ dB}}$, whereas True Non-Water mainland averages $\mathbf{-6.05\text{ dB}}$).
     - Mean VH for False Positives: $\mathbf{-20.41\text{ dB}}$ (closely overlapping True Water at $\mathbf{-22.38\text{ dB}}$).
     - Local texture on smooth sandbars is low ($\le 1.0\text{ dB}$), failing to trigger vegetation canopy penalties.
4. **Deterministic Baseline vs. Random Forest Comparison (Task F):**
   - Random Forest and the Lee 5x5 Dual-AND Otsu baseline exhibit **$47.55\%$ spatial agreement** across the held-out test observations.
   - The primary divergence consists of **$3,212\text{ pixels}$** where Random Forest predicts water while the Otsu baseline predicts non-water.
   - The deterministic baseline requires simultaneous exceedance in both channels ($\sigma^0_{VV} < -16.0\text{ dB} \land \sigma^0_{VH} < -23.5\text{ dB}$), successfully rejecting wet sandbars where only one channel drops.
5. **Model Governance Verdict (Task K):**
   - The Random Forest model status is confirmed as **`RETAINED_AS_PROBABILITY_LAYER`**.
   - Promotion to primary operational baseline is **strictly rejected**.
   - The deterministic Lee 5x5 Dual-AND Otsu classifier remains the official primary baseline for all Earth Pulse operational flood products.

---

## 2. Task A — Explainability Environment Audit

A programmatic audit of the Python environment was performed by `src.ml.explainability.audit_explainability_environment()`:

| Component | Status / Version | Scientific Governance Finding |
| :--- | :---: | :--- |
| **Python Core** | `3.14.8` | Standard Linux execution environment. |
| **`shap` Package** | **`NOT INSTALLED`** | Package installation is strictly prohibited. SHAP package execution is marked as **`BLOCKED_DEPENDENCY_MISSING`**. |
| **`sklearn` Package** | **`NOT INSTALLED`** | Package installation is strictly prohibited. Handled via pure-NumPy model implementations. |
| **`numpy` Package** | `2.4.6` | Verified vectorized numerical engine. |
| **`pandas` Package** | `2.3.3` | Verified tabular manipulation engine. |
| **`matplotlib` Package** | `3.10.9` | Verified publication-quality rendering engine (headless Agg mode). |
| **`scipy` Package** | `1.17.1` | Verified scientific statistics engine. |
| **`joblib` Package** | `1.5.3` | Verified artifact persistence engine. |
| **GDAL Warning Resolution** | **`RESOLVED (0 Warnings)`** | Added `gdal.UseExceptions()` at module load, eliminating the historical `FutureWarning`. |

Because third-party `shap` is absent, all feature attributions are computed via the native pure-NumPy `TreePathExplainer`, which mathematically implements exact path-dependent Shapley decomposition directly on the serialized `RandomForestClassifier` ensemble.

---

## 3. Task B — Model & Feature Schema Audit & Redundancy Analysis

### 3.1 Feature Schema Verification
The input feature vector is structured as:
$$X = \left[ \text{vv\_db}, \text{vh\_db}, \text{vv\_minus\_vh\_db}, \text{cross\_pol\_ratio}, \text{texture\_vv}, \text{texture\_vh} \right]$$

| Feature Name | Polarization | Scale | Valid Range | Physical Mechanism |
| :--- | :---: | :---: | :---: | :--- |
| `vv_db` | VV | Decibels (dB) | $[-35.0, +15.0]$ | Copolarized backscatter. Highly sensitive to surface roughness and specular water reflectance. |
| `vh_db` | VH | Decibels (dB) | $[-40.0, +5.0]$ | Crosspolarized backscatter. Sensitive to volume scattering in vegetation canopies; low over water. |
| `vv_minus_vh_db` | Dual | Decibels (dB) | $[-10.0, +30.0]$ | Logarithmic cross-polarization difference ($\sigma^0_{VV} - \sigma^0_{VH}$). |
| `cross_pol_ratio` | Dual | Linear Ratio | $[0.0, 100.0]$ | Linear power ratio $\sigma^0_{VV} / \sigma^0_{VH}$, clipped to 100. |
| `texture_vv` | VV | Std Dev (dB) | $[0.0, 20.0]$ | Local spatial standard deviation in a $5 \times 5$ window ($100\text{ m} \times 100\text{ m}$). |
| `texture_vh` | VH | Std Dev (dB) | $[0.0, 20.0]$ | Local spatial standard deviation in a $5 \times 5$ window ($100\text{ m} \times 100\text{ m}$). |

### 3.2 Redundancy Investigation: `vv_minus_vh_db` vs. `cross_pol_ratio`
By definition, for any power ratio:
$$\text{cross\_pol\_ratio} = \frac{\sigma^0_{VV, \text{linear}}}{\sigma^0_{VH, \text{linear}}} = 10^{\frac{\sigma^0_{VV, \text{dB}} - \sigma^0_{VH, \text{dB}}}{10}} = 10^{\frac{\text{vv\_minus\_vh\_db}}{10}}$$
When clipped at $100.0$ (corresponding to $20\text{ dB}$):
$$\text{vv\_minus\_vh\_db} = 10 \log_{10}(\text{cross\_pol\_ratio}) \quad \forall \, \text{vv\_minus\_vh\_db} \le 20\text{ dB}$$

Empirical correlation analysis across all 31,522 dataset observations:
- **Pearson Linear Correlation:** $r = \mathbf{0.8558}$ ($p = 0.0$).
- **Spearman Monotonic Rank Correlation:** $r_s = \mathbf{1.0000}$ ($p = 0.0$).

**Spearman Rank Correlation Matrix across All Features:**
```
                 vv_db    vh_db  vv_minus_vh  cross_pol  tex_vv   tex_vh
vv_db           1.0000   0.8546      -0.1181    -0.1181  -0.0213  -0.6318
vh_db           0.8546   1.0000      -0.5454    -0.5454  -0.0134  -0.6987
vv_minus_vh_db -0.1181  -0.5454       1.0000     1.0000  -0.0064   0.4110
cross_pol_ratio-0.1181  -0.5454       1.0000     1.0000  -0.0064   0.4110
texture_vv     -0.0213  -0.0134      -0.0064    -0.0064   1.0000   0.3290
texture_vh     -0.6318  -0.6987       0.4110     0.4110   0.3290   1.0000
```
Notice that every correlation coefficient for `cross_pol_ratio` is bitwise identical to `vv_minus_vh_db`. Because decision trees split along monotonic inequalities ($x_j \le T$), splitting on `cross_pol_ratio` at $10^{T/10}$ partitions the training set identically to splitting on `vv_minus_vh_db` at $T$. Consequently, these two features perform identical discriminatory roles and split feature attribution credit between them.

---

## 4. Task C — Global Tree-Path Attributions & Grouped Attribution

Evaluating the 40-tree ensemble across the held-out test observations ($N = 6,124$) using the training distribution ($N = 18,825$) as background yields a global base probability of:
$$\phi_0 = E[f(X_{\text{train}})] = \mathbf{0.4905}$$

### 4.1 Global Feature Importance Ranking
Feature importance is quantified by Mean Absolute SHAP Attribution ($\frac{1}{N} \sum_{i=1}^N |\phi_{i, j}|$):

| Rank | Feature Name | Mean Absolute Attribution ($\text{Mean}|\text{SHAP}|$) | Mean Signed Attribution | Directionality / Physical Role |
| :---: | :--- | :---: | :---: | :--- |
| **1** | `vv_db` | **0.0508** | $-0.0016$ | Low VV ($< -16\text{ dB}$) pushes strongly toward water ($+0.12$ to $+0.25$). High VV suppresses water. |
| **2** | `vh_db` | **0.0503** | $-0.0014$ | Low VH ($< -24\text{ dB}$) pushes toward water. High VH indicates canopy volume scattering and strongly suppresses water (up to $-0.30$). |
| **3** | `texture_vh` | **0.0292** | $-0.0024$ | Low spatial texture pushes toward water. High texture ($> 3.0\text{ dB}$) indicates settlement or forest canopy edges, strongly suppressing water. |
| **4** | `texture_vv` | **0.0090** | $-0.0003$ | Surface variance discriminator; moderate impact on char margins. |
| **5** | `vv_minus_vh_db` | **0.0077** | $-0.0006$ | Polarization difference; secondary credit-split discriminator. |
| **6** | `cross_pol_ratio` | **0.0074** | $-0.0006$ | Linear power ratio; secondary credit-split discriminator. |

### 4.2 Grouped Feature Attributions
Aggregating collinear and physically linked features into functional groups resolves credit-splitting:

| Rank | Feature Group | Constituent Features | Mean Absolute Attribution | Fraction of Attribution | Mean Signed Attribution |
| :---: | :--- | :--- | :---: | :---: | :---: |
| **1** | **Radiometric Backscatter** | `vv_db`, `vh_db` | **0.0877** | **67.38%** | $-0.0029$ |
| **2** | **Spatial Texture Group** | `texture_vv`, `texture_vh` | **0.0286** | **21.94%** | $-0.0027$ |
| **3** | **Polarization Ratio Group** | `vv_minus_vh_db`, `cross_pol_ratio` | **0.0139** | **10.67%** | $-0.0012$ |

Radiometric backscatter intensity governs more than two-thirds of the model's total decision power, while spatial texture provides the primary spatial regularization mechanism.

---

## 5. Task D — Local Prediction Explanations for Representative Cases

Eight representative held-out test observations were sampled across distinct hydrological states and evaluated with full local feature attributions:

| Case ID | Epoch | Category & Description | $P(\text{Water})$ | Base $\phi_0$ | $\phi(\text{VV})$ | $\phi(\text{VH})$ | $\phi(\text{TexVH})$ | $\phi(\text{TexVV})$ | $\phi(\text{Diff})$ | $\phi(\text{Ratio})$ |
| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `CASE_01_TP` | June | **True Positive:** Deep River Channel | **0.781** | 0.491 | $+0.112$ | $+0.124$ | $+0.042$ | $+0.008$ | $+0.002$ | $+0.002$ |
| `CASE_02_TP` | July | **True Positive:** Inundated Floodplain | **0.846** | 0.491 | $+0.145$ | $+0.158$ | $+0.038$ | $+0.011$ | $+0.001$ | $+0.002$ |
| `CASE_03_TN` | June | **True Negative:** Dry Mainland Farmland | **0.114** | 0.491 | $-0.138$ | $-0.182$ | $-0.048$ | $-0.004$ | $-0.003$ | $-0.002$ |
| `CASE_04_TN` | July | **True Negative:** Settlement Embankment | **0.082** | 0.491 | $-0.152$ | $-0.210$ | $-0.041$ | $-0.003$ | $-0.001$ | $-0.002$ |
| `CASE_05_FP` | June | **Optical Disagreement (FP):** Moist Char Sand | **0.584** | 0.491 | $+0.048$ | $+0.039$ | $+0.004$ | $+0.001$ | $+0.001$ | $+0.000$ |
| `CASE_06_FP` | July | **Optical Disagreement (FP):** Saturated Farmland | **0.612** | 0.491 | $+0.058$ | $+0.052$ | $+0.008$ | $+0.001$ | $+0.000$ | $+0.000$ |
| `CASE_07_FN` | June | **Optical Disagreement (FN):** Shallow Sand Channel | **0.286** | 0.491 | $-0.088$ | $-0.076$ | $-0.032$ | $-0.006$ | $-0.002$ | $-0.001$ |
| `CASE_08_FN` | July | **Optical Disagreement (FN):** Turbid Flood Edge | **0.312** | 0.491 | $-0.072$ | $-0.068$ | $-0.031$ | $-0.005$ | $-0.002$ | $-0.001$ |

### Physical Interpretations:
1. **True Positive Cases (Cases 01 & 02):**
   Strong specular reflection causes copolarized VV backscatter to plummet to $-21.4\text{ dB}$, while depolarizing volume scattering in VH drops to $-28.2\text{ dB}$. Both VV ($+0.112$) and VH ($+0.124$) drive probability sharply upward to $0.781$--$0.846$.
2. **True Negative Cases (Cases 03 & 04):**
   Rough agricultural soil and village vegetation canopies generate high backscatter ($-9.5\text{ dB}$ VV, $-15.2\text{ dB}$ VH). VH attribution strongly suppresses water probability ($-0.182$ to $-0.210$), yielding confident non-water predictions ($P < 0.12$).
3. **Optical Disagreement False Positives (Cases 05 & 06):**
   Fine-grained sand on emerging chars retains moisture. While Sentinel-2 optical SCL correctly classifies these bare sands as non-water (Class 5), smooth wet sand mimics water specular reflection at C-band (VV $\approx -12.5\text{ dB}$, VH $\approx -20.4\text{ dB}$). With an optimal threshold of $\tau^* = 0.35$, the model predicts water ($P = 0.584$).

---

## 6. Task E — False-Positive & False-Negative Error Investigation

On the held-out test set ($6,124\text{ samples}$), the Random Forest model generates **$2,762\text{ false alarms}$** (Optical Disagreement FP) and **$191\text{ missed detections}$** (Optical Disagreement FN).

### 6.1 Backscatter Distribution Comparison

| Sample Subset | Sample Count ($N$) | Mean VV [dB] | Std VV [dB] | Mean VH [dB] | Std VH [dB] | Mean Texture VH [dB] |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **True Positives (TP)** | 2,239 | **$-14.35$** | $2.84$ | **$-22.38$** | $2.61$ | $1.28$ |
| **True Negatives (TN)** | 932 | **$-6.05$** | $3.12$ | **$-13.24$** | $2.88$ | $2.45$ |
| **False Positives (FP All)** | 2,762 | **$-12.57$** | $2.41$ | **$-20.41$** | $2.26$ | $1.52$ |
| *FP June (Pre-Monsoon)* | 1,918 | $-12.68$ | $2.38$ | $-20.72$ | $2.19$ | $1.48$ |
| *FP July (Monsoon Crest)* | 844 | $-12.31$ | $2.45$ | $-19.70$ | $2.29$ | $1.61$ |
| **False Negatives (FN All)**| 191 | **$-8.91$** | $2.65$ | **$-17.20$** | $2.48$ | $2.14$ |

### 6.2 Geophysical Findings on False Positives
1. **Backscatter Proximity to Water:**
   False-positive pixels exhibit a mean VV backscatter of **$-12.57\text{ dB}$**, which is only $1.78\text{ dB}$ higher than true open water ($-14.35\text{ dB}$) and **$6.52\text{ dB}$ lower** than true non-water mainland ($-6.05\text{ dB}$).
2. **Moist Char Sediment Physics:**
   In the braided Jamuna River, large sandbars (chars) comprise fine-grained silt and alluvium with high capillary moisture retention. Even when unflooded, smooth wet sand produces near-specular forward scattering at C-band ($\lambda = 5.55\text{ cm}$), causing both copolarized and crosspolarized returns to drop into the water distribution.
3. **Monsoon Soil Saturation Shift:**
   In July, widespread monsoon precipitation saturates agricultural topsoil across non-inundated chars. The model misclassifies $844$ of $927$ non-water test pixels in July, collapsing July test specificity to $8.95\%$.

---

## 7. Task F — Deterministic Baseline Explanation & Side-by-Side Comparison

### 7.1 Deterministic Lee 5x5 Dual-AND Otsu Baseline Rule
The operational physical baseline relies on transparent, deterministic threshold logic:
$$\text{Class} = \begin{cases} 
\text{Water (1)} & \text{if } (\sigma^0_{VV} < -16.0\text{ dB}) \land (\sigma^0_{VH} < -23.5\text{ dB}) \\
\text{Non-Water (0)} & \text{otherwise} 
\end{cases}$$
- **Speckle Filter:** Adaptive Lee filter ($5 \times 5$ window, 100m footprint) removes speckle noise without blurring channel margins.
- **Dual-AND Conservatism:** Simultaneous exceedance in both channels is strictly required. If wet sand reduces VV to $-14\text{ dB}$ but fails to lower VH below $-23.5\text{ dB}$, the pixel is rejected as water.

### 7.2 Spatial Comparison on Held-Out Test Pixels ($N = 6,124$)

| Comparison Category | Pixel Count | Percentage of Test Set | Scientific Interpretation |
| :--- | :---: | :---: | :--- |
| **Both Models Predict Water** | 1,789 | 29.21% | Unambiguous open water (deep main channels and major braided anabranches). |
| **Both Models Predict Non-Water** | 1,123 | 18.34% | Unambiguous mainland (settlements, elevated embankments, dense forest). |
| **RF Predicts Water / Otsu Predicts Non-Water** | **3,212** | **52.45%** | **Primary Disagreement Regime:** Saturated chars, wet silt, and shallow agricultural waterlogging. RF predicts water ($P \ge 0.35$); Otsu rejects due to dual-AND criteria. |
| **RF Predicts Non-Water / Otsu Predicts Water** | 0 | 0.00% | Otsu never detects water that RF misses on the evaluated test set. |
| **Overall Spatial Agreement** | 2,912 | 47.55% | Baseline agreement rate across diverse fluvial landforms. |

---

## 8. Task G — Probability Calibration & Uncertainty Diagnostics

Evaluating predicted probabilities against binary ground truth:
- **Brier Score:** $\mathbf{0.2270}$
- **Expected Calibration Error (ECE):** $\mathbf{0.0959}$

### 8.1 Reliability Diagram Analysis

| Probability Bin | Bin Range | Sample Count | Mean Predicted $P(\text{Water})$ | Empirical Optical Water Fraction | Calibration Gap |
| :---: | :---: | :---: | :---: | :---: | :---: |
| Bin 1 | $[0.0, 0.1)$ | 65 | 0.0762 | 0.0308 | $+0.0454$ |
| Bin 2 | $[0.1, 0.2)$ | 340 | 0.1584 | 0.0882 | $+0.0702$ |
| Bin 3 | $[0.2, 0.3)$ | 610 | 0.2512 | 0.1852 | $+0.0660$ |
| Bin 4 | $[0.3, 0.4)$ | 1,120 | 0.3531 | 0.2929 | $+0.0602$ |
| Bin 5 | $[0.4, 0.5)$ | 1,450 | 0.4489 | 0.3641 | $+0.0848$ |
| Bin 6 | $[0.5, 0.6)$ | 1,215 | 0.5482 | 0.4724 | $+0.0758$ |
| Bin 7 | $[0.6, 0.7)$ | 780 | 0.6438 | 0.5846 | $+0.0592$ |
| Bin 8 | $[0.7, 0.8)$ | 385 | 0.7412 | 0.7143 | $+0.0269$ |
| Bin 9 | $[0.8, 0.9)$ | 120 | 0.8354 | 0.8250 | $+0.0104$ |
| Bin 10 | $[0.9, 1.0]$ | 39 | 0.9248 | 0.9487 | $-0.0239$ |

### 8.2 Disambiguation of Analytical Terminology
To prevent misleading interpretations, the following five concepts must remain strictly distinct:
1. **Model Probability ($P \in [0, 1]$):** Out-of-bag ensemble soft vote representing the fraction of tree pathways that voted for candidate water.
2. **SHAP Feature Attribution ($\phi \in \mathbb{R}$):** Additive contribution of an individual feature pushing the probability above or below the base rate ($\phi_0$).
3. **Classification Confidence ($|P - 0.5|$):** Distance from maximum decision entropy ($P = 0.5$).
4. **Optical-Reference Agreement:** Statistical match with Sentinel-2 MSI Scene Classification Layer.
5. **Physical Certainty:** The true hydrological state of the surface, which may diverge from optical SCL due to optical cloud shadows, thin cirrus, or sub-canopy water.

---

## 9. Task I — Visualizations Inventory

Nine high-resolution (300 DPI) publication-quality figures were generated in `data/outputs/phase7b/maps/`:

1. [`phase7b_global_shap_beeswarm.png`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b/maps/phase7b_global_shap_beeswarm.png) ($758\text{ KB}$): Global distribution of SHAP feature attributions across 1,000 held-out test points.
2. [`phase7b_global_feature_importance.png`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b/maps/phase7b_global_feature_importance.png) ($131\text{ KB}$): Mean absolute SHAP feature importance bar ranking.
3. [`phase7b_polarization_dependence.png`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b/maps/phase7b_polarization_dependence.png) ($747\text{ KB}$): Two-panel dependence plot (VV and VH backscatter vs. SHAP attribution).
4. [`phase7b_texture_dependence.png`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b/maps/phase7b_texture_dependence.png) ($617\text{ KB}$): Two-panel dependence plot for local spatial texture features.
5. [`phase7b_local_waterfall_examples.png`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b/maps/phase7b_local_waterfall_examples.png) ($353\text{ KB}$): Four-panel waterfall breakdown of representative TP, TN, FP, and FN cases.
6. [`phase7b_false_positive_comparison.png`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b/maps/phase7b_false_positive_comparison.png) ($164\text{ KB}$): Backscatter distribution histograms comparing False Positives against True Water and Mainland.
7. [`phase7b_false_negative_comparison.png`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b/maps/phase7b_false_negative_comparison.png) ($162\text{ KB}$): Boxplot comparisons of missed water vs. open water returns and texture.
8. [`phase7b_rf_vs_otsu_disagreement_map.png`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b/maps/phase7b_rf_vs_otsu_disagreement_map.png) ($928\text{ KB}$): Spatial map of agreement vs. disagreement regimes along the Jamuna River.
9. [`phase7b_probability_uncertainty_map.png`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/outputs/phase7b/maps/phase7b_probability_uncertainty_map.png) ($273\text{ KB}$): Reliability diagram and uncertainty distribution histogram.

---

## 10. Verification Baseline & Test Suite Status

A unit test suite was implemented in [`test_phase7b_explainability.py`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/tests/test_phase7b_explainability.py), verifying:
- Model loading and 40-tree ensemble structure.
- Correct class-1 (candidate water) explanation targeting.
- Feature ordering preservation.
- SHAP output matrix dimensions $(N, 6)$.
- Exact mathematical additivity: $\phi_0 + \sum \phi_j = f(x)$.
- Deterministic sample selection reproducibility.
- Spatial block test-set isolation.
- Local explanation metadata completeness.
- Model registry version preservation.
- Grouped polarization feature attribution.
- Analytical terminology precision.
- Missing-SHAP dependency detection and BLOCKED status handling.
- Multi-region explanation interface flexibility.
- Immutability of the existing Phase 7A model artifact (`85038f0f...`).
- Exact mathematical reproducibility across runs.

```bash
$ python3 -m pytest -q tests/
275 passed in 10.15s
```
**All 275 repository unit tests pass with zero errors and zero warnings.**

