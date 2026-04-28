import os
from collections import defaultdict
from qgis.core import QgsFields, QgsField, QgsFeature, QgsVectorLayer, QgsVectorFileWriter, QgsProject # type: ignore
from qgis.PyQt.QtCore import QVariant # type: ignore
from qgis.PyQt.QtGui import QColor # type: ignore
from .extract_design_session import extract_design_session_name
from .violation_details import get_violation_details
from .styling_methods import apply_style_from_qml, setup_labels


def create_violation_shapefile(run_output_directory, violations, feature, project_path, iface=None, color=None):
    """Create a violation shapefile containing every violation for a feature type.

    All violations with valid geometry are written. Each feature carries a
    'total_cnt' attribute recording how many times that violation_type occurred
    in total. Label crowding is handled at render time via scale-dependent
    labels in setup_labels() (labels only appear when zoomed in).
    """
    if not violations:
        return None

    # Create fields for the shapefile
    # Shapefile DBF limits field names to 10 characters — keep them short
    # so the saved layer exposes the exact names the label expression expects.
    fields = QgsFields()
    fields.append(QgsField('rule_id', QVariant.String))
    fields.append(QgsField('descr', QVariant.String))
    fields.append(QgsField('vio_type', QVariant.String))
    fields.append(QgsField('details', QVariant.String))
    fields.append(QgsField('total_cnt', QVariant.Int))

    # --- Group violations by violation_type, keeping only those with geometry ---
    type_violations = defaultdict(list)
    for violation in violations:
        if 'geometry' not in violation or violation['geometry'] is None:
            continue
        vtype = violation.get('violation_type', 'unknown')
        type_violations[vtype].append(violation)

    # Cap the shapefile at 5 violations to keep the map readable.
    # Round-robin across violation types so each type gets representation
    # before we take a second sample from the same type. The PDF report is
    # generated separately and still includes every violation.
    MAX_VIOLATIONS_PER_SHAPEFILE = 5
    type_totals = {vtype: len(vlist) for vtype, vlist in type_violations.items()}
    remaining = {vtype: list(vlist) for vtype, vlist in type_violations.items()}
    violations_to_display = []
    while remaining and len(violations_to_display) < MAX_VIOLATIONS_PER_SHAPEFILE:
        for vtype in list(remaining.keys()):
            if not remaining[vtype]:
                del remaining[vtype]
                continue
            v = remaining[vtype].pop(0)
            violations_to_display.append((v, type_totals[vtype]))
            if len(violations_to_display) >= MAX_VIOLATIONS_PER_SHAPEFILE:
                break

    # Create memory layer
    vl = QgsVectorLayer("Polygon", f"Design Violations - {feature}", "memory")
    pr = vl.dataProvider()

    project_crs = QgsProject.instance().crs()
    vl.setCrs(project_crs)

    pr.addAttributes(fields)
    vl.updateFields()

    for violation, total_count in violations_to_display:
        geom = violation['geometry']
        geom_type = geom.type()
        # Apply buffer based on geometry type:
        # Points (0) need a larger buffer to be visible
        # Lines (1) need a moderate buffer to create a corridor
        # Polygons (2) already have area, just a slight expansion
        if geom_type == 0:      # Point
            buffer_geometry = geom.buffer(2.0, 8)
        elif geom_type == 1:    # Line
            buffer_geometry = geom.buffer(1.0, 5)
        else:                   # Polygon
            buffer_geometry = geom.buffer(0.5, 5)

        if buffer_geometry is None or buffer_geometry.isEmpty():
            continue

        feat = QgsFeature()
        feat.setGeometry(buffer_geometry)

        violation_details = get_violation_details(violation)
        # Prefer the rule_id set on the violation itself (matches PDF report),
        # falling back to the one derived from violation_type.
        rule_id = violation.get('rule_id') or violation_details.get('rule_id', 'UNKNOWN')
        # Prepend the rule_id to the details text so map labels show it directly,
        # without needing a QGIS expression.
        details_text = f"[{rule_id}] {violation_details.get('details', 'No details')}"
        feat.setAttributes([
            rule_id,
            violation_details.get('description', 'No description'),
            violation_details.get('violation_type', 'unknown'),
            details_text,
            total_count
        ])

        pr.addFeature(feat)

    vl.updateExtents()

    # Save to shapefile
    violation_layer_name = f"{extract_design_session_name(project_path)}_{feature}.shp"
    output_path = os.path.join(run_output_directory, violation_layer_name)
    error = QgsVectorFileWriter.writeAsVectorFormat(
        vl, output_path, "UTF-8", project_crs, "ESRI Shapefile"
    )

    if error[0] == 0:
        #print(f"Violation shapefile created: {output_path}")

        # Optionally add to QGIS project if iface is provided
        if iface:
            violation_layer = QgsVectorLayer(output_path, f"Design Violations - {feature}", "ogr")
            if violation_layer.isValid():
                apply_style_from_qml(violation_layer, os.path.join(os.path.dirname(__file__), '..', 'styles', 'violation_style.qml'))
                setup_labels(violation_layer)
                if color:
                    renderer = violation_layer.renderer()
                    symbol = renderer.symbol()
                    fill_color = QColor(color.red(), color.green(), color.blue(), 30)
                    symbol.setColor(fill_color)
                    symbol.symbolLayer(0).setStrokeColor(
                        QColor(color.red(), color.green(), color.blue(), 220)
                    )
                    violation_layer.triggerRepaint()
                QgsProject.instance().addMapLayer(violation_layer)
                canvas = iface.mapCanvas()
                canvas.setExtent(violation_layer.extent())
                canvas.refresh()
        return output_path
    else:
        #print(f"Error creating violation shapefile: {error}")
        return None