from qgis.core import ( # type: ignore
    QgsProject, QgsVectorLayer, QgsLineSymbol, QgsUnitTypes
)
from qgis.PyQt.QtGui import QColor # type: ignore
from qgis.PyQt.QtCore import Qt # type: ignore
import os

def add_external_wfs_layers(log_message_func):
    """
    Adds predefined external WFS layers to the current QGIS project with visibility turned off.

    Args:
        log_message_func (function): A function to call for logging messages (e.g., self.log_message).
    """
    project = QgsProject.instance()
    root = project.layerTreeRoot()

    wfs_layers_to_add = [
        {
            "name": "GRB - ADP - administratief perceel",
            "uri": "pagingEnabled='true' preferCoordinatesForWfsT11='false' restrictToRequestBBOX='1' srsname='EPSG:31370' typename='GRB:ADP' url='https://geo.api.vlaanderen.be/GRB/wfs' version='auto'"
        },
        {
            "name": "Beschermde monumenten",
            "uri": "pagingEnabled='true' preferCoordinatesForWfsT11='false' restrictToRequestBBOX='1' srsname='EPSG:31370' typename='ps:ps_bes_monument' url='https://www.mercator.vlaanderen.be/raadpleegdienstenmercatorpubliek/ows' version='auto'"
        }
    ]
    
    for layer_info in wfs_layers_to_add:
        layer = QgsVectorLayer(layer_info["uri"], layer_info["name"], "wfs")
        if layer.isValid():
            project.addMapLayer(layer, False)
            # Add layer to the bottom of the layer tree and get its node
            node = root.insertLayer(-1, layer)
            # Set the layer's visibility to off by default
            if node:
                node.setItemVisibilityChecked(False)
            log_message_func(f"Successfully added WFS layer (hidden): '{layer_info['name']}'", "SUCCESS")
        else:
            log_message_func(f"Failed to load WFS layer: '{layer_info['name']}'. Check connection and service details.", "ERROR")

def import_external_maps(layer_name='Possible trench routes'):
    """Get QGIS layer by name. If not in project, load from project folder using predefined paths."""

    # First check if layer exists in current QGIS project
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if layers:
        # print(f"✓ Found layer '{layer_name}' in QGIS project")
        return layers[0]
    
    # Layer not found in project, check if we have a path defined for it
    layer_paths = {
        'Possible trench routes': '/input/IN_PossibleTrenches.shp',
    }
    
    if layer_name not in layer_paths:
        #print(f"✗ Layer '{layer_name}' not found in project and no path defined in layer_paths")
        return None
    
    project = QgsProject.instance()
    project_path = project.fileName()
    
    if not project_path:
        #print(f"⚠ Project is not saved - cannot resolve relative paths for layer '{layer_name}'")
        return None
    
    # Get project directory
    project_dir = os.path.dirname(project_path)
    
    # Get the relative path from layer_paths
    relative_path = layer_paths[layer_name]
    
    # Remove leading slash to make it relative to project directory
    if relative_path.startswith('/'):
        relative_path = relative_path[1:]
    
    # Build absolute path
    absolute_path = os.path.normpath(os.path.join(project_dir, relative_path))
    
    #print(f"Looking for layer '{layer_name}' at: {absolute_path}")
    
    # Check if the file actually exists
    if not os.path.exists(absolute_path):
        #print(f"✗ File not found for layer '{layer_name}' at: {absolute_path}")
        
        # Try alternative path resolution - maybe the project is in a different location
        # Check if we're in a subdirectory and need to go up one level
        parent_dir = os.path.dirname(project_dir)
        alternative_path = os.path.normpath(os.path.join(parent_dir, relative_path))
        
        if os.path.exists(alternative_path):
            #print(f"✓ Found layer '{layer_name}' at alternative path: {alternative_path}")
            absolute_path = alternative_path
        else:
            #print(f"✗ Could not find layer '{layer_name}' at any expected location")
            return None

    # Load the layer without filter initially
    layer = QgsVectorLayer(absolute_path, layer_name, "ogr")
    
    if not layer.isValid():
        #print(f"✗ Failed to load layer '{layer_name}' - invalid layer")
        return None
    
    #print(f"✓ Successfully loaded layer '{layer_name}'")
    
    # Apply custom red symbology
    apply_red_line_symbology(layer)
    
    # Add to project
    project.addMapLayer(layer, False)
    
    # Add to "Utility layers" group
    root = project.layerTreeRoot()
    utility_layers_group = root.findGroup("Utility layers")
    if not utility_layers_group:
        utility_layers_group = root.insertGroup(0, "Utility layers")
        #print("✓ Created 'Utility layers' group")

    utility_layers_group.addLayer(layer)
    #print(f"✓ Added layer '{layer_name}' to 'Utility layers' group")

    return layer


def apply_red_line_symbology(layer):
    """
    Apply custom red line symbology to a vector layer

    Args:
        layer: QgsVectorLayer to apply symbology to
    """
    try:
        # Create a simple line symbol
        symbol = QgsLineSymbol.createSimple({})

        # Set the color to red
        symbol.setColor(QColor(255, 0, 0))  # RGB for red

        # Set line width to 1.0 mm
        symbol.setWidth(1.0)

        # Set line style to solid
        symbol.setWidthUnit(QgsUnitTypes.RenderMillimeters)

        # Apply the symbol to the layer
        layer.renderer().setSymbol(symbol)

        # Trigger repaint
        layer.triggerRepaint()

        #print(f"✓ Applied red line symbology to layer '{layer.name()}'")

    except Exception as e:
        print(f"Could not apply red symbology: {e}")