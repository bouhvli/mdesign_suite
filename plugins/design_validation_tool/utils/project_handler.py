import os

from qgis.core import QgsProject, QgsCoordinateReferenceSystem  # type: ignore


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

        # Ensure project CRS is always set to EPSG:31370 (Belgian Lambert 72)
        current_crs = project.crs()
        if not current_crs.isValid() or current_crs.authid() != 'EPSG:31370':
            default_crs = QgsCoordinateReferenceSystem('EPSG:31370')
            project.setCrs(default_crs)
            print(f"Project CRS changed to: {project.crs().authid()}")
        else:
            print(f"Project CRS already set to: {current_crs.authid()}")

        # Collect layers
        for layer in project.mapLayers().values():
            project_layers[layer.name()] = layer

    except Exception as e:
        print(f"Error loading project: {e}")
        return {}

    return project_layers
