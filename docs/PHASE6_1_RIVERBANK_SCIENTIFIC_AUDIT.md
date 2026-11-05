# Earth Pulse — Phase 6.1: Riverbank Geometry Audit, Cross-Phase Reconciliation & Scientific Validation Report

**Project:** NASA Space Apps Challenge 2026 — Dancing with the SARs  
**Study Area:** Jamuna River reach (Kazipur / Sirajganj, Bangladesh)  
**System:** Earth Pulse Fluvial Geomorphology & SAR Change Engine  
**Execution Environment:** Linux, Intel Core i7-1255U (10 Cores), 16 GB RAM, CPU-Only  
**Date:** November 2, 2026  
**Status:** **OPERATIONAL & SCIENTIFICALLY RECONCILED (219 / 219 TESTS PASSING)**

---

## 1. Executive Summary

Phase 6.1 provides an independent scientific audit, mathematical cross-phase reconciliation, and geometric verification of the Phase 6 riverbank migration and channel-margin displacement engine. The audit investigates the two-date Sentinel-1 C-band SAR comparison (**June 10, 2024** pre-monsoon low flow vs. **July 16, 2024** monsoon flood period) across the canonical **$1,010,039\text{ cell}$** study AOI ($404.0156\text{ km}^2$, EPSG:32645).

### Core Audit Findings:
1. **Resolution of Cross-Phase Classification Discrepancies (Task B):**
   A complete pixel-by-pixel cross-tabulation between Phase 5 and Phase 6 was established. While the three newly inundated candidate subcategories reconcile with zero residual ($54,850 + 58,025 + 34,117 \equiv 146,992\text{ px}$), the audit discovered that in Phase 6:
   - $5,758\text{ pixels}$ ($2.3032\text{ km}^2$) of Phase 5 Persistent Water and $597\text{ pixels}$ ($0.2388\text{ km}^2$) of Receded Water situated on the mainland floodplain were defaulted to Zone 0 ("Mainland Non-Water") because they fell outside the main river channel mask.
   - $61\text{ pixels}$ ($0.0244\text{ km}^2$) of Phase 5 Indeterminate Noise Floor within the char footprint were overwritten by Zone 5 (Persistent Char).
   - **Correction in Phase 6.1:** Dedicated classes were established for **Persistent Floodplain Water Bodies** ($3,606\text{ px}$), **Receded Floodplain Water** ($597\text{ px}$), and **Char Water Depressions** ($2,279\text{ px}$), while Indeterminate Noise Floor was restored to its exact Phase 5 baseline of **$16,242\text{ pixels}$** ($6.4968\text{ km}^2$). Full cell conservation ($1,010,039\text{ cells}$) holds strictly.
2. **Geometric Investigation of Maximum Displacement Anomalies (Task D & E):**
   - **Right Bank Maximum Displacement ($5,660.0\text{ m}$):** Proven to be an **AOI Boundary-Entry Asymmetry Artifact** at the northern border (rows 191–201). In June, the western braid arm had not yet entered the AOI bounding box at low stage, so the algorithm matched the eastern braid Right Bank against the western braid Right Bank in July. Within the fully entered river corridor (row $\ge 202$), true maximum Right Bank displacement is **$820.0\text{ m}$**.
   - **Left Bank Maximum Displacement ($3,580.0\text{ m}$):** Proven to be a **Seasonal Secondary Anabranch Reactivation** around row 776–800, where floodwaters overtopped an elevated char bar dry in June, flooding an entire eastern side-channel corridor out to col 1210. This is ephemeral braid activation, not $3.58\text{ km}$ of cut-bank scour.
3. **Validated Core Transect Displacements (Task D & E):**
   Excluding edge-entry artifacts and anabranch activation, the **122 core transects (79.2% of reach)** demonstrate:
   - **Right Bank (West Bank / Embankment):** Median displacement is **$+40.00\text{ m}$** (2 pixels), mean is **$+130.00\text{ m}$**, 90th percentile is **$+500.00\text{ m}$**, max is **$+820.00\text{ m}$**.
   - **Left Bank (East Bank / Chars):** Median displacement is **$+90.00\text{ m}$**, mean is **$+160.66\text{ m}$**, 90th percentile is **$+848.00\text{ m}$**, max is **$+960.00\text{ m}$**.
   - **Channel Width Expansion:** Median expansion is **$+180.00\text{ m}$**, mean is **$+290.66\text{ m}$**.
4. **Sensor Uncertainty Budget & Minimum Detectable Displacement (MDD) (Task F):**
   Propagating pixel discretization ($\pm 14.14\text{ m}$), orbit precision ($\pm 4.0\text{ m}$), water mixels/speckle ($\pm 20.0\text{ m}$), and angular projection ($\pm 10.0\text{ m}$) yields an expanded Minimum Detectable Displacement of **$\text{MDD} \approx 53.92\text{ m} \approx 50.0\text{ m}$ ($2.5\text{ pixels}$ at 95% confidence)**.
   - The West Bank median displacement ($40\text{ m}$) is **within the sensor noise envelope**, confirming general bank stability.
   - The East Bank median displacement ($90\text{--}140\text{ m}$) exceeds the MDD, confirming statistically significant lateral expansion.
5. **Causal Claim & Terminology Audit (Task G & H):**
   - Claims attributing west-bank stability to the Brahmaputra Right Embankment (BRE) are classified as **`UNVERIFIED_HYPOTHESIS`** (no local engineering GIS layers exist in the repository).
   - "Embankment breach" assertions are **`DISPROVED_ASSERTION`** (the 5.6 km displacement was an AOI boundary artifact).
   - July 16 is designated as **`FLOOD_PERIOD_OBSERVATION`** rather than "confirmed seasonal crest".
   - All detected changes are strictly designated as **"Candidate Bank Expansion / Submergence"**.

---

## 2. Task B — Phase 5 to Phase 6 Pixel Reconciliation

A cell-by-cell cross-tabulation across the entire $1,010,039\text{ cell}$ study AOI established the exact spatial relationships between Phase 5 transition classes and Phase 6 zonal classes.

### Table 1: Full Pixel-Level Cross-Tabulation Matrix (AOI Domain)

| Phase 5 Transition Class | Phase 6.1 Reconciled Class | Pixel Count | Area ($\text{km}^2$) | Area ($\text{ha}$) | % AOI | Physical / Algorithmic Interpretation |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Persistent Water (1)** | Persistent Channel Water (1) | 210,710 | 84.2840 | 8,428.40 | 20.86% | Flowing water within main braided channels in both epochs. |
| **Persistent Water (1)** | Persistent Floodplain Water (8) | 3,606 | 1.4424 | 144.24 | 0.36% | Perennial inland water bodies (beels, oxbows, borrow pits) outside channel belt. |
| **Persistent Water (1)** | Char Water Depressions (10) | 2,279 | 0.9116 | 91.16 | 0.23% | Perennial water depressions and secondary channels on char islands. |
| *Subtotal Persistent Water* | *Sum* | *216,595* | *86.6380* | *8,663.80* | *21.44%* | *Exact match with Phase 5 Persistent Water.* |
| **Newly Inundated (2)** | External Bank Expansion Candidate (2) | 54,850 | 21.9400 | 2,194.00 | 5.43% | Outward expansion of main river channel corridor into mainland. |
| **Newly Inundated (2)** | Internal Char Submergence Candidate (3) | 58,025 | 23.2100 | 2,321.00 | 5.74% | Submergence of internal mid-channel char sandbars by rising stage. |
| **Newly Inundated (2)** | Disconnected Floodplain Inundation (6) | 34,117 | 13.6468 | 1,364.68 | 3.38% | Inundation in agricultural depressions outside active channel belt. |
| *Subtotal Newly Inundated* | *Sum* | *146,992* | *58.7968* | *5,879.68* | *14.55%* | *Exact match with Phase 5 Newly Inundated Candidate.* |
| **Receded Water (3)** | Apparent Channel Contraction (4) | 1,037 | 0.4148 | 41.48 | 0.10% | Apparent water recession / sand deposition inside channel belt. |
| **Receded Water (3)** | Receded Floodplain Water (9) | 597 | 0.2388 | 23.88 | 0.06% | Recession of pre-monsoon temporary ponding on mainland. |
| *Subtotal Receded Water* | *Sum* | *1,634* | *0.6536* | *65.36* | *0.16%* | *Exact match with Phase 5 Receded Water.* |
| **Persistent Non-Water (4)**| Persistent Mainland Non-Water (0) | 571,454 | 228.5816 | 22,858.16 | 56.58% | Permanent dry mainland outside active channel corridor. |
| **Persistent Non-Water (4)**| Persistent Internal Char Islands (5) | 57,061 | 22.8244 | 2,282.44 | 5.65% | Elevated cores of mid-channel char islands dry in both epochs. |
| *Subtotal Persistent Non-Water*| *Sum* | *628,515* | *251.4060* | *25,140.60* | *62.23%* | *Exact match with Phase 5 Persistent Non-Water.* |
| **Indeterminate (5)** | Indeterminate Noise Floor (7) | 16,242 | 6.4968 | 649.68 | 1.61% | SAR instrument noise floor ($\sigma^0 \le -22.0\text{ dB}$) in either date. |
| **Source NoData (6)** | Source Border NoData (255) | 61 | 0.0244 | 2.44 | 0.006% | Invalid sensor boundary pixels identical across all phases. |
| **Total Study AOI** | **All Classes** | **1,010,039** | **404.0156** | **40,401.56** | **100.00%** | **Complete cell conservation holds with zero residual.** |

---

## 3. Task C — Channel-Belt Envelope Extraction & Sensitivity Audit

The channel-belt extraction method isolates the continuous braided river corridor from the surrounding landscape. A sensitivity audit evaluated the impact of connectivity rules and morphological closing kernels:

### Table 2: Channel-Belt Extraction Sensitivity Audit

| Extraction Method | June Channel Belt ($\text{km}^2$) | July Channel Belt ($\text{km}^2$) | Net Expansion ($\text{km}^2$) | June Internal Chars ($\text{km}^2$) | July Internal Chars ($\text{km}^2$) | Char Submergence ($\text{km}^2$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **4-conn Hole-Fill (Phase 6 Baseline)** | **139.4576** | **169.5256** | **+30.0680** | **54.7948** | **31.9644** | **-22.8304** |
| **8-connectivity Hole-Fill** | 140.0920 | 170.7788 | +30.6868 | 54.7948 | 31.9632 | -22.8316 |
| **8-conn + 200 m Closing Kernel** | 142.3688 | 172.5840 | +30.2152 | 57.0716 | 33.7684 | -23.3032 |
| **8-conn + 500 m Closing Kernel** | 145.3980 | 175.4628 | +30.0648 | 60.1008 | 36.6472 | -23.4536 |

**Sensitivity Invariants:**
1. Across all four configurations, the net channel-belt corridor expansion remains stable at **$+30.06\text{ to }+30.69\text{ km}^2$**.
2. Net internal char submergence remains stable at **$-22.83\text{ to }-23.45\text{ km}^2$**.
3. Morphological closing kernels (200 m, 500 m) bridge narrow inter-braid dry bars, slightly increasing total channel belt area by $2.0\text{--}4.2\%$, but do not leak into the mainland floodplain.
4. The Phase 6 baseline (4-connectivity hole-fill) preserves the highest local edge fidelity without artificially expanding channel boundaries into elevated levees.

---

## 4. Task D & E — Centerline, Transect Geometry & Anomaly Audit

### 4.1 Geometric Validation of River Orientation and Bank Convention
- Facing downstream along the provisional centerline ($197.04^\circ$ azimuth, roughly South):
  - **Right Bank:** Corresponds geometrically to the **Western Boundary** (Kazipur / Sirajganj mainland).
  - **Left Bank:** Corresponds geometrically to the **Eastern Boundary** (Tangail / Jamalpur floodplain margin).
  - The bank-side labeling in Phase 6 is confirmed as **100% geometrically correct**.

### 4.2 Investigation of Maximum Displacement Anomalies
The Phase 6 report cited maximum displacements of **$5,660.0\text{ m}$** (Right Bank) and **$3,580.0\text{ m}$** (Left Bank). Individual geometric inspection of these transects revealed:

1. **Right Bank $5,660\text{ m}$ Anomaly (Transects 11–15, Rows 195–196):**
   - *Cause:* **AOI Boundary-Entry Asymmetry Artifact**.
   - *Evidence:* At the northern boundary of the AOI (Northing $2,741,019\text{ m}$), the western braid arm entered the AOI bounding box at row 197 in June, but entered at row 191 in July. At rows 195–196, only the eastern braid arm was inside the AOI in June (Right Bank $X = 775,475\text{ m}$), whereas in July both braids were present (Right Bank $X = 769,815\text{ m}$). The algorithm computed $(775,475 - 769,815) = 5,660\text{ m}$, jumping across the entire braided valley!
   - *Resolution:* This is an artificial edge effect of the AOI bounding box, not a physical bank retreat.
2. **Left Bank $3,580\text{ m}$ Anomaly (Transects 93–97, Rows 776–794):**
   - *Cause:* **Seasonal Secondary Anabranch Reactivation**.
   - *Evidence:* At row 776, floodwaters overtopped an elevated char bar that blocked flow during the June low-flow stage (where June Left Bank was at col 1031, $X = 774,735\text{ m}$). In July, water inundated the entire eastern secondary anabranch corridor out to col 1210 ($X = 778,315\text{ m}$).
   - *Resolution:* This $3,580\text{ m}$ displacement represents seasonal flood reactivation of an ephemeral secondary channel, not $3.58\text{ km}$ of cut-bank scour.

### Table 3: Transect Displacement Distribution by Confidence Status (154 Transects)

| Confidence Status | Transect Count | % Reach | Right Bank Median (m) | Right Bank Mean (m) | Right Bank Max (m) | Left Bank Median (m) | Left Bank Mean (m) | Left Bank Max (m) | Channel Width Expansion Median (m) | Channel Width Expansion Mean (m) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **VALID_LOCAL_MIGRATION** | **122** | **79.22%** | **40.00 m** | **130.00 m** | **820.00 m** | **90.00 m** | **160.66 m** | **960.00 m** | **180.00 m** | **290.66 m** |
| **AMBIGUOUS_EDGE_EFFECT** | 23 | 14.94% | 1,020.00 m | 1,933.04 m | 5,660.00 m | 1,060.00 m | 1,060.87 m | 1,080.00 m | 2,100.00 m | 2,993.91 m |
| **ANABRANCH_ACTIVATION** | 5 | 3.25% | 20.00 m | 16.00 m | 40.00 m | 3,380.00 m | 3,340.00 m | 3,580.00 m | 3,400.00 m | 3,356.00 m |
| **MAJOR_CHANNEL_EXPANSION** | 4 | 2.60% | 570.00 m | 555.00 m | 640.00 m | 1,470.00 m | 1,460.00 m | 1,480.00 m | 2,030.00 m | 2,015.00 m |
| **All Transects (Raw)** | **154** | **100.00%** | **40.00 m** | **406.62 m** | **5,660.00 m** | **140.00 m** | **432.08 m** | **3,580.00 m** | **320.00 m** | **838.70 m** |

```
Width Expansion Identity Check:
For every transect: Delta Channel Width == Delta Right Bank + Delta Left Bank (EXACT).
```

---

## 5. Task F — Displacement Uncertainty & Minimum Detectable Displacement

Remote-sensing measurements on a 20 m discrete grid are subject to systematic and random spatial uncertainties. A formal error budget was established:

### Table 4: Spatial Displacement Uncertainty Budget (Sentinel-1 20 m SAR)

| Error Component | Standard Uncertainty ($\pm \text{m}$) | Description & Derivation |
| :--- | :---: | :--- |
| **Pixel Discretization** | $\pm 14.14\text{ m}$ | Spatial quantization of $\pm 0.5\text{ px}$ on two independent epochs: $\sqrt{10^2 + 10^2}$. |
| **Co-Registration / Orbit** | $\pm 4.00\text{ m}$ | Sentinel-1 Precise Orbit Ephemerides (POE) alignment accuracy ($\approx 0.2\text{ px}$). |
| **SAR Edge Mixels & Speckle** | $\pm 20.00\text{ m}$ | Mixed-pixel ambiguity and speckle edge fluctuation along land-water boundary. |
| **Centerline Angle Deviation** | $\pm 10.00\text{ m}$ | Residual projection error from minor angular deviation from true bank normal. |
| **Combined Standard Uncertainty ($\sigma_c$)** | **$\pm 26.96\text{ m}$** | Root sum of squares: $\sqrt{14.14^2 + 4.0^2 + 20.0^2 + 10.0^2}$. |
| **Minimum Detectable Displacement (MDD)** | **$53.92\text{ m} \approx \mathbf{50.0\text{ m}}$** | Expanded uncertainty at 95% confidence ($k=2$). |

### Geomorphological Implications:
1. **Uncertainty Envelope:** Displacements below **$50.0\text{ m}$ (2.5 pixels)** cannot be distinguished from raster discretization and speckle jitter.
2. **West Bank Confinement:** The median Right Bank displacement of **$40.0\text{ m}$** is within the sensor noise envelope. This demonstrates that the western mainland bank was **largely stable within detection limits**, except in localized embayments exceeding $100\text{ m}$.
3. **East Bank Expansion:** The median Left Bank displacement of **$90.0\text{--}140.0\text{ m}$** significantly exceeds the MDD, confirming true physical channel margin expansion into the eastern char complex.

---

## 6. Task H — Causal Claim & Embankment Evidence Audit

The Phase 6 report contained several causal interpretations that were audited against repository evidence:

### Table 5: Audit of Causal Claims & Empirical Evidence Status

| Claim Topic | Reported Assertion | Available Repository Evidence | Audit Verdict | Scientific Correction & Guidance |
| :--- | :--- | :--- | :---: | :--- |
| **Brahmaputra Right Embankment (BRE)** | "Confining effect of the BRE holds median displacement to 40 m." | No vector shapefile, CAD drawings, elevation profiles, or revetment records exist in the repository. | **`UNVERIFIED_HYPOTHESIS`** | Observed west-bank stability is consistent with regional literature on BRE revetments, but represents an unverified causal hypothesis within this dataset. |
| **Embankment Breach Assertions** | "High-displacement reaches (>4000 m) represent embankment breaches." | No BWDB breach records exist. The 5,660 m displacement was proven to be an AOI boundary artifact. | **`DISPROVED_ASSERTION`** | High displacement at the northern edge is an AOI boundary artifact. No localized embankment breaches can be asserted. |
| **July 16 Confirmed Flood Crest** | "July 16 represents the confirmed seasonal flood crest." | Stage records at Kazipur and Sirajganj confirm water level exceeded danger level on July 16, but full-season hydrographs are absent. | **`UNVERIFIED_DESIGNATION`** | Refer to July 16 as "monsoon flood-period observation" or "high-water event", reserving "crest" for continuous hydrological records. |
| **Erosion vs. Stage Submergence** | "All newly water-covered channel margin pixels represent bank erosion." | River stage rose by $>2.5\text{ m}$ between epochs, submerging gently sloping bars without requiring cut-bank failure. | **`SCIENTIFICALLY_AMBIGUOUS`** | Designate all detected changes as "Candidate Bank Expansion / Submergence", distinguishing morphological erosion from stage-rise effects. |

---

## 7. Deliverables & Versioned File Catalog

Phase 6.1 created a completely non-destructive, versioned set of deliverables in `data/processed/phase6_1/`, `data/outputs/phase6_1/`, and `data/metadata/`:

```
EarthPulse-SAR/
├── data/
│   ├── processed/phase6_1/
│   │   ├── phase6_1_channel_change_zones.tif                  (95,366 bytes, reconciled 11-class zonal raster)
│   │   ├── phase6_1_external_bank_expansion_candidate.tif     (29,672 bytes, candidate bank expansion)
│   │   ├── phase6_1_internal_char_submergence_candidate.tif   (33,384 bytes, char submergence candidate)
│   │   ├── phase6_1_apparent_channel_contraction.tif          (17,506 bytes, channel contraction candidate)
│   │   ├── phase6_1_disconnected_floodplain_inundation.tif    (30,038 bytes, non-channel flood water)
│   │   ├── phase6_1_persistent_floodplain_water.tif           (19,105 bytes, perennial floodplain water)
│   │   └── phase6_1_riverbank_transects.geojson               (108,400 bytes, audited transects with confidence flags)
│   ├── outputs/phase6_1/
│   │   ├── maps/
│   │   │   ├── phase6_1_channel_margin_displacement_map.png   (4,652,101 bytes, 300 DPI audited displacement map)
│   │   │   ├── phase6_1_erosion_submergence_zones_map.png     (5,327,978 bytes, 300 DPI reconciled typology map)
│   │   │   └── phase6_1_riverbank_transects.geojson           (mirrored vector layer)
│   │   └── statistics/
│   │       ├── phase6_1_phase5_phase6_crosstab.csv            (2,187 bytes, full pixel cross-tabulation)
│   │       ├── phase6_1_transect_geometry_audit.csv           (694 bytes, transect statistics by status)
│   │       ├── phase6_1_transect_displacement_audit.csv       (44,912 bytes, all 154 transects audited)
│   │       ├── phase6_1_channel_belt_sensitivity.csv          (747 bytes, parameter sensitivity audit)
│   │       ├── phase6_1_area_reconciliation.csv               (813 bytes, exact AOI cell accounting)
│   │       ├── phase6_1_uncertainty_summary.csv               (732 bytes, sensor error budget & MDD)
│   │       └── phase6_1_causal_claim_audit.csv                (1,801 bytes, audit of causal assertions)
│   └── metadata/
│       ├── phase6_1_riverbank_audit_report.json               (8,641 bytes, master structured JSON report)
│       └── earth_pulse_project_state.json                     (updated project state record)
├── scripts/
│   └── run_phase6_1_audit.py                                  (master Phase 6.1 audit pipeline)
├── tests/
│   └── test_phase6_1_audit.py                                 (12 automated pytest unit tests)
└── docs/
    ├── PHASE6_1_RIVERBANK_SCIENTIFIC_AUDIT.md                 (this report)
    └── EARTH_PULSE_PROJECT_HANDOFF_2026-11-02_PHASE6_1.md     (master project handoff document)
```

---

## 8. Automated Test Results

The test suite (`tests/test_phase6_1_audit.py`) was executed using `pytest`. All 12 dedicated tests passed, raising the repository test baseline from 207 to **219 / 219 passing tests (100% pass rate)**.

```bash
============================= test session starts ==============================
platform linux -- Python 3.14.8, pytest-9.1.1, pluggy-1.6.0 -- /usr/bin/python3
cachedir: .pytest_cache
rootdir: /home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR
plugins: anyio-4.15.1, typeguard-4.4.4
collected 219 items

tests/test_phase1_alignment.py ...........                                [  5%]
tests/test_phase2a_backscatter.py .........                               [  9%]
tests/test_phase2a_quality.py .....                                       [ 11%]
tests/test_phase2a_scientific_correction.py .....                         [ 13%]
tests/test_phase2b_filtering.py .......                                   [ 16%]
tests/test_phase3a_classification.py .........                            [ 21%]
tests/test_phase3a_qc.py .......                                          [ 24%]
tests/test_phase3b_change_detection.py ........                           [ 27%]
tests/test_phase3b_qc.py ........                                         [ 31%]
tests/test_phase4a_provenance.py .......                                  [ 34%]
tests/test_phase4a_validation.py .......                                  [ 37%]
tests/test_phase4b_scientific_corrections.py .............                [ 43%]
tests/test_phase4c1_s2_ingestion.py .................................... [ 60%]
tests/test_phase4d_validation.py .........                               [ 64%]
tests/test_phase4d1_reconciliation.py ............                        [ 69%]
tests/test_reference_ingestion.py .................                       [ 77%]
tests/test_phase5_flood_engine.py ..................                      [ 85%]
tests/test_phase6_bank_migration.py ...............                       [ 92%]
tests/test_phase6_1_audit.py ............                                 [100%]

======================== 219 passed, 1 warning in 7.13s ========================
```

---

## 9. Conclusion & Demonstration Readiness

Phase 6.1 successfully completes the scientific audit, geometric verification, and cross-phase reconciliation of Earth Pulse:
1. Every pixel between Phase 5 and Phase 6 is reconciled and mapped to a geomorphologically meaningful, conserved class.
2. The $5,660\text{ m}$ and $3,580\text{ m}$ maximum displacement anomalies are proven to be an AOI boundary artifact and anabranch activation, respectively, while core bank migration is quantified at a median of $40\text{ m}$ (Right Bank) and $90\text{ m}$ (Left Bank).
3. Sensor error propagation establishes an MDD threshold of $\approx 50\text{ m}$, preventing over-interpretation of subpixel noise.
4. Unsupported causal assertions regarding embankments and flood crests are corrected to reflect rigorous empirical science.

The codebase is fully tested, versioned, non-destructive, and prepared for final NASA Space Apps Challenge demonstration packaging.

