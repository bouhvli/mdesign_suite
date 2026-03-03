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

from .core.validation_engine import ValidationEngine
from .design_validation_tool_dialog import DesignValidationToolDialog
from .utils.extract_design_session import extract_design_session_name
from .utils.layout_generator import run_report
from .utils.project_handler import load_project
from .utils.report_generator import generate_html_report
from .utils.external_map_loader import add_external_wfs_layers, import_external_maps
from .utils.violation_details import get_violation_details
from .utils.styling_methods import apply_style_from_qml, setup_labels
from .utils.geometry_fixer import fix_selected_layers

import importlib
import sys
import gc
import multiprocessing  # Import for potential pool management

class DesignValidationTool:
    def __init__(self, iface):
        self.iface = iface
        self.dialog = None
        self.actions = []
        self.progress_timer = None
        self.current_progress = 0

        self.validation_engine = None  # Track engine if needed across runs

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        self.action = QAction(
            QIcon(icon_path), "Design Validation Tool", self.iface.mainWindow()
        )
        self.action.triggered.connect(self.run)
        self.actions.append(self.action)
        self.iface.addPluginToMenu("Design Validation", self.action)

    def get_actions(self):
        return self.actions

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        self.iface.removePluginMenu("Design Validation", self.action)
        if self.dialog:
            self.dialog.close()

    def run(self):
        """Run method that performs all the real work"""
        if self.dialog is None:
            self.dialog = DesignValidationToolDialog(self.iface.mainWindow())

            self.dialog.clearLogButton.clicked.connect(self.clear_log)
            self.dialog.saveLogButton.clicked.connect(self.save_log)
            self.dialog.fixGeometriesButton.clicked.connect(self.handle_fix_geometries)

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
                f"validation_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                "Text Files (*.txt);;All Files (*)",
            )
            if file_path:
                try:
                    with open(file_path, "w") as f:
                        f.write(self.dialog.logTextEdit.toPlainText())
                    self.log_message(f"Log saved to: {file_path}", "SUCCESS")
                except Exception as e:
                    self.log_message(f"Failed to save log: {e}", "ERROR")

    def handle_fix_geometries(self):
        """Handle the fix geometries button click"""
        self.log_message("Starting geometry fix for selected layers...", "INFO")

        try:
            # Call the geometry fixing function with the log function
            results = fix_selected_layers(self.iface, self.log_message)

            # If no layers were selected or processed, the function already logged it
            if results:
                self.log_message("Geometry fix completed successfully", "SUCCESS")
        except Exception as e:
            error_msg = f"Failed to fix geometries: {e}"
            self.log_message(error_msg, "ERROR")
            self.iface.messageBar().pushMessage("Error", error_msg, level=Qgis.Critical)

    def handle_run_request(self):
        """Handle the run request from dialog"""

        self.log_message("Starting validation process...", "INFO")
        # Validate inputs first
        if not self.dialog.validate_inputs_only():  # type: ignore
            self.log_message("Input validation failed", "ERROR")
            return
        self.log_message("Input validation successful", "SUCCESS")
        # Start processing
        self.path = self.dialog.get_project_file_path()  # type: ignore
        self.process_inputs_with_progress(
            self.path,
            self.dialog.get_output_directory(),  # type: ignore
            self.dialog.get_selected_checks(),  # type: ignore
        )

    def process_inputs_with_progress(
        self, project_file_path, output_directory, selected_checks
    ):
        """Process the inputs from the dialog with progress bar updates"""
        self.dialog.show()  # type: ignore
        self.dialog.start_processing()  # type: ignore
        self.current_progress = 0
        self.start_progress_simulation()

        try:
            self.process_inputs(project_file_path, output_directory, selected_checks)
        except Exception as e:
            error_msg = f"Validation failed: {e}"
            self.log_message(error_msg, "ERROR")
            self.iface.messageBar().pushMessage("Error", error_msg, level=Qgis.Critical)
        finally:
            self.finish_progress() # type: ignore
            self.reset_plugin()  # Automatically reset after each run (success or failure)

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
            self.dialog.update_progress(int(self.current_progress))  # type: ignore

    def finish_progress(self):
        if self.progress_timer:
            self.progress_timer.stop()
            self.progress_timer = None

        self.current_progress = 100
        self.dialog.update_progress(100)  # type: ignore
        self.dialog.finish_processing()  # type: ignore

    def update_progress_step(self, message, progress):
        """Update progress bar and message"""
        self.log_message(message, "INFO")
        self.current_progress = max(self.current_progress, progress)
        self.dialog.update_progress(int(self.current_progress))  # type: ignore

    def process_inputs(self, project_file_path, output_directory, selected_checks):
        """Process the inputs from the dialog"""
        self.log_message("Processing inputs:", "INFO")
        self.log_message(f"Project File: {project_file_path}", "INFO")
        self.log_message(f"Output Directory: {output_directory}", "INFO")
        self.log_message(f"Selected Checks: {selected_checks}", "INFO")

        self.update_progress_step("Loading project file...", 10)
        # load project file
        extracted_layers = load_project(project_file_path)
        add_external_wfs_layers(self.log_message)
        self.log_message(
            f"Extracted {len(extracted_layers)} layers from project.", "INFO"
        )
        self.update_progress_step(
            f"Extracted {len(extracted_layers)} layers from project.", 20
        )

        # Create a unique sub-folder for this validation run
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_name = extract_design_session_name(project_file_path)
        run_folder_name = f"Validation_{session_name}_{timestamp}"
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
        self.update_progress_step("Running validation checks...", 41)
        self.log_message("Running validation checks...", "INFO")
        # Run validation
        self.validation_engine = ValidationEngine(  # Assign to self for potential cleanup
            run_output_directory=run_output_directory,
            project_file_path=project_file_path,
            iface=self.iface,
        )
        validation_results = self.validation_engine.run_validation(selected_checks)
        self.update_progress_step("Generating reports...", 68)
        self.log_message("Validation checks completed.", "SUCCESS")
        # Generate reports
        # csv_report = generate_csv_report(self.path,run_output_directory, validation_results)
        html_report = generate_html_report(
            self.path, run_output_directory, validation_results
        )
        self.log_message(f"Reports generated:{html_report}", "INFO")
        # Create violation shapefile

        self.update_progress_step("Creating violation shapefile...", 80)
        # violation_shp = self.create_violation_shapefile(run_output_directory, validation_engine.get_all_violations())
        # Calculate total violations
        total_violations = sum(
            result.get("violation_count", 0) for result in validation_results
        )
        self.log_message(
            f"Total violations found: {total_violations}",
            "WARNING" if total_violations > 0 else "SUCCESS",
        )
        if total_violations != 0 and selected_checks.get("generate_report", False):
            self.update_progress_step("Generating layout report...", 90)
            run = run_report(
                self.iface,
                layer_name_filter="Design Violations",
                output_dir=run_output_directory,
                report_title="Feature Report",
                max_violations=total_violations,
            )
            self.log_message("Layout report generated", "SUCCESS")
        # Add external WFS layers as basemaps
        self.update_progress_step("Adding external basemaps...", 99)
        import_external_maps()
        self.log_message("External basemaps added", "SUCCESS")
        # Show completion message
        completion_msg = (
            f"Design validation completed. Found {total_violations} violations."
        )
        self.log_message(completion_msg, "SUCCESS")
        self.iface.messageBar().pushMessage(
            "Success", completion_msg, level=Qgis.Success, duration=5
        )

    def reset_plugin(self):
        """Automatically reset the plugin state after each run by reloading modules and cleaning up."""
        try:
            # Close any active multiprocessing resources if tracked (e.g., if ValidationEngine has a pool)
            if hasattr(self, 'validation_engine') and self.validation_engine is not None:
                # Assuming ValidationEngine might have a pool or other resources; add cleanup if needed
                # e.g., if 'pool' in self.validation_engine.__dict__: self.validation_engine.pool.close(); etc.
                self.validation_engine = None  # Dereference

            # Force garbage collection to clear lingering objects (e.g., spatial indexes, features)
            gc.collect()

            # Reload critical modules to reset any global/stateful variables (e.g., multiprocessing in poc_validator)
            modules_to_reload = [
                'core.validation_engine',
                'features.poc_clustering.poc_validator',  # Specific to your multiprocessing issue
                # Add other modules if they hold state, e.g., 'utils.project_handler'
            ]
            for module_name in modules_to_reload:
                full_module_path = f"{__package__}.{module_name}"
                if full_module_path in sys.modules:
                    importlib.reload(sys.modules[full_module_path])
                    self.log_message(f"Reloaded module: {module_name}", "INFO")

            # Reinitialize any persistent state if needed (e.g., if you cache layers globally)
            # self.validation_engine = None  # Already done above

            self.log_message("Plugin state reset successfully after run", "SUCCESS")

        except Exception as e:
            self.log_message(f"Reset failed: {str(e)}", "ERROR")
            self.iface.messageBar().pushMessage("Error", f"Reset failed: {str(e)}", level=Qgis.Critical)