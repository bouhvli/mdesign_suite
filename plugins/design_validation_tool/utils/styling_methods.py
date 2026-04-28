import os
from qgis.core import (  # type: ignore
    QgsVectorLayer, QgsFillSymbol, QgsSingleSymbolRenderer,
    QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings, QgsUnitTypes,
    QgsVectorLayerSimpleLabeling,
)
from PyQt5.QtGui import QColor, QFont


def apply_style_from_qml(layer, qml_path):
    if os.path.exists(qml_path):
        if layer.loadNamedStyle(qml_path):
            layer.triggerRepaint()
            return
    apply_violation_style(layer)


def apply_violation_style(layer):
    """Semi-transparent fill with a solid border. Colour is overridden per feature
    type by shape_file_creation.py after this function runs."""
    try:
        symbol = QgsFillSymbol.createSimple({
            'color': '255,0,0,25',
            'outline_color': '200,0,0,255',
            'outline_width': '0.8',
            'style': 'solid',
            'outline_style': 'solid',
        })
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()
    except Exception as e:
        print(f"Error applying violation style: {e}")
        layer.triggerRepaint()


def setup_labels(layer):
    """Two-line label: bold rule_id on top, plain description below.
    Only visible when zoomed in to avoid crowding the map."""
    try:
        if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            return False

        field_names = [f.name() for f in layer.fields()]
        rule_field = 'rule_id' if 'rule_id' in field_names else None
        # Accept the memory-layer name and the shapefile-truncated variants so
        # labels work whether the layer was loaded from the .shp or built in memory.
        desc_field = next(
            (n for n in ('descr', 'description', 'descriptio') if n in field_names),
            None,
        )
        if not rule_field or not desc_field:
            return False

        settings = QgsPalLayerSettings()
        settings.fieldName = (
            f"coalesce(\"{rule_field}\", '') || '  ' || coalesce(\"{desc_field}\", '')"
        )
        settings.isExpression = True

        font = QFont("Arial", 9, QFont.Bold)

        text_format = QgsTextFormat()
        text_format.setFont(font)
        text_format.setSize(9)
        text_format.setSizeUnit(QgsUnitTypes.RenderPoints)
        text_format.setColor(QColor(30, 30, 30))

        halo = QgsTextBufferSettings()
        halo.setEnabled(True)
        halo.setSize(1.0)
        halo.setSizeUnit(QgsUnitTypes.RenderMillimeters)
        halo.setColor(QColor(255, 255, 255, 220))
        text_format.setBuffer(halo)

        settings.setFormat(text_format)

        settings.placement = QgsPalLayerSettings.Horizontal
        settings.centroidInside = True
        settings.placeDirectionSymbol = False
        settings.multilineAlign = QgsPalLayerSettings.MultiCenter

        settings.displayAll = True
        settings.priority = 10

        # Hide labels when zoomed out, show when zoomed in.
        # Visible between 1:1 (very close) and 1:10000.
        settings.scaleVisibility = True
        settings.minimumScale = 10000
        settings.maximumScale = 1

        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)
        layer.triggerRepaint()

        return True

    except Exception as e:
        print(f"Error setting up labels: {e}")
        return False
