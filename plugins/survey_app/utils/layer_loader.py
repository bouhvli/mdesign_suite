from qgis.core import QgsProject, QgsVectorLayer, QgsLayerTreeGroup # type: ignore
import os


def get_layer_by_name(layer_name):
    """Get QGIS layer by name. If not in project, load from project folder using predefined paths."""

    # First check if layer exists in current QGIS project
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if layers:
        #print(f"✓ Found layer '{layer_name}' in QGIS project")
        return layers[0]
    
    # Layer not found in project, check if we have a path defined for it
    layer_paths = {
        'Primary Distribution Ducts': '/OUT_PrimDistributionDuct.shp',
        'Primary Distribution Points': '/input/CalculationInput/IN_ForcedPrimDistributionPoints.shp',
        'Primary Distribution Cables': '/OUT_PrimDistributionCables.shp',
        'Primary Distribution Clusters': '/input/CalculationInput/IN_ForcedPrimDistributionClusters.shp',
        'Distribution Clusters': '/OUT_DistributionClusters.shp',
        'Distribution Points': '/input/CalculationInput/IN_ForcedDistributionPoints.shp',
        'Distribution Cables': '/OUT_DistributionCables.shp',
        'Distribution Ducts': '/OUT_DistributionDuct.shp',
        'Drop Clusters': '/output/OUT_DropClusters.shp',
        'Drop Cables': '/output/OUT_DropCables.shp',
        'Drop Points': '/input/CalculationInput/IN_ForcedDropPoints.shp',
        'Drop Ducts': '/OUT_DropDuct.shp',
        'Demand Points': '/IN_DemandPoints.shp',
        'Possible trench routes': '/input/IN_PossibleTrenches.shp',
        'buildings': '/input/IN_Buildings.shp',
        'IN_Buildings': '/input/IN_Buildings.shp',
        'OUT_FeederClusters': '/output/OUT_FeederClusters.shp',
    }
    
    if layer_name not in layer_paths:
        print(f"✗ Layer '{layer_name}' not found in project and no path defined in layer_paths")
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
    
    # Load the layer
    layer = QgsVectorLayer(absolute_path, layer_name, "ogr")
    if not layer.isValid():
        #print(f"✗ Failed to load layer '{layer_name}' - invalid layer")
        return None
    
    #print(f"✓ Successfully loaded layer '{layer_name}'")
    
    # Add to project
    project.addMapLayer(layer, False)
    
    # Add to "Missing layers" group
    root = project.layerTreeRoot()
    missing_layers_group = root.findGroup("Missing layers")
    if not missing_layers_group:
        missing_layers_group = root.insertGroup(0, "Missing layers")
        #print("✓ Created 'Missing layers' group")
    
    missing_layers_group.addLayer(layer)
    #print(f"✓ Added layer '{layer_name}' to 'Missing layers' group")

    if 'Primary Distribution Clusters' in layer_name:
        layer_tree_layer = root.findLayer(layer.id())
        if layer_tree_layer:
            layer_tree_layer.setItemVisibilityChecked(False)
            #print(f"✓ Unchecked layer '{layer_name}' (Primary Distribution Clusters layer)")
    
    return layer