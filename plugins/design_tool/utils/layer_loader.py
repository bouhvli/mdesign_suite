from qgis.core import QgsProject, QgsVectorLayer, QgsLayerTreeGroup # type: ignore
import os


def get_layer_by_name(layer_name):
    """
    Get QGIS layer by name. If not in project, search for it by filename in input/output folders.
    
    Search strategy:
    1. Check if layer exists in current QGIS project
    2. Search by layer name in input folder (recursively)
    3. Search by layer name in output folder (recursively)
    4. Load from predefined paths (fallback)
    """

    # First check if layer exists in current QGIS project
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if layers:
        print(f"✓ Found layer '{layer_name}' in QGIS project")
        return layers[0]
    
    project = QgsProject.instance()
    project_path = project.fileName()
    
    if not project_path:
        print(f"⚠ Project is not saved - cannot resolve relative paths for layer '{layer_name}'")
        return None
    
    # Get project directory
    project_dir = os.path.dirname(project_path)
    parent_dir = os.path.dirname(project_dir)
    
    print(f"Looking for layer '{layer_name}'...")
    print(f"  Project directory: {project_dir}")
    print(f"  Parent directory: {parent_dir}")
    
    # Strategy 1: Search by name in input folder
    input_folder = os.path.join(parent_dir, "input")
    if os.path.exists(input_folder):
        print(f"  Searching in input folder: {input_folder}")
        found_path = _search_layer_by_name(layer_name, input_folder)
        if found_path:
            print(f"✓ Found layer '{layer_name}' in input folder: {found_path}")
            return _load_and_add_layer(found_path, layer_name, project)
    
    # Strategy 2: Search by name in output folder
    output_folder = os.path.join(parent_dir, "output")
    if os.path.exists(output_folder):
        print(f"  Searching in output folder: {output_folder}")
        found_path = _search_layer_by_name(layer_name, output_folder)
        if found_path:
            print(f"✓ Found layer '{layer_name}' in output folder: {found_path}")
            return _load_and_add_layer(found_path, layer_name, project)
    
    # Fallback: Check in project directory itself
    print(f"  Searching in project directory: {project_dir}")
    found_path = _search_layer_by_name(layer_name, project_dir)
    if found_path:
        print(f"✓ Found layer '{layer_name}' in project directory: {found_path}")
        return _load_and_add_layer(found_path, layer_name, project)
    
    # Strategy 3: Use predefined paths (legacy fallback)
    print(f"  Attempting to load using predefined paths...")
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
        'feeder_cluster': '/output/OUT_FeederClusters.shp',
        'IN_HomePoints': '/input/IN_HomePoints.shp',
    }
    
    if layer_name not in layer_paths:
        print(f"✗ Layer '{layer_name}' not found in project or folders, and no predefined path available")
        return None
    
    # Get the relative path from layer_paths
    relative_path = layer_paths[layer_name]
    
    # Remove leading slash to make it relative to project directory
    if relative_path.startswith('/'):
        relative_path = relative_path[1:]
    
    # Try from project directory
    absolute_path = os.path.normpath(os.path.join(project_dir, relative_path))
    
    if os.path.exists(absolute_path):
        print(f"✓ Found layer using predefined path: {absolute_path}")
        return _load_and_add_layer(absolute_path, layer_name, project)
    
    # Try from parent directory
    absolute_path = os.path.normpath(os.path.join(parent_dir, relative_path))
    
    if os.path.exists(absolute_path):
        print(f"✓ Found layer using predefined path (parent dir): {absolute_path}")
        return _load_and_add_layer(absolute_path, layer_name, project)
    
    print(f"✗ Could not find layer '{layer_name}' at any location")
    return None


def _search_layer_by_name(layer_name, root_folder):
    """
    Search for a layer file by name (without extension) in root_folder and subfolders.
    Supports .shp, .gpkg, .geojson, .gml formats.
    
    Returns the full path to the file if found, None otherwise.
    """
    supported_extensions = ['.shp', '.gpkg', '.geojson', '.gml', '.json']
    
    # Search for file with exact name match (various extensions)
    for extension in supported_extensions:
        file_path = os.path.join(root_folder, layer_name + extension)
        if os.path.exists(file_path):
            print(f"    ✓ Found: {file_path}")
            return file_path
    
    # Recursive search in subdirectories
    try:
        for root, dirs, files in os.walk(root_folder):
            for file in files:
                # Check if filename (without extension) matches layer_name
                file_base = os.path.splitext(file)[0]
                file_ext = os.path.splitext(file)[1].lower()
                
                if file_base == layer_name and file_ext in supported_extensions:
                    file_path = os.path.join(root, file)
                    print(f"    ✓ Found: {file_path}")
                    return file_path
    except Exception as e:
        print(f"    ⚠ Error searching directory {root_folder}: {e}")
    
    return None


def _load_and_add_layer(file_path, layer_name, project):
    """
    Load a layer from file and add it to the QGIS project.
    Returns the loaded layer or None if loading failed.
    """
    try:
        # Load the layer
        layer = QgsVectorLayer(file_path, layer_name, "ogr")
        
        if not layer.isValid():
            print(f"✗ Failed to load layer '{layer_name}' - invalid layer")
            return None
        
        print(f"✓ Successfully loaded layer '{layer_name}'")
        
        # Add to project
        project.addMapLayer(layer, False)
        
        # Add to "Missing layers" group
        root = project.layerTreeRoot()
        missing_layers_group = root.findGroup("Missing layers")
        if not missing_layers_group:
            missing_layers_group = root.insertGroup(0, "Missing layers")
            print("✓ Created 'Missing layers' group")
        
        missing_layers_group.addLayer(layer)
        print(f"✓ Added layer '{layer_name}' to 'Missing layers' group")
        
        # Handle visibility for specific layers
        if 'Primary Distribution Clusters' in layer_name:
            layer_tree_layer = root.findLayer(layer.id())
            if layer_tree_layer:
                layer_tree_layer.setItemVisibilityChecked(False)
                print(f"✓ Unchecked layer '{layer_name}' (Primary Distribution Clusters layer)")
        
        return layer
        
    except Exception as e:
        print(f"✗ Error loading layer '{layer_name}' from {file_path}: {e}")
        return None