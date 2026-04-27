from qgis.core import (  # type: ignore
    QgsProject, QgsVectorLayer, QgsLineSymbol, QgsUnitTypes,
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsFillSymbol,
    QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
    QgsVectorLayerSimpleLabeling, QgsRuleBasedRenderer, QgsLayerTreeLayer
)
from qgis.PyQt.QtGui import QColor, QFont  # type: ignore
from qgis.PyQt.QtCore import Qt  # type: ignore
import os
from datetime import date


# ── Layer registry (key → loader metadata) ────────────────────────────────────
# Keys must match the keys in LAYER_CATALOGUE inside external_maps_dialog.py.
_WFS_REGISTRY = {
    "grb_adp": {
        "name": "GRB - ADP - administratief perceel",
        "uri": (
            "pagingEnabled='true' preferCoordinatesForWfsT11='false' "
            "restrictToRequestBBOX='1' srsname='EPSG:31370' typename='GRB:ADP' "
            "url='https://geo.api.vlaanderen.be/GRB/wfs' version='auto'"
        ),
    },
    "beschermde_monumenten": {
        "name": "Beschermde monumenten",
        "uri": (
            "pagingEnabled='true' preferCoordinatesForWfsT11='false' "
            "restrictToRequestBBOX='1' srsname='EPSG:31370' typename='ps:ps_bes_monument' "
            "url='https://www.mercator.vlaanderen.be/raadpleegdienstenmercatorpubliek/ows' version='auto'"
        ),
    },
    "verkavelingen": {
        "name": "Omgevingsloket - Verkavelingen - V2",
        "uri": (
            "pagingEnabled='default' preferCoordinatesForWfsT11='false' "
            "restrictToRequestBBOX='1' srsname='EPSG:31370' typename='lu:lu_omv_vk_v2' "
            "url='https://www.mercator.vlaanderen.be/raadpleegdienstenmercatorpubliek/ows?count=1' "
            "url='https://www.mercator.vlaanderen.be/raadpleegdienstenmercatorpubliek/ows?version=2.0.0&typeName=lu:lu_omv_vk_v2&count=1' "
            "version='auto'"
        ),
    },
    "gipod": {
        "name": "GIPOD - inname openbaar domein",
        "uri": (
            "pagingEnabled='true' preferCoordinatesForWfsT11='false' "
            "restrictToRequestBBOX='1' srsname='EPSG:31370' typename='GIPOD:INNAME' "
            "url='https://geo.api.vlaanderen.be/GIPOD/wfs' version='auto'"
        ),
    },
    "grb_wgo": {
        "name": "GRB - WGO - wegopdeling",
        "uri": (
            "pagingEnabled='default' preferCoordinatesForWfsT11='false' "
            "restrictToRequestBBOX='1' srsname='EPSG:31370' typename='GRB:WGO' "
            "url='https://geo.api.vlaanderen.be/GRB/wfs' version='auto'"
        ),
    },
}


def add_external_wfs_layers(log_message_func, selected_keys=None):
    """
    Adds selected external WFS layers to the current QGIS project (hidden by default).
    Organises them in a 'WFS Layers' group positioned above any existing WMS layers.

    Args:
        log_message_func: callable(message: str, level: str) for status reporting.
        selected_keys:    list of layer keys to load (from _WFS_REGISTRY).
                          Loads all layers when None.
    """
    if selected_keys is None:
        selected_keys = list(_WFS_REGISTRY.keys())

    wfs_layers_to_add = [
        _WFS_REGISTRY[key] for key in selected_keys if key in _WFS_REGISTRY
    ]

    if not wfs_layers_to_add:
        log_message_func("No layers selected.", "WARNING")
        return [], []

    project = QgsProject.instance()
    root = project.layerTreeRoot()
    loaded = []
    failed = []

    # Position the WFS group above the highest WMS layer (or at the bottom if none)
    target_position = len(root.children())
    for i in range(len(root.children())):
        child = root.children()[i]
        if isinstance(child, QgsLayerTreeLayer):
            layer = child.layer()
            if layer:
                provider = layer.dataProvider()
                if provider:
                    provider_name = provider.name().lower()
                    provider_type = layer.providerType().lower()
                    if 'wms' in provider_name or 'wms' in provider_type:
                        target_position = i
                        log_message_func(f"Found WMS layer at position {i}: '{layer.name()}'", "INFO")
                        break

    # Re-create the WFS group at the correct position
    wfs_group_name = "WFS Layers"
    existing_group = root.findGroup(wfs_group_name)
    if existing_group:
        root.removeChildNode(existing_group)

    wfs_group = root.insertGroup(target_position, wfs_group_name)
    log_message_func(f"Created '{wfs_group_name}' group at position {target_position}", "INFO")

    for layer_info in wfs_layers_to_add:
        layer = QgsVectorLayer(layer_info["uri"], layer_info["name"], "wfs")
        if not layer.isValid():
            log_message_func(
                f"Failed to load WFS layer: '{layer_info['name']}'. Check connection and service details.",
                "ERROR",
            )
            failed.append(layer_info["name"])
            continue

        project.addMapLayer(layer, False)
        node = wfs_group.insertLayer(-1, layer)
        if node:
            node.setItemVisibilityChecked(False)

        name = layer_info["name"]
        if name == "Omgevingsloket - Verkavelingen - V2":
            apply_verkavelingen_symbology(layer)
            log_message_func(f"Added WFS layer with symbology (hidden): '{name}'", "SUCCESS")
        elif name == "GIPOD - inname openbaar domein":
            apply_gipod_symbology(layer, log_message_func)
            log_message_func(f"Added WFS layer with symbology (hidden): '{name}'", "SUCCESS")
        else:
            log_message_func(f"Added WFS layer (hidden): '{name}'", "SUCCESS")
        loaded.append(name)

    return loaded, failed


def apply_verkavelingen_symbology(layer):
    """
    Apply categorized fill symbology and English labels to the Verkavelingen layer.
    """
    try:
        field_name = 'huidige_toestand'
        categories = {
            'Geen beslissing genomen':               ('#D3D3D3', 'No decision taken'),
            'In behandeling (in eerste aanleg)':     ('#FFD700', 'Under consideration - first instance'),
            'In behandeling (na beroep)':            ('#FFA500', 'Under consideration - after appeal'),
            'Stopgezet':                             ('#9370DB', 'Discontinued'),
            'Vergunning':                            ('#32CD32', 'Permit/Approval'),
            'Weigering':                             ('#FF0000', 'Refusal'),
        }

        renderer = QgsCategorizedSymbolRenderer(field_name)
        for dutch_value, (color_hex, english_text) in categories.items():
            symbol = QgsFillSymbol.createSimple({
                'color': color_hex,
                'outline_color': 'black',
                'outline_width': '0.3',
            })
            renderer.addCategory(QgsRendererCategory(dutch_value, symbol, english_text))
        layer.setRenderer(renderer)

        label_settings = QgsPalLayerSettings()
        label_settings.enabled = True
        label_settings.fieldName = """CASE
        WHEN "huidige_toestand" = 'Geen beslissing genomen' THEN 'No decision taken'
        WHEN "huidige_toestand" = 'In behandeling (in eerste aanleg)' THEN 'Under consideration - first instance'
        WHEN "huidige_toestand" = 'In behandeling (na beroep)' THEN 'Under consideration - after appeal'
        WHEN "huidige_toestand" = 'Stopgezet' THEN 'Discontinued'
        WHEN "huidige_toestand" = 'Vergunning' THEN 'Permit/Approval'
        WHEN "huidige_toestand" = 'Weigering' THEN 'Refusal'
        ELSE "huidige_toestand"
        END"""
        label_settings.isExpression = True

        text_format = QgsTextFormat()
        font = QFont("Arial", 10)
        font.setBold(True)
        text_format.setFont(font)
        text_format.setSize(10)
        text_format.setColor(QColor('black'))

        buffer_settings = QgsTextBufferSettings()
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(1.2)
        buffer_settings.setColor(QColor('white'))
        text_format.setBuffer(buffer_settings)

        label_settings.setFormat(text_format)
        label_settings.placement = QgsPalLayerSettings.AroundPoint
        label_settings.dist = 0
        label_settings.centroidInside = True
        label_settings.centroidWhole = True

        layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))
        layer.setLabelsEnabled(True)
        layer.triggerRepaint()
        return True
    except Exception as e:
        print(f"Could not apply Verkavelingen symbology: {e}")
        return False


def apply_gipod_symbology(layer, log_message_func):
    """
    Apply rule-based symbology to the GIPOD layer, filtering to 'Grondwerk' type only.

    Rules (based on Status and End date):
      - Red:    Uitgevoerd AND End within last 5 years  → Constructed - Closed
      - Yellow: Uitgevoerd AND End older than 5 years   → Constructed - Open
      - Green:  In uitvoering OR Concreet gepland        → Open
    """
    try:
        field_names = [field.name() for field in layer.fields()]
        log_message_func(f"GIPOD available fields: {field_names}", "INFO")

        layer.setSubsetString("\"Type\" = 'Grondwerk'")
        log_message_func("Applied filter: Type = 'Grondwerk'", "INFO")

        current_date = date.today()
        five_years_ago = date(current_date.year - 5, current_date.month, current_date.day)
        five_years_ago_str = five_years_ago.strftime('%Y-%m-%d')

        root_rule = QgsRuleBasedRenderer.Rule(None)

        root_rule.appendChild(QgsRuleBasedRenderer.Rule(
            _fill_symbol(QColor('red')),
            filterExp=f"\"Status\" = 'Uitgevoerd' AND \"End\" >= '{five_years_ago_str}'",
            label="Constructed - Closed",
        ))
        root_rule.appendChild(QgsRuleBasedRenderer.Rule(
            _fill_symbol(QColor('yellow')),
            filterExp=f"\"Status\" = 'Uitgevoerd' AND \"End\" < '{five_years_ago_str}'",
            label="Constructed - Open",
        ))
        root_rule.appendChild(QgsRuleBasedRenderer.Rule(
            _fill_symbol(QColor('green')),
            filterExp="\"Status\" IN ('In uitvoering', 'Concreet gepland')",
            label="Open",
        ))

        layer.setRenderer(QgsRuleBasedRenderer(root_rule))
        layer.triggerRepaint()

        layer_node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
        if layer_node:
            layer_node.setItemVisibilityChecked(False)

        log_message_func("Applied rule-based symbology to GIPOD layer", "SUCCESS")

    except Exception as e:
        log_message_func(f"Error applying GIPOD symbology: {e}", "ERROR")
        import traceback
        log_message_func(f"Traceback: {traceback.format_exc()}", "ERROR")


def _fill_symbol(color):
    """Create a simple fill symbol with the given QColor."""
    return QgsFillSymbol.createSimple({
        'color': color.name(),
        'outline_color': 'black',
        'outline_width': '0.5',
    })
