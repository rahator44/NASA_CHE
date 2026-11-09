# EARTH PULSE — AI MODEL EVOLUTION & REPRODUCIBLE RESEARCH ROADMAP

**Project:** NASA Space Apps Challenge 2026 — Dancing with the SARs  
**Application:** Earth Pulse / EarthPulse-SAR  
**Scope:** Machine Learning Model Versioning, Training Pipeline & Independent Ground-Truth Protocols  
**Date:** November 2026  
**Status:** Authoritative Research & Development Roadmap  

---

## 1. FROZEN REFERENCE MODEL STATUS

### Registry Baseline: `phase7a_rf_jamuna_v1`
- **Model Architecture:** Pure-NumPy Vectorized Decision Tree Random Forest Classifier (`src.ml.random_forest.RandomForestClassifier`).
- **Ensemble Dimensions:** 40 decision trees, maximum tree depth 6, minimum leaf size 5.
- **Input Features (6):** `vv_db`, `vh_db`, `vv_minus_vh_db`, `cross_pol_ratio`, `texture_vv`, `texture_vh`.
- **Artifact Path:** `models/phase7a/phase7a_random_forest_model.joblib`.
- **Cryptographic SHA-256 Checksum:**
  `85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad`
- **Validation Metrics (Spatial Block Holdout):**
  - ROC-AUC: 0.6810
  - Precision: 0.4477 (at operating threshold 0.35)
  - Recall: 0.9214
- **Operational Role:** `RETAINED_AS_PROBABILITY_LAYER`.
  The model serves as an experimental secondary probability layer and interpretability tool. It does NOT replace the primary, physically grounded Lee 5x5 + Dual-Pol Otsu threshold classifier.

---

## 2. THE VERSIONED MODEL TRAINING FRAMEWORK (`src/ml/training/`)

To support continuous machine learning experimentation without endangering the frozen reference model, Earth Pulse introduces a modular training framework:

```text
src/ml/training/
├── __init__.py
├── dataset_splitter.py    # Spatial Block Quadrant & Stratified Temporal Splitters
├── feature_selection.py   # Feature Cross-Correlation & Class Weight Balancing
└── trainer.py             # Pure-NumPy RF Training, Calibration & Registry Ingestion
```

### Key Capabilities:
1. **Spatial Leakage Prevention (`dataset_splitter.py`):**
   Partitions training data by spatial quadrants or geographic tiles, ensuring samples from the same immediate hydrological reach do not appear in both train and validation sets.
2. **Temporal Holdout Evaluation:**
   Supports training on historical observations (e.g., 2024) while holding out distinct observation periods (e.g., 2025–2026) to test seasonal transferability.
3. **Multicollinearity Diagnostics (`feature_selection.py`):**
   Evaluates Pearson correlation matrices across features to identify redundant polarimetric ratios.
4. **Class Imbalance Rebalancing:**
   Calculates inverse class frequencies:
   $$w_j = \frac{N_{\text{total}}}{2 \cdot N_j}$$
   to counteract heavy class imbalance between land and flood water.

---

## 3. STRICT DECISION RULES FOR MODEL PROMOTION

### Rule 1: No Self-Referential Ground Truth
A model must NEVER be trained on its own predictions or unsupervised Otsu masks labeled as ground truth. Doing so causes confirmation bias, memorizes algorithmic artifacts, and invalidates scientific evaluation.

### Rule 2: Ground Truth Provenance Requirements
Promotion from experimental to candidate status requires verified, independent labels:
- High-resolution optical reference data (e.g., cloud-free Sentinel-2 MSI NDWI / MNDWI or PlanetScope).
- In-situ hydrometric water-level stations and hydrological gauge readings.
- Independent spatial validation demonstrating statistically significant gains in ROC-AUC ($> 0.75$) and Precision ($> 0.65$ at Recall $\ge 0.90$).

### Rule 3: Candidate v2 Registration Status
In the absence of independent ground-truth data for new observation dates, experimental training runs in `src/ml/training/` register candidate models with the explicit status:
`STATUS = "PENDING_INDEPENDENT_GROUND_TRUTH"`

This guarantees scientific integrity: the system acknowledges model experimentation while preventing unvalidated models from claiming production readiness.

---

## 4. FUTURE SENSOR EXPANSION: NISAR & MULTI-FREQUENCY SAR

The architecture features sensor-specific adapters (`src.ml.adapters.BaseSensorAdapter`). When NASA-ISRO SAR (NISAR) L-band and S-band observations become available:
1. **Frequency Discrepancy:** L-band (24 cm wavelength) penetrates vegetative canopies and exhibits significantly different surface dielectric scattering compared to Sentinel-1 C-band (5.6 cm). C-band and L-band features cannot be directly mixed or fed into C-band trained models.
2. **Dedicated NISAR Adapters:** New adapters (`NISARAdapter`) will define L-band physical bounds and separate model registry entries (`rf_jamuna_nisar_lband_v1`).
3. **Dual-Frequency Fusion:** Future architectures will support separate feature branches for C-band and L-band observations, evaluated through joint independent optical validation.

