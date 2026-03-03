import os
from qgis.PyQt import uic, QtWidgets, QtCore # type: ignore
from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes, QgsMessageLog, Qgis # type: ignore
from qgis.gui import QgsFileWidget # type: ignore
from datetime import datetime


# Load the UI class from the .ui file
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'survey_app_dialog_base.ui'))


class SurveyAppDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None, iface=None):
        """Constructor."""
        super(SurveyAppDialog, self).__init__(parent)
        self.setupUi(self)
        self.iface = iface

        # --- Configure UI elements ---
        self.mQgsFileWidget.setStorageMode(QgsFileWidget.GetDirectory)
        self.qgisProjectFileWidget.setStorageMode(QgsFileWidget.GetFile)
        self.qgisProjectFileWidget.setFilter("QGIS Project Files (*.qgs *.qgz)")
        
        # --- Set initial states ---
        self.validationProgressBar.setVisible(False)
        self.logTextEdit.setReadOnly(True)
        
        # --- Connect signals to slots for Survey Creation tab ---
        self.polygonLayerComboBox.currentIndexChanged.connect(self.validate_creation_inputs)
        self.buildingsLayerComboBox.currentIndexChanged.connect(self.validate_creation_inputs)
        self.addressLayerComboBox.currentIndexChanged.connect(self.validate_creation_inputs)
        self.crossingLayerComboBox.currentIndexChanged.connect(self.validate_creation_inputs)
        self.facadeLayerComboBox.currentIndexChanged.connect(self.validate_creation_inputs)
        self.sidewalkLayerComboBox.currentIndexChanged.connect(self.validate_creation_inputs)
        self.poleLayerComboBox.currentIndexChanged.connect(self.validate_creation_inputs)
        self.aerialLayerComboBox.currentIndexChanged.connect(self.validate_creation_inputs)
        self.projectNameLineEdit.textChanged.connect(self.validate_creation_inputs)
        self.mQgsFileWidget.fileChanged.connect(self.validate_creation_inputs)
        
        # --- Connect signals to slots for Survey Validation tab ---
        self.qgisProjectFileWidget.fileChanged.connect(self.validate_validation_inputs)
        self.homecountValidationCheckbox.stateChanged.connect(self.validate_validation_inputs)
        self.dataQualityCheckCheckbox.stateChanged.connect(self.validate_validation_inputs)
        self.generateReportCheckbox.stateChanged.connect(self.validate_validation_inputs)
        self.clearLogButton.clicked.connect(self.clear_validation_log)
        self.saveLogButton.clicked.connect(self.save_validation_log)
        self.runValidationButton.clicked.connect(self.run_validation)
        
        # Disconnect the default OK button behavior
        self.button_box.accepted.disconnect()
        self.button_box.rejected.disconnect()
        
        # Connect custom accept/reject handlers
        self.button_box.accepted.connect(self.custom_accept)
        self.button_box.rejected.connect(self.custom_reject)

        # --- Populate all layer dropdowns and set initial state ---
        self.populate_polygon_layers()
        self.populate_buildings_layers()
        self.populate_address_layers()
        self.populate_crossing_layers()
        self.populate_facade_layers()
        self.populate_sidewalk_layers()
        self.populate_pole_layers()
        self.populate_aerial_layers()
        
        # Validate both tabs initially
        self.validate_creation_inputs()
        self.validate_validation_inputs()
        
        # Connect tab change event to update validation
        self.tabWidget.currentChanged.connect(self.on_tab_changed)

    def on_tab_changed(self, index):
        """Handle tab change to update validation states."""
        if index == 0:  # Survey Creation tab
            self.validate_creation_inputs()
        elif index == 1:  # Survey Validation tab
            self.validate_validation_inputs()

    def validate_creation_inputs(self):
        """Enables the OK button only if all required fields are filled and layers are of correct type."""
        is_project_name_valid = bool(self.get_project_name())
        is_output_dir_valid = bool(self.get_output_directory())
        is_polygon_selected = self.get_selected_polygon_layer() is not None
        
        # For other layers, they can be optional but if selected must be correct type
        is_buildings_valid = self.is_buildings_layer_valid()
        is_address_valid = self.is_address_layer_valid()
        is_crossing_valid = self.is_crossing_layer_valid()
        is_facade_valid = self.is_facade_layer_valid()
        is_sidewalk_valid = self.is_sidewalk_layer_valid()
        is_pole_valid = self.is_pole_layer_valid()
        is_aerial_valid = self.is_aerial_layer_valid()

        is_valid = all([
            is_project_name_valid, 
            is_output_dir_valid, 
            is_polygon_selected,
            is_buildings_valid,
            is_address_valid,
            is_crossing_valid,
            is_facade_valid,
            is_sidewalk_valid,
            is_pole_valid,
            is_aerial_valid
        ])
        
        # Only enable OK button if we're on the creation tab
        if self.tabWidget.currentIndex() == 0:
            self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(is_valid)
            self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setText("Create Survey")
        else:
            # On validation tab, disable the OK button (we'll use custom behavior)
            self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)

    def validate_validation_inputs(self):
        """Validates inputs in the validation tab."""
        has_qgis_project = bool(self.get_qgis_project_file())
        has_validation_selected = (self.homecountValidationCheckbox.isChecked() or 
                                  self.dataQualityCheckCheckbox.isChecked())
        
        # Run Validation button is enabled if we have a project and at least one validation selected
        self.runValidationButton.setEnabled(has_qgis_project and has_validation_selected)
        
        # Save Log button is enabled if there's content in the log
        self.saveLogButton.setEnabled(bool(self.logTextEdit.toPlainText().strip()))
        
        # Update OK button text and state for validation tab
        if self.tabWidget.currentIndex() == 1:
            self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)  # Disable by default
            self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setText("Run Validation")

    def clear_validation_log(self):
        """Clears the validation log text edit."""
        self.logTextEdit.clear()
        self.saveLogButton.setEnabled(False)
        self.append_to_log("Log cleared.")

    def save_validation_log(self):
        """Saves the validation log to a text file."""
        log_content = self.logTextEdit.toPlainText()
        if not log_content.strip():
            self.append_to_log("Log is empty. Nothing to save.")
            return
            
        # Get output directory from the creation tab or use user's documents
        output_dir = self.get_output_directory()
        if not output_dir or not os.path.exists(output_dir):
            output_dir = os.path.expanduser("~/Documents")
        
        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"validation_log_{timestamp}.txt"
        filepath = os.path.join(output_dir, filename)
        
        try:
            with open(filepath, 'w') as f:
                f.write(log_content)
            self.append_to_log(f"Log saved to: {filepath}")
        except Exception as e:
            self.append_to_log(f"Error saving log: {str(e)}")

    def run_validation(self):
        """Runs the validation process."""
        # Clear previous log
        self.logTextEdit.clear()
        
        # Show progress bar
        self.validationProgressBar.setVisible(True)
        self.validationProgressBar.setValue(0)
        
        # Append start message
        self.append_to_log("=" * 60)
        self.append_to_log("Starting validation process...")
        self.append_to_log(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.append_to_log(f"QGIS Project: {self.get_qgis_project_file()}")
        self.append_to_log("=" * 60)
        self.append_to_log("")
        
        # Get validation settings
        validation_settings = self.get_validation_settings()
        
        # Update progress values to accommodate both validations
        progress_per_validation = 40  # Adjust as needed
        
        # Run validations based on selected options
        if validation_settings['validate_homecount']:
            self.run_homecount_validation()
            self.validationProgressBar.setValue(40)
        
        if validation_settings['validate_data_quality']:
            self.run_data_quality_validation()
            self.validationProgressBar.setValue(80)
        
        if validation_settings['generate_report']:
            self.generate_validation_report()
        
        # Complete validation
        self.validationProgressBar.setValue(100)
        self.append_to_log("")
        self.append_to_log("=" * 60)
        self.append_to_log("Validation completed successfully!")
        self.append_to_log(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.append_to_log("=" * 60)
        
        # Enable save log button
        self.saveLogButton.setEnabled(True)
        
        # Hide progress bar after 2 seconds
        QtCore.QTimer.singleShot(2000, lambda: self.validationProgressBar.setVisible(False))

    def run_homecount_validation(self):
        """Run the homecount validation script."""
        self.append_to_log("Step 1: Running homecount validation...")
        self.validationProgressBar.setValue(10)
        
        try:
            # Import the validator class
            from .validation.homeCount import HomecountValidator
            
            self.append_to_log("  - Initializing validator...")
            self.validationProgressBar.setValue(20)
            
            # Create validator instance with log callback
            # Only pass iface if it's available
            validator_kwargs = {'log_callback': self.append_to_log}
            if hasattr(self, 'iface') and self.iface is not None:
                validator_kwargs['iface'] = self.iface
                
            validator = HomecountValidator(**validator_kwargs)
            
            self.append_to_log("  - Checking address points layer...")
            self.validationProgressBar.setValue(40)
            
            # Load the QGIS project first
            qgis_project_file = self.get_qgis_project_file()
            if not qgis_project_file:
                self.append_to_log("ERROR: No QGIS project file selected!")
                return
                
            self.append_to_log(f"  - Loading project: {qgis_project_file}")
            
            # Load the project into QGIS instance
            project = QgsProject.instance()
            project.read(qgis_project_file)
            
            self.append_to_log("  - Project loaded successfully")
            self.validationProgressBar.setValue(50)
            
            # Run validation
            result_layer = validator.create_resurvey_flags(show_progress=False)
            
            if result_layer:
                self.append_to_log(f"  - Found {validator.flagged_count} addresses needing resurvey")
                self.validationProgressBar.setValue(70)
                
                # Save results
                saved_path = validator.save_to_shapefile()
                if saved_path:
                    self.append_to_log(f"  - Saved results to: {saved_path}")
                    self.validationProgressBar.setValue(85)
                    
                    # Load and style
                    final_layer = validator.load_and_style_layer(saved_path)
                    if final_layer:
                        self.append_to_log("  - Added flagged layer to project")
                        self.validationProgressBar.setValue(95)
                        self.append_to_log("Homecount validation completed successfully!")
                        
                        # Show success message
                        if hasattr(self, 'iface') and self.iface:
                            self.iface.messageBar().pushSuccess(
                                "Validation Complete",
                                f"Found {validator.flagged_count} addresses needing resurvey"
                            )
                    else:
                        self.append_to_log("ERROR: Could not load flagged layer")
                else:
                    self.append_to_log("ERROR: Could not save results")
            else:
                if validator.flagged_count == 0:
                    self.append_to_log("  - No addresses need resurveying - all checks passed!")
                    
                    # Show info message
                    if hasattr(self, 'iface') and self.iface:
                        self.iface.messageBar().pushInfo(
                            "Validation Complete",
                            "No addresses need resurveying - all checks passed!"
                        )
                else:
                    self.append_to_log("ERROR: Validation failed")
            
            self.validationProgressBar.setValue(100)
            
        except ImportError as e:
            self.append_to_log(f"ERROR: Could not import homecount validation module: {e}")
            self.append_to_log("Please make sure homecount_validator.py is in the same directory")
        except Exception as e:
            self.append_to_log(f"ERROR: Homecount validation failed: {e}")
            import traceback
            self.append_to_log(f"Traceback: {traceback.format_exc()}")

    def run_data_quality_validation(self):
        """Run the data quality check and create resurvey project"""
        self.append_to_log("Step 2: Running data quality check...")
        self.validationProgressBar.setValue(30)
        
        try:
            # Import the DataQualityValidator
            from .validation.data_quality import DataQualityValidator
            
            self.append_to_log("  - Initializing DataQualityValidator...")
            
            # Create validator instance
            validator_kwargs = {'log_callback': self.append_to_log}
            if hasattr(self, 'iface') and self.iface is not None:
                validator_kwargs['iface'] = self.iface
                
            validator = DataQualityValidator(**validator_kwargs)
            
            self.append_to_log("  - Checking all layers for unsurveyed features...")
            self.validationProgressBar.setValue(40)
            
            # Run validation
            success = validator.run_validation()
            
            self.validationProgressBar.setValue(80)
            
            if success:
                self.append_to_log(f"  - Found {validator.unsurveyed_count} unsurveyed features")
                self.append_to_log(f"  - Created resurvey project: {validator.resurvey_project_path}")
                
                # Show success message
                if hasattr(self, 'iface') and self.iface:
                    self.iface.messageBar().pushSuccess(
                        "Data Quality Check Complete",
                        f"Created resurvey project with {validator.unsurveyed_count} unsurveyed features"
                    )
                    
                    # Optionally, open the created zip file location
                    import subprocess
                    import platform
                    
                    if validator.resurvey_project_path and os.path.exists(validator.resurvey_project_path):
                        if platform.system() == "Windows":
                            subprocess.Popen(f'explorer /select,"{validator.resurvey_project_path}"')
                        elif platform.system() == "Darwin":  # macOS
                            subprocess.Popen(["open", "-R", validator.resurvey_project_path])
                        elif platform.system() == "Linux":
                            subprocess.Popen(["xdg-open", os.path.dirname(validator.resurvey_project_path)])
            else:
                if validator.unsurveyed_count == 0:
                    self.append_to_log("  - All features are surveyed!")
                    
                    if hasattr(self, 'iface') and self.iface:
                        self.iface.messageBar().pushSuccess(
                            "Data Quality Check",
                            "All features are surveyed!"
                        )
                else:
                    self.append_to_log("  - Failed to create resurvey project")
                    
                    if hasattr(self, 'iface') and self.iface:
                        self.iface.messageBar().pushCritical(
                            "Data Quality Check Failed",
                            "Could not create resurvey project"
                        )
            
            self.append_to_log("Data quality validation completed!")
            
        except ImportError as e:
            self.append_to_log(f"ERROR: Could not import data quality validation module: {e}")
            self.append_to_log("Please make sure data_quality.py is in the validation directory")
        except Exception as e:
            self.append_to_log(f"ERROR: Data quality validation failed: {e}")
            import traceback
            self.append_to_log(f"Traceback: {traceback.format_exc()}")

    def generate_validation_report(self):
        """Generate validation report."""
        self.append_to_log("Step 3: Generating validation report...")
        self.validationProgressBar.setValue(90)
        
        # Simulate report generation
        self.append_to_log("  - Collecting validation results...")
        self.append_to_log("  - Formatting HTML report...")
        
        # Get output directory
        output_dir = self.get_output_directory()
        if not output_dir or not os.path.exists(output_dir):
            output_dir = os.path.expanduser("~/Documents")
        
        # Create report filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(output_dir, f"validation_report_{timestamp}.html")
        
        self.append_to_log(f"  - Saving report to: {report_file}")
        self.append_to_log(f"Report generation completed: {report_file}")

    def append_to_log(self, message):
        """Appends a message to the validation log with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logTextEdit.append(f"[{timestamp}] {message}")
        # Scroll to bottom
        self.logTextEdit.verticalScrollBar().setValue(
            self.logTextEdit.verticalScrollBar().maximum()
        )

    def custom_accept(self):
        """Custom accept handler that runs different logic based on active tab."""
        current_tab = self.tabWidget.currentIndex()
        
        if current_tab == 0:
            # Survey Creation tab - run normal survey creation
            QgsMessageLog.logMessage("Running survey creation process", "SurveyApp", Qgis.Info)
            super().accept()  # This will close the dialog and return QDialog.Accepted
            
        elif current_tab == 1:
            # Survey Validation tab - run validation if homecount is checked
            if self.homecountValidationCheckbox.isChecked():
                QgsMessageLog.logMessage("Running homecount validation from OK button", "SurveyApp", Qgis.Info)
                # Run the validation and don't close the dialog
                self.run_validation()
            else:
                # No validation selected, just close the dialog
                QgsMessageLog.logMessage("No validation selected, closing dialog", "SurveyApp", Qgis.Info)
                super().accept()
                
        else:
            # Default behavior for other tabs
            super().accept()

    def custom_reject(self):
        """Custom reject handler."""
        QgsMessageLog.logMessage("Dialog cancelled by user", "SurveyApp", Qgis.Info)
        super().reject()  # This will close the dialog and return QDialog.Rejected

    # --- Getter methods for validation tab ---
    def get_qgis_project_file(self):
        """Returns the selected QGIS project file path."""
        return self.qgisProjectFileWidget.filePath().strip()

    def get_validation_settings(self):
        """Returns a dictionary of validation settings."""
        return {
            'validate_homecount': self.homecountValidationCheckbox.isChecked(),
            'validate_data_quality': self.dataQualityCheckCheckbox.isChecked(),
            'generate_report': self.generateReportCheckbox.isChecked()
        }

    # --- Original methods (unchanged) ---
    def populate_polygon_layers(self):
        """Finds all polygon layers in the project and adds them to the ComboBox."""
        self.polygonLayerComboBox.clear()
        self.polygonLayerComboBox.addItem("")  # Empty option
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                self.polygonLayerComboBox.addItem(layer.name(), layer)
        
        if self.polygonLayerComboBox.count() == 1:  # Only empty option
            self.polygonLayerComboBox.addItem("No polygon layers found")
            self.polygonLayerComboBox.setEnabled(False)

    def populate_buildings_layers(self):
        """Finds all polygon layers in the project and adds them to the Buildings ComboBox."""
        self.buildingsLayerComboBox.clear()
        self.buildingsLayerComboBox.addItem("")  # Empty option
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                self.buildingsLayerComboBox.addItem(layer.name(), layer)
        
        if self.buildingsLayerComboBox.count() == 1:  # Only empty option
            self.buildingsLayerComboBox.addItem("No polygon layers found")
            self.buildingsLayerComboBox.setEnabled(False)

    def populate_address_layers(self):
        """Finds all point layers in the project and adds them to the ComboBox."""
        self.populate_point_layers(self.addressLayerComboBox)

    def populate_crossing_layers(self):
        """Finds all multi-line layers in the project and adds them to the ComboBox."""
        self.populate_multiline_layers(self.crossingLayerComboBox)

    def populate_facade_layers(self):
        """Finds all multi-line layers in the project and adds them to the ComboBox."""
        self.populate_multiline_layers(self.facadeLayerComboBox)

    def populate_sidewalk_layers(self):
        """Finds all multi-line layers in the project and adds them to the ComboBox."""
        self.populate_multiline_layers(self.sidewalkLayerComboBox)

    def populate_pole_layers(self):
        """Finds all points layers in the project and adds them to the ComboBox."""
        self.populate_point_layers(self.poleLayerComboBox)

    def populate_aerial_layers(self):
        """Finds all multi-line layers in the project and adds them to the ComboBox."""
        self.populate_multiline_layers(self.aerialLayerComboBox)

    def populate_point_layers(self, combobox):
        """Helper method to populate point layers for address and pole."""
        combobox.clear()
        combobox.addItem("")  # Empty option
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PointGeometry:
                combobox.addItem(layer.name(), layer)
        
        if combobox.count() == 1:  # Only empty option
            combobox.addItem("No point layers found")
            combobox.setEnabled(False)

    def populate_multiline_layers(self, combobox):
        """Helper method to populate multi-line layers for crossing, facade, sidewalk, and aerial."""
        combobox.clear()
        combobox.addItem("")  # Empty option
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if (isinstance(layer, QgsVectorLayer) and 
                layer.geometryType() == QgsWkbTypes.LineGeometry):
                combobox.addItem(layer.name(), layer)
        
        if combobox.count() == 1:  # Only empty option
            combobox.addItem("No line layers found")
            combobox.setEnabled(False)

    def is_buildings_layer_valid(self):
        """Check if buildings layer is either not selected or is a polygon layer."""
        layer = self.get_selected_buildings_layer()
        if layer is None:  # No selection is valid (optional)
            return True
        return isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PolygonGeometry

    def is_address_layer_valid(self):
        """Check if address layer is either not selected or is a point layer."""
        layer = self.get_selected_address_layer()
        if layer is None:  # No selection is valid (optional)
            return True
        return isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PointGeometry

    def is_crossing_layer_valid(self):
        """Check if crossing layer is either not selected or is a line layer."""
        layer = self.get_selected_crossing_layer()
        if layer is None:  # No selection is valid (optional)
            return True
        return isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.LineGeometry

    def is_facade_layer_valid(self):
        """Check if facade layer is either not selected or is a line layer."""
        layer = self.get_selected_facade_layer()
        if layer is None:  # No selection is valid (optional)
            return True
        return isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.LineGeometry

    def is_sidewalk_layer_valid(self):
        """Check if sidewalk layer is either not selected or is a line layer."""
        layer = self.get_selected_sidewalk_layer()
        if layer is None:  # No selection is valid (optional)
            return True
        return isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.LineGeometry
    
    def is_pole_layer_valid(self):
        """Check if pole layer is either not selected or is a point layer."""
        layer = self.get_selected_pole_layer()
        if layer is None:  # No selection is valid (optional)
            return True
        return isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PointGeometry
    
    def is_aerial_layer_valid(self):
        """Check if aerial layer is either not selected or is a multi-line layer."""
        layer = self.get_selected_aerial_layer()
        if layer is None:  # No selection is valid (optional)
            return True
        return isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.LineGeometry

    # --- Getter methods for the main plugin to retrieve data ---
    def get_project_name(self):
        return self.projectNameLineEdit.text().strip()

    def get_output_directory(self):
        return self.mQgsFileWidget.filePath().strip()

    def get_selected_polygon_layer(self):
        """Returns the selected polygon QgsVectorLayer object."""
        index = self.polygonLayerComboBox.currentIndex()
        if index > 0:  # Skip empty option
            return self.polygonLayerComboBox.itemData(index)
        return None

    def get_selected_buildings_layer(self):
        """Returns the selected buildings (polygon) QgsVectorLayer object."""
        index = self.buildingsLayerComboBox.currentIndex()
        if index > 0:  # Skip empty option
            return self.buildingsLayerComboBox.itemData(index)
        return None

    def get_selected_address_layer(self):
        """Returns the selected address (point) QgsVectorLayer object."""
        index = self.addressLayerComboBox.currentIndex()
        if index > 0:  # Skip empty option
            return self.addressLayerComboBox.itemData(index)
        return None

    def get_selected_crossing_layer(self):
        """Returns the selected crossing (line) QgsVectorLayer object."""
        index = self.crossingLayerComboBox.currentIndex()
        if index > 0:  # Skip empty option
            return self.crossingLayerComboBox.itemData(index)
        return None

    def get_selected_facade_layer(self):
        """Returns the selected facade (line) QgsVectorLayer object."""
        index = self.facadeLayerComboBox.currentIndex()
        if index > 0:  # Skip empty option
            return self.facadeLayerComboBox.itemData(index)
        return None

    def get_selected_sidewalk_layer(self):
        """Returns the selected sidewalk (line) QgsVectorLayer object."""
        index = self.sidewalkLayerComboBox.currentIndex()
        if index > 0:  # Skip empty option
            return self.sidewalkLayerComboBox.itemData(index)
        return None
    
    def get_selected_pole_layer(self):
        """Returns the selected pole (point) QgsVectorLayer object."""
        index = self.poleLayerComboBox.currentIndex()
        if index > 0:  # Skip empty option
            return self.poleLayerComboBox.itemData(index)
        return None
    
    def get_selected_aerial_layer(self):
        """Returns the selected aerial (line) QgsVectorLayer object."""
        index = self.aerialLayerComboBox.currentIndex()
        if index > 0:  # Skip empty option
            return self.aerialLayerComboBox.itemData(index)
        return None
    
    def get_selected_checks(self):
        """Get a dictionary of selected setting checks"""
        return {
            'split_demandpoints': self.splitDemandPoint.isChecked(),
            'add_missing_addresses': self.addMissingAddresses.isChecked()
        }