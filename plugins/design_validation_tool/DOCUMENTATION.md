# Design Validation Tool - Documentation

## Table of Contents

1. [Overview](#overview)
2. [How to Use](#how-to-use)
3. [Required Input Layers](#required-input-layers)
4. [Validation Rules Reference](#validation-rules-reference)
   - [POC Clustering](#poc-clustering-rules)
   - [Overlapping](#overlapping-rules)
   - [Primary Distribution](#primary-distribution-rules)
   - [Feeder](#feeder-rules)
   - [Distribution](#distribution-rules)
   - [Data Quality](#data-quality-rules)
   - [Trenches](#trenches-rules)
   - [Crossings](#crossings-rules)
   - [Feature Lock](#feature-lock-rule)
5. [Outputs](#outputs)
6. [Violation Display Behaviour](#violation-display-behaviour)
7. [Default Parameter Reference](#default-parameter-reference)

---

## Overview

The **Design Validation Tool** is a QGIS plugin that automatically checks a fibre-network design project against a set of engineering rules. It reads the layers loaded in a QGIS project file (`.qgz`), runs the selected checks, and produces:

- Colour-coded violation layers added directly to the QGIS map canvas
- Shapefiles saved to disk for each violation category
- An HTML summary report

The tool is accessed from the QGIS menu: **Plugins → Design Validation → Design Validation Tool**.

---

## How to Use

### Step 1 - Open the dialog

Navigate to **Plugins → Design Validation → Design Validation Tool** in the QGIS menu bar. The validation dialog will open.

### Step 2 - Select the project file

Click the folder icon next to **Design Session Project File** and browse to the `.qgz` project file that contains the design to be validated. The tool will load all layers from this project automatically.

### Step 3 - Select the output directory

Click the folder icon next to **Output Directory** and choose where the results (shapefiles, reports) should be saved. A timestamped subfolder will be created inside this directory for each run.

### Step 4 - Choose which checks to run

Enable one or more of the following checkboxes:

| Checkbox | Validation category |
|---|---|
| POC Clustering | POC placement, connections, proximity, drop cable rules |
| Overlap | Parallel duct overlap and cluster overlap |
| Primary Distribution | PDP cable limits and primary cable placement |
| Feeder | Feeder cable length, crossings, count, and POP capacity |
| Distribution | DP cable limits, cable types, length rules |
| Data Quality | SUBTYPE integrity, locked features, BOM files, monuments |
| Trenches | SUBTYPE validity, routing, sharp angles, missing trenches |
| Crossings | Crossing angle, position, proximity, and road width rules |
| Generate Report | If ticked, generates a PDF layout report in addition to the HTML report |

### Step 5 - Run

Click **OK / Run**. A progress bar and colour-coded log panel show real-time status. When finished, violation layers appear on the map canvas and output files appear in the chosen directory.

### Additional buttons

| Button | Action |
|---|---|
| Clear Log | Clears the log panel |
| Save Log | Saves the log text to a file |
| Fix Geometries | Runs QGIS geometry repair on the selected layers before validation |
| Close | Closes the dialog without running |

---

## Required Input Layers

The tool identifies layers by their **exact name** inside the loaded project. The table below lists every layer name the tool looks for and the attribute fields it reads from each one.

> If a required layer is missing or a field name is spelled differently, the affected rule will either skip the check or report an error in the log.

### Drop / POC layers

| Layer name | Required fields |
|---|---|
| `Drop Points` | `AGG_ID`, `SUBCLUSTER` |
| `Drop Clusters` | `AGG_ID`, `HOMECOUNT` |
| `Drop Cables` | `TYPE`, `CABLE_ID`, `LENGTH`, `TOP_AGG_ID` |
| `Demand Points` | `ID_DROP` |

### Cable layers

| Layer name | Required fields |
|---|---|
| `Distribution Cables` | `CAB_GROUP`, `CABLE_ID`, `TYPE`, `SUBCLUSTER` |
| `Primary Distribution Cables` | `TYPE`, `TOP_AGG_ID` |
| `Feeder Cables` | `LENGTH`, `CABLE_ID`, `CABLEGRAN` |

### Node / equipment layers

| Layer name | Required fields |
|---|---|
| `Distribution Points` | `AGG_ID` |
| `Primary Distribution Points` | `AGG_ID` |
| `Central Offices` | `AGG_ID`, `HOMECOUNT` |
| `Poles` | - (presence only) |

### Duct layers

| Layer name | Required fields |
|---|---|
| `Primary Distribution Ducts` | `DUCT_ID`, `DUCT_GROUP`, `IDENTIFIER`, `TYPE`, `CAPACITY` |
| `Distribution Ducts` | `DUCT_ID`, `DUCT_GROUP`, `IDENTIFIER`, `TYPE`, `CAPACITY` |

### Cluster layers

| Layer name | Required fields |
|---|---|
| `Primary Distribution Clusters` | - (geometry only) |
| `Distribution Clusters` | - (geometry only) |

### Reference / base layers

| Layer name | Required fields |
|---|---|
| `Possible trench routes` | `SUBTYPE`, `LENGTH` |
| `Possible Routes` | - (geometry only, aerial routes) |
| `Street Center Lines` | `STREETNAME` |
| `Building Polygons` | - (geometry only) |
| `IN_Crossings` | `SUBTYPE`, `LENGTH` |
| `IN_ExistingPipes` | - (geometry only) |

### Lock field (all layers)

Any layer that carries a field named `LOCKED` (case-insensitive) will be checked by the **Feature Lock** rule. A value of `'Unlocked'` flags a violation.

---

## Validation Rules Reference

### POC Clustering Rules

These rules verify the placement, connections, and grouping of Point of Connection (POC) elements.

---

#### POC_001 - Maximum POCs per distribution cable

| Attribute | Value |
|---|---|
| Rule ID | `POC_001` |
| Default threshold | 11 POCs per cable (22 for aerial cables) |
| Layers used | `Distribution Cables`, `Drop Points` |
| Fields used | `CAB_GROUP`, `CABLE_ID`, `TYPE`, `SUBCLUSTER` |

**What it checks:** Counts the number of POCs (Drop Points) served by each distribution cable. A cable must not serve more than 11 POCs (or 22 for aerial-type cables).

**Violation:** The cable `CABLE_ID` has more POCs than the allowed maximum.

---

#### POC_002 - Maximum connections per POC

| Attribute | Value |
|---|---|
| Rule ID | `POC_002` |
| Default threshold | 8 demand-point connections per POC |
| Layers used | `Drop Points`, `Demand Points` |
| Fields used | `AGG_ID` |

**What it checks:** Counts the number of demand points (homes/units) associated with each POC within a 5 m radius. A POC must not serve more than 8 demand points.

**Violation:** POC `AGG_ID` has more than 8 connections.

---

#### POC_003 - UG / Façade connection balance

| Attribute | Value |
|---|---|
| Rule ID | `POC_003` |
| Default threshold | max 4 left connections, max 4 right connections |
| Layers used | `Drop Points`, `Demand Points` |
| Fields used | `AGG_ID`, `orientation` |

**What it checks:** Verifies that the left-side and right-side demand-point connections per POC do not each exceed 4.

**Violation:** POC `AGG_ID` has too many connections on one side (e.g. 5 left).

---

#### POC_004 - POC in a single drop cluster

| Attribute | Value |
|---|---|
| Rule ID | `POC_004` |
| Default threshold | Cluster membership within 1 m |
| Layers used | `Drop Points`, `Drop Clusters` |
| Fields used | `AGG_ID` |

**What it checks:** Each POC must belong to exactly one drop cluster. A POC that sits in more than one cluster, or outside any cluster, is flagged.

**Violation:** POC `AGG_ID` belongs to multiple clusters or none.

---

#### POC_005 - POC proximity, home count, and drop cable length

| Attribute | Value |
|---|---|
| Rule ID | `POC_005` |
| Default thresholds | Max distance between neighbour POCs: 50 m · Max combined home count: 8 · Max drop cable length: 100 m |
| Layers used | `Drop Points`, `Distribution Cables`, `Drop Clusters`, `Drop Cables` |
| Fields used | `SUBCLUSTER`, `CAB_GROUP`, `CABLE_ID`, `TYPE`, `HOMECOUNT`, `LENGTH`, `TOP_AGG_ID` |

**What it checks:** For each pair of POCs that share the same distribution cable (within 50 m of each other), the combined home count of their clusters must not exceed 8 and the total drop cable length must not exceed 100 m.

**Violation:** POCs `poc1_id` & `poc2_id` are X m apart with Y combined homes.

---

#### POC_006 - Aerial drop cable length

| Attribute | Value |
|---|---|
| Rule ID | `POC_006` |
| Default threshold | 40 m maximum |
| Layers used | `Drop Cables` |
| Fields used | `TYPE`, `CABLE_ID`, `LENGTH` |

**What it checks:** Each aerial drop cable must not exceed 40 m in length.

**Violation:** Drop cable `CABLE_ID` is X m long (max 40 m).

---

#### POC_007 - Façade drop cables must not cross building gaps

| Attribute | Value |
|---|---|
| Rule ID | `POC_007` |
| Layers used | `Drop Cables`, `Building Polygons`, `Possible Routes` |
| Fields used | `TYPE`, `CABLE_ID` |

**What it checks:** Façade-type drop cables are not permitted to cross an open gap between buildings (i.e. they must remain on a continuous building facade).

**Violation:** Drop cable `CABLE_ID` crosses an open span between buildings.

---

#### POC_008 - Stacked POCs

| Attribute | Value |
|---|---|
| Rule ID | `POC_008` |
| Default threshold | Minimum 1 m separation between POCs |
| Layers used | `Drop Points` |
| Fields used | `AGG_ID` |

**What it checks:** No two POCs may be placed at the same location or within 1 m of each other.

**Violation:** POC `poc_id` is X m from POC `nearby_poc_id` (min 1 m required).

---

#### POC_009 - POC placement between served buildings

| Attribute | Value |
|---|---|
| Rule ID | `POC_009` |
| Default threshold | Max 0.5 m offset from the geometric centre of served buildings |
| Layers used | `Drop Points`, `Demand Points`, `Building Polygons` |
| Fields used | `AGG_ID`, `ID_DROP` |

**What it checks:** Each POC must be positioned at (or very close to) the geometric centre of the buildings it serves. An offset greater than 0.5 m is a violation.

**Violation:** POC `poc_id` is X m from the centre of Y served buildings (max 0.5 m).

---

### Overlapping Rules

These rules detect redundant or conflicting duct and cluster geometries.

---

#### OVERLAP_001 - Parallel duct overlap

| Attribute | Value |
|---|---|
| Rule ID | `OVERLAP_001` |
| Default thresholds | Min overlap to flag: 50 m (parallel ducts) · Min shared route: 20 m (same-IDENTIFIER ducts) · Max lateral separation: 2 m |
| Layers used | `Primary Distribution Ducts`, `Distribution Ducts` |
| Fields used | `DUCT_ID`, `DUCT_GROUP`, `IDENTIFIER`, `TYPE`, `CAPACITY` |

**What it checks:**
- Two ducts with the same capacity that run parallel within 2 m of each other for more than 50 m.
- Two ducts that share the same `IDENTIFIER` value and share a route for more than 20 m.
- Two ducts that form a redundant parallel route for more than 20 m.

**Violation:** Ducts `duct1_id` & `duct2_id` - overlap X m / shared route X m.

---

#### OVERLAP_003 / 004 / 005 - Cluster overlap

| Rule ID | Cluster type | Min overlap area to flag |
|---|---|---|
| `OVERLAP_003` | Primary Distribution Clusters | 10 m² |
| `OVERLAP_004` | Distribution Clusters | 10 m² |
| `OVERLAP_005` | Drop Clusters | 10 m² |

**What it checks:** Two clusters of the same type must not overlap by more than 10 m².

**Violation:** Clusters `cluster1_id` & `cluster2_id` - overlap X %.

---

### Primary Distribution Rules

---

#### PRIMARY_001 - PDP cable limits

| Attribute | Value |
|---|---|
| Rule ID | `PRIMARY_001` |
| Default thresholds | Max 8 cables leaving a PDP · Min 3 primary cables |
| Layers used | `Primary Distribution Points`, `Primary Distribution Cables` |
| Fields used | `AGG_ID`, `TOP_AGG_ID`, `TYPE` |

**What it checks:** Each Primary Distribution Point (PDP) must have at least 3 primary cables and no more than 8 cables total leaving it.

**Violation:** PDP `pdp_id` - X cables (max 8 / min 3 primary).

---

#### PRIMARY_002 - No primary cables on poles

| Attribute | Value |
|---|---|
| Rule ID | `PRIMARY_002` |
| Layers used | `Primary Distribution Cables`, `Poles` |
| Fields used | `LAYER` |

**What it checks:** Primary distribution cables must not be routed on poles. They must be underground or on a building.

**Violation:** Pole `pole_eq_id` - primary cable is placed on a pole.

---

#### PRIMARY_003 - Primary cable split

| Attribute | Value |
|---|---|
| Rule ID | `DISTRIBUTION_012` |
| Default threshold | 1 m topology tolerance |
| Layers used | `Primary Distribution Cables` |

**What it checks:** Every primary distribution cable must start from a PDP. A cable whose start point has no PDP within 1 m is considered a "split" cable.

**Violation:** Primary cable `cable_id` - no PDP at start point (split cable).

---

### Feeder Rules

---

#### FEEDER_001 - Feeder cable length

| Attribute | Value |
|---|---|
| Rule ID | `FEEDER_001` |
| Default threshold | 50 m maximum |
| Layers used | `Feeder Cables` |
| Fields used | `LENGTH`, `CABLE_ID` |

**What it checks:** Each feeder cable must not exceed 50 m in length.

**Violation:** Feeder `cable_id` - X m (too long).

---

#### FEEDER_002 - Feeder cable street crossing

| Attribute | Value |
|---|---|
| Rule ID | `FEEDER_002` |
| Layers used | `Feeder Cables`, `Street Center Lines` |
| Fields used | `CABLE_ID`, `STREETNAME` |

**What it checks:** Feeder cables must not cross street centre lines. A feeder that geometrically intersects a street centre line is flagged.

**Violation:** Feeder `cable_id` - crosses street `street_id`.

---

#### FEEDER_003 - Feeder cable count and granularity

| Attribute | Value |
|---|---|
| Rule ID | `FEEDER_003` |
| Default thresholds | Exactly 6 feeder cables · Each cable must have 192 fibres (`CABLEGRAN = 192`) |
| Layers used | `Feeder Cables`, `Central Offices` |
| Fields used | `CABLEGRAN`, `CABLE_ID`, `AGG_ID` |

**What it checks:**
1. The total number of feeder cables in the project must equal 6.
2. Each feeder cable must carry exactly 192 fibres (granularity check on `CABLEGRAN`).

**Violations:**
- Feeder count: X (need 6).
- Feeder `cable_id` - wrong granularity (`actual_granularity`).

---

#### FEEDER_004 - POP cabinet capacity

| Attribute | Value |
|---|---|
| Rule ID | `FEEDER_004` |
| Default threshold | 1024 homes maximum per Central Office |
| Layers used | `Central Offices` |
| Fields used | `HOMECOUNT`, `AGG_ID` |

**What it checks:** The total home count served by each Central Office (CO / POP) must not exceed 1 024.

**Violation:** CO `co_id` - X homes (over capacity).

---

### Distribution Rules

---

#### DISTRIBUTION_001 - Max cables leaving a DP

| Attribute | Value |
|---|---|
| Rule ID | `DISTRIBUTION_001` |
| Default threshold | 5 cables maximum per Distribution Point |
| Layers used | `Distribution Points`, `Distribution Cables` |
| Fields used | `AGG_ID`, `TOP_AGG_ID`, `CABLE_ID` |

**What it checks:** Each Distribution Point (DP) must not have more than 5 distribution cables leaving it.

**Violation:** DP `dp_id` - X cables (max 5).

---

#### DISTRIBUTION_002 - Façade cable maximum length

| Attribute | Value |
|---|---|
| Rule ID | `DISTRIBUTION_002` |
| Default threshold | 500 m maximum |
| Layers used | `Distribution Cables` |
| Fields used | `TYPE`, `LENGTH`, `CABLE_ID` |

**What it checks:** Each façade-type distribution cable must not exceed 500 m in length.

**Violation:** Façade cable `cable_id` - X m (max 500 m).

---

#### DISTRIBUTION_003 - Aerial cable POC limit

| Attribute | Value |
|---|---|
| Rule ID | `DISTRIBUTION_003` |
| Default thresholds | Max 22 POCs per aerial cable · Max 4 drop connections per POC on that cable |
| Layers used | `Distribution Cables`, `Drop Points`, `Demand Points` |
| Fields used | `TYPE`, `SUBCLUSTER`, `AGG_ID` |

**What it checks:** Aerial distribution cables must not serve more than 22 POCs, and no individual POC on the cable may have more than 4 drop connections.

**Violation:** Aerial cable `cable_id` - X POCs (max 22).

---

#### DISTRIBUTION_004 - Parallel cable POC connection

| Attribute | Value |
|---|---|
| Rule ID | `DISTRIBUTION_004` |
| Default threshold | POCs must connect to the cable set of 11 POCs |
| Layers used | `Distribution Cables`, `Drop Points` |

**What it checks:** When parallel distribution cables exist, all POCs must connect to the longest cable in the set (the one that carries up to 11 POCs) rather than a shorter parallel cable.

**Violation:** POC `poc_id` - should connect to cable `longest_cable_id`.

---

#### DISTRIBUTION_005 - Façade underground section length

| Attribute | Value |
|---|---|
| Rule ID | `DISTRIBUTION_005` |
| Default threshold | 40 m maximum per underground section |
| Layers used | `Distribution Cables` |
| Fields used | `TYPE`, `LENGTH` |

**What it checks:** The underground section of a façade cable must not exceed 40 m per section.

**Violation:** Cable `cable_id` - underground section X m (too long).

---

#### DISTRIBUTION_006 - Parallel aerial cable limit

| Attribute | Value |
|---|---|
| Rule ID | `DISTRIBUTION_006` |
| Default threshold | Max 2 parallel aerial cables in the same location |
| Layers used | `Distribution Cables` |
| Fields used | `TYPE` |

**What it checks:** No more than 2 aerial distribution cables may run parallel in the same corridor.

**Violation:** Group `cable_group` - X parallel aerial cables.

---

#### DISTRIBUTION_007 - Underground drop consistency

| Attribute | Value |
|---|---|
| Rule ID | `DISTRIBUTION_007` |
| Layers used | `Drop Points`, `Distribution Cables` |
| Fields used | `SUBCLUSTER` |

**What it checks:** If the parent distribution cable is underground, all drop cables belonging to the same cable group must also be underground.

**Violation:** Drop cable `drop_cable_id` - not underground (parent cable is underground).

---

#### DISTRIBUTION_008 - Façade total underground length

| Attribute | Value |
|---|---|
| Rule ID | `DISTRIBUTION_008` |
| Default threshold | 60 m total maximum |
| Layers used | `Distribution Cables` |
| Fields used | `TYPE`, `LENGTH` |

**What it checks:** The cumulative underground length across all underground sections on a single façade cable must not exceed 60 m.

**Violation:** Façade cable `cable_id` - total underground length X m (max 60 m).

---

#### DISTRIBUTION_009 - DP inside a drop cluster

| Attribute | Value |
|---|---|
| Rule ID | `DISTRIBUTION_009` |
| Default threshold | 2 m buffer |
| Layers used | `Distribution Points`, `Drop Clusters` |
| Fields used | `AGG_ID` |

**What it checks:** A Distribution Point must not be placed inside a drop cluster or within 2 m of a drop cluster boundary.

**Violation:** DP `dp_id` - inside drop cluster.

---

#### DISTRIBUTION_010 - DP in private domain

| Attribute | Value |
|---|---|
| Rule ID | `DISTRIBUTION_010` |
| Layers used | `Distribution Points`, `Building Polygons` |
| Fields used | `AGG_ID` |

**What it checks:** Distribution Points must not be placed inside private domains (building footprints classed as private).

**Violation:** DP `dp_id` - in private domain.

---

#### DISTRIBUTION_011 - Mini-DP on façade

| Attribute | Value |
|---|---|
| Rule ID | `DISTRIBUTION_011` |
| Layers used | `Distribution Cables`, `Building Polygons` |
| Fields used | `TYPE` |

**What it checks:** Mini Distribution Points placed on a façade must have the correct configuration (proper cable type and building association).

**Violation:** Mini-DP `mini_dp_id` - façade configuration issue.

---

#### DISTRIBUTION_012 - Distribution cable split

| Attribute | Value |
|---|---|
| Rule ID | `DISTRIBUTION_012` |
| Default threshold | 1 m topology tolerance |
| Layers used | `Distribution Cables` |

**What it checks:** Every distribution cable must start at a DP or PDP. A cable whose start point has no DP or PDP within 1 m is a "split" cable.

**Violation:** Cable `cable_id` - no DP or PDP at start point (split cable).

---

### Data Quality Rules

---

#### DATA_Q_001 - SUBTYPE validity

| Attribute | Value |
|---|---|
| Rule ID | `DATA_Q_001` |
| Layers used | `Possible trench routes`, `IN_Crossings` |
| Fields used | `SUBTYPE`, `LENGTH` |

**What it checks:**
- The `SUBTYPE` field must not be empty.
- The value must be one of the valid subtypes (see [Trenches rules](#trenches-rules) for the list).
- Features with subtype `Doorsteek (1m diep)` must not exceed 8 m in length; longer features should use `Gestuurde boring`.

**Violations:**
- Feature `feature_id` - `SUBTYPE` empty.
- Feature `feature_id` - invalid subtype `'value'`.
- Feature `feature_id` - `Doorsteek (1m diep)` > 8 m; use `Gestuurde boring`.
- Feature `feature_id` - `SUBTYPE` missing.

---

#### DATA_Q_002 - Façade on protected monument

| Attribute | Value |
|---|---|
| Rule ID | `DATA_Q_002` |
| Layers used | `Distribution Cables`, Protected Monuments layer |
| Fields used | `TYPE`, `CABLE_ID` |

**What it checks:** Façade-type distribution cables must not be routed across or through a building that is a legally protected monument.

**Violation:** Façade cable `cable_id` - on a protected monument.

---

#### DATA_Q_003 - Features must be locked

| Attribute | Value |
|---|---|
| Rule ID | `DATA_Q_003` |
| Layers used | All layers with a `LOCKED` field |
| Fields used | `LOCKED` |

**What it checks:** Every feature across all layers that carries a `LOCKED` attribute must have it set to a locked state. Features where `LOCKED = 'Unlocked'` are flagged.

**Violation:** `layer_name` - X unlocked features.

---

#### DATA_Q_004 - Multiple BOM files

| Attribute | Value |
|---|---|
| Rule ID | `DATA_Q_004` |
| Source | Project directory file scan |

**What it checks:** The project directory must not contain more than one Bill of Materials (BOM) file. Multiple BOM files indicate an inconsistent project state.

**Violation:** BOM file `bom_file` - duplicate BOM detected.

---

#### DATA_Q_005 - Existing pipe trench subtype

| Attribute | Value |
|---|---|
| Rule ID | `DATA_Q_005` |
| Layers used | `IN_ExistingPipes`, `Possible trench routes` |
| Fields used | `SUBTYPE`, `feature_id`, `pipe_id` |

**What it checks:** Trench route features that spatially coincide with an existing pipe must have their `SUBTYPE` set to `'Existing Pipes'`.

**Violation:** Trench `feature_id` - should be `'Existing Pipes'` (overlaps pipe `pipe_id`).

---

#### DATA_Q_006 - Layer feature count

| Attribute | Value |
|---|---|
| Rule ID | `DATA_Q_006` |
| Layers used | All duct layers |

**What it checks:** Duct layers (Primary Distribution Ducts, Distribution Ducts) must not be empty - they must contain at least one feature.

**Violation:** Layer `layer_name` - empty (0 features).

---

### Trenches Rules

---

#### TRENCH_001 - Cable not on sidewalk / Drop cable not perpendicular

| Attribute | Value |
|---|---|
| Rule ID | `TRENCH_001` |
| Layers used | `Distribution Cables`, `Possible trench routes`, `Building Polygons` |

**What it checks:**
- Distribution cables must be routed on the sidewalk, not in the road carriageway.
- Drop cables must be perpendicular to the building façade they connect to.

**Violations:**
- Cable `cable_id` - not on sidewalk.
- Drop cable `cable_id` - not perpendicular.

---

#### TRENCH_002 - Sharp trenching angle

| Attribute | Value |
|---|---|
| Rule ID | `TRENCH_002` |
| Layers used | `Possible trench routes` |

**What it checks:** Sharp changes in direction along a trench route are flagged. Bends tighter than 90° indicate a routing problem that could cause installation difficulties.

**Violation:** Cable `cable_id` - sharp angle (X°).

---

#### TRENCH_003 - Missing trench

| Attribute | Value |
|---|---|
| Rule ID | `TRENCH_003` |
| Layers used | `Drop Cables`, `Distribution Cables` |

**What it checks:** Every drop cable must have a corresponding distribution cable (parent cable). Drop cables without a valid distribution cable parent are flagged as missing a trench.

**Violation:** Drop cable `cable_id` - no distribution cable found.

---

#### TRENCH_004 - U-shape detour / Cable overextension

| Attribute | Value |
|---|---|
| Rule ID | `TRENCH_004` |
| Layers used | `Possible trench routes`, `Distribution Cables`, `Drop Points` |

**What it checks:**
- U-shaped detours: a trench that doubles back on itself, adding unnecessary length.
- Cable overextension: a cable that extends beyond the last drop point it serves.

**Violations:**
- Cable `cable_id` - U-shape detour detected.
- Cable `cable_id` - extends X m past last drop point.

---

#### Valid SUBTYPE values (Trenches and Crossings)

The following values are accepted in the `SUBTYPE` field. Any other value will trigger a `DATA_Q_001` violation:

| SUBTYPE value | Notes |
|---|---|
| `Doorsteek (1m diep)` | Max length 8 m; longer features must use `Gestuurde boring` |
| `Doorsteek (wachthuis)` | |
| `Gestuurde boring` | Required for underground routes > 8 m |
| `In berm` | |
| `In berm (synergie)` | |
| `Monoliete verharding` | And variants (e.g. `Monoliete verharding - ...`) |
| `Niet-monoliete verharding` | And variants |
| `Existing` | And variants |
| `Dummy` | |

---

### Crossings Rules

---

#### CROSS_001 - Crossing angle

| Attribute | Value |
|---|---|
| Rule ID | `CROSS_001` |
| Default thresholds | Perpendicular range: 75°–105° · Parallel range: 0°–15° or 165°–180° |
| Layers used | `IN_Crossings`, `Possible trench routes` |

**What it checks:** Crossings must approach a trench either perpendicularly (75°–105°) or nearly parallel (0°–15° / 165°–180°). Any other angle is a violation.

**Violation:** Crossing `feature_id` - invalid angle to trench.

---

#### CROSS_002 - Crossing intersects a sidewalk trench

| Attribute | Value |
|---|---|
| Rule ID | `CROSS_002` |
| Layers used | `IN_Crossings`, `Possible trench routes` |

**What it checks:** A crossing feature must not intersect an existing sidewalk trench. Crossings should only occur at road crossings, not along the sidewalk.

**Violation:** Crossing `feature_id` - intersects a sidewalk trench.

---

#### CROSS_003 - Crossings too close together

| Attribute | Value |
|---|---|
| Rule ID | `CROSS_003` |
| Default threshold | 50 m minimum separation |
| Layers used | `IN_Crossings` |

**What it checks:** Two crossings must be at least 50 m apart along the same road.

**Violation:** Crossings `feature_1_id` & `feature_2_id` - X m apart (min 50 m).

---

#### CROSS_004 - Crossing in a road-widening area

| Attribute | Value |
|---|---|
| Rule ID | `CROSS_004` |
| Default threshold | Max road width: 15 m |
| Layers used | `IN_Crossings`, `Street Center Lines` |

**What it checks:** Crossings must not be placed in sections of road that are wider than 15 m (road-widening areas), as these locations require special crossing methods.

**Violation:** Crossing `feature_id` - in road-widening area.

---

### Feature Lock Rule

---

#### FEATURE_LOCK_001 - All features must be locked

| Attribute | Value |
|---|---|
| Rule ID | `DATA_Q_003` |
| Layers used | All layers with a `LOCKED` field |
| Fields used | `LOCKED` |

**What it checks:** This rule runs automatically alongside the Trenches check. It scans every layer in the project that has a `LOCKED` attribute and flags any feature where the value is `'Unlocked'`.

**Violation:** `layer_name` - X unlocked features.

> This is the same rule as DATA_Q_003 but runs as an independent check to ensure it is always executed when Trenches validation is selected.

---

## Outputs

When a validation run completes, a timestamped folder is created inside the chosen output directory:

```
<output_directory>/
└── Validation_<SessionName>_<YYYYMMDD_HHMMSS>/
    ├── <SessionName>_POC_Clustering.shp        ← POC violation polygons
    ├── <SessionName>_POC_Clustering.dbf
    ├── <SessionName>_POC_Clustering.shx
    ├── <SessionName>_OVERLAPPING.shp           ← Overlap violation polygons
    ├── <SessionName>_PRIMARY_DISTRIBUTION.shp  ← Primary distribution violations
    ├── <SessionName>_FEEDER.shp                ← Feeder violations
    ├── <SessionName>_DISTRIBUTION.shp          ← Distribution violations
    ├── <SessionName>_TRENCHES.shp              ← Trench violations
    ├── <SessionName>_CROSSINGS.shp             ← Crossing violations
    ├── <SessionName>_DATA_QUALITY.shp          ← Data quality violations
    └── validation_report_<SessionName>.html    ← Summary HTML report
```

A PDF layout report is also written to this folder when **Generate Report** is checked and violations exist.

### Shapefiles

Each shapefile contains buffered polygon geometries marking the location of each violation. The attribute table has the following columns:

| Field | Type | Description |
|---|---|---|
| `rule_id` | String | Rule identifier (e.g. `POC_001`) |
| `description` | String | Human-readable rule description |
| `violation_type` | String | Internal violation type code |
| `details` | String | Feature-specific detail (IDs, measurements) |
| `total_cnt` | Integer | Total number of times this violation type was found |

> If a rule fires more than **5 times**, only the **first 5 instances** are shown on the map and written to the shapefile. The `total_cnt` field always records the real total so the full scope of the issue is visible in the attribute table.

**Geometry buffer sizes** (applied to make point/line violations visible as polygons):

| Source geometry | Buffer applied |
|---|---|
| Point | 2.0 m |
| Line | 1.0 m |
| Polygon | 0.5 m |

**Layer colours** on the QGIS canvas:

| Category | Colour |
|---|---|
| POC Clustering | Blue |
| Overlapping | Red |
| Primary Distribution | Green |
| Feeder | Magenta |
| Distribution | Orange |
| Data Quality | Purple |
| Trenches | Dark blue |
| Crossings | Pink |

### HTML Report

The HTML report (`validation_report_<SessionName>.html`) contains one row per rule that was checked:

| Column | Description |
|---|---|
| Rule ID | e.g. `POC_001` |
| Description | Rule description |
| Status | `PASS` (green) / `FAIL` (red) / `ERROR` (orange) |
| Violation Count | Number of violations found |
| Failed Features | Comma-separated list of feature IDs |
| Message | Detailed message from the validator |

---

## Violation Display Behaviour

When the same rule fires more than **5 times**:

1. Only the **first 5** violations for that rule are added to the map layer and written to the shapefile.
2. The `total_cnt` attribute on each of those 5 features shows the **actual total** (e.g. `23`) so the user knows how widespread the issue is.
3. The HTML report is not affected - it always shows the full violation count and all failed feature IDs.

This behaviour prevents map clutter on large projects while still communicating the full scale of each issue.

---

## Default Parameter Reference

The following table consolidates all numeric thresholds used across all rules for quick reference.

| Rule ID | Parameter | Default value |
|---|---|---|
| POC_001 | Max POCs per cable (standard) | 11 |
| POC_001 | Max POCs per cable (aerial) | 22 |
| POC_002 | Max demand-point connections per POC | 8 |
| POC_003 | Max left-side connections per POC | 4 |
| POC_003 | Max right-side connections per POC | 4 |
| POC_004 | Cluster membership tolerance | 1 m |
| POC_005 | Max distance between neighbour POCs | 50 m |
| POC_005 | Max combined home count | 8 |
| POC_005 | Max drop cable length | 100 m |
| POC_006 | Max aerial drop cable length | 40 m |
| POC_008 | Min separation between POCs | 1 m |
| POC_009 | Max POC offset from building centre | 0.5 m |
| OVERLAP_001 | Min parallel overlap to flag | 50 m |
| OVERLAP_001 | Min same-IDENTIFIER shared route to flag | 20 m |
| OVERLAP_001 | Max lateral separation for "parallel" | 2 m |
| OVERLAP_003/4/5 | Min cluster overlap area to flag | 10 m² |
| PRIMARY_001 | Max cables leaving a PDP | 8 |
| PRIMARY_001 | Min primary cables per PDP | 3 |
| PRIMARY_003 | Cable-split topology tolerance | 1 m |
| FEEDER_001 | Max feeder cable length | 50 m |
| FEEDER_003 | Required feeder cable count | 6 |
| FEEDER_003 | Required fibre granularity | 192 fibres |
| FEEDER_004 | Max homes per Central Office | 1 024 |
| DISTRIBUTION_001 | Max cables leaving a DP | 5 |
| DISTRIBUTION_002 | Max façade cable length | 500 m |
| DISTRIBUTION_003 | Max POCs per aerial cable | 22 |
| DISTRIBUTION_003 | Max drop connections per POC | 4 |
| DISTRIBUTION_005 | Max façade underground section | 40 m |
| DISTRIBUTION_006 | Max parallel aerial cables | 2 |
| DISTRIBUTION_008 | Max façade total underground length | 60 m |
| DISTRIBUTION_009 | DP-to-cluster boundary buffer | 2 m |
| DISTRIBUTION_012 | Cable-split topology tolerance | 1 m |
| DATA_Q_001 | Max length for `Doorsteek (1m diep)` | 8 m |
| CROSS_001 | Perpendicular angle range | 75°–105° |
| CROSS_001 | Parallel angle range | 0°–15° / 165°–180° |
| CROSS_003 | Min separation between crossings | 50 m |
| CROSS_004 | Max road width before flagging | 15 m |
| (global) | Max violations shown on map per rule | 5 |
