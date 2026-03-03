import os
from qgis.core import (  # type: ignore
    QgsVectorLayer, QgsFillSymbol, QgsSingleSymbolRenderer,
    QgsPalLayerSettings, QgsTextFormat, QgsUnitTypes,
    QgsVectorLayerSimpleLabeling
    )
from PyQt5.QtGui import QColor, QFont


def apply_style_from_qml(layer, qml_path):
    """Apply style from QML file"""
    if os.path.exists(qml_path):
        success = layer.loadNamedStyle(qml_path)
        if success:
            layer.triggerRepaint()
        else:
            apply_violation_style(layer)  # Fallback
    else:
        apply_violation_style(layer)  # Fallback

def apply_violation_style(layer):
    """Apply transparent buffer with red boundaries style to the layer"""
    try:
        # Create symbol with transparent red fill and solid red border
        symbol = QgsFillSymbol.createSimple({
            'color': '255,0,0,40',
            'color_border': '255,0,0,255',
            'width_border': '0.8',
            'style': 'solid',
            'style_border': 'solid'
        })
        
        # Create renderer and apply to layer
        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)
        
        # Commit changes and trigger repaint
        layer.triggerRepaint()
        #print("Style applied successfully to violation layer")
        
    except Exception as e:
        #print(f"Error applying style: {str(e)}")
        # Fallback: use simple styling
        layer.loadNamedStyle('')  # Reset any existing style
        layer.triggerRepaint()

def setup_labels(layer):
    """Setup labels for the given QGIS vector layer using the 'details' attribute.

    Args:
        layer (QgsVectorLayer): The vector layer to configure labels for.

    Returns:
        bool: True if labels were configured successfully, False otherwise.
    """
    try:
        # Check if layer is valid and is a vector layer
        if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            #print("Error: Invalid or non-vector layer provided")
            return False

        # Verify that the 'details' field exists
        if 'details' not in [field.name() for field in layer.fields()]:
            #print("Error: 'details' field not found in layer attributes")
            return False

        # Label settings
        settings = QgsPalLayerSettings()
        settings.fieldName = 'details'
        settings.isExpression = False

        # Configure text format
        text_format = QgsTextFormat()
        text_format.setSize(8)
        text_format.setSizeUnit(QgsUnitTypes.RenderPoints)  # Explicitly set to points
        text_format.setColor(QColor(0, 0, 0))  # Red labels

        # Use QFont to make text bold and set a font family
        font = QFont("Arial", 28)  # Specify font family for consistency
        font.setBold(True)
        text_format.setFont(font)

        settings.setFormat(text_format)

        # Dynamic placement based on geometry type
        geometry_type = layer.geometryType()
        if geometry_type == 0:  # Point
            settings.placement = QgsPalLayerSettings.OverPoint
            settings.quadOffset = QgsPalLayerSettings.QuadrantAbove
        elif geometry_type == 1:  # Line
            settings.placement = QgsPalLayerSettings.Line
        elif geometry_type == 2:  # Polygon
            settings.placement = QgsPalLayerSettings.AroundPoint
        else:
            #print("Warning: Unknown geometry type, using default placement")
            settings.placement = QgsPalLayerSettings.OverPoint

        # Set label priority (0-10, higher is more important)
        settings.priority = 5  # Moderate priority for labels

        # Apply labeling
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)

        # Trigger repaint (note: layer must be added to a map canvas)
        layer.triggerRepaint()

        return True

    except Exception as e:
        print(f"Error setting up labels: {str(e)}")
        return False