from qgis.core import (QgsProject, QgsVectorLayer, QgsField, QgsFeature, QgsVectorFileWriter, # type: ignore
                      QgsSymbol, QgsMarkerSymbol, QgsRendererCategory,
                      QgsCategorizedSymbolRenderer, QgsPalLayerSettings, QgsTextFormat,
                      QgsTextBufferSettings, QgsVectorLayerSimpleLabeling)
from PyQt5.QtCore import QVariant
from PyQt5.QtGui import QColor, QFont
from qgis.PyQt.QtWidgets import QProgressDialog # type: ignore
from qgis.PyQt.QtCore import Qt # type: ignore
import os
from datetime import datetime


class HomecountValidator:
    """Validator for homecount data in survey projects"""
    
    def __init__(self, iface=None, log_callback=None):
        """Initialize the validator.
        
        Args:
            iface: QGIS interface (optional)
            log_callback: Function to call for logging messages (optional)
        """
        self.iface = iface
        self.log_callback = log_callback or print
        self.flagged_count = 0
        self.output_layer = None
        
    def log(self, message, level="INFO"):
        """Log a message."""
        formatted_message = f"[HomecountValidator] {message}"
        if self.log_callback:
            self.log_callback(formatted_message)
    
    def find_address_points_layer(self):
        """Find the Address Points layer in the project."""
        layer_name = "Address Points"
        
        # Search by name
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name() == layer_name and isinstance(layer, QgsVectorLayer):
                return layer
        
        # Try alternative names
        alternative_names = ["Address", "address_points", "AddressPoints", "Demand Points"]
        for alt_name in alternative_names:
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsVectorLayer) and alt_name.lower() in layer.name().lower():
                    self.log(f"Found layer by alternative name: {layer.name()}")
                    return layer
        
        self.log(f"Layer '{layer_name}' not found in project!", "ERROR")
        return None
    
    def validate_required_fields(self, layer):
        """Check if required fields exist in the layer."""
        required_fields = ['P2P_HOMES', 'SURVEYED']
        layer_fields = [field.name() for field in layer.fields()]
        
        missing_fields = []
        for field in required_fields:
            if field not in layer_fields:
                missing_fields.append(field)
        
        if missing_fields:
            self.log(f"Missing required fields: {missing_fields}", "ERROR")
            self.log(f"Available fields: {layer_fields}", "DEBUG")
            return False
        
        return True
    
    def create_resurvey_flags(self, show_progress=True):
        """Main function to check Address Points layer for resurvey issues and create flagged shapefile."""
        
        # Find the Address Points layer
        layer = self.find_address_points_layer()
        if not layer:
            return None
        
        self.log(f"Found layer: {layer.name()} (Type: {layer.geometryType()})")
        
        # Check if layer is valid
        if not layer.isValid():
            self.log("Layer is not valid!", "ERROR")
            return None
        
        # Check required fields
        if not self.validate_required_fields(layer):
            return None
        
        # Create output layer with same geometry type as source
        output_crs = layer.crs()
        
        # Define geometry type string for memory layer
        geom_type_map = {
            0: "Point",
            1: "LineString", 
            2: "Polygon",
            3: "MultiPoint",
            4: "MultiLineString",
            5: "MultiPolygon"
        }
        
        geom_type = geom_type_map.get(layer.geometryType(), "Point")
        
        # Create memory layer
        self.output_layer = QgsVectorLayer(
            f"{geom_type}?crs={output_crs.authid()}", 
            "Address_Resurvey_Flags", 
            "memory"
        )
        output_data = self.output_layer.dataProvider()
        
        # Add all original fields plus new ones
        fields = layer.fields()
        fields.append(QgsField("ISSUE_TYPE", QVariant.String, len=50))
        fields.append(QgsField("COMMENT", QVariant.String, len=255))
        fields.append(QgsField("FLAG_DATE", QVariant.String, len=20))
        
        output_data.addAttributes(fields)
        self.output_layer.updateFields()
        
        # Get current date
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Counter for flagged features
        self.flagged_count = 0
        
        # Start editing
        self.output_layer.startEditing()
        
        # Create progress dialog if requested
        progress = None
        if show_progress and self.iface:
            total_features = layer.featureCount()
            progress = QProgressDialog(
                "Validating address points...", 
                "Cancel", 
                0, 
                total_features,
                self.iface.mainWindow()
            )
            progress.setWindowModality(Qt.WindowModal)
            progress.setWindowTitle("Homecount Validation")
        
        # Iterate through features
        total_features = layer.featureCount()
        self.log(f"Processing {total_features} features...")
        
        try:
            for i, feature in enumerate(layer.getFeatures()):
                # Update progress dialog
                if progress:
                    progress.setValue(i)
                    if progress.wasCanceled():
                        self.log("Validation cancelled by user", "WARNING")
                        self.output_layer.rollBack()
                        return None
                
                # Get field values
                p2p_homes = feature['P2P_HOMES']
                surveyed = feature['SURVEYED']
                
                issue_type = None
                comment = None
                
                # Check P2P_HOMES condition
                try:
                    if p2p_homes is not None and p2p_homes != '':
                        p2p_val = float(p2p_homes)
                        if p2p_val == 0:
                            issue_type = "ZERO_P2P_HOMES"
                            comment = "Address should be resurveyed - P2P_HOMES is 0"
                except (ValueError, TypeError):
                    # Handle non-numeric P2P_HOMES values
                    if p2p_homes == '0' or str(p2p_homes).strip() == '0':
                        issue_type = "ZERO_P2P_HOMES"
                        comment = "Address should be resurveyed - P2P_HOMES is 0"
                
                # Check SURVEYED condition (only if not already flagged for P2P_HOMES)
                if not issue_type and surveyed is not None:
                    # Handle different representations of False
                    surveyed_str = str(surveyed).upper().strip()
                    if surveyed_str in ['FALSE', 'F', '0', 'NO', 'N']:
                        issue_type = "NOT_SURVEYED"
                        comment = "Address should be resurveyed - SURVEYED is False"
                
                # If any condition met, create flagged feature
                if issue_type and comment:
                    self.flagged_count += 1
                    
                    # Create new feature
                    new_feature = QgsFeature(self.output_layer.fields())
                    
                    # Copy all attributes from original
                    attrs = feature.attributes()
                    for idx, attr in enumerate(attrs):
                        if idx < len(feature.fields()):
                            new_feature.setAttribute(idx, attr)
                    
                    # Set new attributes
                    new_feature.setAttribute("ISSUE_TYPE", issue_type)
                    new_feature.setAttribute("COMMENT", comment)
                    new_feature.setAttribute("FLAG_DATE", current_date)
                    
                    # Set geometry
                    if feature.geometry():
                        new_feature.setGeometry(feature.geometry())
                    
                    # Add feature to output layer
                    output_data.addFeature(new_feature)
            
            # Commit changes
            self.output_layer.commitChanges()
            self.output_layer.updateExtents()
            
            self.log(f"Found {self.flagged_count} features that need resurvey")
            
        finally:
            # Close progress dialog
            if progress:
                progress.close()
        
        return self.output_layer
    
    def save_to_shapefile(self, output_path=None):
        """Save the flagged layer to a shapefile."""
        if not self.output_layer or self.flagged_count == 0:
            self.log("No flagged features to save", "WARNING")
            return None
        
        # Determine output path
        if not output_path:
            project_path = QgsProject.instance().fileName()
            if project_path and os.path.dirname(project_path):
                project_folder = os.path.dirname(project_path)
            else:
                # Default to home directory
                project_folder = os.path.expanduser("~")
            
            # Create output filename
            base_name = "address_resurvey_flags"
            output_path = os.path.join(project_folder, f"{base_name}.shp")
            
            # Handle file overwriting
            counter = 1
            while os.path.exists(output_path):
                output_path = os.path.join(project_folder, f"{base_name}_{counter}.shp")
                counter += 1
        
        self.log(f"Saving to: {output_path}")
        
        # Save as shapefile
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = "ESRI Shapefile"
        save_options.fileEncoding = "UTF-8"
        
        context = QgsProject.instance().transformContext()
        
        error = QgsVectorFileWriter.writeAsVectorFormatV3(
            self.output_layer,
            output_path,
            context,
            save_options
        )
        
        if error[0] == QgsVectorFileWriter.NoError:
            self.log(f"Successfully saved shapefile to: {output_path}")
            return output_path
        else:
            self.log(f"Error saving shapefile: {error}", "ERROR")
            return None
    
    def load_and_style_layer(self, shapefile_path):
        """Load and style the saved shapefile."""
        if not os.path.exists(shapefile_path):
            self.log(f"Shapefile not found: {shapefile_path}", "ERROR")
            return None
        
        saved_layer = QgsVectorLayer(shapefile_path, "Address Resurvey Flags", "ogr")
        
        if saved_layer.isValid():
            self.apply_styling(saved_layer)
            
            # Add to project
            QgsProject.instance().addMapLayer(saved_layer)
            
            self.log(f"✓ Created flag layer with {self.flagged_count} flagged addresses")
            self.log(f"✓ Layer added to project as 'Address Resurvey Flags'")
            
            # Zoom to layer extent if iface is available
            if self.iface:
                self.iface.setActiveLayer(saved_layer)
                self.iface.zoomToActiveLayer()
                
                # Show message in status bar
                self.iface.messageBar().pushSuccess(
                    "Success", 
                    f"Created resurvey flags layer with {self.flagged_count} addresses"
                )
            
            return saved_layer
        else:
            self.log("Error: Could not load the saved shapefile", "ERROR")
            return None
    
    def apply_styling(self, layer):
        """Apply unique styling and labeling to the flagged layer."""
        if not layer or not layer.isValid():
            self.log("Invalid layer for styling", "ERROR")
            return
        
        # Clear any existing renderer
        layer.setRenderer(None)
        
        # Create categories for different issue types
        categories = []
        
        # Style 1: ZERO_P2P_HOMES (Red)
        if layer.geometryType() == 0:  # Point geometry
            # Red triangle for ZERO_P2P_HOMES
            symbol1 = QgsMarkerSymbol.createSimple({
                'color': '255,0,0,255',
                'size': '4',
                'name': 'triangle',
                'outline_color': '0,0,0,255',
                'outline_width': '0.5'
            })
            
            # Orange circle for NOT_SURVEYED
            symbol2 = QgsMarkerSymbol.createSimple({
                'color': '255,165,0,255',
                'size': '4',
                'name': 'circle',
                'outline_color': '0,0,0,255',
                'outline_width': '0.5'
            })
        else:
            # For non-point geometries, use simple symbols
            symbol1 = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol1.setColor(QColor(255, 0, 0))
            
            symbol2 = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol2.setColor(QColor(255, 165, 0))
        
        # Create categories
        category1 = QgsRendererCategory("ZERO_P2P_HOMES", symbol1, "P2P_HOMES = 0")
        category2 = QgsRendererCategory("NOT_SURVEYED", symbol2, "SURVEYED = False")
        
        categories.append(category1)
        categories.append(category2)
        
        # Create and set categorized renderer
        renderer = QgsCategorizedSymbolRenderer("ISSUE_TYPE", categories)
        layer.setRenderer(renderer)
        
        # Configure labels
        label_settings = QgsPalLayerSettings()
        
        # Use expression to create label
        label_settings.fieldName = "ISSUE_TYPE"
        label_settings.isExpression = False
        
        # Configure text format
        text_format = QgsTextFormat()
        text_format.setSize(9)
        text_format.setColor(QColor(0, 0, 0))
        text_format.setFont(QFont("Arial", 9, QFont.Bold))
        
        # Add text buffer for better readability
        buffer_settings = QgsTextBufferSettings()
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(0.7)
        buffer_settings.setColor(QColor(255, 255, 255))
        text_format.setBuffer(buffer_settings)
        
        label_settings.setFormat(text_format)
        label_settings.enabled = True
        
        # Set label placement for points
        if layer.geometryType() == 0:  # Point
            label_settings.placement = QgsPalLayerSettings.AroundPoint
            label_settings.dist = 2.0  # Distance from point in mm
        
        # Create and apply labeling
        labeling = QgsVectorLayerSimpleLabeling(label_settings)
        layer.setLabeling(labeling)
        layer.setLabelsEnabled(True)
        
        # Refresh the layer
        layer.triggerRepaint()
        
        # Update legend
        if self.iface:
            try:
                self.iface.layerTreeView().refreshLayerSymbology(layer.id())
            except AttributeError:
                self.log("Note: Could not refresh layer symbology in UI", "INFO")
        
        self.log("✓ Applied styling and labels to the flag layer")
    
    def run_full_validation(self, output_path=None):
        """Run the complete validation pipeline."""
        self.log("Starting homecount validation...")
        
        # Step 1: Create resurvey flags
        flagged_layer = self.create_resurvey_flags()
        if not flagged_layer:
            self.log("No flagged features found", "INFO")
            if self.iface:
                self.iface.messageBar().pushWarning("No Issues", "No addresses found that need resurveying.")
            return None
        
        # Step 2: Save to shapefile
        saved_path = self.save_to_shapefile(output_path)
        if not saved_path:
            return None
        
        # Step 3: Load and style the layer
        final_layer = self.load_and_style_layer(saved_path)
        
        return final_layer


# For backward compatibility, keep the original function
def create_resurvey_flags():
    """Legacy function - use HomecountValidator class instead."""
    validator = HomecountValidator()
    return validator.run_full_validation()