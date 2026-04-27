# -*- coding: utf-8 -*-
"""
Custom map tool for identifying features and displaying images
"""

import os
from qgis.PyQt.QtCore import Qt
from qgis.PyQt import QtWidgets
from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsMapToolIdentifyFeature, QgsRubberBand


class ImageIdentifyMapTool(QgsMapToolIdentifyFeature):
    """Custom map tool for identifying features and displaying images."""
    
    def __init__(self, canvas, dock_widget):
        """Constructor.
        
        :param canvas: The map canvas
        :param dock_widget: The dock widget for displaying results
        """
        super().__init__(canvas)
        self.canvas = canvas
        self.dock_widget = dock_widget
        self.rubber_band = None
        
        # Set cursor
        self.setCursor(Qt.CrossCursor)
    
    def activate(self):
        """Activate the tool."""
        super().activate()
        self.create_rubber_band()
    
    def deactivate(self):
        """Deactivate the tool."""
        if self.rubber_band:
            self.canvas.scene().removeItem(self.rubber_band)
            self.rubber_band = None
        super().deactivate()
    
    def create_rubber_band(self):
        """Create rubber band for highlighting selected features."""
        if self.rubber_band:
            self.canvas.scene().removeItem(self.rubber_band)
        
        self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setColor(Qt.red)
        self.rubber_band.setWidth(2)
        self.rubber_band.setFillColor(Qt.transparent)
    
    def canvasReleaseEvent(self, event):
        """Handle mouse click events."""
        # Clear previous results
        self.dock_widget.clear_display()
        
        # Find all vector layers
        vector_layers = []
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                vector_layers.append(layer)
        
        if not vector_layers:
            self.show_message("No vector layers found in the project!")
            return
        
        try:
            # Identify features at click position across all vector layers
            point = self.toMapCoordinates(event.pos())
            features_found = False
            
            for layer in vector_layers:
                # Identify features in this layer
                features = self.identify(event.x(), event.y(), [layer], self.TopDownAll)
                
                if features:
                    # Get the first feature from this layer
                    feature = features[0].mFeature
                    self.display_feature_info(feature, layer)
                    
                    # Highlight the feature
                    self.highlight_feature(feature)
                    
                    features_found = True
                    break  # Stop after finding the first feature
            
            if not features_found:
                self.show_message("No features found at this location")
                
        except Exception as e:
            self.show_message(f"Error identifying feature: {str(e)}")
    
    def display_feature_info(self, feature, layer):
        """Display feature attributes and all images."""
        # Add layer information to the display
        layer_info = f"Layer: {layer.name()}"
        self.dock_widget.attributeTable.setRowCount(1)
        self.dock_widget.attributeTable.setItem(0, 0, QtWidgets.QTableWidgetItem("Source"))
        self.dock_widget.attributeTable.setItem(0, 1, QtWidgets.QTableWidgetItem(layer_info))
        
        # Now display the actual feature information
        self.dock_widget.display_feature_info(feature, layer)
    
    def highlight_feature(self, feature):
        """Highlight the selected feature with rubber band."""
        if not self.rubber_band:
            self.create_rubber_band()
        
        self.rubber_band.reset() # type: ignore
        geometry = feature.geometry()
        
        if geometry:
            self.rubber_band.setToGeometry(geometry) # type: ignore
    
    def show_message(self, message):
        """Show message in the dock widget."""
        # Clear any existing content
        self.dock_widget.clear_display()
        
        # Add message to attribute table
        self.dock_widget.attributeTable.setRowCount(1)
        self.dock_widget.attributeTable.setItem(0, 0, QtWidgets.QTableWidgetItem("Information"))
        message_item = QtWidgets.QTableWidgetItem(message)
        message_item.setForeground(Qt.red)  # Make error messages red
        self.dock_widget.attributeTable.setItem(0, 1, message_item)
        
        # Also show in image info label
        self.dock_widget.imageInfoLabel.setText(f"<span style='color: red;'>{message}</span>")