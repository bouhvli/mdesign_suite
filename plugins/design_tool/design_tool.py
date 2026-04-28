import os
from datetime import datetime

from qgis.core import (  # type: ignore
    Qgis,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant  # type: ignore
from qgis.PyQt.QtCore import QTimer  # type: ignore
from qgis.PyQt.QtGui import QIcon  # type: ignore
from qgis.PyQt.QtWidgets import QAction, QFileDialog  # type: ignore
from .utils.plugin_logger import PluginLogger

from .core.design_engine import DesignEngine
from .design_tool_dialog import DesignToolDialog
from .utils.extract_design_session import extract_design_session_name
from .utils.project_handler import load_project
from .utils.report_generator import generate_html_report
from .utils.external_map_loader import add_external_wfs_layers, import_external_maps
from .utils.violation_details import get_violation_details
from .utils.layer_loader import get_layer_by_name  # Import the utility function

import importlib
import sys
import gc

class DesignTool:
    def __init__(self, iface):
        self.iface = iface
        self.dialog = None
        self.progress_timer = None
        self.current_progress = 0

        self.actions = []
        self.design_engine = None  # Track engine if needed across runs
        # Initialize logger
        # Note: SUPABASE_URL should be the project URL and SUPABASE_KEY the API key/token.
        SUPABASE_URL = "https://mjqzyvlkxjvemmkostrv.supabase.co"
        SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1qcXp5dmxreGp2ZW1ta29zdHJ2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjMxMDE5OTIsImV4cCI6MjA3ODY3Nzk5Mn0.xfuztVHXgDIxuueFi4zDt4sVdw4pJ8VJsRc3bA_SJ50"
        self.logger = PluginLogger(SUPABASE_URL, SUPABASE_KEY)

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        self.action = QAction(
            QIcon(icon_path), "Design Tool", self.iface.mainWindow()
        )
        self.action.triggered.connect(self.run)
        self.actions.append(self.action)
        self.iface.addPluginToMenu("Design", self.action)

    def get_actions(self):
        return self.actions

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        self.iface.removePluginMenu("Design", self.action)
        if self.dialog:
            self.dialog.close()
        self.reset_plugin()  # Ensure cleanup on unload

    def run(self):
        """Run method that performs all the real work"""
        if self.dialog is None:
            self.dialog = DesignToolDialog(self.iface.mainWindow())

            self.dialog.clearLogButton.clicked.connect(self.clear_log)
            self.dialog.saveLogButton.clicked.connect(self.save_log)

            # Optional: Add manual reset button to dialog if desired
            # self.dialog.resetButton.clicked.connect(self.reset_plugin)  # Assuming you add a resetButton in the dialog UI

        self.dialog.button_box.accepted.disconnect()  # Disconnect default
        self.dialog.button_box.accepted.connect(self.handle_run_request)

        self.dialog.show()

    def log_message(self, message, message_type="INFO"):
        """Add a message to the log with timestamp and type"""
        if self.dialog and hasattr(self.dialog, "logTextEdit"):
            timestamp = datetime.now().strftime("%H:%M:%S")

            # Color coding based on message type
            color_map = {
                "INFO": "black",
                "SUCCESS": "green",
                "WARNING": "orange",
                "ERROR": "red",
            }

            color = color_map.get(message_type, "black")
            formatted_message = f"<span style=\"color: {color}; font-family: 'Geist Mono', monospace;\">[{timestamp}] [{message_type}] {message}</span>"

            # Move cursor to end and insert HTML
            cursor = self.dialog.logTextEdit.textCursor()
            cursor.movePosition(cursor.End)
            self.dialog.logTextEdit.setTextCursor(cursor)
            self.dialog.logTextEdit.insertHtml(formatted_message + "<br>")

            # Ensure cursor is visible
            self.dialog.logTextEdit.ensureCursorVisible()

            # Also print to console for debugging
            console_msg = f"[{timestamp}] [{message_type}] {message}"
            print(console_msg)

    def clear_log(self):
        """Clear the log text edit"""
        if self.dialog and hasattr(self.dialog, "logTextEdit"):
            self.dialog.logTextEdit.clear()
            self.log_message("Log cleared", "INFO")

    def save_log(self):
        """Save the log to a file"""
        if self.dialog and hasattr(self.dialog, "logTextEdit"):
            file_path, _ = QFileDialog.getSaveFileName(
                self.dialog,
                "Save Log File",
                f"design_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                "Text Files (*.txt);;All Files (*)",
            )
            if file_path:
                try:
                    with open(file_path, "w") as f:
                        f.write(self.dialog.logTextEdit.toPlainText())
                    self.log_message(f"Log saved to: {file_path}", "SUCCESS")
                except Exception as e:
                    self.log_message(f"Failed to save log: {e}", "ERROR")

    def handle_run_request(self):
        """Handle the run request from dialog"""
        self.log_message("Starting process...", "INFO")
        
        # Validate inputs first
        if not self.dialog.validate_inputs_only():# type: ignore
            self.log_message("Input validation failed", "ERROR")
            return
        
        self.log_message("Input validation successful", "SUCCESS")
        
        # Get all inputs
        project_file_path = self.dialog.get_project_file_path()# type: ignore
        output_directory = self.dialog.get_output_directory()# type: ignore
        
        # Get sidewalks intersection analysis parameters
        analyze_intersections = self.dialog.get_analyze_intersections()# type: ignore
        trenches_layer_name = None
        
        if analyze_intersections:
            # Store layer NAME instead of object
            trenches_layer = self.dialog.get_trenches_layer()# type: ignore
            trenches_layer_name = trenches_layer.name() if trenches_layer else None
        
        # Get cluster assignment parameters
        assign_clusters_by_distribution = self.dialog.get_assign_clusters_by_distribution()# type: ignore
        
        # Get address update parameters
        update_addresses = self.dialog.updateAddressesCheckbox.isChecked()# type: ignore
        point_layer_name = None
        surveyed_addresses_file = None
        
        if update_addresses:
            # Store layer NAME instead of object
            # point_layer = self.dialog.pointLayerComboBox.currentLayer()# type: ignore
            # point_layer_name = point_layer.name() if point_layer else None
            surveyed_addresses_file = self.dialog.get_surveyed_addresses_file_path()# type: ignore
        
        # Start processing with all parameters
        self.process_inputs_with_progress(
            project_file_path=project_file_path,
            output_directory=output_directory,
            analyze_intersections=analyze_intersections,
            trenches_layer_name=trenches_layer_name,  # Pass name instead of object
            update_addresses=update_addresses,
            surveyed_addresses_file=surveyed_addresses_file,
            assign_clusters_by_distribution=assign_clusters_by_distribution
        )

    def process_inputs_with_progress(
        self, 
        project_file_path, 
        output_directory,
        analyze_intersections=False,
        trenches_layer_name=None,  # Changed from trenches_layer to name
        update_addresses=False,
        surveyed_addresses_file=None,
        assign_clusters_by_distribution=False
    ):
        """Process the inputs from the dialog with progress bar updates"""
        self.dialog.show()# type: ignore
        self.dialog.start_processing()# type: ignore
        self.current_progress = 0
        self.start_progress_simulation()

        try:
            self.process_inputs(
                project_file_path=project_file_path,
                output_directory=output_directory,
                analyze_intersections=analyze_intersections,
                trenches_layer_name=trenches_layer_name,  # Pass name
                update_addresses=update_addresses,
                surveyed_addresses_file=surveyed_addresses_file,
                assign_clusters_by_distribution=assign_clusters_by_distribution
            )
        except Exception as e:
            error_msg = f"failed: {e}"
            self.log_message(error_msg, "ERROR")
            self.iface.messageBar().pushMessage("Error", error_msg, level=Qgis.Critical)
        finally:
            self.finish_progress()
            self.reset_plugin()

    def start_progress_simulation(self):
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self.update_progress)
        self.progress_timer.start(100)

    def update_progress(self):
        if self.current_progress < 95:
            if self.current_progress < 50:
                increment = 2
            elif self.current_progress < 80:
                increment = 1
            else:
                increment = 0.5

            self.current_progress += increment
            self.dialog.update_progress(int(self.current_progress))# type: ignore

    def finish_progress(self):
        if self.progress_timer:
            self.progress_timer.stop()
            self.progress_timer = None

        self.current_progress = 100
        self.dialog.update_progress(100)# type: ignore
        self.dialog.finish_processing()# type: ignore

    def update_progress_step(self, message, progress):
        """Update progress bar and message"""
        self.log_message(message, "INFO")
        self.current_progress = max(self.current_progress, progress)
        self.dialog.update_progress(int(self.current_progress)) # type: ignore

    def process_inputs(
        self, 
        project_file_path, 
        output_directory,
        analyze_intersections=False,
        trenches_layer_name=None,  # Changed from trenches_layer
        update_addresses=False,
        surveyed_addresses_file=None,
        assign_clusters_by_distribution=False
    ):
        """Process the inputs from the dialog"""
        self.log_message("Processing inputs:", "INFO")
        self.log_message(f"Project File: {project_file_path}", "INFO")
        self.log_message(f"Output Directory: {output_directory}", "INFO")
        
        # Log cluster assignment parameter
        if assign_clusters_by_distribution:
            self.log_message("✓ Cluster assignment by distribution cables: ENABLED", "SUCCESS")
        else:
            self.log_message("○ Cluster assignment by distribution cables: DISABLED", "INFO")
        
        # Log sidewalks intersection analysis parameters
        self.log_message(f"Trenches layer name: {trenches_layer_name}", "INFO")

        # Load layers using get_layer_by_name utility function
        trenches_layer = None
        point_layer = None
        
        if analyze_intersections and trenches_layer_name:
            self.log_message(f"Looking for trenches layer: {trenches_layer_name}", "INFO")
            trenches_layer = get_layer_by_name(trenches_layer_name)
            if trenches_layer:
                self.log_message(f"✓ Successfully loaded trenches layer: {trenches_layer.name()}", "SUCCESS")
            else:
                self.log_message(f"✗ Could not load trenches layer: {trenches_layer_name}", "ERROR")
                # You might want to decide whether to continue or abort here

        self.update_progress_step("Loading project file...", 10)
        # load project file
        extracted_layers = load_project(project_file_path)
        self.log_message(
            f"Extracted {len(extracted_layers)} layers from project.", "INFO"
        )
        # Log the layer names for debugging
        layer_names = list(extracted_layers.keys())
        self.log_message(f"Layer names: {layer_names}", "INFO")
        
        self.update_progress_step(
            f"Extracted {len(extracted_layers)} layers from project.", 20
        )

        if update_addresses:
            point_layer = get_layer_by_name("IN_HomePoints")
            if point_layer:
                self.log_message(f"✓ Successfully loaded point layer: {point_layer.name()}", "SUCCESS")
            else:
                self.log_message(f"✗ Could not load point layer: {'IN_HomePoints'}", "ERROR")
                # You might want to decide whether to continue or abort here
                # For address updates, you might want to disable the feature if layer can't be loaded
                update_addresses = False
                self.log_message("Address update feature disabled due to missing point layer", "WARNING")

        # Create a unique sub-folder for this run
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_name = extract_design_session_name(project_file_path)
        run_folder_name = f"design_{session_name}_{timestamp}"
        run_output_directory = os.path.join(output_directory, run_folder_name)

        try:
            os.makedirs(run_output_directory, exist_ok=True)
            self.log_message(
                f"Created output directory: {run_output_directory}", "SUCCESS"
            )
        except Exception as e:
            error_msg = f"Could not create output directory: {e}"
            self.log_message(error_msg, "ERROR")
            self.iface.messageBar().pushMessage("Error", error_msg, level=Qgis.Critical)
            return
        
        self.update_progress_step("Running checks...", 41)
        self.log_message("Running checks...", "INFO")
        
        # IMPORTANT: Use the freshly loaded layer objects, not the names
        self.design_engine = DesignEngine(
            run_output_directory=run_output_directory,
            project_file_path=project_file_path,
            update_addresses=update_addresses,
            point_layer=point_layer,  # Use the loaded layer object
            surveyed_addresses_file=surveyed_addresses_file,
            analyze_intersections=analyze_intersections,
            trenches_layer_name=trenches_layer.name() if trenches_layer else None,  # Pass name to DesignEngine
            assign_clusters_by_distribution=assign_clusters_by_distribution
        )
        
        try:
            design_results = self.design_engine.run_design()
            for result in design_results:
                if result is None:
                    continue
                if result.get('operation') == 'sync_addresses_from_survey':
                    if result['status'] == 'completed':
                        self.log_message(f"Address synchronization completed successfully", "SUCCESS")
                        self.log_message(f"Demand groups processed: {result['demand_groups_processed']}", "INFO")
                        self.log_message(f"Demand groups adjusted: {result['demand_groups_adjusted']}", "INFO")
                        self.log_message(f"Addresses added: {result['addresses_added']}", "INFO")
                        self.log_message(f"Addresses deleted: {result['addresses_deactivated']}", "INFO")
                        self.log_message(f"Addresses orphaned: {result['orphaned_removed']}", "INFO")
                        self.log_message(f"Final In_homepoints count: {result['final_count']}", "INFO")
                        self.log_message(f"Detailed logs: {result['detailed_logs']}", "INFO")
                        self.log_message(f"Verification summary: {result['verification_summary']}", "INFO")

                        # Log detailed information
                        if 'detailed_logs' in result:
                            self.log_message("=== Address Synchronization Details ===", "INFO")
                            for log_entry in result['detailed_logs']:
                                self.log_message(log_entry, "INFO")
                            self.log_message("========================================", "INFO")
                        
                        # Log added addresses shapefile export
                        if 'added_export_result' in result:
                            added_result = result['added_export_result']
                            if added_result.get('status') == 'completed':
                                self.log_message("=== Added Addresses Shapefile ===", "SUCCESS")
                                self.log_message(f"Layer name: {added_result.get('layer_name')}", "INFO")
                                self.log_message(f"Shapefile path: {added_result.get('shapefile_path')}", "INFO")
                                self.log_message(f"Features: {added_result.get('feature_count')}", "INFO")
                                self.log_message(added_result.get('message'), "SUCCESS")
                                self.log_message("==================================", "INFO")
                            elif added_result.get('status') == 'skipped':
                                self.log_message(f"Added addresses: {added_result.get('message')}", "INFO")
                            else:
                                self.log_message(f"Added addresses export failed: {added_result.get('error')}", "WARNING")
                        
                        # Log deleted addresses shapefile export
                        if 'deleted_export_result' in result:
                            deleted_result = result['deleted_export_result']
                            if deleted_result.get('status') == 'completed':
                                self.log_message("=== Deleted Addresses Shapefile ===", "SUCCESS")
                                self.log_message(f"Layer name: {deleted_result.get('layer_name')}", "INFO")
                                self.log_message(f"Shapefile path: {deleted_result.get('shapefile_path')}", "INFO")
                                self.log_message(f"Features: {deleted_result.get('feature_count')}", "INFO")
                                self.log_message(deleted_result.get('message'), "SUCCESS")
                                self.log_message("====================================", "INFO")
                            elif deleted_result.get('status') == 'skipped':
                                self.log_message(f"Deleted addresses: {deleted_result.get('message')}", "INFO")
                            else:
                                self.log_message(f"Deleted addresses export failed: {deleted_result.get('error')}", "WARNING")
                    else:
                        self.log_message(f"Address synchronization failed: {result.get('error', 'Unknown error')}", "ERROR")
        except Exception as e:
             import traceback
             full_traceback = traceback.format_exc()
             self.log_message(f"{type(e).__name__} in run_design: {e}", "ERROR")
             self.log_message(f"Traceback:\n{full_traceback}", "ERROR")
             raise
        self.update_progress_step("Generating reports...", 68)
        self.log_message("checks completed.", "SUCCESS")
        # Generate reports
        # csv_report = generate_csv_report(self.path,run_output_directory, design_results)
        #html_report = generate_html_report(
            #self.path, run_output_directory, design_results
        #)
        #self.log_message(f"Reports generated:{html_report}", "INFO")

        # Add external WFS layers as basemaps
        self.update_progress_step("Adding external basemaps...", 99)
        add_external_wfs_layers(self.log_message)
        import_external_maps()
        self.log_message("External basemaps added", "SUCCESS")
        # Show completion message
        completion_msg = (
            f"Design completed."
        )
        # LOG THE SURVEY CREATION HERE
        self.logger.log(
            types="design",
            design_session=session_name,
            description=f"design design"
        )
        self.log_message(completion_msg, "SUCCESS")
        self.iface.messageBar().pushMessage(
            "Success", completion_msg, level=Qgis.Success, duration=5
        )

    def reset_plugin(self):
        """Automatically reset the plugin state after each run by reloading modules and cleaning up."""
        try:
            # Close any active multiprocessing resources if tracked (e.g., if designEngine has a pool)
            if hasattr(self, 'design_engine') and self.design_engine is not None:
                # Assuming designEngine might have a pool or other resources; add cleanup if needed
                # e.g., if 'pool' in self.design_engine.__dict__: self.design_engine.pool.close(); etc.
                self.design_engine = None  # Dereference

            # Force garbage collection to clear lingering objects (e.g., spatial indexes, features)
            gc.collect()

            # Reload critical modules to reset any global/stateful variables (e.g., multiprocessing in poc_validator)
            modules_to_reload = [
                'core.design_engine'
            ]
            for module_name in modules_to_reload:
                full_module_path = f"{__package__}.{module_name}"
                if full_module_path in sys.modules:
                    importlib.reload(sys.modules[full_module_path])
                    self.log_message(f"Reloaded module: {module_name}", "INFO")

            # Reinitialize any persistent state if needed (e.g., if you cache layers globally)
            # self.design_engine = None  # Already done above

            self.log_message("Plugin state reset successfully after run", "SUCCESS")

        except Exception as e:
            self.log_message(f"Reset failed: {str(e)}", "ERROR")
            self.iface.messageBar().pushMessage("Error", f"Reset failed: {str(e)}", level=Qgis.Critical)