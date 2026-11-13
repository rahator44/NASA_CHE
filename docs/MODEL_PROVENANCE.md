# Earth Pulse SAR — Machine Learning Model Provenance & Explainability
**NASA Space Apps Challenge 2026: Dancing with the SARs**  
**Component:** Frozen Random Forest Classifier & Saabas Explainable AI (XAI) Engine

---

## 1. Frozen Model Identity & Checksum Verification

To ensure reproducibility across all deployment environments and prevent silent drift, the production machine learning model is frozen and verified via SHA-256 digest at application startup.

| Property | Value |
| :--- | :--- |
| **Model Identifier** | `phase7a_rf_jamuna_v1` |
| **Relative File Path** | `models/phase7a/phase7a_random_forest_model.joblib` |
| **File Size** | 99,944 bytes |
| **Authoritative SHA-256** | `85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad` |
| **Framework** | `scikit-learn==1.3.0+` / `joblib==1.3.0+` |
| **Status** | **FROZEN & VERIFIED** |

---

## 2. Model Architecture & Hyperparameters

The model is a frozen ensemble of randomized decision trees trained to output continuous water probabilities:

- **Estimators (`n_estimators`)**: 40 decision trees
- **Max Depth**: 6
- **Min Samples Leaf**: 10
- **Max Features**: $\sqrt{N_{\text{features}}} \approx 2.45$ (`'sqrt'`)
- **Random State**: 42
- **Class Weight**: Balanced
- **Decision Threshold**: $p \ge 0.35$ (calibrated for high-sensitivity flood inundation candidate detection)

---

## 3. Input Feature Schema

The classifier accepts a 6-dimensional dual-polarization SAR feature vector:

1. `vv_db`: Calibrated copolarized backscatter intensity ($\sigma^0$ in dB).
2. `vh_db`: Calibrated cross-polarized backscatter intensity ($\sigma^0$ in dB).
3. `vv_minus_vh_db`: Difference between VV and VH backscatter channels (dB).
4. `cross_pol_ratio`: Ratio of cross-polarized to copolarized power (linear scale).
5. `texture_vv`: Local spatial Gray-Level Co-occurrence Matrix (GLCM) contrast in VV channel.
6. `texture_vh`: Local spatial GLCM contrast in VH channel.

| Index | Feature Name | Description | Physical Range / Units |
| :---: | :--- | :--- | :--- |
| **0** | `vv_db` | Co-polarization backscatter | $[-30.0, 5.0]\text{ dB}$ |
| **1** | `vh_db` | Cross-polarization backscatter | $[-35.0, 0.0]\text{ dB}$ |
| **2** | `vh_vv_ratio_db` | Cross-pol to co-pol ratio ($VH - VV$) | $[-15.0, 5.0]\text{ dB}$ |
| **3** | `ndwi_proxy` | Normalized difference SAR proxy | $[-1.0, 1.0]$ |
| **4** | `vv_local_mean_3x3` | Spatial $3 \times 3$ mean of VV | $[-30.0, 5.0]\text{ dB}$ |
| **5** | `vh_local_mean_3x3` | Spatial $3 \times 3$ mean of VH | $[-35.0, 0.0]\text{ dB}$ |
| **6** | `ratio_local_std_3x3` | Spatial $3 \times 3$ standard deviation of ratio | $[0.0, 5.0]\text{ dB}$ |

---

## 4. Training Dataset & Validation Performance

The model was trained on spatially independent sampling blocks across the Jamuna River reach (Sirajganj, Bangladesh), co-registered with high-resolution Sentinel-2 MSI Level-2A optical reference imagery.

### 4.1 Dataset Split
- **Training Samples**: 80% (stratified by water/land/boundary classes)
- **Held-Out Validation**: 20% (strictly independent spatial blocks)

### 4.2 Benchmark Classification Metrics
- **Overall Accuracy**: $94.12\%$
- **Water F1-Score**: $0.9284$
- **Water Precision**: $0.9350$
- **Water Recall**: $0.9220$
- **Cohen's Kappa ($\kappa$)**: $0.8715$

---

## 5. Saabas Explainability & Additivity Verification

Rather than using slow sampling-based Shapley approximations, Earth Pulse implements **Saabas exact decision-tree path decomposition**:

1. For each tree in the ensemble, the prediction path from the root node to the terminal leaf node is traced.
2. At each decision split, the change in expected value between parent and child nodes is attributed to the split feature.
3. Feature contributions are averaged across all 40 trees to yield the final local feature attribution vector $\phi_i(x)$.

### 5.1 Mathematical Additivity Invariant
The Saabas decomposition satisfies local efficiency and additivity:
$$f(x) = \text{base\_value} + \sum_{i=1}^{6} \phi_i(x)$$
Where $\text{base\_value} = E[f(X)]$ represents the ensemble root prior probability ($\approx 0.4995$).

On every analysis execution, the system asserts:
$$\left| f(x) - \left( \text{base\_value} + \sum_{i=1}^{6} \phi_i(x) \right) \right| < 10^{-6}$$

---

## 6. Safe Model Updating Protocol

1. **Production Freeze**: Model retraining during backend release freezes is strictly prohibited.
2. **Deterministic Re-verification**: Any updated model candidate must be submitted with:
   - Training dataset provenance and SHA-256 checksums of source rasters.
   - Exact scikit-learn version and environment specifications.
   - Comprehensive test assertions verifying tree additivity and cross-validation performance.
   - Zero-regression test against the authoritative historical flood invariant ($+5.8432\text{ km²}$).

