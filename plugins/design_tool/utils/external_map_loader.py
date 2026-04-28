from qgis.core import ( # type: ignore
    QgsProject, QgsVectorLayer, QgsLineSymbol, QgsUnitTypes, 
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsFillSymbol,
    QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
    QgsVectorLayerSimpleLabeling, QgsRuleBasedRenderer, QgsLayerTreeLayer
)
from qgis.PyQt.QtGui import QColor, QFont # type: ignore
from qgis.PyQt.QtCore import Qt # type: ignore
import os
from datetime import date

def add_external_wfs_layers(log_message_func):
    """
    Adds predefined external WFS layers to the current QGIS project with visibility turned off.
    Organizes layers in a group positioned at the base (bottom) or above existing WMS layers.
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
        },
        {
            "name": "Omgevingsloket - Verkavelingen - V2",
            "uri": "pagingEnabled='default' preferCoordinatesForWfsT11='false' restrictToRequestBBOX='1' srsname='EPSG:31370' typename='lu:lu_omv_vk_v2' url='https://www.mercator.vlaanderen.be/raadpleegdienstenmercatorpubliek/ows?count=1' url='https://www.mercator.vlaanderen.be/raadpleegdienstenmercatorpubliek/ows?version=2.0.0&typeName=lu:lu_omv_vk_v2&count=1' version='auto'"
        },
        {
            "name": "GIPOD - inname openbaar domein",
            "uri": "pagingEnabled='true' preferCoordinatesForWfsT11='false' restrictToRequestBBOX='1' srsname='EPSG:31370' typename='GIPOD:INNAME' url='https://geo.api.vlaanderen.be/GIPOD/wfs' version='auto'"
        },
        {
            "name": "GRB - WGO - wegopdeling",
            "uri": "pagingEnabled='default' preferCoordinatesForWfsT11='false' restrictToRequestBBOX='1' srsname='EPSG:31370' typename='GRB:WGO' url='https://geo.api.vlaanderen.be/GRB/wfs' version='auto'"
        }
    ]

    # Strategy: Find where to position the WFS group
    target_position = len(root.children())  # Default: at the bottom
    
    # Look for the first WMS layer from the TOP DOWN
    # This ensures we position above the highest WMS layer
    for i in range(len(root.children())):
        child = root.children()[i]
        if isinstance(child, QgsLayerTreeLayer):
            layer = child.layer()
            if layer:
                provider = layer.dataProvider()
                if provider:
                    provider_name = provider.name().lower()
                    provider_type = layer.providerType().lower()
                    if ('wms' in provider_name or 
                        'wms' in provider_type or
                        provider_name == 'wms' or
                        provider_type == 'wms'):
                        target_position = i  # Position above this WMS layer
                        log_message_func(f"Found WMS layer at position {i}: '{layer.name()}'", "INFO")
                        break

    # Create or get WFS group - do this AFTER determining position
    wfs_group_name = "WFS Layers"
    wfs_group = root.findGroup(wfs_group_name)

    if wfs_group:
        # If group exists, remove it first
        root.removeChildNode(wfs_group)
        # The old wfs_group object is now invalid, so we need to recreate it
        wfs_group = None

    # Create new group at the correct position
    wfs_group = root.insertGroup(target_position, wfs_group_name)
    log_message_func(f"Created WFS group at position {target_position}: '{wfs_group_name}'", "INFO")

    # Add WFS layers to the group
    for layer_info in wfs_layers_to_add:
        layer = QgsVectorLayer(layer_info["uri"], layer_info["name"], "wfs")
        if layer.isValid():
            project.addMapLayer(layer, False)
            # Add layer to the WFS group and get its node
            node = wfs_group.insertLayer(-1, layer)
            # Set the layer's visibility to off by default
            if node:
                node.setItemVisibilityChecked(False)
            
            # Apply symbology to "Omgevingsloket - Verkavelingen - V2" layer
            if layer_info["name"] == "Omgevingsloket - Verkavelingen - V2":
                apply_verkavelingen_symbology(layer)
                log_message_func(f"Successfully added WFS layer with symbology (hidden): '{layer_info['name']}'", "SUCCESS")
            elif layer_info["name"] == "GIPOD - inname openbaar domein":
                apply_gipod_symbology(layer, log_message_func)
            else:
                log_message_func(f"Successfully added WFS layer (hidden): '{layer_info['name']}'", "SUCCESS")
        else:
            log_message_func(f"Failed to load WFS layer: '{layer_info['name']}'. Check connection and service details.", "ERROR")

def apply_verkavelingen_symbology(layer):
    """
    Apply categorized symbology and English labels to the Verkavelingen layer
    Args:
        layer: QgsVectorLayer to apply symbology to
    """
    try:
        # Field name
        field_name = 'huidige_toestand'

        # Categories: Dutch value → (color, English legend + label text)
        categories = {
            'Geen beslissing genomen': ('#D3D3D3', 'No decision taken'),
            'In behandeling (in eerste aanleg)': ('#FFD700', 'Under consideration - first instance'),
            'In behandeling (na beroep)': ('#FFA500', 'Under consideration - after appeal'),
            'Stopgezet': ('#9370DB', 'Discontinued'),
            'Vergunning': ('#32CD32', 'Permit/Approval'),
            'Weigering': ('#FF0000', 'Refusal')
        }

        # Create categorized renderer (legend will show English)
        renderer = QgsCategorizedSymbolRenderer(field_name)

        for dutch_value, (color_hex, english_text) in categories.items():
            symbol = QgsFillSymbol.createSimple({
                'color': color_hex,
                'outline_color': 'black',
                'outline_width': '0.3'
            })
            category = QgsRendererCategory(dutch_value, symbol, english_text)
            renderer.addCategory(category)

        layer.setRenderer(renderer)

        # Labels: show English translation using CASE expression
        label_settings = QgsPalLayerSettings()
        label_settings.enabled = True

        label_expression = """CASE
        WHEN "huidige_toestand" = 'Geen beslissing genomen' THEN 'No decision taken'
        WHEN "huidige_toestand" = 'In behandeling (in eerste aanleg)' THEN 'Under consideration - first instance'
        WHEN "huidige_toestand" = 'In behandeling (na beroep)' THEN 'Under consideration - after appeal'
        WHEN "huidige_toestand" = 'Stopgezet' THEN 'Discontinued'
        WHEN "huidige_toestand" = 'Vergunning' THEN 'Permit/Approval'
        WHEN "huidige_toestand" = 'Weigering' THEN 'Refusal'
        ELSE "huidige_toestand"
        END"""

        label_settings.fieldName = label_expression
        label_settings.isExpression = True

        # Label styling: bold, size 10, black text with white halo for readability
        text_format = QgsTextFormat()
        font = QFont("Arial", 10)
        font.setBold(True)
        text_format.setFont(font)
        text_format.setSize(10)
        text_format.setColor(QColor('black'))

        # White halo/buffer
        buffer_settings = QgsTextBufferSettings()
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(1.2)
        buffer_settings.setColor(QColor('white'))
        text_format.setBuffer(buffer_settings)

        label_settings.setFormat(text_format)

        # Placement: over the centroid for polygons
        label_settings.placement = QgsPalLayerSettings.AroundPoint
        label_settings.dist = 0  # Distance 0 to place over the centroid
        label_settings.centroidInside = True  # Ensure centroid is inside the polygon
        label_settings.centroidWhole = True  # Use centroid of whole multi-part feature

        # Apply labeling
        labeling = QgsVectorLayerSimpleLabeling(label_settings)
        layer.setLabeling(labeling)
        layer.setLabelsEnabled(True)

        # Refresh
        layer.triggerRepaint()
        
        return True
    except Exception as e:
        print(f"Could not apply Verkavelingen symbology: {e}")
        return False

def apply_gipod_symbology(layer, log_message_func):
    """
    Applies rule-based symbology to GIPOD layer based on Type and Status fields.
    """
    try:
        # First, let's check what fields are actually available in the layer
        field_names = [field.name() for field in layer.fields()]
        log_message_func(f"Available fields in GIPOD layer: {field_names}", "INFO")
        
        # Check if we have sample data to understand the field values
        sample_features = []
        for i, feature in enumerate(layer.getFeatures()):
            if i >= 3:  # Just get first 3 features for sampling
                break
            sample_features.append(feature)
        
        for i, feature in enumerate(sample_features):
            log_message_func(f"Sample feature {i+1}: Type='{feature['Type']}', Status='{feature['Status']}', End='{feature['End']}'", "INFO")
        
        # First filter to only show "Grondwerk" types
        # Use the correct field name - might be different in the actual WFS
        type_field = 'Type'  # Try common variations if this doesn't work: 'TYPE', 'type', etc.
        layer.setSubsetString(f"\"{type_field}\" = 'Grondwerk'")
        log_message_func(f"Applied filter: {type_field} = 'Grondwerk'", "INFO")
        
        # Create rule-based renderer
        root_rule = QgsRuleBasedRenderer.Rule(None)
        
        # Get current date for date comparisons
        current_date = date.today()
        current_date_str = current_date.strftime('%Y-%m-%d')
        
        # Use proper SQLite date functions
        # Calculate date 5 years ago
        five_years_ago = date(current_date.year - 5, current_date.month, current_date.day)
        five_years_ago_str = five_years_ago.strftime('%Y-%m-%d')
        
        # Rule 1: Uitgevoerd AND End date is within last 5 years -> RED
        rule1 = QgsRuleBasedRenderer.Rule(
            create_symbol(QColor('red')), 
            filterExp=f"\"Status\" = 'Uitgevoerd' AND \"End\" >= '{five_years_ago_str}'",
            label="Constructed - Closed",
            description=""
        )
        root_rule.appendChild(rule1)
        
        # Rule 2: Uitgevoerd AND End date is older than 5 years -> YELLOW
        rule2 = QgsRuleBasedRenderer.Rule(
            create_symbol(QColor('yellow')), 
            filterExp=f"\"Status\" = 'Uitgevoerd' AND \"End\" < '{five_years_ago_str}'",
            label="Constructed - Open",
            description=""
        )
        root_rule.appendChild(rule2)
        
        # Rule 3: In uitvoering OR Concreet gepland -> GREEN
        rule3 = QgsRuleBasedRenderer.Rule(
            create_symbol(QColor('green')), 
            filterExp="\"Status\" IN ('In uitvoering', 'Concreet gepland')",
            label="Open",
            description=""
        )
        root_rule.appendChild(rule3)
        
        # Create renderer and set it to the layer
        renderer = QgsRuleBasedRenderer(root_rule)
        layer.setRenderer(renderer)
        
        # Refresh the layer
        layer.triggerRepaint()
        
        # Force the layer to be visible for testing
        layer_node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
        if layer_node:
            layer_node.setItemVisibilityChecked(False)
        
        log_message_func("Applied rule-based symbology to GIPOD layer", "SUCCESS")
        
        # Log how many features match each rule
        for rule in [rule1, rule2, rule3]:
            count = layer.featureCount(rule.filterExpression())
            log_message_func(f"Rule '{rule.label()}': {count} features", "INFO")
        
    except Exception as e:
        log_message_func(f"Error applying GIPOD symbology: {str(e)}", "ERROR")
        import traceback
        log_message_func(f"Traceback: {traceback.format_exc()}", "ERROR")

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

def create_symbol(color):
    """
    Creates a simple fill symbol with the specified color.
    """
    symbol = QgsFillSymbol.createSimple({
        'color': color.name(),
        'outline_color': 'black',
        'outline_width': '0.5'
    })
    return symbol