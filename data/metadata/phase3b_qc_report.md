# Earth Pulse — Phase 3B.1: Transition Classification & Full-Scene NoData Audit Report

**Project:** NASA Space Apps Challenge 2026 — *Dancing with the SARs*
**Study Reach:** Jamuna River, Kazipur & Sirajganj Districts, Bangladesh
**Audit Objective:** Verify input category semantics, priority rules, full-scene NoData reconciliation, AOI conservation, and connected-component accuracy.

---

## 1. Root Cause & Discrepancy Investigation

### Reported Observation:
The user noted that previous summary text stated full-scene results as:
- *Indeterminate: 595,953 pixels (30.45%)*
- *NoData / Invalid: 284 pixels (0.01%)*

Whereas Phase 1 and Phase 2 documented that approximately ~29.5% of the scene is composed of source NoData.

### Audit Findings & Root Cause Analysis:
1. **Physical Rasters & Master JSON Report Integrity:**
   Inspection of the actual GeoTIFF transition rasters (`transition_primary.tif`, `transition_2d_otsu.tif`, etc.)    and the master JSON report (`phase3b_change_detection_report.json`) confirmed that **the underlying computational engine was completely correct all along**:
   - **Class 6 (NoData / Invalid):** $577,307\text{ cells}$ (**29.4971%** of full raster, matching Phase 1 alignment metrics exactly).
   - **Class 5 (Indeterminate / Clipping Floor):** $18,930\text{ cells}$ (**0.9672%** of full raster).

2. **Conversational Formatting Blunder:**
   The discrepancy originated strictly as an inverted typographical reporting error in the chat summary.    The union of non-definitive observations ($577,307 + 18,930 = 596,237$ cells) was conflated, and 284 cells was erroneously assigned to NoData instead of preserving the true raster distribution.
3. **Scientific Integrity Verified:** NoData was never converted into indeterminate water during transition mapping.

---

## 2. Input Category Semantics & Quality Mask Truth

Cross-checking Phase 3A.1 candidate classification masks against original Phase 2B quality masks confirms 100% exact equivalence:

| Code | Semantic Category | Phase 3A.1 Candidate Masks | Phase 2B Quality Masks | Priority in Transition Engine |
| :---: | :--- | :--- | :--- | :--- |
| **0** | Candidate Non-Water | Backscatter above water threshold | Quality == 0 (Valid ordinary observation) | Tier 3: Binary Transition |
| **1** | Candidate Water | Backscatter below water threshold | Quality == 0 (Valid ordinary observation) | Tier 3: Binary Transition |
| **2** | Indeterminate (Clipping Floor) | Extreme low-backscatter artifact (< -35 dB) | Quality == 2 (SNAP clipping-floor) | Tier 2: Priority Indeterminate |
| **3** | Source NoData / Border | Out-of-swath / invalid border | Quality == 1 (Source NoData) | Tier 1: Top Priority NoData |
| **4** | Ambiguous 2D Otsu | Discordant polarization quadrants (2D Otsu only) | N/A (Derived method boundary) | Tier 2: Priority Indeterminate |

---

## 3. Full-Scene NoData Reconciliation ($782.87\text{ km}^2$, $1,957,165$ Cells)

Reconciliation against Phase 1 alignment coverage and Phase 2B quality masks:

- **June 10 Source NoData:** $577,183\text{ cells}$ (230.8732 km²)
- **July 16 Source NoData:** $576,591\text{ cells}$ (230.6364 km²)
- **Intersection (NoData in Both Dates):** $576,467\text{ cells}$
- **June-only NoData:** $716\text{ cells}$
- **July-only NoData:** $124\text{ cells}$
- **Union NoData (Class 6 - Either Date Invalid):** $\mathbf{577,307\text{ cells}}$ ($\mathbf{29.4971\%}$ of full raster)
- **Indeterminate / Clipping Floor (Class 5):** $\mathbf{18,930\text{ cells}}$ ($\mathbf{0.9672\%}$ of full raster)
- **Definitive Valid Transitions (Classes 1-4):** $\mathbf{1,360,928\text{ cells}}$ ($\mathbf{69.5357\%}$ of full raster)

$$\sum_{i=1}^6 C_i = 250,766 + 200,211 + 2,145 + 907,806 + 18,930 + 577,307 = \mathbf{1,957,165\text{ cells}} \quad (100.000\%)\$$

---

## 4. Kazipur Study AOI Reconciliation ($404.02\text{ km}^2$, $1,010,039$ Cells)

| Class Code | Transition Class Name | Pixel Count | Area (km²) | Area (ha) | % of Total AOI | % of Valid Domain |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **1** | Persistent Water | 216,595 | 86.6380 | 8663.80 | 21.44% | 21.80% |
| **2** | Newly Inundated Candidate | 146,992 | 58.7968 | 5879.68 | 14.55% | 14.79% |
| **3** | Receded Water | 1,634 | 0.6536 | 65.36 | 0.16% | 0.16% |
| **4** | Persistent Non-Water | 628,515 | 251.4060 | 25140.60 | 62.23% | 63.25% |
| **5** | Indeterminate / Clipping Floor | 16,242 | 6.4968 | 649.68 | 1.61% | — |
| **6** | NoData / Invalid Boundary | 61 | 0.0244 | 2.44 | 0.0060% | — |
| **Total** | **Conservation Sum** | **1,010,039** | **404.0156** | **40,401.56** | **100.00%** | **100.00%** |

### Verified Mathematical Area Identity:
- **Gross Candidate Water Expansion ($C_2$):** $+58.7968\text{ km}^2$ ($146,992\text{ px}$)
- **Gross Candidate Water Recession ($C_3$):** $-0.6536\text{ km}^2$ ($1,634\text{ px}$)
- **Net Candidate Water Area Change ($C_2 - C_3$):** $\mathbf{+58.1432\text{ km}^2}$ ($145,358\text{ px}$)
- **Valid July Water minus Valid June Water:** $363,587 - 218,229 = \mathbf{+145,358\text{ px}} \equiv \mathbf{+58.1432\text{ km}^2}$
- **Area Reconciliation Identity:** **HOLDS EXACTLY TO THE SINGLE PIXEL (0 discrepancy).**

---

## 5. Connected Components Audit (8-Connectivity)

- Total discrete candidate inundation clusters inside AOI: **3,934**
- Total pixels across all clusters: **146,992 cells** (conserving exactly $146,992\text{ pixels}$)
- Large clusters $\ge 100\text{ pixels}$ ($4\text{ ha}$): **138 clusters** containing **129,739 pixels** (88.26% of inundation).
- Small remnants $< 5\text{ pixels}$ ($< 0.2\text{ ha}$): **3,168 clusters** containing **4,236 pixels** (2.88% of inundation).

---

## 6. Audit Verdict & Conclusion

1. **Data Authenticity:** The underlying Phase 3B GeoTIFF transition rasters, GeoJSON vectors, and JSON reports are fully valid, methodologically sound, and preserved.
2. **Versioned Corrections:** All audited and verified products have been exported into `data/processed/phase3b_qc/` and `data/outputs/phase3b_qc/`.
3. **Scientific Documentation:** This QC report serves as the definitive reference document rectifying the conversational reporting ambiguity.
