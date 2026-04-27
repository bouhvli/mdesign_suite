import os

from qgis.core import QgsProject  # type: ignore


def load_project(project_path):
    """
    Load a QGIS project from a given path.
    
    Args:
        project_path (str): Path to the .qgs or .qgz project file.
        
    Returns:
        dict: Dictionary of layer names and QgsMapLayer objects.
    """
    project_layers = {}

    if not os.path.exists(project_path):
        #print(f"Project file does not exist: {project_path}")
        return {}

    try:
        project = QgsProject.instance()
        if project.read(project_path):
            print(f"Loaded project: {project_path}")
        else:
            print(f"Failed to load project: {project_path}")
            return {}

        # Collect layers
        for layer in project.mapLayers().values():
            project_layers[layer.name()] = layer

    except Exception as e:
        print(f"Error loading project: {e}")
        return {}

    return project_layers
