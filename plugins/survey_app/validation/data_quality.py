# validation/data_quality.py
import os
import shutil
import zipfile
from datetime import datetime
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsVectorFileWriter,
    QgsCoordinateTransformContext, QgsFillSymbol, QgsLineSymbol,
    QgsMarkerSymbol, QgsSingleSymbolRenderer, QgsRuleBasedRenderer,
    QgsWkbTypes, QgsSymbol, QgsRasterLayer, QgsSimpleFillSymbolLayer,
    QgsLinePatternFillSymbolLayer
)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import QVariant


class DataQualityValidator:
    def __init__(self, iface=None, log_callback=None):
        self.iface = iface
        self.log_callback = log_callback
        self.unsurveyed_count = 0
        self.layers_checked = 0
        self.resurvey_project_path = None
        
    def log(self, message):
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)
    
    def check_all_layers_for_unsurveyed(self):
        """Check all layers in the project for unsurveyed features"""
        self.log("Checking all layers for unsurveyed features...")
        
        project = QgsProject.instance()
        layers = project.mapLayers().values()
        
        self.unsurveyed_count = 0
        self.layers_checked = 0
        layers_to_process = []
        
        # Layers to skip
        layers_to_skip = ["Buildings", "Survey Area", "Address Resurvey Flags", "GRB Basemap"]
        
        for layer in layers:
            layer_name = layer.name()
            
            # Skip specific layers
            if layer_name in layers_to_skip:
                self.log(f"  - Skipping layer: {layer_name}")
                continue
                
            # Only check vector layers
            if not isinstance(layer, QgsVectorLayer):
                continue
                
            self.layers_checked += 1
            
            fields = layer.fields()
            surveyed_idx = fields.indexFromName("SURVEYED")
            
            if surveyed_idx == -1:
                self.log(f"  - Layer '{layer_name}': No SURVEYED field found, skipping")
                continue
            
            unsurveyed_features = 0
            total_features = 0
            
            for feature in layer.getFeatures():
                total_features += 1
                surveyed = feature["SURVEYED"]
                
                if surveyed in [False, 0, None, QVariant()] or str(surveyed).upper() in ['FALSE', 'F', '0', 'NO', 'N']:
                    unsurveyed_features += 1
            
            if unsurveyed_features > 0:
                self.unsurveyed_count += unsurveyed_features
                self.log(f"  - Layer '{layer_name}': {unsurveyed_features}/{total_features} features not surveyed")
                layers_to_process.append(layer)
            else:
                self.log(f"  - Layer '{layer_name}': All {total_features} features are surveyed")
                # Still process to make surveyed features transparent
                layers_to_process.append(layer)
        
        return layers_to_process
    
    def create_resurvey_project(self, layers_to_process):
        """Create a new project with modified symbology"""
        try:
            # Get current project info
            current_project = QgsProject.instance()
            current_project_path = current_project.fileName()
            
            if not current_project_path:
                self.log("ERROR: Current project is not saved. Please save the project first.")
                return None
            
            # Create new project name and directory
            project_dir = os.path.dirname(current_project_path)
            project_name = os.path.splitext(os.path.basename(current_project_path))[0]
            
            # Remove existing _resurvey suffix if present
            if project_name.endswith('_resurvey'):
                project_name = project_name[:-9]
            
            resurvey_project_name = f"{project_name}_resurvey"
            resurvey_project_dir = os.path.join(project_dir, resurvey_project_name)
            
            # Remove existing directory if it exists
            if os.path.exists(resurvey_project_dir):
                shutil.rmtree(resurvey_project_dir)
            
            # Create directory
            os.makedirs(resurvey_project_dir)
            
            self.log(f"Creating resurvey project: {resurvey_project_name}")
            self.log(f"Output directory: {resurvey_project_dir}")
            
            # Create a COPY of the original project
            new_project = QgsProject()
            
            # Track layers to maintain order
            raster_layers = []
            special_layers = {}
            regular_layers = []
            
            # Process all layers from original project
            for layer in current_project.mapLayers().values():
                if isinstance(layer, QgsRasterLayer):
                    # For raster layers, save for later addition (to be at bottom)
                    raster_layers.append(layer)
                elif isinstance(layer, QgsVectorLayer):
                    # For vector layers, save as shapefile
                    layer_path = self.save_layer_as_shapefile(layer, resurvey_project_dir)
                    if layer_path:
                        # Load the saved shapefile
                        saved_layer = QgsVectorLayer(layer_path, layer.name(), "ogr")
                        if saved_layer.isValid():
                            # Check if it's a special layer
                            layer_name = layer.name()
                            if layer_name == "Buildings":
                                special_layers["Buildings"] = saved_layer
                            elif layer_name == "Survey Area":
                                special_layers["Survey Area"] = saved_layer
                            elif layer_name == "Address Resurvey Flags":
                                special_layers["Address Resurvey Flags"] = saved_layer
                            else:
                                # Apply resurvey symbology to regular layers
                                self.apply_resurvey_symbology(saved_layer)
                                regular_layers.append(saved_layer)

            # IMPORTANT: Add layers in reverse order because QGIS renders from bottom up
            # We want: raster (bottom), Survey Area, Buildings, other layers (top)
            # So we add in this order: other layers, Buildings, Survey Area, raster

            # 5. Finally add all raster layers last (will end up at BOTTOM)
            for layer in raster_layers:
                cloned_raster = layer.clone()
                new_project.addMapLayer(cloned_raster)
                self.log(f"  - Added raster layer (bottom): {layer.name()}")
            
            # 4. Add Survey Area layer
            if "Survey Area" in special_layers:
                self.apply_survey_area_style(special_layers["Survey Area"])
                new_project.addMapLayer(special_layers["Survey Area"])
                self.log(f"  - Added and styled layer: Survey Area")
            
            # 3. Add Buildings layer
            if "Buildings" in special_layers:
                self.apply_buildings_striped_style(special_layers["Buildings"])
                new_project.addMapLayer(special_layers["Buildings"])
                self.log(f"  - Added and styled layer: Buildings")
            
            # 2. Add Address Resurvey Flags layer (if it exists)
            if "Address Resurvey Flags" in special_layers:
                new_project.addMapLayer(special_layers["Address Resurvey Flags"])
                self.log(f"  - Added layer: Address Resurvey Flags")

            # 1. Add regular layers first (will end up at TOP)
            for layer in regular_layers:
                new_project.addMapLayer(layer)
                self.log(f"  - Added regular layer (top): {layer.name()}")
            
            # Copy project properties
            new_project.setCrs(current_project.crs())
            new_project.setTitle(resurvey_project_name)
            
            # Copy project extent if available
            if current_project.viewSettings().defaultViewExtent():
                new_project.viewSettings().setDefaultViewExtent(
                    current_project.viewSettings().defaultViewExtent()
                )
            
            # Save the project
            project_file = os.path.join(resurvey_project_dir, f"{resurvey_project_name}.qgz")
            success = new_project.write(project_file)
            
            if success:
                self.log(f"Saved project to: {project_file}")
                
                # Copy supporting files (excluding DCIM)
                self.copy_supporting_files(current_project_path, resurvey_project_dir)
                
                # Create zip file
                zip_path = self.create_zip(resurvey_project_dir, project_dir)
                
                self.resurvey_project_path = zip_path
                return zip_path
            else:
                self.log(f"ERROR: Failed to save project: {new_project.error()}")
                return None
                
        except Exception as e:
            self.log(f"ERROR creating resurvey project: {str(e)}")
            import traceback
            self.log(f"Traceback: {traceback.format_exc()}")
            return None
    
    def save_layer_as_shapefile(self, layer, output_dir):
        """Save a layer as shapefile to the output directory"""
        try:
            # Create safe filename
            safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in layer.name())
            shapefile_path = os.path.join(output_dir, f"{safe_name}.shp")
            
            # Skip if already exists
            if os.path.exists(shapefile_path):
                return shapefile_path
            
            # Save to shapefile
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "ESRI Shapefile"
            options.fileEncoding = "utf-8"
            options.includeZ = False
            options.includeM = False
            options.layerOptions = ['ENCODING=UTF-8']
            
            transform_context = QgsCoordinateTransformContext()
            
            error = QgsVectorFileWriter.writeAsVectorFormatV2(
                layer,
                shapefile_path,
                transform_context,
                options
            )
            
            if error[0] == QgsVectorFileWriter.NoError:
                self.log(f"    - Saved: {layer.name()} -> {safe_name}.shp")
                return shapefile_path
            else:
                self.log(f"    - Failed to save {layer.name()}: {error[1]}")
                return None
                
        except Exception as e:
            self.log(f"ERROR saving layer {layer.name()}: {str(e)}")
            return None
    
    def apply_resurvey_symbology(self, layer):
        """Apply resurvey symbology: surveyed=transparent, unsurveyed=red"""
        try:
            # Check if layer has SURVEYED field
            fields = layer.fields()
            surveyed_idx = fields.indexFromName("SURVEYED")
            
            if surveyed_idx == -1:
                self.log(f"    - Layer '{layer.name()}' has no SURVEYED field, applying default style")
                self.apply_default_red_symbology(layer)
                return
            
            geom_type = layer.geometryType()
            
            # Create symbols
            if geom_type == QgsWkbTypes.PolygonGeometry:
                # Transparent symbol for surveyed features
                transparent_symbol = QgsFillSymbol.createSimple({
                    'color': '0,0,0,0',  # Fully transparent
                    'outline_color': '0,0,0,0',  # Transparent outline
                    'outline_width': '0',
                    'outline_style': 'solid'
                })
                
                # Red symbol for unsurveyed features
                red_symbol = QgsFillSymbol.createSimple({
                    'color': '255,0,0,150',  # Semi-transparent red fill
                    'outline_color': '200,0,0,255',  # Dark red outline
                    'outline_width': '0.8',
                    'outline_style': 'solid'
                })
                
            elif geom_type == QgsWkbTypes.LineGeometry:
                # Transparent symbol for surveyed features
                transparent_symbol = QgsLineSymbol.createSimple({
                    'color': '0,0,0,0',  # Transparent
                    'width': '0',
                    'line_style': 'solid'
                })
                
                # Red symbol for unsurveyed features
                red_symbol = QgsLineSymbol.createSimple({
                    'color': '255,0,0,255',
                    'width': '2.0',
                    'line_style': 'solid'
                })
                
            elif geom_type == QgsWkbTypes.PointGeometry:
                # Transparent symbol for surveyed features
                transparent_symbol = QgsMarkerSymbol.createSimple({
                    'color': '0,0,0,0',  # Transparent
                    'outline_color': '0,0,0,0',
                    'size': '0',
                    'name': 'circle'
                })
                
                # Red symbol for unsurveyed features
                red_symbol = QgsMarkerSymbol.createSimple({
                    'color': '255,0,0,255',
                    'outline_color': '200,0,0,255',
                    'size': '5',
                    'name': 'circle'
                })
                
            else:
                # Default symbols for other geometry types
                transparent_symbol = QgsSymbol.defaultSymbol(geom_type)
                transparent_symbol.setColor(QColor(0, 0, 0, 0))
                
                red_symbol = QgsSymbol.defaultSymbol(geom_type)
                red_symbol.setColor(QColor(255, 0, 0))
            
            # Create rule-based renderer
            root_rule = QgsRuleBasedRenderer.Rule(None)
            
            # Rule for unsurveyed features (red)
            unsurveyed_rule = QgsRuleBasedRenderer.Rule(red_symbol)
            unsurveyed_rule.setFilterExpression('"SURVEYED" = 0 OR "SURVEYED" IS NULL OR "SURVEYED" = false')
            unsurveyed_rule.setLabel("Needs Survey")
            
            # Rule for surveyed features (transparent)
            surveyed_rule = QgsRuleBasedRenderer.Rule(transparent_symbol)
            surveyed_rule.setFilterExpression('"SURVEYED" = 1 OR "SURVEYED" = true')
            surveyed_rule.setLabel("Surveyed (Transparent)")
            
            # Add rules to root
            root_rule.appendChild(unsurveyed_rule)
            root_rule.appendChild(surveyed_rule)
            
            # Create and apply renderer
            renderer = QgsRuleBasedRenderer(root_rule)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
            
            self.log(f"    - Applied resurvey symbology to {layer.name()}")
            
        except Exception as e:
            self.log(f"ERROR applying resurvey symbology to {layer.name()}: {str(e)}")
            # Fallback to default red symbology
            self.apply_default_red_symbology(layer)
    
    def apply_default_red_symbology(self, layer):
        """Apply default red symbology (fallback)"""
        try:
            geom_type = layer.geometryType()
            
            if geom_type == QgsWkbTypes.PolygonGeometry:
                symbol = QgsFillSymbol.createSimple({
                    'color': '255,0,0,150',
                    'outline_color': '200,0,0,255',
                    'outline_width': '0.8',
                    'outline_style': 'solid'
                })
            elif geom_type == QgsWkbTypes.LineGeometry:
                symbol = QgsLineSymbol.createSimple({
                    'color': '255,0,0,255',
                    'width': '2.0',
                    'line_style': 'solid'
                })
            elif geom_type == QgsWkbTypes.PointGeometry:
                symbol = QgsMarkerSymbol.createSimple({
                    'color': '255,0,0,255',
                    'outline_color': '200,0,0,255',
                    'size': '5',
                    'name': 'circle'
                })
            else:
                symbol = QgsSymbol.defaultSymbol(geom_type)
                symbol.setColor(QColor(255, 0, 0))
            
            renderer = QgsSingleSymbolRenderer(symbol)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
            
        except Exception as e:
            self.log(f"ERROR applying default symbology: {str(e)}")
    
    def apply_buildings_striped_style(self, layer):
        """Apply the specific striped style for Buildings layer"""
        try:
            if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
                return
            
            # Create a fill symbol
            symbol = QgsFillSymbol.createSimple({})
            
            # Remove default layers
            for i in range(symbol.symbolLayerCount()):
                symbol.deleteSymbolLayer(0)
            
            # Add a solid fill as base layer (blue with transparency)
            simple_fill = QgsSimpleFillSymbolLayer()
            simple_fill.setFillColor(QColor(0, 70, 200, 100))  # Light blue with transparency
            simple_fill.setStrokeColor(QColor(0, 70, 200, 255))
            simple_fill.setStrokeWidth(0.5)
            symbol.appendSymbolLayer(simple_fill)
            
            # Add line pattern fill for stripes
            line_pattern_fill = QgsLinePatternFillSymbolLayer()
            line_pattern_fill.setLineAngle(45)  # 45 degree angle for stripes
            line_pattern_fill.setDistance(3.0)  # Distance between lines
            
            # Create a line symbol for the pattern
            line_symbol = line_pattern_fill.subSymbol()
            if line_symbol:
                line_symbol.setWidth(1.0)  # Width of stripe lines
                line_symbol.setColor(QColor(0, 70, 200, 255))  # Stripe color
            
            # Add the line pattern as another symbol layer
            symbol.appendSymbolLayer(line_pattern_fill)
            
            # Apply the symbol to the layer
            renderer = QgsSingleSymbolRenderer(symbol)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
            
            self.log(f"    - Applied Buildings striped style")
            
        except Exception as e:
            self.log(f"ERROR applying Buildings style: {str(e)}")
            # Fallback to simple blue style
            symbol = QgsFillSymbol.createSimple({
                'color': '0,70,200,100',
                'outline_color': '0,70,200,255',
                'outline_width': '0.5',
                'outline_style': 'solid'
            })
            renderer = QgsSingleSymbolRenderer(symbol)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
    
    def apply_survey_area_style(self, layer):
        """Apply the specific style for Survey Area layer"""
        try:
            if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
                return
            
            # Create symbol with transparent fill and red outline
            symbol = QgsFillSymbol.createSimple({
                'color': '0,0,0,0',  # Transparent fill
                'outline_color': '228,26,28,255',  # Red outline
                'outline_width': '0.96',
                'outline_style': 'solid'
            })
            
            # Apply the symbol
            renderer = QgsSingleSymbolRenderer(symbol)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
            
            self.log(f"    - Applied Survey Area style")
            
        except Exception as e:
            self.log(f"ERROR applying Survey Area style: {str(e)}")
    
    def copy_supporting_files(self, original_project_path, target_dir):
        """Copy all supporting files except DCIM folder"""
        try:
            original_dir = os.path.dirname(original_project_path)
            
            # Don't copy if source and target are the same
            if original_dir == target_dir:
                return
            
            self.log("Copying supporting files...")
            
            for item in os.listdir(original_dir):
                item_path = os.path.join(original_dir, item)
                
                # Skip DCIM folder
                if item.upper() == "DCIM":
                    continue
                
                # Skip the new resurvey project directory
                if os.path.basename(target_dir) == item:
                    continue
                
                # Skip QGIS project files (we'll create new ones)
                if item.endswith(('.qgs', '.qgz')):
                    continue
                
                target_path = os.path.join(target_dir, item)
                
                # Copy files and directories
                if os.path.isdir(item_path):
                    if not os.path.exists(target_path):
                        shutil.copytree(item_path, target_path, 
                                       ignore=shutil.ignore_patterns('DCIM', '*_resurvey*'))
                        self.log(f"    - Copied directory: {item}")
                else:
                    shutil.copy2(item_path, target_path)
                    self.log(f"    - Copied file: {item}")
                    
        except Exception as e:
            self.log(f"ERROR copying files: {str(e)}")
    
    def create_zip(self, source_dir, output_dir):
        """Create a zip file of the resurvey project"""
        try:
            project_name = os.path.basename(source_dir)
            zip_filename = f"{project_name}.zip"
            zip_path = os.path.join(output_dir, zip_filename)
            
            # Remove existing zip if it exists
            if os.path.exists(zip_path):
                os.remove(zip_path)
            
            self.log(f"Creating zip file: {zip_path}")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(source_dir):
                    # Skip DCIM folder
                    dirs[:] = [d for d in dirs if d.upper() != "DCIM"]
                    
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source_dir)
                        zipf.write(file_path, arcname)
            
            self.log(f"Created zip file successfully: {zip_path}")
            return zip_path
            
        except Exception as e:
            self.log(f"ERROR creating zip file: {str(e)}")
            return None
    
    def run_validation(self):
        """Main method to run the data quality validation"""
        self.log("=" * 60)
        self.log("Starting Data Quality Validation...")
        self.log(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("=" * 60)
        
        # Check for unsurveyed features
        layers_to_process = self.check_all_layers_for_unsurveyed()
        
        if not layers_to_process:
            self.log("\nNo layers with SURVEYED field found to process.")
            self.log("=" * 60)
            
            if self.iface:
                self.iface.messageBar().pushInfo(
                    "Data Quality Check",
                    "No layers with SURVEYED field found."
                )
            return False
        
        self.log(f"\nFound {self.unsurveyed_count} unsurveyed features across {len(layers_to_process)} layers")
        
        # Create resurvey project
        self.log("\nCreating resurvey project...")
        zip_path = self.create_resurvey_project(layers_to_process)
        
        if zip_path:
            self.log(f"\n✓ Resurvey project created successfully!")
            self.log(f"✓ Zip file: {zip_path}")
            
            # Show success message
            if self.iface:
                self.iface.messageBar().pushSuccess(
                    "Resurvey Project Created",
                    f"Created '{os.path.basename(zip_path)}' with modified symbology"
                )
            
            self.log("=" * 60)
            return True
        else:
            self.log("\n✗ ERROR: Failed to create resurvey project")
            self.log("=" * 60)
            
            if self.iface:
                self.iface.messageBar().pushCritical(
                    "Data Quality Check Failed",
                    "Could not create resurvey project"
                )
            return False