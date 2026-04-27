import os
from qgis.core import QgsFields, QgsField, QgsFeature, QgsVectorLayer, QgsVectorFileWriter, QgsProject # type: ignore
from qgis.PyQt.QtCore import QVariant # type: ignore
from .extract_design_session import extract_design_session_name
from .violation_details import get_violation_details
from .styling_methods import apply_style_from_qml, setup_labels

def create_violation_shapefile(run_output_directory, violations, feature, project_path, iface=None, color=None):
    """Create violation shapefile with bounding boxes of violations for a specific feature type"""
    if not violations:
        return None

    # Create fields for the shapefile
    fields = QgsFields()
    fields.append(QgsField('rule_id', QVariant.String))
    fields.append(QgsField('description', QVariant.String))
    fields.append(QgsField('violation_type', QVariant.String))
    fields.append(QgsField('details', QVariant.String))

    # Create memory layer
    vl = QgsVectorLayer("Polygon", f"Design Violations - {feature}", "memory")
    pr = vl.dataProvider()

    project_crs = QgsProject.instance().crs()
    vl.setCrs(project_crs)

    pr.addAttributes(fields)
    vl.updateFields()

    # Add features
    for violation in violations:
        if 'geometry' not in violation or violation['geometry'] is None:
            continue

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
        feat.setAttributes([
            violation_details.get('rule_id', 'UNKNOWN'),
            violation_details.get('description', 'No description'),
            violation_details.get('violation_type', 'unknown'),
            violation_details.get('details', 'No details')
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
                    symbol.setColor(color)
                    symbol.setOpacity(0.2)
                    violation_layer.triggerRepaint()
                QgsProject.instance().addMapLayer(violation_layer)
                canvas = iface.mapCanvas()
                canvas.setExtent(violation_layer.extent())
                canvas.refresh()
        return output_path
    else:
        #print(f"Error creating violation shapefile: {error}")
        return None