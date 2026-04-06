import os
import shutil
import glob
from datetime import datetime
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsRasterLayer, 
    QgsVectorFileWriter, QgsFeature, QgsCoordinateReferenceSystem,
    QgsMessageLog, Qgis
)
import processing

class InstanceMerger(QObject):
    """Handles the logic for merging QGIS instances."""
    
    progress_updated = pyqtSignal(int, str)  # value, message
    log_message = pyqtSignal(str)
    merge_finished = pyqtSignal(bool, str)  # success, message
    
    def __init__(self):
        super().__init__()
        self.instance_paths = []
        self.output_folder = ""
        self.output_name = "merged_project"
        self.merge_DCIM = True
        self.preserve_styles = True
        self.create_backup = False
        self.project_folder = ""
        
    def set_parameters(self, instance_paths, output_folder, output_name, 
                      merge_DCIM=True, preserve_styles=True, create_backup=False):
        """Set merger parameters."""
        self.instance_paths = instance_paths
        self.output_folder = output_folder
        self.output_name = output_name
        self.merge_DCIM = merge_DCIM
        self.preserve_styles = preserve_styles
        self.create_backup = create_backup
        # Create project folder path
        self.project_folder = os.path.join(self.output_folder, self.output_name)
    
    def start_merge(self):
        """Start the merging process."""
        try:
            self._merge_instances()
            self.merge_finished.emit(True, f"Merge completed successfully!\nProject location: {self.project_folder}")
        except Exception as e:
            error_msg = f"Merge failed: {str(e)}"
            self.log_message.emit(error_msg)
            self.merge_finished.emit(False, error_msg)
    
    def _merge_instances(self):
        """Main merge method."""
        self.progress_updated.emit(0, "Starting merge process...")
        
        # Create project folder structure
        self._create_project_structure()
        
        # Create backup if requested
        if self.create_backup:
            self._create_backups()
        
        # Analyze instances and find common layers
        layer_analysis = self._analyze_instances()
        self.progress_updated.emit(30, f"Found {len(layer_analysis['layer_groups'])} unique layer groups")
        
        # Create new project
        merged_project = QgsProject.instance()
        merged_project.clear()
        
        # Merge layers and save them to project folder
        self._merge_layers(merged_project, layer_analysis)
        self.progress_updated.emit(70, "Layers merged successfully")
        
        # Merge DCIM folders if requested
        if self.merge_DCIM:
            self._merge_DCIM_folders()
            self.progress_updated.emit(90, "DCIM folders merged")
        
        # Save merged project to project folder
        output_path = os.path.join(self.project_folder, f"{self.output_name}.qgz")
        success = merged_project.write(output_path)
        
        if success:
            self.progress_updated.emit(100, f"Project saved: {output_path}")
        else:
            raise Exception(f"Failed to save project to {output_path}")
        
    def _create_project_structure(self):
        """Create the project folder structure."""
        # Create main project folder
        os.makedirs(self.project_folder, exist_ok=True)
        
        # Create data subfolder for layers
        self.data_folder = os.path.join(self.project_folder, "data")
        os.makedirs(self.data_folder, exist_ok=True)
        
        # Create DCIM folder
        self.DCIM_folder = os.path.join(self.project_folder, "DCIM")
        os.makedirs(self.DCIM_folder, exist_ok=True)
        
        self.log_message.emit(f"Created project structure in: {self.project_folder}")
    
    def _analyze_instances(self):
        """Analyze all instances and group layers by name."""
        layer_groups = {}
        project_files = {}
        
        for i, instance_path in enumerate(self.instance_paths):
            self.progress_updated.emit(10 + i * 5, f"Analyzing instance {i+1}/{len(self.instance_paths)}")
            
            # Find QGIS project file
            project_file = self._find_project_file(instance_path)
            if not project_file:
                self.log_message.emit(f"Warning: No project file found in {instance_path}")
                continue
            
            project_files[instance_path] = project_file
            
            # Load project temporarily to get layer information
            temp_project = QgsProject()
            if temp_project.read(project_file):
                layers = temp_project.mapLayers()
                
                for layer_id, layer in layers.items():
                    layer_name = layer.name()
                    if layer_name not in layer_groups:
                        layer_groups[layer_name] = []
                    
                    # Store layer source information instead of layer object
                    layer_info = {
                        'instance_path': instance_path,
                        'project_file': project_file,
                        'layer_id': layer_id,
                        'source': layer.source(),
                        'provider': layer.providerType(),
                        'crs': layer.crs(),
                        'geometry_type': self._get_geometry_type(layer),
                        'is_valid': layer.isValid(),
                        'layer_type': 'vector' if isinstance(layer, QgsVectorLayer) else 'raster',
                        'fields': [field.name() for field in layer.fields()] if isinstance(layer, QgsVectorLayer) else []
                    }
                    
                    layer_groups[layer_name].append(layer_info)
                
                # Clear the temporary project without deleting layers
                temp_project.clear()
        
        return {
            'layer_groups': layer_groups,
            'project_files': project_files
        }
    
    def _get_geometry_type(self, layer):
        """Get geometry type for vector layers."""
        if isinstance(layer, QgsVectorLayer):
            return layer.geometryType()
        return None
    
    def _find_project_file(self, instance_path):
        """Find QGIS project file in instance folder."""
        # Look for .qgz files first (new format)
        qgz_files = glob.glob(os.path.join(instance_path, "*.qgz"))
        if qgz_files:
            return qgz_files[0]
        
        # Then look for .qgs files (old format)
        qgs_files = glob.glob(os.path.join(instance_path, "*.qgs"))
        if qgs_files:
            return qgs_files[0]
        
        return None
    
    def _merge_layers(self, merged_project, layer_analysis):
        """Merge layers with common names and save to project data folder."""
        layer_groups = layer_analysis['layer_groups']
        total_layers = len(layer_groups)
        
        for i, (layer_name, layer_info_list) in enumerate(layer_groups.items()):
            progress = 30 + (i / total_layers) * 40
            self.progress_updated.emit(int(progress), f"Merging layer: {layer_name}")
            
            if len(layer_info_list) == 1:
                # Single layer, save it to project data folder
                self._save_single_layer(merged_project, layer_info_list[0], layer_name)
            else:
                # Multiple layers with same name, merge them and save to project data folder
                self._merge_and_save_layers(merged_project, layer_info_list, layer_name)
    
    def _save_single_layer(self, merged_project, layer_info, layer_name):
        """Save a single layer to project data folder and add to project."""
        try:
            if layer_info['layer_type'] == 'vector':
                # Create a copy in the project data folder
                output_path = os.path.join(self.data_folder, f"{layer_name}.gpkg")
                
                # Load the original layer
                original_layer = QgsVectorLayer(layer_info['source'], "temp", layer_info['provider'])
                if original_layer.isValid():
                    # Save to project data folder
                    error = QgsVectorFileWriter.writeAsVectorFormat(
                        original_layer, 
                        output_path, 
                        "UTF-8", 
                        original_layer.crs(), 
                        "GPKG"
                    )
                    
                    if error[0] == QgsVectorFileWriter.NoError:
                        # Load the saved layer
                        saved_layer = QgsVectorLayer(output_path, layer_name, "ogr")
                        if saved_layer.isValid():
                            merged_project.addMapLayer(saved_layer)
                            self.log_message.emit(f"Saved layer to project: {layer_name}")
                        else:
                            self.log_message.emit(f"Warning: Failed to load saved layer {layer_name}")
                    else:
                        self.log_message.emit(f"Warning: Failed to save layer {layer_name} to project data folder")
                else:
                    self.log_message.emit(f"Warning: Invalid source layer {layer_name}")
            else:
                # For raster layers, just add them directly (they might be large files)
                layer = QgsRasterLayer(layer_info['source'], layer_name, layer_info['provider'])
                if layer.isValid():
                    merged_project.addMapLayer(layer)
                    self.log_message.emit(f"Added raster layer: {layer_name}")
                else:
                    self.log_message.emit(f"Warning: Failed to load raster layer {layer_name}")
                    
        except Exception as e:
            self.log_message.emit(f"Error processing layer {layer_name}: {str(e)}")
    
    def _merge_and_save_layers(self, merged_project, layer_info_list, layer_name):
        """Merge multiple layers and save the result to project data folder."""
        # Separate vector and raster layers
        vector_layers_info = [info for info in layer_info_list if info['layer_type'] == 'vector']
        raster_layers_info = [info for info in layer_info_list if info['layer_type'] == 'raster']
        
        # Handle vector layers
        if vector_layers_info:
            self._merge_vector_layers(merged_project, vector_layers_info, layer_name)
        
        # Handle raster layers (for now, just use first one)
        if raster_layers_info:
            self._save_single_layer(merged_project, raster_layers_info[0], layer_name)
    
    def _merge_vector_layers(self, merged_project, vector_layers_info, layer_name):
        """Merge multiple vector layers and save to project data folder."""
        if len(vector_layers_info) == 1:
            # Single layer
            self._save_single_layer(merged_project, vector_layers_info[0], layer_name)
            return
        
        try:
            # Create temporary layers for merging
            temp_layers = []
            valid_layers_count = 0
            
            for layer_info in vector_layers_info:
                try:
                    layer = QgsVectorLayer(layer_info['source'], f"temp_{layer_name}_{valid_layers_count}", layer_info['provider'])
                    if layer.isValid():
                        temp_layers.append(layer)
                        valid_layers_count += 1
                    else:
                        self.log_message.emit(f"Warning: Invalid layer {layer_name} from {layer_info['source']}")
                except Exception as e:
                    self.log_message.emit(f"Error creating temporary layer: {str(e)}")
            
            if valid_layers_count == 0:
                self.log_message.emit(f"Error: No valid layers to merge for {layer_name}")
                return
            
            if valid_layers_count == 1:
                # Only one valid layer, use it directly
                self._save_single_layer(merged_project, vector_layers_info[0], layer_name)
                return
            
            # Use processing algorithm to merge layers
            params = {
                'LAYERS': temp_layers,
                'CRS': temp_layers[0].crs(),
                'OUTPUT': 'memory:'
            }
            
            result = processing.run("native:mergevectorlayers", params)
            merged_layer = result['OUTPUT']
            
            if merged_layer.isValid():
                # Save merged layer to project data folder
                output_path = os.path.join(self.data_folder, f"{layer_name}.gpkg")
                error = QgsVectorFileWriter.writeAsVectorFormat(
                    merged_layer, 
                    output_path, 
                    "UTF-8", 
                    merged_layer.crs(), 
                    "GPKG"
                )
                
                if error[0] == QgsVectorFileWriter.NoError:
                    # Load the saved merged layer
                    saved_merged_layer = QgsVectorLayer(output_path, layer_name, "ogr")
                    if saved_merged_layer.isValid():
                        merged_project.addMapLayer(saved_merged_layer)
                        self.log_message.emit(f"Successfully merged and saved {valid_layers_count} {layer_name} layers")
                    else:
                        raise Exception("Failed to load saved merged layer")
                else:
                    raise Exception("Failed to save merged layer to project data folder")
                    
            else:
                raise Exception("Processing algorithm returned invalid layer")
                
        except Exception as e:
            self.log_message.emit(f"Error merging {layer_name} layers: {str(e)}")
            # Fallback: use first valid layer
            for layer_info in vector_layers_info:
                try:
                    self._save_single_layer(merged_project, layer_info, layer_name)
                    self.log_message.emit(f"Using single layer as fallback: {layer_name}")
                    break
                except:
                    continue
    
    def _merge_DCIM_folders(self):
        """Merge DCIM folders (containing images) from all instances."""
        DCIM_folders = []
        
        # Collect all DCIM folders
        for instance_path in self.instance_paths:
            DCIM_path = os.path.join(instance_path, "DCIM")
            if os.path.exists(DCIM_path) and os.path.isdir(DCIM_path):
                DCIM_folders.append(DCIM_path)
        
        if not DCIM_folders:
            self.log_message.emit("No DCIM folders found to merge")
            return
        
        # Merge all DCIM folders into the project DCIM folder
        copied_files_count = 0
        for DCIM_folder in DCIM_folders:
            if os.path.isdir(DCIM_folder):
                for root, dirs, files in os.walk(DCIM_folder):
                    for file in files:
                        source_file = os.path.join(root, file)
                        if os.path.isfile(source_file):
                            # Determine relative path to maintain structure
                            relative_path = os.path.relpath(source_file, DCIM_folder)
                            dest_file = os.path.join(self.DCIM_folder, relative_path)
                            
                            # Create subdirectories if needed
                            os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                            
                            # Copy file (handle duplicates)
                            if not os.path.exists(dest_file):
                                shutil.copy2(source_file, dest_file)
                                copied_files_count += 1
                                self.log_message.emit(f"Copied DCIM image: {file}")
                            else:
                                # Handle duplicate by adding prefix
                                name, ext = os.path.splitext(file)
                                counter = 1
                                while True:
                                    new_name = f"{name}_{counter}{ext}"
                                    new_dest = os.path.join(os.path.dirname(dest_file), new_name)
                                    if not os.path.exists(new_dest):
                                        shutil.copy2(source_file, new_dest)
                                        copied_files_count += 1
                                        self.log_message.emit(f"Copied DCIM image (renamed): {new_name}")
                                        break
                                    counter += 1
        
        self.log_message.emit(f"Successfully merged {copied_files_count} DCIM images from {len(DCIM_folders)} folders")
    
    def _create_backups(self):
        """Create backups of original instances."""
        backup_folder = os.path.join(self.output_folder, "backups")
        os.makedirs(backup_folder, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for i, instance_path in enumerate(self.instance_paths):
            backup_path = os.path.join(backup_folder, f"instance_{i+1}_{timestamp}")
            try:
                shutil.copytree(instance_path, backup_path)
                self.log_message.emit(f"Created backup: {backup_path}")
            except Exception as e:
                self.log_message.emit(f"Error creating backup for {instance_path}: {str(e)}")