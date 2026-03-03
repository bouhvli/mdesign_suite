# QGIS Design Validation Tool

A comprehensive QGIS plugin for automating the validation of fiber optic network designs against predefined business and technical rules.

## 🔍 Overview

The Design Validation Tool is a QGIS plugin that provides automated validation capabilities for fiber optic network infrastructure designs.

## ✨ Key Features

- **Unified Interface**: Access all validation features from a single plugin interface.
- **POC Clustering Validation**: Automated validation of Points of Connection (POCs) against business rules.
- **Duct Overlap & Cluster Validation**: Detects parallel duct overlaps and cluster polygon intersections.
- **Design Compliance Check**: Verify designs against technical standards and business rules.
- **Reporting & Export**: Generate detailed validation reports in CSV, HTML, and PDF formats.
- **Violation Shapefiles**: Automatically creates shapefiles for each feature type with dynamic color and opacity styling.

### Manual Installation
1. Download the plugin files.
2. Copy to your QGIS plugins directory:
   - Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
   - Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - macOS: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
3. Restart QGIS.
4. Enable the plugin in `Plugins` → `Manage and Install Plugins`.

## Available Features

### 🎯 POC Clustering Validation
**Purpose**: Validates Points of Connection (POCs) against critical business and technical rules for fiber optic network designs.

**Required Input Layers**:
- **POC Layer (Drop point)**: Point layer representing Points of Connection.
- **Drop Cable Layer**: Line layer representing cables connecting to POCs.
- **Closure Layer**: Point layer for identifying assignments between drop points and demand points.

**Validation Rules**:
- **DROP_01**: Maximum POCs in Line (no single daisy-chained drop cable connects more than 11 POCs).
- **DROP_02**: Maximum Connections per POC (no individual POC has more than 8 drop cables connected).
- **DROP_03**: Connections per Side (UG/Facade) (no POC has more than 4 underground or facade connections on either "left" or "right" side).

### 🟦 Overlapping & Cluster Validation
**Purpose**: Detects spatial overlaps in duct and cluster layers.

**Rules**:
- **OVERLAP_001**: Flags parallel duct overlaps within the same layer (Primary, Distribution, Drop Ducts).
- **OVERLAP_002**: Detects oversized ducts serving endpoints.
- **OVERLAP_003**: Flags overlaps between Primary Distribution Clusters.
- **OVERLAP_004**: Flags overlaps between Distribution Clusters.
- **OVERLAP_005**: Flags overlaps between Drop Clusters.

**Outputs**:
- **Violation Shapefiles**: 
  - Polygon features representing bounding boxes of rule violations.
  - Dynamic color styling (e.g., red for POC, blue for overlapping) and opacity (20%).
  - Attributes: `rule_id`, `description`, `violation_type`, `details`.
- **Validation Checklist**: 
  - Comprehensive report (CSV/HTML/PDF format).
  - Summary of all rules with Pass/Fail status.
  - List of specific features that failed validation.

## Project Structure

```
design_validation_tool/
├── core/                   # Core business logic and functionality
│   ├── validation_engine.py        # Main validation logic coordinator
│   ├── rule_processor.py          # Business rule processing engine
│   └── geometry_validator.py      # Spatial geometry validation
├── features/              # Individual feature implementations
│   ├── poc_clustering/            # POC clustering validation
│   │   ├── poc_validator.py       # POC validation logic
│   │   └── poc_rules.py           # POC-specific rules
│   ├── overlapping/              # Duct and cluster overlap validation
│   │   └── overlapping_validator.py
│   └── base_feature.py           # Abstract base class for features
├── models/                # Data models and structures
│   ├── network_models.py         # Fiber network component models
│   ├── validation_models.py      # Validation rule and result models
│   └── report_models.py          # Report and output models
├── processing/            # QGIS Processing framework algorithms
├── utils/                 # Utility functions and helpers
├── data/                  # Default data and templates
├── images/                # Image assets and icons
├── test/                  # Testing files and test cases
├── help/                  # Documentation and help files
├── i18n/                  # Internationalization files
├── scripts/               # Development and deployment scripts
├── design_validation_tool.py         # Main plugin class
├── design_validation_tool_dialog.py  # Main dialog implementation
├── metadata.txt           # Plugin metadata
├── icon.png               # Plugin icon
└── README.md              # This file
```

## 🔧 Requirements

- **QGIS Version**: 3.0 or higher
- **Python**: 3.6+
- **Required Layers for Validation**:
  - POC Layer (point geometry)
  - Drop Cable Layer (line geometry)
  - Closure Layer (point geometry)
  - Duct and Cluster Layers (polygon/line geometry)
- **Dependencies**: Listed in requirements.txt 

## 👥 Authors

**Hamza Bouhali & Musa Haruna**  
*M.design solutions*

📧 **Contact**: info@mdesignsolutions.be

## 🙏 Acknowledgments

- QGIS Development Team for the excellent GIS platform
- Contributors and testers
- Fiber optic industry experts who provided domain knowledge

## 📊 Version History

- **v0.1** (Current) - Initial development version
  - Project structure setup
  - POC clustering validation framework
  - Duct and cluster overlap validation
  - Dynamic violation shapefile styling

---

*For more information, contact us