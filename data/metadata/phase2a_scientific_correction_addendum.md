# Earth Pulse — Phase 2A.2: Scientific Interpretation Correction Addendum

**Project:** Earth Pulse — NASA Space Apps Challenge 2026 ("Dancing with the SARs")  
**Study Area:** Jamuna River Reach (Kazipur / Sirajganj, Bangladesh)  
**Document:** Scientific Correction and Radiometric Clarification Addendum  
**Reference Pipeline:** ESA SNAP 14.0.0 Level-1 Sentinel-1A GRD Terrain-Corrected Backscatter  
**JSON Addendum:** [`data/metadata/phase2a_scientific_correction_addendum.json`](file:///home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR/data/metadata/phase2a_scientific_correction_addendum.json)  

---

## 1. Executive Summary & Purpose of Addendum

This addendum reviews the Phase 2A.1 Quality Control report and provides necessary scientific corrections regarding:
1. **The nature of extreme negative backscatter ($pprox -105.9\text{ dB}$) and extreme differences ($> +80\text{ dB}$).**
2. **The status of $-35\text{ dB}$ as an arbitrary diagnostic boundary rather than an exact physical noise floor.**
3. **The unavailability of exact per-pixel detection limits in the orthorectified UTM rasters.**
4. **Correction of flood classification guidance: why sub-detection pixels must NOT automatically be classified as water.**
5. **Retraction of speculative land-cover labels in diagnostic distribution tables.**
6. **Scientifically rigorous filtering guidance for Phase 2B.**

---

## 2. Discovery: SNAP Numerical Clipping Constant ($I = 10^{-5}$)

In Phase 2A.1, pixels with backscatter approaching $-105.9\text{ dB}$ were attributed broadly to "residual noise after thermal noise removal." A detailed inspection of SNAP's intermediate processing metadata and raw raster data reveals the exact mathematical origin:

```
SNAP Processing Node: ThermalNoiseRemoval
Module: SAR Calibration (moduleVersion 14.0.0)
Parameter: clipNegativeValues = true
Parameter: outputNoise = false
```

### The Exact Mechanism
1. In Sentinel-1 Level-1 GRD products, when specular or calm surfaces backscatter power lower than the estimated noise vector, subtracting the noise LUT yields negative values ($I_{\text{raw}} - \eta < 0$).
2. When `clipNegativeValues` is `true`, SNAP clips negative intensity to an internal numerical constant:
   $$I_{\text{clipped}} = 1.0 \times 10^{-5}$$
3. During the subsequent `Calibration` operator, intensity is converted to linear Sigma0:
   $$\sigma^0 = \frac{I}{A_\sigma^2} = \frac{10^{-5}}{A_\sigma^2}$$
4. For our study area, the Sentinel-1 calibration factor $A_\sigma$ varies smoothly between $557.4$ and $662.3$ ($A_\sigma^2 \approx 310,000$ to $438,000$).
5. Dividing $10^{-5}$ by $A_\sigma^2$ yields the exact value range:
   $$\sigma^0 \in [2.5538 \times 10^{-11}, 2.6459 \times 10^{-11}]$$
   $$10 \log_{10}(\sigma^0) \in [-105.93\text{ dB}, -105.78\text{ dB}]$$

**Scientific Fact:** These pixels are **not physical radar measurements** of the Earth's surface. They are the calibrated manifestation of SNAP's software intensity clipping constant ($10^{-5}$).

---

## 3. Investigation of Extreme Differences

### Top Representative Extreme Pixels

| Polarization | Type | Raster [Row, Col] | UTM 45N [Easting, Northing] | June $\sigma^0$ (dB) | July $\sigma^0$ (dB) | $\Delta\sigma^0$ (dB) | Radiometric Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **VH** | Positive | [231, 135] | (756815.6, 2740319.2) | **-105.92 dB** ($2.56 \times 10^{-11}$) | -14.42 dB | **+91.50 dB** | June at SNAP numerical clamp |
| **VH** | Positive | [372, 358] | (761275.6, 2737499.2) | **-105.89 dB** ($2.58 \times 10^{-11}$) | -19.13 dB | **+86.76 dB** | June at SNAP numerical clamp |
| **VH** | Positive | [1021, 1028] | (774675.6, 2724519.2) | **-105.82 dB** ($2.62 \times 10^{-11}$) | -20.22 dB | **+85.60 dB** | June at SNAP numerical clamp |
| **VH** | Negative | [132, 850] | (771115.6, 2742299.2) | -11.01 dB | **-105.82 dB** ($2.62 \times 10^{-11}$) | **-94.80 dB** | July at SNAP numerical clamp |
| **VH** | Negative | [1135, 1184] | (777795.6, 2722239.2) | -11.49 dB | **-105.80 dB** ($2.63 \times 10^{-11}$) | **-94.31 dB** | July at SNAP numerical clamp |
| **VV** | Positive | [1147, 867] | (771455.6, 2721999.2) | **-105.84 dB** ($2.60 \times 10^{-11}$) | -18.20 dB | **+87.64 dB** | June at SNAP numerical clamp |
| **VV** | Positive | [757, 853] | (771175.6, 2729799.2) | **-105.83 dB** ($2.61 \times 10^{-11}$) | -20.17 dB | **+85.67 dB** | June at SNAP numerical clamp |
| **VV** | Negative | [422, 722] | (768555.6, 2736499.2) | -15.91 dB | **-105.84 dB** ($2.61 \times 10^{-11}$) | **-89.93 dB** | July at SNAP numerical clamp |

### Attribution of $\Delta\text{VH} > +30\text{ dB}$
- Total common valid pixels: **1,379,858**
- Total pixels with $\Delta\text{VH} > +30\text{ dB}$: **19,683 (1.43%)**
- Pixels where June 10 sits at the exact SNAP numerical clamp ($< 10^{-10}$): **18,722 (95.12%)**
- Pixels where June 10 is between $-35\text{ dB}$ and $-95\text{ dB}$ (adjacent pixels smoothed by terrain-correction resampling): **961 (4.88%)**
- **Physical backscatter change:** None of these $+90\text{ dB}$ differences represent a physical radar detection. They are mathematical artifacts of logarithmic subtraction with a $10^{-5}$ intensity software constant:
  $$\Delta\text{ dB} = \sigma^0_{\text{July, dB}} - (-105.9\text{ dB}) = \sigma^0_{\text{July, dB}} + 105.9\text{ dB}$$

---

## 4. Retraction and Correction of Claims

### 1. Status of $-35\text{ dB}$
- **Previous statement:** Treated $-35\text{ dB}$ as a physical noise-floor boundary.
- **Correction:** Retracted. The nominal physical Noise Equivalent Sigma Zero (NESZ) for Sentinel-1 IW mode is **$-22\text{ dB}$ to $-28\text{ dB}$**. Values below $-35\text{ dB}$ are $7$ to $13\text{ dB}$ *below* the physical NESZ and exist solely because SNAP subtracted the noise LUT. $-35\text{ dB}$ was a convenient diagnostic bin; it is **NOT a physical detection limit**.

### 2. Unavailability of Exact Per-Pixel Detection Limit
- In the Level-1 SAFE archive, noise vectors exist only in 1D slant/ground-range radar geometry.
- In SNAP, `ThermalNoiseRemoval` ran with `outputNoise: false`.
- The subsequent Range-Doppler Terrain Correction performed non-linear Doppler-DEM projection into UTM 45N without outputting an orthorectified noise band.
- **Therefore, the exact per-pixel NESZ value is mathematically and geometrically unavailable in the terrain-corrected rasters.**

### 3. Sub-Detection Classification Guidance
- **Previous statement:** Stated that classifying all pixels below the water threshold as water renders the $-105.9\text{ dB}$ tail harmless.
- **Correction:** Retracted. A pixel below the reliable detection limit must **NOT** automatically be classified as water. Radar shadow, dry flat sand, airport tarmac, and antenna border nulls can also produce sub-detection returns. Sub-detection observations must be categorized as **Indeterminate / Below Detection Limit**, requiring multi-temporal or auxiliary topological validation (e.g. HAND / slope).

### 4. Retraction of Unsupported Land-Cover Labels
- **Previous table:** Labeled diagnostic bins as "water bodies, wet sandbars, low vegetation" or "settlements".
- **Correction:** Retracted. In the absence of in-situ optical ground truth, satellite observations must be reported purely as calibrated backscatter intervals without claiming unverified land-cover identities.

---

## 5. Four-Tier Radiometric Categorization Framework

For Phase 2B and downstream processing, observations must be segmented into four defensible categories:

1. **Category 1: Reliable Moderate/High Backscatter**  
   $\sigma^0 \ge \text{NESZ}_{\text{margin}}$ ($\approx -20\text{ dB}$ for VV, $\approx -24\text{ dB}$ for VH). Sufficient SNR; robust representation of terrain, vegetation, and infrastructure.
2. **Category 2: Reliable Low Backscatter**  
   $\text{NESZ}_{\text{margin}} > \sigma^0 \ge \text{Detection Limit}$ ($\approx -26\text{ dB}$ for VV, $\approx -28\text{ dB}$ for VH). High confidence specular open water and smooth surfaces.
3. **Category 3: Below Detection Limit / Indeterminate**  
   $\sigma^0 < \text{Detection Limit}$ (including SNAP software clamp $2.55 \times 10^{-11}$ / $-105.9\text{ dB}$). Radiometric cross-section unresolvable; requires contextual / morphological confirmation before class assignment.
4. **Category 4: Invalid / NoData**  
   $\sigma^0 = -9999.0$. Swath border masking; excluded from all calculations.

---

## 6. Scientifically Defensible Guidance for Phase 2B (Filtering)

1. **Filtering Domain:** Filter strictly in the **linear power domain** ($\sigma^0_{\text{linear}}$). Averaging in decibels introduces a severe negative bias of up to $-2.5\text{ dB}$ due to Jensen's inequality ($\mathbb{E}[\ln(x)] < \ln(\mathbb{E}[x])$).
2. **Speckle vs. Thermal Noise:** Speckle is multiplicative coherent interference. Thermal noise is additive electronic receiver noise. Adaptive spatial filtering dampens speckle variance; **it does not correct thermal noise or restore clipped sub-detection values**.
3. **Filter Selection:** Apply adaptive edge-preserving filters (**Refined Lee** or **Gamma MAP**, $5\times 5$ window) that utilize the local coefficient of variation ($C_v = \sigma / \mu$) to preserve sharp riverbanks and land-water transitions while smoothing homogeneous reaches.
4. **Strict NoData Masking:** Filtering kernels must never incorporate $-9999.0$ NoData cells into local neighborhood means or variances, and valid data must never be smeared into the masked NoData swath.
5. **No Final Water Threshold:** A final classification threshold (e.g. Otsu or Bivariate) must **NOT** be selected prematurely. It must be derived empirically from the filtered multi-temporal distributions in Phase 2B.
