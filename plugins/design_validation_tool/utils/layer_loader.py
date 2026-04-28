from qgis.core import QgsProject, QgsVectorLayer, QgsMessageLog, Qgis, QgsWkbTypes  # type: ignore
import os
import processing
from qgis.utils import iface # type: ignore

def get_layer_by_name(layer_name):
    """Get QGIS layer by name. If not in project, load from project folder using predefined paths."""

    # First check if layer exists in current QGIS project
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if layers:
        # print(f"✓ Found layer '{layer_name}' in QGIS project")
        return layers[0]

    # Layer not found in project, check if we have a path defined for it
    layer_paths = {
        "Primary Distribution Ducts": "/OUT_PrimDistributionDuct.shp",
        "Primary Distribution Points": "/input/CalculationInput/IN_ForcedPrimDistributionPoints.shp",
        "Primary Distribution Cables": "/OUT_PrimDistributionCables.shp",
        "Primary Distribution Clusters": "/input/CalculationInput/IN_ForcedPrimDistributionClusters.shp",
        "Distribution Clusters": "/OUT_DistributionClusters.shp",
        "Distribution Points": "/input/CalculationInput/IN_ForcedDistributionPoints.shp",
        "Distribution Cables": "/OUT_DistributionCables.shp",
        "Distribution Ducts": "/OUT_DistributionDuct.shp",
        "Drop Clusters": "/OUT_DropClusters.shp",
        "Drop Cables": "/OUT_DropCables.shp",
        "Drop Points": "/input/CalculationInput/IN_ForcedDropPoints.shp",
        "Drop Ducts": "/OUT_DropDuct.shp",
        "Possible trench routes": "/input/IN_PossibleTrenches.shp",
        "IN_Crossings": "/input/IN_Crossings.shp",
        "IN_ExistingPipes": "/input/IN_ExistingPipes.shp",
        "buildings": "/input/IN_Buildings.shp",
        "Feeder Clusters": "/input/CalculationInput/IN_ForcedFeederClusters.shp",
    }

    if layer_name not in layer_paths:
        # print(f"✗ Layer '{layer_name}' not found in project and no path defined in layer_paths")
        return None

    project = QgsProject.instance()
    project_path = project.fileName()

    if not project_path:
        # print(f"⚠ Project is not saved - cannot resolve relative paths for layer '{layer_name}'")
        return None

    # Get project directory
    project_dir = os.path.dirname(project_path)

    # Get the relative path from layer_paths
    relative_path = layer_paths[layer_name]

    # Remove leading slash to make it relative to project directory
    if relative_path.startswith("/"):
        relative_path = relative_path[1:]

    # Build absolute path
    absolute_path = os.path.normpath(os.path.join(project_dir, relative_path))

    # print(f"Looking for layer '{layer_name}' at: {absolute_path}")

    # Check if the file actually exists
    if not os.path.exists(absolute_path):
        # print(f"✗ File not found for layer '{layer_name}' at: {absolute_path}")

        # Try alternative path resolution - maybe the project is in a different location
        # Check if we're in a subdirectory and need to go up one level
        parent_dir = os.path.dirname(project_dir)
        alternative_path = os.path.normpath(os.path.join(parent_dir, relative_path))

        if os.path.exists(alternative_path):
            # print(f"✓ Found layer '{layer_name}' at alternative path: {alternative_path}")
            absolute_path = alternative_path
        else:
            # print(f"✗ Could not find layer '{layer_name}' at any expected location")
            return None

    # Load the layer
    layer = QgsVectorLayer(absolute_path, layer_name, "ogr")
    if not layer.isValid():
        # print(f"✗ Failed to load layer '{layer_name}' - invalid layer")
        return None

    # print(f"✓ Successfully loaded layer '{layer_name}'")

    # Add to project
    project.addMapLayer(layer, False)

    # Add to "Missing layers" group
    root = project.layerTreeRoot()
    missing_layers_group = root.findGroup("Missing layers")
    if not missing_layers_group:
        missing_layers_group = root.insertGroup(0, "Missing layers")
        # print("✓ Created 'Missing layers' group")

    missing_layers_group.addLayer(layer)
    # print(f"✓ Added layer '{layer_name}' to 'Missing layers' group")

    if "Primary Distribution Clusters" in layer_name:
        layer_tree_layer = root.findLayer(layer.id())
        if layer_tree_layer:
            layer_tree_layer.setItemVisibilityChecked(False)
            # print(f"✓ Unchecked layer '{layer_name}' (Primary Distribution Clusters layer)")

    return layer


def get_layer_from_API(
    name="GRB - WGO - wegopdeling",
    api="pagingEnabled='default' preferCoordinatesForWfsT11='false' restrictToRequestBBOX='1' srsname='EPSG:31370' typename='GRB:WGO' url='https://geo.api.vlaanderen.be/GRB/wfs' version='auto'",
    polygon_layer="Feeder Clusters",
):
    """
    Import a layer from a WFS API and clip it based on a polygon layer.

    Parameters:
    name (str): Name for the layer
    api (str): URI connection string for WFS service
    polygon_layer (QgsVectorLayer or str): Polygon layer to use for clipping.
                                           Can be a layer object or layer name/ID.

    Returns:
    QgsVectorLayer: The clipped layer, or None if operation failed
    """

    # Set up logging
    def log_message(message, level=Qgis.Warning):
        QgsMessageLog.logMessage(message, "get_layer_from_API", level)
        if level == Qgis.Critical:
            iface.messageBar().pushCritical("Error", message)
        elif level == Qgis.Warning:
            iface.messageBar().pushWarning("Warning", message)

    try:
        # Create layer from API
        log_message(f"Loading layer from API: {name}", Qgis.Info)
        layer = QgsVectorLayer(api, name, "wfs")

        if not layer.isValid():
            error_msg = f"Failed to load layer '{name}' from API. URI might be incorrect or service unavailable."
            log_message(error_msg, Qgis.Critical)
            return None

        log_message(
            f"Successfully loaded layer: {layer.featureCount()} features", Qgis.Info
        )

        # Handle polygon layer parameter
        if polygon_layer is None:
            log_message(
                "No polygon layer provided for clipping. Returning original layer.",
                Qgis.Warning,
            )
            QgsProject.instance().addMapLayer(layer)
            return layer

        # Get polygon layer object if string is provided
        if isinstance(polygon_layer, str):
            polygon = QgsProject.instance().mapLayersByName(polygon_layer)
            if not polygon:
                polygon = QgsProject.instance().mapLayersByShortName(polygon_layer)
            if not polygon:
                # Try by layer ID
                polygon = QgsProject.instance().mapLayer(polygon_layer)
                if polygon:
                    polygon = [polygon]

            if not polygon:
                log_message(
                    f"Polygon layer '{polygon_layer}' not found. Returning original layer.",
                    Qgis.Warning,
                )
                QgsProject.instance().addMapLayer(layer)
                return layer
            polygon_layer_obj = polygon[0]
        else:
            polygon_layer_obj = polygon_layer

        # Validate polygon layer
        if polygon_layer_obj.geometryType() != QgsWkbTypes.PolygonGeometry:
            log_message(
                "Provided layer is not a polygon layer. Cannot clip.", Qgis.Critical
            )
            QgsProject.instance().addMapLayer(layer)
            return layer

        # Check if polygon layer has features
        if polygon_layer_obj.featureCount() == 0:
            log_message("Polygon layer has no features. Cannot clip.", Qgis.Warning)
            QgsProject.instance().addMapLayer(layer)
            return layer

        # Perform clipping
        log_message(
            f"Clipping layer with polygon layer: {polygon_layer_obj.name()}", Qgis.Info
        )

        # Run clip algorithm
        clipped_layer = processing.run( # type: ignore
            "native:clip",
            {  # type: ignore
                "INPUT": layer,
                "OVERLAY": polygon_layer_obj,
                "OUTPUT": "memory:",
            },
        )["OUTPUT"]

        if clipped_layer is None or clipped_layer.featureCount() == 0:
            log_message(
                "Clip operation resulted in empty layer or failed.", Qgis.Warning
            )
            # Return original layer as fallback
            QgsProject.instance().addMapLayer(layer)
            return layer

        # Set appropriate name for clipped layer
        clipped_layer.setName(f"{name} (clipped)")

        # Add to project
        QgsProject.instance().addMapLayer(clipped_layer)

        log_message(
            f"Clipping completed: {clipped_layer.featureCount()} features after clip",
            Qgis.Info,
        )

        return clipped_layer

    except Exception as e:
        error_msg = f"Error in get_layer_from_API: {str(e)}"
        log_message(error_msg, Qgis.Critical)
        return None
