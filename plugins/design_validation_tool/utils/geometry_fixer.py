"""
Utility module for creating spatial indexes for QGIS layers.

This module provides functionality to create spatial indexes for selected layers,
which improves rendering performance and can help fix zoom visibility issues.
"""

from qgis.core import (  # type: ignore
    QgsVectorLayer,
    Qgis,
)
from qgis.PyQt.QtWidgets import QMessageBox  # type: ignore
import processing  # type: ignore


def fix_selected_layers(iface, log_function=None):
    """
    Create spatial indexes for all selected layers in QGIS.

    This function processes all layers selected in the QGIS Layers panel,
    and creates spatial indexes to improve rendering performance.

    Args:
        iface: QGIS interface instance
        log_function: Optional logging function for progress messages

    Returns:
        dict: Summary of the process with counts of processed layers
    """
    def log(message, msg_type="INFO"):
        """Helper function for logging"""
        if log_function:
            log_function(message, msg_type)
        else:
            print(f"[{msg_type}] {message}")

    # Get selected layers
    selected_layers = iface.layerTreeView().selectedLayers()

    if not selected_layers:
        log("No layers selected. Please select one or more layers in the Layers panel.", "WARNING")
        QMessageBox.warning(
            iface.mainWindow(),
            "No Layers Selected",
            "Please select one or more layers in the Layers panel."
        )
        return {}

    # Filter to only vector layers and collect their names
    vector_layers = []
    layer_names = []
    for layer in selected_layers:
        if isinstance(layer, QgsVectorLayer) and layer.isValid():
            vector_layers.append(layer)
            layer_names.append(layer.name())

    if not vector_layers:
        log("No valid vector layers selected.", "WARNING")
        QMessageBox.warning(
            iface.mainWindow(),
            "No Valid Layers",
            "None of the selected layers are valid vector layers."
        )
        return {}

    # Show confirmation dialog with layer names
    layer_list = "\n".join([f"  • {name}" for name in layer_names])
    confirmation_message = (
        f"Create spatial indexes for the following layer(s):\n\n"
        f"{layer_list}\n\n"
        f"Do you want to continue?"
    )

    reply = QMessageBox.question(
        iface.mainWindow(),
        "Confirm Spatial Index Creation",
        confirmation_message,
        QMessageBox.Ok | QMessageBox.Cancel,
        QMessageBox.Cancel  # Default button
    )

    if reply == QMessageBox.Cancel:
        log("Spatial index creation cancelled by user.", "INFO")
        return {}

    log(f"Creating spatial indexes for {len(vector_layers)} selected layer(s)...", "INFO")

    results = {}
    success_count = 0
    error_count = 0

    # Process the confirmed vector layers
    for layer in vector_layers:
        layer_name = layer.name()
        log(f"Processing layer: {layer_name}", "INFO")

        try:
            # Run the create spatial index algorithm (creates .qix file)
            processing.run("native:createspatialindex", {
                'INPUT': layer
            })

            log(f"Created new spatial index (.qix) for layer '{layer_name}'", "SUCCESS")
            results[layer_name] = {'success': True}
            success_count += 1

        except Exception as e:
            log(f"Error creating spatial index for layer '{layer_name}': {e}", "ERROR")
            results[layer_name] = {'success': False, 'error': str(e)}
            error_count += 1

    # Display summary message box
    if success_count > 0:
        success_message = (
            f"Successfully created spatial indexes for {success_count} layer(s).\n\n"
        )

        log(f"Successfully created spatial indexes for {success_count} layer(s)", "SUCCESS")

        QMessageBox.information(
            iface.mainWindow(),
            "Spatial Indexes Created",
            success_message
        )

        iface.messageBar().pushMessage(
            "Spatial Index Creation Complete",
            f"Created spatial indexes for {success_count} layer(s)",
            level=Qgis.Success,
            duration=5
        )

    if error_count > 0:
        log(f"Failed to create spatial indexes for {error_count} layer(s)", "WARNING")

    return results


def check_layer_for_invalid_geometries(layer):
    """
    Check a layer for invalid geometries without fixing them.

    Args:
        layer: QgsVectorLayer to check

    Returns:
        dict: Dictionary with count of invalid geometries and list of invalid feature IDs
    """
    invalid_features = []

    for feature in layer.getFeatures():
        geom = feature.geometry()

        if geom is None or geom.isEmpty():
            continue

        if not geom.isGeosValid():
            invalid_features.append(feature.id())

    return {
        'layer_name': layer.name(),
        'total_features': layer.featureCount(),
        'invalid_count': len(invalid_features),
        'invalid_feature_ids': invalid_features
    }
