import os
import traceback

from docx import Document
from docx.shared import Inches
from qgis.core import (QgsFillSymbol, QgsLayout,  # type: ignore
                       QgsLayoutExporter, QgsLayoutItemMap, QgsLayoutPoint,
                       QgsLayoutSize, QgsProject, QgsRectangle,
                       QgsRuleBasedRenderer, QgsSimpleFillSymbolLayer,
                       QgsUnitTypes)
from qgis.PyQt.QtCore import QRectF  # type: ignore
from qgis.PyQt.QtCore import Qt  # type: ignore
from qgis.PyQt.QtGui import QColor  # type: ignore
from qgis.utils import iface  # type: ignore


def uncheck_locked_symbols(project, target_layer_names=None):
    """
    Unchecks (disables) symbols that have the label "Locked" for layers with QgsRuleBasedRenderer.
    
    Args:
        project: QgsProject instance
        target_layer_names: List of layer names to process. If None, processes all layers.
    
    Returns:
        dict: Dictionary storing original states for potential restoration
    """
    original_states = {}
    
    # Get layers to process
    if target_layer_names:
        layers_to_process = []
        for layer_name in target_layer_names:
            layers = project.mapLayersByName(layer_name)
            if layers:
                layers_to_process.extend(layers)
            # else:
            #     print(f"Warning: Layer '{layer_name}' not found.")
    else:
        # Process all layers in the project
        layers_to_process = list(project.mapLayers().values())
    
    for layer in layers_to_process:
        if not hasattr(layer, 'renderer') or not layer.renderer():
            continue
            
        renderer = layer.renderer()
        
        # Only process rule-based renderers
        if isinstance(renderer, QgsRuleBasedRenderer):
            # print(f"Processing rule-based layer: '{layer.name()}'")
            original_states[layer.id()] = {}
            
            root_rule = renderer.rootRule()
            modified = False
            
            # Process all rules recursively
            def process_rules(rule, path=""):
                nonlocal modified
                
                # Check if this rule has a label containing "Locked"
                rule_label = rule.label() if rule.label() else ""
                rule_key = rule.ruleKey()
                current_path = f"{path}/{rule_label}" if path else rule_label
                
                
                if "Locked" in rule_label:
                    # Store original state
                    original_states[layer.id()][rule_key] = rule.active()
                    
                    if rule.active():
                        rule.setActive(False)
                        modified = True
                # Process child rules recursively
                for child_rule in rule.children():
                    process_rules(child_rule, current_path)
            
            # Start processing from root rule
            for child_rule in root_rule.children():
                process_rules(child_rule)
            
            if modified:
                # Update the renderer and trigger repaint
                layer.setRenderer(renderer.clone())
                layer.triggerRepaint()
    
    # Refresh canvas after all layers are processed

    if iface:
        iface.mapCanvas().refreshAllLayers()
        #print("Canvas refreshed after unchecking locked symbols.")
    
    return original_states

def restore_locked_symbols(project, original_states):
    """
    Restores the original active/inactive state of previously modified locked symbols.
    
    Args:
        project: QgsProject instance
        original_states: Dictionary returned by uncheck_locked_symbols
    """
    if not original_states:
        return
    
    for layer_id, rule_states in original_states.items():
        layer = project.mapLayer(layer_id)
        if not layer or not layer.renderer():
            continue
            
        renderer = layer.renderer()
        if not isinstance(renderer, QgsRuleBasedRenderer):
            continue
            
        root_rule = renderer.rootRule()
        modified = False
        
        def restore_rules(rule):
            nonlocal modified
            rule_key = rule.ruleKey()
            
            if rule_key in rule_states:
                original_state = rule_states[rule_key]
                if rule.active() != original_state:
                    rule.setActive(original_state)
                    modified = True
            
            # Process child rules recursively
            for child_rule in rule.children():
                restore_rules(child_rule)
        
        # Start restoring from root rule
        for child_rule in root_rule.children():
            restore_rules(child_rule)
        
        if modified:
            layer.setRenderer(renderer.clone())
            layer.triggerRepaint()
    
    #print("Restored original locked symbol states.")

def run_report(iface, layer_name_filter, output_dir, report_title, max_violations):
    print("=== Starting Feature Report Generation ===")
    project = QgsProject.instance()
    locked_symbol_states = {}
    
    try:
        # Uncheck locked symbols for all layers
        locked_symbol_states = uncheck_locked_symbols(project)
        iface.mapCanvas().refreshAllLayers()

        # Find all layers that contain the filter string
        all_layers = QgsProject.instance().mapLayers().values()
        matching_layers = [layer for layer in all_layers if layer_name_filter.lower() in layer.name().lower()]
        
        if not matching_layers:
            available_layers = [layer.name() for layer in all_layers]
            # print(f"ERROR: No layers found containing '{layer_name_filter}'")
            # print(f"Available layers: {available_layers}")
            return False
        
        #print(f"Found {len(matching_layers)} layers matching '{layer_name_filter}':")
        for layer in matching_layers:
            print(f"  - {layer.name()} ({layer.featureCount()} features)")
        
        # Validate output directory
        try:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
        except Exception as e:
            print(f"ERROR: Cannot create/access output directory: {e}")
            return False
        
        # Check canvas
        canvas = iface.mapCanvas()
        if not canvas:
            #print("ERROR: Cannot access map canvas")
            return False
        
        #print("SUCCESS: Map canvas accessible")
        
        # Initialize Word document
        try:
            doc = Document()
            doc.add_heading(report_title, 0)
        except Exception as e:
            print(f"ERROR: Failed to initialize Word document: {e}")
            return False
        
        # Process each matching layer
        total_processed = 0
        total_successful = 0
        
        for layer_idx, layer in enumerate(matching_layers, 1):
            if not layer.isValid():
                #print(f"WARNING: Layer '{layer.name()}' is not valid, skipping")
                continue
            
            feature_count = layer.featureCount()
            #print(f"\n--- Processing Layer {layer_idx}/{len(matching_layers)}: {layer.name()} ({feature_count} features) ---")
            
            # Get features (limit if specified)
            features = list(layer.getFeatures())
            if max_violations:
                features = features[:max_violations]
            
            for i, feature in enumerate(features, 1):
                try:
                    # Get feature ID
                    feature_id = get_feature_id(feature)
                    #print(f"Processing feature {i}/{len(features)}: {feature_id}")
                    
                    # Check geometry
                    geom = feature.geometry()
                    if not geom or geom.isEmpty():
                        print(f"WARNING: Feature {feature_id} has no geometry, skipping")
                        continue
                    
                    # Calculate extent
                    bbox = geom.boundingBox()
                    if bbox.isEmpty():
                        print(f"WARNING: Feature {feature_id} has empty bounding box, skipping")
                        continue
                    
                    # Buffer extent (add 10% margin)
                    buffer_x = max(bbox.width() * 0.02, 10)
                    buffer_y = max(bbox.height() * 0.02, 10)
                    
                    buffered_bbox = QgsRectangle(
                        bbox.xMinimum() - buffer_x,
                        bbox.yMinimum() - buffer_y,
                        bbox.xMaximum() + buffer_x,
                        bbox.yMaximum() + buffer_y
                    )
                    
                    # Set canvas extent
                    canvas.setExtent(buffered_bbox)
                    canvas.refresh()
                    
                    # Create layout
                    layout = create_feature_layout(project, buffered_bbox, layer.crs())
                    
                    # Export image
                    image_path = os.path.join(output_dir, f"feature_{feature_id}.png")
                    
                    if export_layout_image(layout, image_path):
                        total_successful += 1
                        
                        # Add to Word document
                        try:
                            doc.add_heading(f"Feature {feature_id}", level=2)
                            doc.add_picture(image_path, width=Inches(6))
                            doc.add_paragraph(f"Rule ID: {feature['rule_id']}")
                            doc.add_paragraph(f"Violation: {feature['violation_']}")
                            doc.add_paragraph(f"Description: {feature['details']}")
                            doc.add_paragraph("")  # Add spacing
                        except Exception as e:
                            print(f"WARNING: Failed to add feature {feature_id} to Word document: {e}")
                    else:
                        print(f"FAILED: Could not export {image_path}")
                    
                    total_processed += 1
                    
                except Exception as e:
                    print(f"ERROR processing feature: {e}")
                    traceback.print_exc()
                    continue
            
            #print(f"Layer '{layer.name()}' complete: {total_successful - (total_successful - total_processed)} features exported")
        
        # Save Word document
        word_path = os.path.join(output_dir, "feature_report.docx")
        try:
            doc.save(word_path)
            #print(f"\nSUCCESS: Saved Word document at {word_path}")
        except Exception as e:
            print(f"ERROR: Failed to save Word document: {e}")
            return False
        
        # print(f"\n=== Summary ===")
        # print(f"Total layers processed: {len(matching_layers)}")
        # print(f"Total features processed: {total_processed}")
        # print(f"Total successful exports: {total_successful}")
        
        if total_successful > 0:
            #print(f"SUCCESS: Generated comprehensive report with {total_successful} features from {len(matching_layers)} layers!")
            return True
        else:
            print("ERROR: No features were successfully exported")
            return False
            
    except Exception as e:
        #print(f"FATAL ERROR: {e}")
        traceback.print_exc()
        return False
    finally:
        # Restore locked symbols
        restore_locked_symbols(project, locked_symbol_states)
        iface.mapCanvas().refreshAllLayers()
        #print("=== Feature Report Generation Completed ===")
def get_feature_id(feature):
    """Get feature ID from various possible fields"""
    id_fields = ['id', 'ID', 'fid', 'FID', 'objectid', 'OBJECTID', 'gid', 'GID']
    
    for field_name in id_fields:
        try:
            if field_name in [f.name() for f in feature.fields()]:
                value = feature[field_name]
                if value is not None:
                    return str(value)
        except Exception as e:
            print(f"Error getting feature ID: {e}")
            continue
    
    return str(feature.id())

def create_feature_layout(project, extent, crs):
    """Create a layout for a single feature (map only, no text)"""
    layout = QgsLayout(project)
    layout.initializeDefaults()
    
    # Remove page border and set white background
    try:
        if layout.pageCollection().pageCount() > 0:
            page = layout.pageCollection().page(0)
            page.setPageSize(QgsLayoutSize(210, 297, QgsUnitTypes.LayoutMillimeters))
            
            # Create a simple white fill symbol with no border
            symbol = QgsFillSymbol()
            symbol.deleteSymbolLayer(0)  # Remove default symbol layer
            simple_fill = QgsSimpleFillSymbolLayer()
            simple_fill.setColor(QColor(255, 255, 255))  # White
            simple_fill.setStrokeStyle(Qt.NoPen)  # No border
            symbol.appendSymbolLayer(simple_fill)
            
            page.setPageStyleSymbol(symbol)
    except Exception as e:
        print(f"Warning: Could not configure page style: {e}")
    
    # Add map item with white background
    map_item = QgsLayoutItemMap(layout)
    map_item.setFrameEnabled(False)  # Remove map frame
    map_item.setBackgroundEnabled(True)  # Enable background
    map_item.setBackgroundColor(QColor(255, 255, 255))  # White background
    
    # Set map position and size
    try:
        map_item.attemptSetSceneRect(QRectF(10, 10, 190, 260))  # Increased height to fill page
    except Exception as e:
        try:
            map_item.attemptMove(QgsLayoutPoint(10, 10, QgsUnitTypes.LayoutMillimeters))
            map_item.attemptResize(QgsLayoutSize(190, 260, QgsUnitTypes.LayoutMillimeters))
        except Exception as e:
            print(f"Error setting map item position/size: {e}")
            pass
    
    map_item.setCrs(crs)
    map_item.setExtent(extent)
    layout.addLayoutItem(map_item)

    return layout

def export_layout_image(layout, output_path):
    """Export layout to PNG image"""
    try:
        # First refresh the layout to ensure everything is rendered properly
        layout.refresh()
        
        exporter = QgsLayoutExporter(layout)
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 300
        settings.cropToContents = True  # Keep white background
        
        # Set image format to PNG with better quality
        settings.imageFormat = "PNG"
        
        result = exporter.exportToImage(output_path, settings)
        
        if result == QgsLayoutExporter.Success:
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                return True
            else:
                return False
        else:
            return False
        
    except Exception as e:
        #print(f"Export error: {e}")
        traceback.print_exc()
        return False