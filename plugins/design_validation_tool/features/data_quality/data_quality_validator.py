import os
from qgis.core import QgsSpatialIndex, QgsProject, QgsVectorLayer, QgsFeatureRequest  # type: ignore
from ...utils.layer_loader import get_layer_by_name


class DataQualityValidator:
    def __init__(self):
        self.violations = []

    def validate_subtype(self):
        """
        Rule 1: Validate that Subtype is filled in correctly and exists in known list.
        Checks Possible trench routes and IN_Crossings layers for SUBTYPE values.
        Flags any features with empty/None values OR values not in the valid list.
        For IN_Crossings: if SUBTYPE is "Doorsteek (1m diep)", validates length is <= 8m.
        """
        print("Validating subtype attribute...")
        
        # Known valid SUBTYPE values for Possible trench routes and IN_Crossings
        VALID_SUBTYPES = [
            'Doorsteek (1m diep)',
            'Doorsteek (wachthuis)', 
            'Dummy',
            'Gestuurde boring',
            'In berm',
            'In berm (synergie)',
            'Monoliete verharding',
            'Monoliete verharding (synergie)',
            'Niet-monoliete verharding',
            'Niet-monoliete verharding (synergie)',
            'Existing',
            'Existing pipes',
            'Existing Pipes'
            'Dummy'
        ]
        
        violations = []

        # Check 1: Possible trench routes for invalid or missing SUBTYPE values
        possible_trenches_layer = get_layer_by_name("Possible trench routes")
        if possible_trenches_layer:
            if "SUBTYPE" in possible_trenches_layer.fields().names():
                for feature in possible_trenches_layer.getFeatures():
                    subtype_value = feature["SUBTYPE"]
                    
                    # Convert to string and strip whitespace for comparison
                    if subtype_value is None:
                        subtype_str = ""
                    else:
                        subtype_str = str(subtype_value).strip()
                    
                    # Flag if empty or not in valid list
                    if not subtype_str or subtype_str not in VALID_SUBTYPES:
                        feature_id = feature.id()
                        geometry = feature.geometry()
                        
                        # Determine violation type
                        if not subtype_str:
                            violation_type = "subtype_empty"
                            reason = "SUBTYPE is empty or missing"
                        else:
                            violation_type = "subtype_invalid"
                            reason = f"SUBTYPE '{subtype_str}' is not in the known subtypes list"

                        violation_info = {
                            "violation_type": violation_type,
                            "feature_id": feature_id,
                            "layer_name": "Possible trench routes",
                            "subtype": subtype_str if subtype_str else "EMPTY",
                            "geometry": geometry,
                            "violation_reason": reason
                        }
                        violations.append(violation_info)

        # Check 2: IN_Crossings for invalid or missing SUBTYPE values AND length validation
        crossings_layer = get_layer_by_name("IN_Crossings")
        if crossings_layer:
            if "SUBTYPE" in crossings_layer.fields().names():
                # Check if layer has a LENGTH field
                has_length_field = "LENGTH" in crossings_layer.fields().names()

                for feature in crossings_layer.getFeatures():
                    subtype_value = feature["SUBTYPE"]

                    # Convert to string and strip whitespace for comparison
                    if subtype_value is None:
                        subtype_str = ""
                    else:
                        subtype_str = str(subtype_value).strip()

                    # Flag if empty or not in valid list
                    if not subtype_str or subtype_str not in VALID_SUBTYPES:
                        feature_id = feature.id()
                        geometry = feature.geometry()

                        # Determine violation type
                        if not subtype_str:
                            violation_type = "subtype_empty"
                            reason = "SUBTYPE is empty or missing"
                        else:
                            violation_type = "subtype_invalid"
                            reason = f"SUBTYPE '{subtype_str}' is not in the known subtypes list"

                        violation_info = {
                            "violation_type": violation_type,
                            "feature_id": feature_id,
                            "layer_name": "IN_Crossings",
                            "subtype": subtype_str if subtype_str else "EMPTY",
                            "geometry": geometry,
                            "violation_reason": reason
                        }
                        violations.append(violation_info)
                    
                    # Additional check: if SUBTYPE is "Doorsteek (1m diep)", length must be <= 8m
                    elif subtype_str == "Doorsteek (1m diep)":
                        feature_length = None
                        geometry = feature.geometry()
                        
                        # Try to get length from LENGTH field first
                        if has_length_field:
                            length_value = feature["LENGTH"]
                            if length_value is not None:
                                try:
                                    feature_length = float(length_value)
                                except (ValueError, TypeError):
                                    pass
                        
                        # If no LENGTH field or field is empty, calculate from geometry
                        if feature_length is None or feature_length == 0:
                            if geometry and not geometry.isEmpty():
                                feature_length = geometry.length()
                        
                        print(f"DEBUG: Feature {feature.id()} - SUBTYPE: {subtype_str}, Length: {feature_length}")
                        
                        # Flag if length exceeds 8m
                        if feature_length is not None and feature_length > 8:
                            feature_id = feature.id()
                            
                            violation_info = {
                                "violation_type": "subtype_length_exceeded",
                                "feature_id": feature_id,
                                "layer_name": "IN_Crossings",
                                "subtype": subtype_str,
                                "geometry": geometry,
                                "violation_reason": f"SUBTYPE '{subtype_str}' exceeds maximum length of 8m (actual: {feature_length:.2f}m). Should be 'Gestuurde boring'"
                            }
                            violations.append(violation_info)

        description = "Subtype must be filled in correctly and exist in known list"
        violation_count = len(violations)
        if violation_count > 0:
            message = f"Found {violation_count} features with missing or invalid Subtype."
        else:
            message = "No violations found."

        result = self._create_result("DATA_Q_001", description, violations, message)
        self.violations.extend(violations)
        return result

    def validate_unlocked_feature(self):
        """
        Rule 2: Validate that all features in layers are locked (LOCKED != 'Unlocked').
        Checks across all layers in the project for unlocked features.
        Reports only the total count per layer, not individual features.
        """
        print("Validating unlocked features...")
        description = "Features must be Locked"

        project = QgsProject.instance()
        layers = list(project.mapLayers().values())

        violations = []
        layers_with_unlocked = {}  # Track which layers have unlocked features
        total_unlocked = 0

        for layer in layers:
            # Check if layer is a vector layer
            if not isinstance(layer, QgsVectorLayer):
                continue

            # Check if layer has 'LOCKED' column (case-insensitive check)
            field_names = [field.name().upper() for field in layer.fields()]

            if 'LOCKED' not in field_names:
                continue

            # Find the actual field name (preserving original case)
            actual_field_name = None
            for field in layer.fields():
                if field.name().upper() == 'LOCKED':
                    actual_field_name = field.name()
                    break

            # Count features where LOCKED = 'Unlocked'
            expression = f'"{actual_field_name}" = \'Unlocked\''
            features = layer.getFeatures(QgsFeatureRequest().setFilterExpression(expression))

            # Count unlocked features in this layer
            unlocked_count = 0
            for feature in features:
                unlocked_count += 1
                total_unlocked += 1

            # Store the count for this layer
            if unlocked_count > 0:
                layers_with_unlocked[layer.name()] = unlocked_count
                # Create a single violation entry per layer with the count
                violation_info = {
                    'violation_type': 'feature_unlocked',
                    'layer': layer.name(),
                    'unlocked_count': unlocked_count,
                    'violation_reason': f"{layer.name()}: {unlocked_count} unlocked features"
                }
                violations.append(violation_info)

        message = f'Found {total_unlocked} unlocked features across {len(layers_with_unlocked)} layers' if total_unlocked > 0 else 'All features are locked'
        result = self._create_result("DATA_Q_003", description, violations, message)
        self.violations.extend(violations)
        return result

    def validate_facade_protected_monument(self):
        """
        Rule 3: Validate that Facade cables cannot be on protected monuments.
        Checks Distribution Cables with TYPE containing 'façade' or 'facade' 
        that intersect with protected monument layers.
        """
        print("Validating facade cables on protected monuments...")
        
        # Get required layers
        distribution_cables_layer = get_layer_by_name("Distribution Cables")
        monument_layer = get_layer_by_name("Beschermde monumenten")

        if not distribution_cables_layer:
            return self._create_error_result(
                "DATA_Q_002", "Distribution Cables layer not found.",
            )

        if not monument_layer:
            return self._create_error_result(
                "DATA_Q_002", "Protected Monuments layer not found.",
            )

        # Check if TYPE field exists in Distribution Cables
        if "TYPE" not in distribution_cables_layer.fields().names():
            return self._create_error_result(
                "DATA_Q_002", "Distribution Cables layer missing TYPE field.",
            )

        monument_index = QgsSpatialIndex(monument_layer.getFeatures())
        violations = []

        # Check each distribution cable
        for cable_feature in distribution_cables_layer.getFeatures():
            cable_type = cable_feature["TYPE"]
            cable_geom = cable_feature.geometry()
            
            # Check if this is a facade cable
            is_facade = (
                cable_type
                and isinstance(cable_type, str)
                and ("lenient" in cable_type.lower() or "facade" in cable_type.lower())
            )
            
            if not is_facade or not cable_geom or cable_geom.isEmpty():
                continue

            # Check if this facade cable intersects with any monument
            candidate_monument_ids = monument_index.intersects(cable_geom.boundingBox())
            for monument_id in candidate_monument_ids:
                monument_feature = monument_layer.getFeature(monument_id)
                if cable_geom.intersects(monument_feature.geometry()):
                    cable_id = (
                        cable_feature["CABLE_ID"]
                        if "CABLE_ID" in cable_feature.fields().names()
                        else cable_feature.id()
                    )
                    violation_info = {
                        "violation_type": "facade_on_monument",
                        "cable_id": cable_id,
                        "cable_type": cable_type,
                        "geometry": cable_geom,
                        "violation_reason": f"Facade Cable (ID: {cable_id}) overlaps with a protected monument.",
                    }
                    violations.append(violation_info)
                    break

        description = "Facade cables cannot be placed on protected monuments"
        violation_count = len(violations)
        if violation_count > 0:
            message = f"Found {violation_count} facade cables on protected monuments."
        else:
            message = "No violations found."

        result = self._create_result("DATA_Q_002", description, violations, message)
        self.violations.extend(violations)
        return result

    def validate_multiple_boms(self):
        """
        Rule 4: Validate that there is not more than one BOM (Bill of Materials) Excel file present.
        Checks the output folder for Excel files (.xlsx, .xls) with "BOM" in the filename.
        """
        print("Validating multiple BOMs...")
        
        # Get project directory
        project = QgsProject.instance()
        project_path = project.fileName()
        
        if not project_path:
            return self._create_error_result(
                "DATA_Q_004", "Project is not saved - cannot resolve output folder."
            )
        
        # Get project directory
        project_dir = os.path.dirname(project_path)
        
        output_folder = project_dir
        
        # If that doesn't exist, try parent directory
        if not os.path.exists(output_folder):
            output_folder = os.path.dirname(project_dir)
        
        if not os.path.exists(output_folder):
            return self._create_error_result(
                "DATA_Q_004", f"Output folder not found at: {output_folder}"
            )
        
        # Search for Excel files with "BOM" in the filename
        bom_files = []
        excel_extensions = ('.xlsx', '.xls', '.xlsm')
        
        try:
            for filename in os.listdir(output_folder):
                # Check if filename contains "BOM" and has Excel extension
                if "BOM" in filename.upper() and filename.lower().endswith(excel_extensions):
                    bom_files.append(filename)
        except Exception as e:
            return self._create_error_result(
                "DATA_Q_004", f"Error scanning output folder: {str(e)}"
            )
        
        description = "Only one BOM (Bill of Materials) Excel file should be present"
        
        # Only create violations if more than 1 BOM file exists
        violations = []
        if len(bom_files) > 1:
            for bom_file in bom_files:
                violation_info = {
                    "violation_type": "multiple_boms",
                    "bom_file": bom_file,
                    "bom_path": os.path.join(output_folder, bom_file)
                }
                violations.append(violation_info)
            message = f"Found {len(bom_files)} BOM files in output folder. Expected: 1 BOM file."
        else:
            message = "No violations found."
        
        result = self._create_result("DATA_Q_004", description, violations, message)
        return result

    def validate_existing_pipes_trenches(self):
        """
        Rule 5: Validate that existing pipes are properly associated with trenches marked as "Existing Pipes".
        Checks IN_ExistingPipes layer features that intersect with Possible trench routes layer features.
        If an existing pipe overlays a trench, that trench must have SUBTYPE = "Existing Pipes".
        """
        print("Validating existing pipes association with trenches...")

        # Get required layers
        existing_pipes_layer = get_layer_by_name("IN_ExistingPipes")
        possible_trenches_layer = get_layer_by_name("Possible trench routes")

        if not existing_pipes_layer:
            return self._create_error_result(
                "DATA_Q_005", "IN_ExistingPipes layer not found."
            )

        if not possible_trenches_layer:
            return self._create_error_result(
                "DATA_Q_005", "Possible trench routes layer not found."
            )

        # Check if SUBTYPE field exists in Possible trench routes
        if "SUBTYPE" not in possible_trenches_layer.fields().names():
            return self._create_error_result(
                "DATA_Q_005", "Possible trench routes layer missing SUBTYPE field."
            )

        # Create spatial index for existing pipes for efficient intersection queries
        pipe_index = QgsSpatialIndex(existing_pipes_layer.getFeatures())
        violations = []

        # Check each trench
        for trench_feature in possible_trenches_layer.getFeatures():
            trench_geom = trench_feature.geometry()
            trench_id = trench_feature.id()

            if not trench_geom or trench_geom.isEmpty():
                continue

            # Skip trenches with TYPE = "Dummy"
            if "TYPE" in possible_trenches_layer.fields().names():
                type_value = trench_feature["TYPE"]
                if type_value and str(type_value).strip().lower() == "dummy":
                    continue

            # Check the SUBTYPE of the trench
            subtype_value = trench_feature["SUBTYPE"]

            # Convert to string and strip whitespace for comparison
            if subtype_value is None:
                subtype_str = ""
            else:
                subtype_str = str(subtype_value).strip()

            # Skip if SUBTYPE is already "Existing Pipes" (case-insensitive)
            if subtype_str.lower() == ("Existing Pipes").lower():
                continue

            # Buffer distance to catch pipes running alongside the trench
            BUFFER_DISTANCE = 4  # meters
            # Minimum overlap threshold (in meters)
            MIN_OVERLAP_LENGTH = 5  # meters

            # Create a buffer around the trench to catch nearby pipes
            trench_buffered = trench_geom.buffer(BUFFER_DISTANCE, 5)

            # Find candidate pipes that intersect with the buffered trench's bounding box
            candidate_pipe_ids = pipe_index.intersects(trench_buffered.boundingBox())

            # Check if any existing pipe actually intersects with the buffered trench
            for pipe_id in candidate_pipe_ids:
                pipe_feature = existing_pipes_layer.getFeature(pipe_id)
                pipe_geom = pipe_feature.geometry()

                # Check if pipe intersects with the buffered trench
                if pipe_geom and pipe_geom.intersects(trench_buffered):
                    # Calculate the intersection to check if it's significant
                    intersection = pipe_geom.intersection(trench_buffered)

                    # Only flag if intersection length is > MIN_OVERLAP_LENGTH (to avoid just touching tips)
                    if intersection and not intersection.isEmpty():
                        intersection_length = intersection.length()

                        if intersection_length > MIN_OVERLAP_LENGTH:
                            # Flag this trench - use the trench's geometry for highlighting
                            violation_info = {
                                "violation_type": "existing_pipe_wrong_trench_subtype",
                                "feature_id": trench_id,
                                "layer_name": "Possible trench routes",
                                "pipe_id": pipe_id,
                                "trench_subtype": subtype_str if subtype_str else "EMPTY",
                                "geometry": trench_geom,
                                "violation_reason": f"Trench (ID: {trench_id}) runs alongside existing pipe (ID: {pipe_id}) but has SUBTYPE '{subtype_str}' instead of 'Existing Pipes'"
                            }
                            violations.append(violation_info)
                            break  # Only flag this trench once (with the first intersecting pipe)

        description = "Existing pipes must be associated with trenches marked as 'Existing Pipes'"
        violation_count = len(violations)
        if violation_count > 0:
            message = f"Found {violation_count} trenches intersecting existing pipes with incorrect SUBTYPE."
        else:
            message = "No violations found."

        result = self._create_result("DATA_Q_005", description, violations, message)
        self.violations.extend(violations)
        return result

    def validate_layer_feature_count(self):
        """
        Rule 6: Validate that critical duct layers contain features.
        Checks Primary Distribution Ducts, Distribution Ducts, and Drop Ducts layers
        to ensure they are not empty (have at least 1 feature).
        """
        print("Validating layer feature counts...")

        # Get all required layers
        primary_dist_ducts = get_layer_by_name("Primary Distribution Ducts")
        dist_ducts = get_layer_by_name("Distribution Ducts")
        drop_ducts = get_layer_by_name("Drop Ducts")

        # Check if any layers are missing
        if not primary_dist_ducts:
            return self._create_error_result(
                "DATA_Q_006", "Primary Distribution Ducts layer not found."
            )
        if not dist_ducts:
            return self._create_error_result(
                "DATA_Q_006", "Distribution Ducts layer not found."
            )
        if not drop_ducts:
            return self._create_error_result(
                "DATA_Q_006", "Drop Ducts layer not found."
            )

        violations = []
        empty_layers = []

        # Check feature counts
        layers_to_check = [
            ("Primary Distribution Ducts", primary_dist_ducts),
            ("Distribution Ducts", dist_ducts),
            ("Drop Ducts", drop_ducts)
        ]

        for layer_name, layer in layers_to_check:
            if layer.featureCount() == 0:
                violation_info = {
                    "violation_type": "ducts_layer_empty",
                    "layer_name": layer_name,
                    "violation_reason": f"Layer '{layer_name}' contains no features"
                }
                violations.append(violation_info)
                empty_layers.append(layer_name)

        description = "Duct layers must contain features"

        if empty_layers:
            message = f"Empty layers: {', '.join(empty_layers)}."
        else:
            message = "No violations found."

        result = self._create_result("DATA_Q_006", description, violations, message)
        self.violations.extend(violations)
        return result

    def data_quality_rules(self):
        """Run all Data Quality validation rules."""
        self.violations = []
        print("Running all Data Quality validation rules...")
        results = []
        results.append(self.validate_subtype())
        results.append(self.validate_unlocked_feature())
        results.append(self.validate_facade_protected_monument())
        results.append(self.validate_multiple_boms())
        results.append(self.validate_existing_pipes_trenches())
        results.append(self.validate_layer_feature_count())
        return results

    def _create_result(self, rule_id, description, violations, message):
        """
        Create a result dictionary from violations.
        Handles both dictionary violations (with feature_id, layer, etc.) 
        and simple string violations (like filenames from BOM check).
        """
        failed_ids = []
        
        # Layer name abbreviations for cleaner output
        layer_abbreviations = {
            'Possible trench routes': 'PossibleTrench',
            'IN_Crossings': 'Crossing',
            'IN_ExistingPipes': 'ExistingPipe'
        }
        
        for v in violations:
            if isinstance(v, dict):
                # Handle dictionary violations
                if v.get("unlocked_count") is not None:
                    # Handle unlocked features (summary by layer)
                    failed_ids.append(f"{v.get('layer')}: {v.get('unlocked_count')}")
                elif v.get("bom_file") is not None:
                    # Handle BOM file violations
                    failed_ids.append(f"BOM_{v.get('bom_file')}")
                elif v.get("feature_id") is not None:
                    layer_name = v.get('layer_name')
                    feature_id = v.get('feature_id')
                    if layer_name:
                        # Use abbreviation if available, otherwise use full name
                        abbreviated_layer = layer_abbreviations.get(layer_name, layer_name)
                        failed_ids.append(f"{abbreviated_layer}_{feature_id}")
                    else:
                        failed_ids.append(f"Feature_{feature_id}")
                elif v.get("cable_id") is not None:
                    # Handle cable violations (for facade cables on monuments)
                    failed_ids.append(f"Cable_{v.get('cable_id')}")
            else:
                # Handle simple string violations (like filenames)
                failed_ids.append(str(v))
        
        failed_features_str = ", ".join(failed_ids) if failed_ids else ""

        return {
            "rule_id": rule_id,
            "Description": description,
            "status": "PASS" if not violations else "FAIL",
            "violation_count": len(violations),
            "failed_features": failed_features_str,
            "message": message,
        }

    def _create_error_result(self, rule_id, message):
        return {
            "rule_id": rule_id,
            "Description": "Data Quality validation rule",
            "status": "ERROR",
            "violation_count": 0,
            "failed_features": "",
            "message": message,
        }
