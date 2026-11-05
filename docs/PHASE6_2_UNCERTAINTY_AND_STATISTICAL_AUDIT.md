# Earth Pulse — Phase 6.2: Displacement Uncertainty, Statistical Confidence & Final Scientific Readiness Audit

**Project:** NASA Space Apps Challenge 2026 — Dancing with the SARs  
**Study Area:** Jamuna River reach (Kazipur / Sirajganj, Bangladesh)  
**System:** Earth Pulse Fluvial Geomorphology & SAR Change Engine  
**Execution Environment:** Linux, Intel Core i7-1255U (10 Cores), 16 GB RAM, CPU-Only  
**Date:** November 2, 2026  
**Status:** **OPERATIONAL & SCIENTIFICALLY RECONCILED (219 / 219 TESTS PASSING)**

---

## 1. Executive Summary

Phase 6.2 completes the rigorous scientific uncertainty assessment, spatial statistical modeling, and operational readiness audit of the Earth Pulse riverbank migration and channel-margin displacement engine. Operating on multi-temporal Sentinel-1 C-band SAR observations (**June 10, 2024** pre-monsoon low flow vs. **July 16, 2024** flood-period observation) across the canonical **$1,010,039\text{ cell}$** study AOI ($404.0156\text{ km}^2$, EPSG:32645, $20.0\text{ m}$ spacing), Phase 6.2 replaces unverified assumptions and falsely precise single-value metrics with defensible physical and statistical models.

### Core Audit Milestones & Discoveries:
1. **Arithmetic & Epistemic Audit of Phase 6.1 Uncertainty Budget (Task A):**
   - Independent verification revealed an arithmetic calculation discrepancy: $\sqrt{14.14^2 + 4^2 + 20^2 + 10^2} = \mathbf{26.757\text{ m}}$, compared to the reported value of $26.96\text{ m}$ (discrepancy of $+0.203\text{ m}$).
   - The reported pixel discretization uncertainty ($14.14\text{ m} = \sqrt{10^2 + 10^2}$) committed an epistemic error by treating uniform distribution half-width bounds ($10\text{ m}$) as standard deviations ($1\sigma$). For a $20\text{ m}$ grid, true single-epoch uniform quantization standard deviation is $\sigma = 20 / \sqrt{12} \approx \mathbf{5.77\text{ m}}$, and two-epoch differential discretization standard deviation is $\sigma = 20 / \sqrt{6} \approx \mathbf{8.16\text{ m}}$.
   - Orbit and co-registration uncertainty ($4.00\text{ m}$) was unverified by local ground control points: both `ground_control_points.csv` files in the repository intermediate directories contain only empty template headers (0 measured points).
   - Mixed-pixel uncertainty ($20\text{ m}$) and pixel discretization are physically coupled, violating the assumption of mutual statistical independence in root-sum-square quadrature.
   - Transect angular offset ($10\text{ m}$) was incorrectly treated as an additive random Gaussian noise term, whereas it is a systematic geometric projection scale factor ($\Delta D / \cos\theta \le 6\%$ distortion).
2. **Defensible Displacement Uncertainty Models & Provisional Range (Task B):**
   - Displaced boundaries require explicit two-epoch differential propagation: $\sigma_{\Delta} = \sqrt{\sigma_1^2 + \sigma_2^2}$.
   - A single point-estimate Minimum Detectable Displacement ($\approx 50\text{ m}$) is replaced by a **Provisional Displacement Detection Threshold Range**:
     - **Optimistic / Consolidated Cut-Bank (Steep West Bank):** $\sigma_{\Delta} \approx 16.60\text{ m}$, Detection Threshold ($2\sigma$) $\approx \mathbf{35.0\text{ m}}$ ($1.75\text{ pixels}$).
     - **Central / Typical Bank (Braided Channel Margin):** $\sigma_{\Delta} \approx 29.86\text{ m}$, Detection Threshold ($2\sigma$) $\approx \mathbf{60.0\text{ m}}$ ($3.0\text{ pixels}$).
     - **Conservative / Low-Gradient Char Margin (Saturated Sandbars):** $\sigma_{\Delta} \approx 43.77\text{ m}$, Detection Threshold ($2\sigma$) $\approx \mathbf{85.0\text{ m}}$ ($4.25\text{ pixels}$).
3. **Reassessment of Bank Displacements & Spatial Block Bootstrap (Task C):**
   - Direct recalculation from the 122 audited `VALID_LOCAL_MIGRATION` transects confirms:
     - **Right Bank (West Bank / Mainland):** Median $= \mathbf{+40.00\text{ m}}$, Mean $= +130.00\text{ m}$, $\text{P90} = \mathbf{+440.00\text{ m}}$, $\text{P95} = +578.00\text{ m}$.
     - **Left Bank (East Bank / Chars):** Median $= \mathbf{+90.00\text{ m}}$, Mean $= +160.66\text{ m}$, $\text{P90} = \mathbf{+400.00\text{ m}}$, $\text{P95} = +539.00\text{ m}$.
     - **Channel Width Expansion:** Median $= \mathbf{+180.00\text{ m}}$, Mean $= +290.66\text{ m}$, $\text{P90} = +760.00\text{ m}$, $\text{P95} = +879.00\text{ m}$.
   - Spatial autocorrelation along the reach is high (lag-1 $r = 0.766$ on West, $0.728$ on East). To prevent false precision from pseudo-replication, a deterministic **Spatial Moving Block Bootstrap** ($N=2,000$ iterations, seed=42, block length = 6 transects / $1.2\text{ km}$) derived rigorous 95% confidence intervals:
     - Right Bank Median 95% CI: **$[+20.00, +80.00]\text{ m}$** (Bootstrap SE $= 19.17\text{ m}$).
     - Left Bank Median 95% CI: **$[+20.00, +150.00]\text{ m}$** (Bootstrap SE $= 35.73\text{ m}$).
     - Channel Width Expansion Median 95% CI: **$[+120.00, +320.00]\text{ m}$** (Bootstrap SE $= 52.82\text{ m}$).
   - Threshold Exceedance: At the central $60.0\text{ m}$ threshold, **$64.8\%$ of the West Bank transects fall within sensor noise**, confirming overall structural stability. Conversely, **$52.5\%$ of the East Bank transects exceed $60.0\text{ m}$** ($50.0\%$ exceed $85.0\text{ m}$), confirming statistically significant lateral expansion along the braided margin.
4. **Correction of Sampling Sensitivity Fallacy (Task D):**
   - The reported invariance of the median ($40.0\text{ m}$) across 100m, 200m, 500m, and 1000m spacings does **not** prove freedom from sampling artifacts. It merely reflects discrete raster grid quantization ($20\text{ m}$ multiples) and the 50% breakdown point of the sample median.
   - Coarse spacing ($1,000\text{ m}$) completely skipped the extreme northern boundary anomaly rows, artificially reducing the maximum displacement from $5,660\text{ m}$ to $4,420\text{ m}$.
5. **Causal Assertions & Standardized Terminology (Task E):**
   - Brahmaputra Right Embankment (BRE) attribution retained as **`UNVERIFIED_HYPOTHESIS`** (no local engineering GIS layers exist in the repository).
   - July 16 observation retained as **`FLOOD_PERIOD_OBSERVATION`** (unverified peak crest).
   - Standardized terminology strictly enforced: **Candidate Bank Expansion / Submergence**, **Apparent Channel Contraction**, and **Candidate Accretion**.
6. **Scientific Readiness Classifications (Task F):**
   - Scientific Demonstration: `READY_WITH_LIMITATIONS`.
   - Relative Channel-Margin Comparison: `READY_WITH_LIMITATIONS`.
   - Candidate Erosion/Accretion Mapping: `READY_WITH_LIMITATIONS`.
   - Quantitative Displacement Reporting: `READY_WITH_LIMITATIONS`.
   - Long-Term Geomorphic Erosion-Rate Estimation: **`BLOCKED`** (Strictly blocked: two-date 36-day flood rise cannot be annualized into decadal geomorphic erosion rates).

---

## 2. Task A — Audit of the Phase 6.1 Uncertainty Budget

### 2.1 Arithmetic Verification
The Phase 6.1 uncertainty table presented the combined root-mean-square (RMS) uncertainty as:
$$\text{Reported Combined Uncertainty} = 26.96\text{ m}$$
$$\text{Reported MDD (95\% Confidence, } k=2) = 53.92\text{ m}$$

Independent recalculation from the stated individual components:
$$\sqrt{14.14^2 + 4.00^2 + 20.00^2 + 10.00^2} = \sqrt{199.9396 + 16.0000 + 400.0000 + 100.0000} = \sqrt{715.9396} = \mathbf{26.757048\dots\text{ m}}$$
$$\text{Calculated MDD} = 2.0 \times 26.757048 = \mathbf{53.514095\dots\text{ m}}$$

**Discrepancy:**
- The reported RMS was overstated by **$+0.203\text{ m}$** ($26.96 - 26.757$).
- The reported MDD was overstated by **$+0.406\text{ m}$** ($53.92 - 53.514$).
This arithmetic flaw indicates that the values were hardcoded or manually transcribed rather than dynamically evaluated in code.

### 2.2 Detailed Epistemic Audit of Error Components

| Error Component | Reported Phase 6.1 | Provenance & Epistemic Basis | Uncertainty Measure | Dimensionality | Temporal Scope | Statistical Independence | Audit Evaluation & Scientific Critique |
| :--- | :---: | :--- | :--- | :---: | :---: | :---: | :--- |
| **Pixel Discretization** | 14.14 m | Mathematical Discretization | Claimed $1\sigma$; actually root-sum-square of half-widths | 1D along transect | Two-Epoch Combined ($\sqrt{10^2+10^2}$) | Coupled with mixed pixels | **FLAWED PROVENANCE:** Uniform distribution on $[-10, +10]\text{ m}$ has variance $\sigma^2 = \Delta^2/12 = 33.33\text{ m}^2$, giving $\sigma = 20/\sqrt{12} \approx 5.77\text{ m}$ single-epoch and $\sigma = 20/\sqrt{6} \approx 8.16\text{ m}$ two-epoch. The reported $14.14\text{ m}$ treated the half-width bound ($10\text{ m}$) as a standard deviation. |
| **Orbit & Co-Registration** | 4.00 m | Sentinel-1 POEORB Spec | Nominal literature $1\sigma$ proxy; unmeasured locally | 2D Radial | Single-Epoch proxy applied to Two-Epoch | Independent of speckle | **UNVERIFIED BY LOCAL GCPS:** Both `ground_control_points.csv` in `data/intermediate/` are empty template headers (0 measured points). In Phase 1, raw origin offset was $7.39\text{ m}$ ($\Delta X = 7.26\text{ m}, \Delta Y = 1.37\text{ m}$), harmonized via GDAL bilinear resampling. Residual cross-scene distortion is unmeasured. |
| **Water Edge Mixels & Speckle** | 20.00 m | Heuristic Estimate | Equivalent to $1.0\text{ pixel}$ nominal edge uncertainty | 1D cross-bank | Single-Epoch edge uncertainty | NOT INDEPENDENT | **COUPLING & STAGE SENSITIVITY:** Mixed pixels exist because of finite pixel resolution. Adding them in quadrature with discretization double-counts the spatial sampling limit. Furthermore, on low-gradient eastern chars, rising flood stage shifts waterlines across 20–40 m of saturated sandbars. |
| **Centerline Smoothing & Angle** | 10.00 m | Centerline Smoothing | Heuristic additive term (misclassified) | Angular projection offset | Static Transect Geometry | Systematic scale factor | **METHODOLOGICAL MISCLASSIFICATION:** Angular offset is a systematic geometric projection factor ($\Delta D_{\text{meas}} = \Delta D_{\text{true}}/\cos\theta$), NOT an additive zero-mean Gaussian random noise variable. For reach angles $\theta \le 20^\circ$, projection distortion is $< 6\%$ of displacement magnitude. |
| **Combined Uncertainty (RMS)** | 26.96 m | Root-Sum-Square Combination | Claimed combined standard uncertainty | Composite | Mixed single & two-epoch | Falsely assumes mutual independence | **ARITHMETIC DISCREPANCY:** True quadratic sum is $26.757\text{ m}$. Combines single-epoch and two-epoch terms without mathematical justification. |
| **Minimum Detectable Displacement** | 53.92 m | $k=2.0$ Multiplier on RMS | Claimed 95% confidence detection threshold | Composite | Two-Epoch threshold | Dependent on assumptions | **FALSELY PRECISE SINGLE VALUE:** A single MDD of $\approx 50\text{ m}$ ignores variable bank geomorphology. A defensible provisional range ($35\text{--}85\text{ m}$) is required. |

### 2.3 Single-Epoch vs. Two-Epoch vs. Minimum Detectable Displacement
To establish scientific clarity, three distinct uncertainty concepts must be separated:
1. **Single-Epoch Boundary-Location Uncertainty ($\sigma_b$):** The standard error in digitizing the physical waterline on a single date $t$:
   $$\sigma_b = \sqrt{\sigma_{\text{quant, single}}^2 + \sigma_{\text{coreg, single}}^2 + \sigma_{\text{edge, single}}^2}$$
2. **Two-Epoch Boundary-Displacement Uncertainty ($\sigma_{\Delta}$):** The uncertainty in the displacement $\Delta D = x_{t2} - x_{t1}$ between two independent acquisitions:
   $$\sigma_{\Delta}^2 = \sigma_{b1}^2 + \sigma_{b2}^2 - 2 \rho_{12} \sigma_{b1} \sigma_{b2}$$
   Assuming independent image acquisitions ($\rho_{12} \approx 0$) and comparable edge conditions ($\sigma_{b1} \approx \sigma_{b2} = \sigma_b$):
   $$\sigma_{\Delta} = \sqrt{2} \, \sigma_b$$
   Phase 6.1 incorrectly applied single-epoch estimates directly to the two-epoch displacement without the $\sqrt{2}$ multiplier.
3. **Minimum Detectable Displacement (MDD):** The critical decision threshold in two-tailed statistical hypothesis testing ($H_0: \Delta D = 0$ vs. $H_1: \Delta D \neq 0$) at significance level $\alpha = 0.05$ ($z_{1-\alpha/2} = 1.960$):
   $$\text{MDD}_{95\%} = 1.960 \times \sigma_{\Delta} \quad (\text{or } 2.0 \times \sigma_{\Delta})$$

---

## 3. Task B — Defensible Displacement Uncertainty Model

Because measured ground control point residuals are unavailable locally, presenting a single falsely precise MDD violates scientific software auditing standards. Instead, Phase 6.2 formulates three geomorphologically grounded models spanning the physical conditions across the Jamuna reach:

### Table 1: Defensible Two-Epoch Displacement Uncertainty Models

| Operational Model | Surface Geomorphology & Sensor Conditions | Component Uncertainties (Two-Epoch) | Total $\sigma_{\Delta}$ | Nominal Threshold ($k=1.96$) | Nominal Threshold ($k=2.0$) | Operational Threshold |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **Optimistic Model** | Steep, consolidated western cut-bank; high backscatter contrast; POEORB orbit alignment. | $\sigma_{\text{quant}} = 8.16\text{ m}$<br>$\sigma_{\text{coreg}} = 3.00\text{ m}$<br>$\sigma_{\text{edge}} = 14.14\text{ m}$ ($\pm 0.5\text{ px/date}$) | **$16.60\text{ m}$** | $32.54\text{ m}$ | $33.21\text{ m}$ | **$\approx 35.0\text{ m}$** ($1.75\text{ px}$) |
| **Central / Typical Model** | Typical braided channel margin; standard land-water mixed-pixel boundary; minor backscatter ambiguity. | $\sigma_{\text{quant}} = 8.16\text{ m}$<br>$\sigma_{\text{coreg}} = 5.00\text{ m}$<br>$\sigma_{\text{edge}} = 28.28\text{ m}$ ($\pm 1.0\text{ px/date}$) | **$29.86\text{ m}$** | $58.53\text{ m}$ | $59.72\text{ m}$ | **$\approx 60.0\text{ m}$** ($3.00\text{ px}$) |
| **Conservative Model** | Low-gradient char margin; saturated sandbar fringe; active stage-induced boundary migration. | $\sigma_{\text{quant}} = 8.16\text{ m}$<br>$\sigma_{\text{coreg}} = 7.00\text{ m}$<br>$\sigma_{\text{edge}} = 42.43\text{ m}$ ($\pm 1.5\text{ px/date}$) | **$43.77\text{ m}$** | $85.79\text{ m}$ | $87.54\text{ m}$ | **$\approx 85.0\text{ m}$** ($4.25\text{ px}$) |

**Provisional Displacement Detection Threshold Range:**
$$\text{Detection Threshold Range} = \mathbf{35.0\text{ m to } 85.0\text{ m}} \quad (1.75\text{ to } 4.25\text{ raster pixels})$$
- Lateral movements $< 35.0\text{ m}$ must be considered within sensor discretization noise across all bank environments.
- Lateral movements between $35.0\text{ m}$ and $60.0\text{ m}$ represent candidate changes that are statistically reliable only on steep consolidated banks.
- Lateral movements $\ge 60.0\text{ m}$ represent statistically significant channel-margin displacements under typical riverbank conditions.
- On low-gradient char margins, displacements below $85.0\text{ m}$ cannot be disentangled from stage-induced sandbar submergence.

---

## 4. Task C — Reassessment of West and East Bank Displacements

### 4.1 Empirical Distribution of the 122 Valid Local Migration Transects
Direct recalculation from the 122 audited `VALID_LOCAL_MIGRATION` transects yields the following verified sample statistics:

### Table 2: Verified Empirical Transect Displacement Statistics ($n=122$)

| Feature / Margin | Transects | Mean (m) | Median (m) | Std Dev (m) | Min (m) | Max (m) | P10 (m) | P25 (m) | P75 (m) | P90 (m) | P95 (m) | IQR (m) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Right Bank (West / Mainland)** | **122** | **+130.00** | **+40.00** | 200.83 | -120.00 | +820.00 | 0.00 | 0.00 | +200.00 | **+440.00** | **+578.00** | 200.00 |
| **Left Bank (East / Chars)** | **122** | **+160.66** | **+90.00** | 209.95 | -20.00 | +960.00 | 0.00 | 0.00 | +275.00 | **+400.00** | **+539.00** | 275.00 |
| **Channel Width Expansion** | **122** | **+290.66** | **+180.00** | 286.68 | -60.00 | +1100.00 | 0.00 | +60.00 | +420.00 | **+760.00** | **+879.00** | 360.00 |

*Note on Percentile Clarification:* In the Phase 6.1 text, P90 was cited as $+500.0\text{ m}$ (Right) and $+848.0\text{ m}$ (Left). Direct evaluation confirms the exact empirical sample 90th percentiles are **$+440.00\text{ m}$** for the Right Bank and **$+400.00\text{ m}$** for the Left Bank.

### 4.2 Threshold Exceedance Assessment

### Table 3: Transect Detection Threshold Exceedance ($n=122$)

| Threshold Level | Target Feature | Exceeding Count | % Exceeding | Sub-Threshold Count | % Sub-Threshold | Scientific Status & Physical Interpretation |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **35.0 m** *(Optimistic, 1.75 px)* | Right Bank (West) | 68 | 55.74% | 54 | 44.26% | Detectable only under steep consolidated cut-bank assumptions. |
|  | Left Bank (East) | 75 | 61.48% | 47 | 38.52% | Detectable expansion along majority of reach. |
|  | Channel Width Expansion | 106 | 86.89% | 16 | 13.11% | Channel widened along 86.9% of valid reach. |
| **50.0 m** *(Legacy Baseline, 2.5 px)*| Right Bank (West) | 52 | 42.62% | 70 | 57.38% | **57.4% of West Bank is indistinguishable from sensor noise.** |
|  | Left Bank (East) | 69 | 56.56% | 53 | 43.44% | 56.6% exceeds legacy nominal threshold. |
|  | Channel Width Expansion | 100 | 81.97% | 22 | 18.03% | 82.0% widened beyond nominal sensor noise. |
| **60.0 m** *(Central Realistic, 3.0 px)*| Right Bank (West) | 43 | 35.25% | 79 | 64.75% | **64.8% of West Bank is indistinguishable from sensor noise.** |
|  | Left Bank (East) | 64 | 52.46% | 58 | 47.54% | **52.5% of East Bank displays statistically significant expansion.** |
|  | Channel Width Expansion | 90 | 73.77% | 32 | 26.23% | 73.8% widened beyond central realistic threshold. |
| **85.0 m** *(Conservative, 4.25 px)*| Right Bank (West) | 38 | 31.15% | 84 | 68.85% | 68.8% falls below conservative noise ceiling. |
|  | Left Bank (East) | 61 | 50.00% | 61 | 50.00% | Exactly 50.0% of East Bank exceeds conservative threshold. |
|  | Channel Width Expansion | 85 | 69.67% | 37 | 30.33% | 69.7% widened beyond conservative noise ceiling. |

### 4.3 Spatial Autocorrelation & Moving Block Bootstrap Confidence Intervals
Spatial autocorrelation analysis along the stream centerline demonstrated that adjacent transects are strongly coupled:
- **Right Bank Lag-1 Autocorrelation ($200\text{ m}$):** $r = 0.766$ (remains $> 0.50$ out to $1,000\text{ m}$).
- **Left Bank Lag-1 Autocorrelation ($200\text{ m}$):** $r = 0.728$.
- **Channel Width Expansion Lag-1 Autocorrelation ($200\text{ m}$):** $r = 0.767$.

Because adjacent transects share high mutual information, treating them as independent degrees of freedom artificially shrinks standard errors (pseudo-replication). To account for this, a **Spatial Moving Block Bootstrap** was implemented ($N = 2,000$ iterations, block size = 6 transects / $1.2\text{ km}$, deterministic random seed = 42).

### Table 4: Spatial Moving Block Bootstrap Confidence Intervals ($N=2000$, Block=1.2 km, Seed=42)

| Feature / Margin | Parameter | Sample Point Estimate | Bootstrap Mean | Bootstrap Std Error | 95% Bootstrap CI Lower | 95% Bootstrap CI Upper |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Right Bank (West)** | **Median Displacement** | **+40.00 m** | +34.69 m | $\pm 19.17\text{ m}$ | **+20.00 m** | **+80.00 m** |
|  | Mean Displacement | +130.00 m | +126.18 m | $\pm 36.97\text{ m}$ | +59.83 m | +203.28 m |
|  | 90th Percentile (P90) | +440.00 m | +434.60 m | $\pm 103.59\text{ m}$ | +189.95 m | +598.00 m |
|  | 95th Percentile (P95) | +578.00 m | +551.90 m | $\pm 88.82\text{ m}$ | +398.95 m | +700.00 m |
| **Left Bank (East)** | **Median Displacement** | **+90.00 m** | +83.85 m | $\pm 35.73\text{ m}$ | **+20.00 m** | **+150.00 m** |
|  | Mean Displacement | +160.66 m | +157.67 m | $\pm 30.76\text{ m}$ | +101.96 m | +222.80 m |
|  | 90th Percentile (P90) | +400.00 m | +415.66 m | $\pm 93.23\text{ m}$ | +280.00 m | +540.00 m |
|  | 95th Percentile (P95) | +539.00 m | +589.07 m | $\pm 178.21\text{ m}$ | +360.00 m | +860.00 m |
| **Channel Width** | **Median Expansion** | **+180.00 m** | +199.06 m | $\pm 52.82\text{ m}$ | **+120.00 m** | **+320.00 m** |
|  | Mean Expansion | +290.66 m | +283.85 m | $\pm 47.28\text{ m}$ | +194.42 m | +378.04 m |
|  | 90th Percentile (P90) | +760.00 m | +692.11 m | $\pm 127.80\text{ m}$ | +420.00 m | +880.00 m |
|  | 95th Percentile (P95) | +879.00 m | +842.93 m | $\pm 113.80\text{ m}$ | +540.00 m | +1060.00 m |

---

## 5. Task D — Audit of the Sampling Sensitivity Conclusion

Phase 6 executed a transect spacing sensitivity experiment comparing $100\text{ m}$ (307 transects), $200\text{ m}$ (154 transects), $500\text{ m}$ (62 transects), and $1,000\text{ m}$ (31 transects). The Phase 6 report concluded:
> *"The median Right Bank displacement remained stable at exactly 40.00 m across all four scales, confirming structural stability and proving measurements are free from sampling artifacts."*

### Scientific Correction & Critical Findings:
1. **Mathematical Artifact vs. Physical Reality:** The stability of the sample median at $+40.0\text{ m}$ does **not** prove that measurements are free from sampling artifacts. Because the raster spacing is $20.0\text{ m}$, lateral boundary movements occur in discrete integer increments ($0, 20, 40, 60\text{ m}$). Across the central $20\text{ km}$ of the reach, more than $50\%$ of transects sampled sections with a $40\text{ m}$ shift. Because the sample median has a breakdown point of $50\%$, its value remained $40.0\text{ m}$ purely as a mathematical property of rank order, regardless of sampling density.
2. **Inclusion of Unfiltered Boundary Artifacts:** The sensitivity test was executed on **raw, unfiltered transects**. It included the northern boundary entry asymmetry ($5,660\text{ m}$) and secondary anabranch activations ($3,580\text{ m}$) indiscriminately.
3. **Severe Spatial Aliasing at Coarse Spacing:** At $1,000\text{ m}$ spacing (31 transects), the coarse sampling grid completely stepped over and missed the northernmost scanlines where the peak boundary artifact occurred. As a result, the maximum right bank displacement artificially dropped from $5,660\text{ m}$ to $4,420\text{ m}$, and maximum channel expansion dropped from $6,700\text{ m}$ to $5,480\text{ m}$.
4. **Omission of Localized Failure Nodes:** In braided rivers, cut-bank failure nodes typically span along-stream lengths of $100\text{--}300\text{ m}$. Spacings of $500\text{ m}$ and $1,000\text{ m}$ completely skip these embayments.
5. **Conclusion:** Sampling density strongly affects the detection of extreme events, reach-level mean displacements, and channel branch intersections. The $200\text{ m}$ interval remains the recommended operational baseline, but its outputs must be interpreted with explicit confidence filtering.

---

## 6. Task E — Causal Claim & Terminology Reassessment

All project documentation, maps, metadata, and reports must enforce the following scientific standards:

1. **Standardized Morphological Terminology:**
   - **Candidate Bank Expansion / Submergence:** Replaces "bank erosion". A single-event radar comparison convolves stage-induced submergence of low-gradient bank profiles with cut-bank scour.
   - **Candidate Char Submergence:** Replaces "char scour". Low sandbars are drowned as stage rises by $>2.5\text{ m}$.
   - **Apparent Channel Contraction:** Replaces "permanent accretion/sedimentation".
   - **Disconnected Floodplain Inundation:** Identifies water bodies situated outside the active channel belt.
2. **Brahmaputra Right Embankment (BRE):**
   - Retained strictly as **`UNVERIFIED_HYPOTHESIS`**. While the stability of the West Bank (median $40\text{ m}$, with $64.8\%$ below noise) is physically consistent with bank protection, no engineering GIS layers, revetment surveys, or maintenance records exist in the repository.
3. **July 16 Flood Observation:**
   - Designated strictly as **`FLOOD_PERIOD_OBSERVATION`**. Continuous daily hydrograph records (FFWC/BWDB) are unverified locally; therefore, July 16 cannot be confirmed as the seasonal flood crest.

---

## 7. Task F — Final Scientific Readiness Assessment

### Table 5: Scientific Readiness Assessment across Core Use Cases

| Use Case ID | Application Domain | Readiness Status | Operational Scope & Conditions | Prohibited Actions & Strict Constraints |
| :---: | :--- | :---: | :--- | :--- |
| **UC-01** | **Scientific Project Demonstration** | **`READY_WITH_LIMITATIONS`** | Proof-of-concept demonstrating automated SAR flood inundation, active contour thresholding, and transect mechanics for NASA Space Apps Challenge. Must include explicit uncertainty range ($35\text{--}85\text{ m}$). | Do not claim operational flood control decision readiness or cadastral precision. |
| **UC-02** | **Relative Channel-Margin Comparison** | **`READY_WITH_LIMITATIONS`** | Comparing macro-scale asymmetry between western consolidated bank (median $40\text{ m}$) and eastern braided margin (median $90\text{ m}$). Local differences must exceed $60\text{ m}$. | Do not attribute west bank stability to the BRE without engineering GIS datasets. |
| **UC-03** | **Candidate Erosion / Accretion Mapping** | **`READY_WITH_LIMITATIONS`** | Spatial screening and hazard zonal mapping to identify candidate reach segments experiencing rapid channel-margin expansion or char submergence. | Do not claim confirmed permanent cut-bank land loss without stage normalization and high-resolution optical/LiDAR ground truthing. |
| **UC-04** | **Quantitative Displacement Reporting** | **`READY_WITH_LIMITATIONS`** | Reporting numerical lateral boundary shifts along vetted transects. Restricted strictly to the 122 `VALID_LOCAL_MIGRATION` transects. Displacements $<50\text{--}60\text{ m}$ must be noted as within sensor noise. | Do not report unfiltered displacements from the 32 ambiguous transects. Do not claim statistical significance solely because displacement exceeds a nominal threshold. |
| **UC-05** | **Long-Term Geomorphic Erosion-Rate Estimation** | **`BLOCKED`** | Estimating annualized or multi-year riverbank erosion rates ($\text{m/year}$) or decadal sediment transport budgets. | **STRICTLY BLOCKED:** Only two acquisition dates spanning a 36-day seasonal flood rise are available. Extrapolating a 36-day flood rise into annual erosion rates violates fundamental fluvial geomorphology. |

---

## 8. Deliverables Inventory

```
EarthPulse-SAR/
├── data/
│   ├── outputs/phase6_2/statistics/
│   │   ├── phase6_2_uncertainty_budget.csv                  (3,245 bytes, comprehensive component audit & models)
│   │   ├── phase6_2_bank_displacement_statistics.csv        (896 bytes, verified sample distribution & percentiles)
│   │   ├── phase6_2_spatial_bootstrap_intervals.csv         (1,420 bytes, moving block bootstrap standard errors & CIs)
│   │   ├── phase6_2_detection_threshold_assessment.csv      (1,950 bytes, exceedance across 35m, 50m, 60m, 85m thresholds)
│   │   ├── phase6_2_sampling_sensitivity_audit.csv          (1,820 bytes, audit of 100m, 200m, 500m, 1000m spacings)
│   │   └── phase6_2_scientific_readiness.csv                (2,640 bytes, readiness verdicts across 5 use cases)
│   └── metadata/
│       ├── phase6_2_uncertainty_audit.json                  (master Phase 6.2 JSON metadata report)
│       └── earth_pulse_project_state.json                   (updated master repository state & roadmap)
├── scripts/
│   └── run_phase6_2_audit.py                                (executable master Phase 6.2 processing pipeline)
├── tests/
│   └── test_phase6_2_uncertainty.py                         (comprehensive automated unit test suite)
└── docs/
    ├── PHASE6_2_UNCERTAINTY_AND_STATISTICAL_AUDIT.md        (this comprehensive scientific audit report)
    └── EARTH_PULSE_PROJECT_HANDOFF_2026-11-02_PHASE6_2.md    (master project handoff document)
```

---

## 9. Verification & Automated Testing

All Phase 6.2 algorithms, statistical models, and threshold calculations are fully automated and verified via pytest.
```bash
cd EarthPulse-SAR
python3 -m pytest -q tests/
```
Phase 6.2 is complete, reproducible, and provides the rigorous scientific foundation required for Phase 7 (Random Forest & Explainable AI).

