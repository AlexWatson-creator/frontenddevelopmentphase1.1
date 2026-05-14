# Rundown Spreadsheet — Complete Technical Reference

> **ALWAYS read this file when working on rundown/spreadsheet-to-platform integration.**
> Source template: `D:\RESEARCH\Claude\Rundown Template (version 3_13b).xltm`
> VBA modules: `D:\RESEARCH\Claude\RUNDOWN VBA\`
> Completed examples: `D:\RESEARCH\Claude\20205 2-24 TEMPLE Rundown May-24-2023.xlsm` (normal marks), `D:\RESEARCH\Claude\Rundown 24043.xlsm` (W001-style marks)

---

## 1. Workbook Structure

Every rundown workbook has these **system sheets** (excluded from element iteration via `PopulateWSDict()` reading `DATA.rngWSExclude`):

| Sheet | Purpose |
|-------|---------|
| **TEMPLATE** | Blueprint for every element sheet. Cloned when new element detected. |
| **IMPORT** | Load type lookup (B2:F27) + level/filepath table (H:K). 25 load type rows, fixed. |
| **LOAD FILE** | Detailed load buildup per occupancy (layers → DL/LL kPa). Populates IMPORT. |
| **SUMMARY** | Cross-element overview. User picks which column to display (DL, LL, PW, PF, etc.) |
| **TRANSFERS** | Validation dashboard: Transfer Summary, Transfer Checks, Area Checks, Worksheet Checks |
| **DATA** | Configuration: display options (col numbers, formats), excluded sheet list, bar sizes |
| **CW SCHEDULE** | Column/Wall schedule export to CAD (ignore for platform) |

All other sheets are **element sheets** — one per vertical element (C1, W1, PW101, !FDNW1, W12-W13-W14, etc.).

---

## 2. IMPORT Sheet — The Lookup Table

### Load Types (B2:F27) — exactly 25 rows, never delete/add

| Col | Field | Example |
|-----|-------|---------|
| B | Description | RESIDENTIAL, BALCONY, PARKING |
| C | Name (code) | RES, BAL, PAR — **variable length**, matches CAD area prefix |
| D | DEAD (kPa) | 6.1 |
| E | LIVE (kPa) | 1.9 |
| F | LLRF type | N (none), R0.3, R0.5 |

### Level/Filepath Table (H:K) — dynamic size matching TEMPLATE levels

| Col | Field |
|-----|-------|
| H | BOT LVL (level name) |
| I | "-" (literal separator) |
| J | TOP LVL |
| K | FILEPATH (path to .dwg CAD file) |

One row per level pair. Same CAD file can be linked to multiple consecutive levels.

### Metadata (rows 38-40)
- B38: Job Name
- B39: Job Number
- B40: Designer Initials

---

## 3. TEMPLATE / Element Sheet Layout

### Fixed Column Map (row 3 = headers, row 4 = units/DL values)

**Data starts at row 7.** Each row = one level pair (BOT LVL to TOP LVL), ordered top-to-bottom (roof first, footings last).

| Column(s) | Header | Unit | Description |
|-----------|--------|------|-------------|
| A | BOT LEVEL | — | Bottom level name (e.g., "GROUND", "P1", "10") |
| B | "to" | — | Literal separator |
| C | TOP LEVEL | — | Top level name |
| D | HT above | m | Story height |
| E | Conc. Str. | MPa | Concrete strength for this level |
| **F** | **DL** | **kN** | **Cumulative dead load** — THE primary output |
| **G** | **LL** | **kN** | **Cumulative live load** (with LLRF applied) |
| **H** | **PW** | **kN** | **Service load = DL + LL** (Pw = DL + LL) |
| **I** | **PF** | **kN** | **Factored load** (1.25*DL + 1.5*LL) |
| J | F / A | MPa | Axial stress = factored load / element area |
| K | a (alpha) | — | `=MAX(0.85 - 0.0015*E, 0.67)` — concrete alpha factor |
| L | % Steel | — | Reinforcement ratio (design output) |
| M | As | mm2 | Steel area (design output) |
| N | Bar Size | — | Rebar bar size |
| O | QTY | — | Rebar quantity |
| P | Nbars | — | Number of bars |
| Q | Cbars | — | Corner bars |
| R | Rebar | — | Rebar design string (e.g., "8-20") |
| **S** | **AREA** | **m2** | **This-floor tributary area** |
| **T** | **XFER AREA** | **m2** | **Transfer area received this floor** |
| **U** | **CUM AREA** | **m2** | **Cumulative area = AREA + XFER AREA + CUM AREA from above** |
| **V** | **B-WT** | **kN** | **Beam weight** (from CAD: `BM= xx kN`) |
| **W** | **C-WALL** | **m** | **Cladding perimeter** (from CAD: `P= xx m`) |
| **X** | **Col. / Wall Dim.** | **mm** | **Dimension 1** (thickness for walls, width for columns) |
| **Y** | *(continued)* | **mm** | **Dimension 2** (length for walls, depth for columns). "D" if circular. |
| Z | Size | m2 | Element cross-section area = X*Y/1e6 |

### Area Breakdown Columns (AA:AY) — row 3 = load type codes, row 4 = DL kPa values

| Range | Section | Description |
|-------|---------|-------------|
| AA3:AY3 | Load type codes | Match IMPORT column C exactly (ROOF, MEC, STA, RES, BAL...) |
| AA4:AY4 | DL kPa | From IMPORT column D, auto-populated |
| AA7:AY{lastRow} | **Area per type per floor** | From CAD text: `Ares= 7.8 m2` → column matching "RES" |

### Cumulative Area Columns (BA:BY)
Same layout as AA:AY but stores cumulative area (this floor + all floors above).

### LLRF Columns (CA:CY)
Row 4 = LLRF type from IMPORT col F. Data rows = computed LLRF factor based on cumulative area.

### Cumulative Live Load — Non-Reducible Only (CZ:DY)
Tracks non-reducible live loads separately for code compliance.

---

## 4. TRANSFERS RECEIVED Section

Located below the level data in each element sheet. Position depends on number of levels.

| Row offset | Content |
|-----------|---------|
| +0 | "TRANSFERS RECEIVED" label (col A), "Cladding Wall:" + kPa value (cols E-G) |
| +1 | Load type legend (I-J columns: "RES = RESIDENTIAL", etc.) |
| +2 | Headers: NAME (A), LVL (B), PERCENT (C), DL (D), LL (E), CUM AREA (F) |
| +3.. | Transfer data rows |

### Transfer Row Format
| Col | Field | Example | Description |
|-----|-------|---------|-------------|
| A | NAME | C1.1 | Source element (transfers load FROM this element) |
| B | LVL | 2 | Level at which transfer occurs (TOP LVL of the receiving floor) |
| C | PERCENT | 1 (=100%) | Fraction of source element's load transferred |
| D | DL | (formula) | Calculated: source element's DL at that level × PERCENT |
| E | LL | (formula) | Calculated: source element's LL at that level × PERCENT |
| F | CUM AREA | (formula) | Calculated: source element's CUM AREA at that level × PERCENT |

**Named range `TransfersReceivedRange`** covers column B (LVL column) of the transfer rows.

### Transfer Logic
- "W1 receives 100% of C1A at level MPH" means: at MPH level, W1 gets C1A's full accumulated load
- Transfer can be fractional: 50%/50% split when wall sits on two columns
- Transfer area contributes to XFER AREA (col T) which feeds CUM AREA (col U)
- **Area Checks must balance to 0**: Cum.Area[floor N] - Tot.Area[floor N] - Cum.Area[floor N-1] = 0

---

## 5. Load Calculation Formulas (TRANSPARENT — replicate exactly)

> **Verified against actual Excel cell formulas AND numerical output from projects 20205 and 24043.**

### Dead Load (DL) per floor — Column F (CUMULATIVE)
Exact Excel formula (row N):
```
F[N] = F[N-1]
     + SUMPRODUCT($AA$4:$AY$4, AA[N]:AY[N])
     + IFERROR(SUMIF(TransfersReceivedRange, C[N], DL_transfer_col), 0)
     + Z[N] * D[N] * 24
     + cladding_kPa * W[N] * D[N-1]
     + V[N]
```
Note: `cladding_kPa` and `TransfersReceivedRange` positions shift based on number of levels (see Section 4).
Breaking down each term:

| # | Term | Formula | Description |
|---|------|---------|-------------|
| 1 | DL from above | `F[N-1]` | Cumulative DL from floor above |
| 2 | Floor load | `SUMPRODUCT(DL_kPa_per_type, area_per_type)` | Area × DL kPa for each of 25 load types |
| 3 | Transfer DL | `SUMIF(TransfersReceivedRange, C[N], DL_col)` | Sum of transfer DL where transfer LVL matches **TOP LEVEL (col C)** |
| 4 | Self-weight | `Z[N] × D[N] × 24` | Element cross-section (m2) × this story height (m) × 24 kN/m3 |
| 5 | Cladding | `$F$28 × W[N] × D[N-1]` | Cladding kPa × perimeter × **height of STORY ABOVE (D from previous row)** |
| 6 | Beam weight | `V[N]` | Beam dead load in kN (from CAD text) |

**CRITICAL: Cladding uses `D[N-1]` (the row above), NOT `D[N]`.** At the topmost floor (row 7), D[6] = 0 so no cladding. This is because the cladding between floors N-1 and N bears on floor N-1, and as we accumulate downward, that load is added when computing the element at floor N.

**Verified**: C1 row 10 in 20205: `78.302 + (5.3×6.1 + 1.9×5.3) + 0 + 0.2×2.95×24 + 2×4.6×3.35 + 0 = 165.682` matches actual.

### Live Load (LL) per floor — Column G (RECOMPUTED, not cumulative addition)
Exact Excel formula:
```
G[N] = SUMPRODUCT(BA[N]:BY[N], $BA$4:$BY$4, CA[N]:CY[N]) + DY[N]
```

**LL is NOT computed as `LL_above + delta`.** It is recomputed fresh at each floor from:
1. **Reducible LL**: `SUMPRODUCT(cum_area_per_type × LL_kPa × LLRF_factor)` — where cumulative area columns (BA:BY) already accumulate top-to-bottom
2. **Non-reducible cumulative LL** (`DY[N]`): separate accumulation path (see below)

This is fundamentally different from DL because LLRF changes as cumulative area grows — you can't just add a delta.

### Non-Reducible Live Load Path (CZ:DY columns)
For load types with LLRF = "N" (no reduction), live load bypasses the LLRF computation:

```
CZ[N] = IF(OR(type="R0.3", type="R0.5"), 0, AA[N] × LL_kPa)
  ... (one column per type, CZ through DX)
DY[N] = SUM(CZ[N]:DX[N]) + IFERROR(SUMIF(TransfersReceivedRange, C[N], LL_col), 0) + DY[N-1]
```

- Reducible types (R0.3, R0.5): CZ value = 0 (handled by LLRF path in G formula)
- Non-reducible types ("N"): CZ value = this_floor_area × LL_kPa
- `DY` = cumulative sum of non-reducible LL + **transfer LL** (cumulative)

**Two-path system**: Reducible LL goes through cum_area × LL_kPa × LLRF. Non-reducible LL accumulates floor-by-floor through DY.

### LLRF (Live Load Reduction Factor) — per load type (CA:CY columns)
Exact Excel formula:
```
IF(type = "R0.3":
    IF(cum_area > 20,  0.3 + SQRT(9.8 / cum_area),  1.0)
IF(type = "R0.5":
    IF(cum_area > 80,  0.5 + SQRT(20 / cum_area),  1.0)
IF(type = "N":
    0    ← non-reducible types return 0 in LLRF (handled by DY path instead)
```

- **R0.3**: reduction kicks in when cumulative area > 20 m2. Factor = `0.3 + sqrt(9.8/area)`
- **R0.5**: reduction kicks in when cumulative area > 80 m2. Factor = `0.5 + sqrt(20/area)`
- **"N"**: LLRF = 0 (the LL for these types flows through the non-reducible DY path instead)

### Self-Weight
```
self_weight = Z[N] × D[N] × 24
```
Where Z = element cross-section area in m2 (col Z), D = story height in m (col D).

Z is computed as:
```
Z = IF(Y="D", 0.25 × PI × (X/1000)^2,    ← circular column (diameter in mm)
    IF(Y="S", X,                            ← steel section (area directly)
    IF(Y="W", X/24,                         ← special case
    X × Y / 1e6)))                          ← default: width(mm) × depth/length(mm)
```

### Cladding Load
```
cladding_load = cladding_kPa × W[N] × D[N-1]
```
- Cladding kPa = from TRANSFERS RECEIVED section, col F of the "Cladding Wall:" row. **Row position is NOT fixed** — it's `$F$28` in a 19-level project (20205) but `$F$59` in a 50-level project (24043). Always at the TRANSFERS RECEIVED header row. Typically 1.5 kPa for glass, 2.0-3.0 for brick/precast.
- `W[N]` = cladding perimeter in m (col W, from CAD text "P= xx m")
- `D[N-1]` = **height of the story ABOVE** (the previous row's D value). At the topmost row, D[N-1] = 0.

### Beam Weight
```
beam_weight = V[N] in kN — directly from CAD text "BM= xx kN"
```
Original CAD formula: `(beam_depth - slab_thickness) × beam_width × beam_length × 24 / 1e9`

### Service Load (PW) — Column H
```
PW = DL + LL
```

### Factored Load (PF) — Column I
```
PF = MAX(1.25 × DL + 1.5 × LL, 1.4 × DL)
```
**Verified**: C1 row 10 in 20205: `MAX(165.682×1.25 + 44.63×1.5, 1.4×165.682) = MAX(274.048, 231.955) = 274.048` matches actual.

### Area Calculation
```
S[N]  = AZ[N] = SUM(AA[N]:AY[N])           # total area this floor
T[N]  = SUMIF(transfer_LVL, C[N], transfer_CUM_AREA)  # transfer area (matches TOP LEVEL)
U[N]  = IF(Z[N]=0, 0, S[N] + T[N] + U[N-1])          # cumulative (only if element has size)
```
- **S (AREA)** = `AZ` column which is `SUM(AA:AY)` for that row
- **T (XFER AREA)** = sum of transfer CUM AREA where transfer LVL matches **TOP LEVEL (col C)**
- **U (CUM AREA)** = guarded by `IF(Z=0, 0, ...)` — only accumulates if element has a cross-section at this floor

### Cumulative Area per Type (BA:BY columns)
```
BA[N] = BA[N-1] + AA[N]    (cumulative area for load type 1)
BB[N] = BB[N-1] + AB[N]    (cumulative area for load type 2)
... etc through BY
```
These per-type cumulative areas feed the LL and LLRF calculations.

### Axial Stress — Column J
```
f/A = IFERROR(PF / 1000 / Z, "")   in MPa
```
Note: PF is in kN, divided by 1000 to get MN, then divided by Z (m2) = MPa.

### Alpha Factor — Column K
```
alpha = MAX(0.85 - 0.0015 × f'c, 0.67)
```
Where f'c = concrete strength (col E) in MPa.

### % Steel — Column L
```
L = IFERROR(MAX(
    (f_over_A / phi - alpha × 0.65 × f'c) / (0.85 × 400 - alpha × 0.65 × f'c),
    0.01
), 0)
```
Where phi depends on element shape:
- Circular (Y="D"): phi = 0.8
- Square columns (X=Y, min > 300): phi = 0.8
- Other: phi = `0.2 + 0.002 × MIN(X, Y)`

---

## 6. CAD Multi-Line Text Format (RUNDOWN layer)

VBA reads **only MText objects on the "rundown" layer**. Single-line text (Text objects) on that layer triggers a warning.

### Text Structure
```
{element_name}          ← Line 0: sheet name (C1, W1, PW101, W12-W13-W14, !FDNW1)
A{code}= {value} m2    ← Area: prefix "A" + load type code + "= " + number + " m2"
A{code}= {value} m2    ← Multiple areas allowed (different types)
D= {dim1}x{dim2}       ← Dimensions: "D= " + mm + "x" + mm (or "D= 400d" for circular)
P= {value} m           ← Perimeter: "P= " + meters + " m" (cladding)
BM= {value} kN         ← Beam weight: "BM= " + kN + " kN" (optional)
```

### VBA Parsing Logic (ImportRundown.bas → `ImportRDData`)

1. **Line 0** = element name → becomes sheet name (cloned from TEMPLATE if new)
2. Lines 1+ parsed by **first character**:
   - `A` → Area: extract code (everything between "A" and "="), extract value (between "=" and "m2"). Look up code in AA3:AY3. Write value to matching area column for the floor range.
   - `P` → Perimeter: extract value (between "=" and "m"). Write to col W for floor range.
   - `D` → Dimensions: extract after "=", split on "x". Left = col X, Right = col Y. If contains "d" → circular.
   - `B` → Beam weight: extract value (between "=" and "kN"). Write to col V for floor range.
3. **Floor range** = `startRow:endRow` determined by which CAD file is linked to which levels in IMPORT.K
4. **Duplicate detection**: if element name appears twice in same CAD file → error logged, second ignored.
5. **Missing dimension check**: if no "D" line found → error logged.
6. **Area accumulation**: if same area type appears multiple times, values are **added** (not replaced).

### Real Examples from Production
```
W1                      C1                      PW101
Ares= 69.5 m2          AAMT= 5.3 m2           APAR= 5.9 m2
Abal= 28.0 m2          D= 250x800              D= 200x3700
D= 200x15840
P= 21.2 m
BM= 230.9 kN
```

---

## 7. Element Naming Convention — Complete Rules

### Format: `[PREFIX][C/W][NUMBER][SUFFIX][.COMMENT]`

| Part | Required | Description | Examples |
|------|----------|-------------|----------|
| PREFIX | Optional | Location prefix | P (parking), H (heritage), TWB, E, ! (no-schedule) |
| C or W | **Required** | Column or Wall | C, W |
| NUMBER | **Required** | Element number | 1, 001, 56 |
| SUFFIX | Optional | Sub-element letter | A, B, C |
| .COMMENT | Optional | Sheet disambiguator | .1, .2, .G, .44 |

### Key Rules
- **C{n} and W{n} cannot share the same number on the same floor** (e.g., no C1 and W1 together)
- **Comments after period**: `.1`, `.2` etc. create separate sheets but DON'T affect the CW schedule. Used when same element name appears on different floors in the vertical chain.
- **Grouped walls**: `W12-W13-W14` → one sheet, but generates 3 schedule entries. Elements share load.
- **`!` prefix**: Read by spreadsheet but excluded from CW schedule (foundation walls, air shafts)
- **`P` prefix**: Parking elements (PC104, PW101)
- **`H` prefix**: Heritage elements (HC041, HW022)
- Mark lengths vary: C1, C001, W12-W13-W14-W20A, !FDNW1

### VBA Sheet Sorting (Miscellaneous.bas → `SortSheets`)
Sorts by: prefix → element number (numeric) → suffix. `!` elements sorted to end.

---

## 8. TRANSFERS Sheet — Validation Dashboard

Built by VBA `GetTransfers()` which calls four functions:

### Transfer Summary (cols A-F, row 8+)
Lists every transfer relationship:
- To this member | From this member | At this Floor | Lowest Floor | Percent | Transfer Area

**Red highlight**: transfers above 100%

### Transfer Checks (cols G-J)
Per-element transfer audit:
- Member | % Transferred | To Member(s) | All Transfers Within Floor Range?

Color coding:
- Yellow: 0% transferred (element goes to foundation)
- Blue: >110% transferred
- Red: <100% transferred
- "All Within Range?" = No → red cell (transfer occurs outside element's active floor range)

### Area Checks (cols K-P)
Per-level balance verification:
- Bottom Level | to | Top Level | Tot. Area (m2) | Cum. Area (m2) | **Area Difference (m2)**

```
Area Difference[top floor] = Cum.Area - Tot.Area
Area Difference[other]     = Cum.Area[this] - Tot.Area[this] - Cum.Area[above]
```

**All Area Differences must be 0 when transfers are correct.** Red highlight if |diff| > 1.

### Worksheet Checks
Verifies all element sheets have correct column/row structure matching TEMPLATE.

---

## 9. SUMMARY Sheet

Two modes (toggled by user):
1. **Grid view**: Rows = levels, Columns = elements, Cell = selected metric (DL, LL, PW, PF, AREA, etc.). Column number chosen from DATA.B1.
2. **Lowest floor list**: Name | Lowest Floor | DL | LL | PW | PF | Dim X | Dim Y | Bar Size

---

## 10. DATA Sheet — Configuration

| Range | Purpose |
|-------|---------|
| A1:F13 | Display options: column number, format, example, units, rounding |
| H3:H11 (rngWSExclude) | Sheet names to exclude from element loops: SUMMARY, DATA, LOAD FILE, IMPORT, Sheet1, CW SCHEDULE, TEMPLATE, TRANSFERS |
| K4:L11 | Bar sizes and cross-sectional areas (10M=100mm2 through 55M=2500mm2) |

---

## 11. What the Platform Must Replicate

### Data Input (replaces CAD → VBA import)
1. **Load types**: Already in `design.load_tables` (DL/LL kPa + LLRF per type)
2. **Areas by type per element per floor**: From Voronoi tributary computation OR spreadsheet upload
3. **Element dimensions**: From Revit/Clarity (dbo.Columns, dbo.Walls) OR CAD text
4. **Cladding perimeters**: Manual input or computed from wall adjacency
5. **Beam weights**: Computed from Revit beam data: `(depth - slab_thickness) × width × length × 24 / 1e9`
6. **Transfers**: Engineering judgment — manual input via UI

### Computation (replaces Excel formulas)
All formulas from Section 5 must be replicated server-side. **Every intermediate value must be visible and traceable** — no black boxes.

Required outputs per element per floor:
- DL (kN), LL (kN), PW (kN), PF (kN)
- AREA (m2), XFER AREA (m2), CUM AREA (m2)
- Self-weight (kN), Cladding load (kN), Beam weight (kN)
- LLRF per load type
- f/A (MPa), alpha
- Area breakdown by load type

### Validation (replaces TRANSFERS sheet)
- Transfer summary: who transfers to whom, at what level, what percent
- Transfer checks: every element's total transferred percentage
- **Area checks: Area Difference must be 0 for every floor**
- Data gap detection: elements with missing dimensions or discontinuous floor data

### Dual Source Strategy
The platform must accept data from TWO sources:
1. **CAD-based** (legacy): Upload existing rundown spreadsheet, extract all data
2. **Revit-based** (modern): Use Revit geometry from Clarity + Voronoi + platform-computed values

Both paths feed the same computation engine. Engineers can transition project-by-project.

---

## 12. Spreadsheet Upload — Data Extraction Map

When reading a completed .xlsm rundown, extract:

### From IMPORT Sheet
- Load types: B3:F27 (Description, Name, DEAD, LIVE, LLRF)
- Levels: H3:J{last} (BOT LVL, TOP LVL)
- Metadata: B38 (Job Name), B39 (Job Number), B40 (Designer)

### From Each Element Sheet
- Level data rows: row 7 to last non-empty row in col A
- Per row: A (BOT LVL), C (TOP LVL), D (HT), E (f'c), F (DL), G (LL), H (PW), I (PF)
- S (AREA), T (XFER AREA), U (CUM AREA)
- V (B-WT), W (C-WALL), X (Dim1), Y (Dim2)
- AA:AY (area breakdown per load type)
- Cladding kPa: from transfers section (offset from "Cladding Wall:" label)
- Transfers: rows below "NAME" header — cols A (NAME), B (LVL), C (PERCENT)

### Element Classification
- Sheet name → parse with mark parser to get type (C/W), number, prefix, suffix, comment
- Grouped walls (contains "-"): split on "-" for schedule entries
- `!` prefix: foundation/hidden elements
- `P` prefix: parking
- `H` prefix: heritage

---

## 13. Key Differences Between Projects

| Aspect | Template (v3_13b) | 20205 TEMPLE | 24043 |
|--------|-------------------|--------------|-------|
| Levels | 14 (MPH→Ftgs) | 19 (MPH→Ftgs) | varies |
| Load types | 25 standard | 25 (some custom: MECP, EXT, GROOF) | 25 |
| Marks | C1, W1 | C1, W1, PW101, !FDNW1 | C001, W001 (zero-padded) |
| Element count | 0 (template) | ~210 | ~190 |
| Cladding kPa | 1.5 | 2.0 | varies |
| Concrete strengths | 30/35 MPa | 30/35/40 MPa | varies |

**The platform must handle all these variations.** Load type names and counts are project-specific. Level names and counts vary. Mark formats vary.
