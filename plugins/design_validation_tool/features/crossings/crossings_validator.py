from qgis.core import ( # type: ignore
    QgsSpatialIndex,
    QgsProject,
    QgsDistanceArea,
    QgsCoordinateReferenceSystem,
    QgsGeometry,
)
from ...utils.layer_loader import get_layer_by_name, get_layer_from_API
from .crossings_helper import (
    _create_result,
    _create_error_result,
    _get_line_points,
    _calculate_line_angle,
    _calculate_line_angle,
    _calculate_min_distance,
    _calculate_min_distance_between_crossings,
)
from .rule_4_helpers import (
    _get_grb_direction_at_point,
    _get_overall_line_direction,
    _find_diverging_grb_pairs,
    _find_grb_direction_changes,
    _create_widening_area_violation,
)

from .rule_2_helpers import (
    _check_crossing_extends_beyond_intersection,
    _calculate_extension_beyond_intersection,
)


class CrossingsValidator:
    def __init__(self):
        self.violations = []
        self.distance_calculator = QgsDistanceArea()
        self.distance_calculator.setSourceCrs(
            QgsCoordinateReferenceSystem("EPSG:4326"), 
            QgsProject.instance().transformContext()
        )
        self.distance_calculator.setEllipsoid("WGS84")

    def validate_crossings_straight(self):
        """
            Rule CROSS_001: Crossing features should have valid relationship with Possible Trenches

            Valid relationships:
            1. Crossing is perpendicular to trench (75-105°)
            2. Crossing runs parallel to trench (0-15° or 165-180°) - following trench path
            3. Crossing connects to trench (T-junction)

            Invalid:
            - Crossing at odd angles (neither parallel nor perpendicular)
            - Crossing that doesn't relate to any trench
        """
        print("Validating crossing relationships to possible trenches...")

        # Get required layers
        crossings_layer = get_layer_by_name("IN_Crossings")
        trenches_layer = get_layer_by_name("Possible trench routes")

        print(f"Crossings layer: {crossings_layer}")
        print(f"Trenches layer: {trenches_layer}")
        
        if crossings_layer:
            print(f"Crossings feature count: {crossings_layer.featureCount()}")
            print(f"Crossings geometry type: {crossings_layer.geometryType()}")
        
        if trenches_layer:
            print(f"Trenches feature count: {trenches_layer.featureCount()}")
            print(f"Trenches geometry type: {trenches_layer.geometryType()}")
        
        # Check if layers exist
        if not crossings_layer:
            return _create_error_result(
                "CROSS_001", "IN_Crossings layer not found."
            )
        
        if not trenches_layer:
            return _create_error_result(
                "CROSS_001", "IN_PossibleTrenches layer not found."
            )
        
        # Check if layers have features
        if crossings_layer.featureCount() == 0:
            return _create_result(
                "CROSS_001",
                "Crossings should be perpendicular to possible trenches",
                [],
                "IN_Crossings layer has no features - validation skipped."
            )
        
        if trenches_layer.featureCount() == 0:
            return _create_result(
                "CROSS_001",
                "Crossings should be perpendicular to possible trenches",
                [],
                "IN_PossibleTrenches layer has no features - validation skipped."
            )
        
        # Validate geometry types
        if crossings_layer.geometryType() != 1:  # 1 = Line geometry
            return _create_error_result(
                "CROSS_001", "IN_Crossings layer should contain line features."
            )
        
        # Possible trenches could be lines or polygons
        trench_geom_type = trenches_layer.geometryType()
        if trench_geom_type not in [1, 2]:  # 1 = Line, 2 = Polygon
            return _create_error_result(
                "CROSS_001", "IN_PossibleTrenches layer should be line or polygon features."
            )
        
        # Build spatial index for trenches
        trenches_index = QgsSpatialIndex(trenches_layer.getFeatures())
        trench_features = {feature.id(): feature for feature in trenches_layer.getFeatures()}
        
        violations = []
        max_parallel_angle = 15.0  # ±15° from 0° or 180°
        min_perpendicular_angle = 75.0  # Minimum for "near perpendicular"
        max_perpendicular_angle = 105.0  # Maximum for "near perpendicular"
        search_buffer_distance = 10.0  # meters
        
        for crossing_feature in crossings_layer.getFeatures():
            crossing_geom = crossing_feature.geometry()
            if crossing_geom.isEmpty():
                continue
            
            crossing_points = _get_line_points(crossing_geom)
            if len(crossing_points) < 2:
                continue
            
            # Check if crossing relates to any trench
            search_geom = crossing_geom.buffer(search_buffer_distance, 5)
            candidate_trench_ids = trenches_index.intersects(search_geom.boundingBox())
            
            has_valid_relationship = False
            violation_details = []
            
            for trench_id in candidate_trench_ids:
                trench_feature = trench_features.get(trench_id)
                if not trench_feature:
                    continue
                
                trench_geom = trench_feature.geometry()
                if trench_geom.isEmpty():
                    continue
                
                # Calculate angle between crossing and trench
                angle = _calculate_line_angle(crossing_geom, trench_geom)
                if angle is None:
                    continue
                
                # Check relationship type
                is_parallel = (angle <= max_parallel_angle) or (angle >= (180 - max_parallel_angle))
                is_perpendicular = (min_perpendicular_angle <= angle <= max_perpendicular_angle)
                
                if is_parallel or is_perpendicular:
                    has_valid_relationship = True
                    best_angle = angle
                    best_trench_id = trench_id
                    break  # Found one valid relationship, no need to check more
                else:
                    # Track this invalid relationship for reporting
                    violation_details.append(f"Trench {trench_id}: angle {angle:.1f}°")
            
            # If no valid relationship found, create violation
            if not has_valid_relationship:
                crossing_id = crossing_feature.id()
                
                # Create helpful message
                if violation_details:
                    angle_details = f" Angles found: {', '.join(violation_details)}"
                else:
                    angle_details = " No nearby trenches found."
                
                violation_info = {
                    "violation_type": "crossing_invalid_angle",
                    "feature_id": crossing_id,
                    "geometry": crossing_geom,
                    "layer": "IN_Crossings",
                    "violation_reason": f"Crossing (ID: {crossing_id}) has invalid angle to possible trenches. \n"
                                    f"Should be nearly parallel (0-{max_parallel_angle}° or {180-max_parallel_angle}-180°) \n"
                                    f"or nearly perpendicular ({min_perpendicular_angle}-{max_perpendicular_angle}°).\n"
                                    f"{angle_details}"
                }
                violations.append(violation_info)
        
        description = f"Crossings should be nearly parallel (0-{max_parallel_angle}° or {180-max_parallel_angle}-180°) " \
                    f"or nearly perpendicular ({min_perpendicular_angle}-{max_perpendicular_angle}°) to possible trenches"
        
        violation_count = len(violations)
        message = f"Found {violation_count} crossings with invalid angles to trenches." if violation_count > 0 \
                else "All crossings have valid relationships with possible trenches."
        
        result = _create_result("CROSS_001", description, violations, message)
        self.violations.extend(violations)
        return result
    
    def validate_crossings_on_sidewalks(self):
        """
        Rule 2: Crossings limited to the sidewalks
        
        Checks if crossings intersect with sidewalk trenches.
        A crossing should NOT intersect with sidewalk trenches.
        
        Logic:
        1. Check if crossing intersects with trenches layer
        2. If YES intersection:
        - Check if the crossing continues after intersection by at least 30 cm.
        3. If NO intersection → VALID (crossing is away from trench)
        """
        print("Starting validate_crossings_on_sidewalks...")
    
        crossings_layer = get_layer_by_name("IN_Crossings")
        trenches_layer = get_layer_by_name('GRB - WGO - wegopdeling (clipped)')

        if not crossings_layer:
            print("DEBUG: No crossings layer found")
            return _create_error_result("CROSS_002", "IN_Crossings layer not found.")
        
        if not trenches_layer:
            print("DEBUG: No trenches layer found in project, trying API...")
            trenches_layer = get_layer_from_API()
            #print(f"DEBUG: Trenches layer from API: {trenches_layer}")
        
        if not trenches_layer:
            print("DEBUG: No trenches layer found at all")
            return _create_result(
                "CROSS_002", 
                "Crossings should not intersect with sidewalk trenches", 
                [], 
                "GRB - WGO - wegopdeling layer not found - validation skipped."
            )
        
        if crossings_layer.featureCount() == 0:
            print("DEBUG: Crossings layer is empty")
            return _create_result(
                "CROSS_002",
                "Crossings should not intersect with sidewalk trenches",
                [],
                "IN_Crossings layer has no features - validation skipped."
            )
        
        if trenches_layer.featureCount() == 0:
            print("DEBUG: Trenches layer is empty")
            return _create_result(
                "CROSS_002",
                "Crossings should not intersect with sidewalk trenches",
                [],
                "GRB - WGO - wegopdeling layer has no features - validation skipped."
            )
        
        # Build spatial index for trenches
        trenches_index = QgsSpatialIndex(trenches_layer.getFeatures())
        trench_features = {feature.id(): feature for feature in trenches_layer.getFeatures()}
        
        violations = []
        min_extension = 0.30
        buffer_distance = 0.50
        total_checked = 0
        intersections_found = 0
        extension_checks = 0
        
        for crossing_feature in crossings_layer.getFeatures():
            total_checked += 1
            crossing_geom = crossing_feature.geometry()
            crossing_id = crossing_feature.id()
            
            if crossing_geom.isEmpty():
                continue
            
            # Search for nearby trenches
            search_geom = crossing_geom.buffer(buffer_distance, 5)
            if search_geom.isEmpty():
                continue
            
            candidate_trench_ids = trenches_index.intersects(search_geom.boundingBox())
            
            has_intersection_violation = False
            violation_details = []
            
            for trench_id in candidate_trench_ids:
                trench_feature = trench_features.get(trench_id)
                if not trench_feature:
                    continue
                
                trench_geom = trench_feature.geometry()
                if trench_geom.isEmpty():
                    continue
                
                # Check intersection
                intersects = crossing_geom.intersects(trench_geom)
                
                if intersects:
                    intersections_found += 1
                    
                    # Get intersection geometry
                    intersection = crossing_geom.intersection(trench_geom)
                    
                    if not intersection.isEmpty():
                        extension_checks += 1

                        extends_beyond = _check_crossing_extends_beyond_intersection(
                            crossing_geom,
                            trench_geom,
                            intersection,
                            min_extension
                        )

                        if extends_beyond:
                            # Crossing continues beyond the sidewalk trench - VIOLATION
                            extension_distance = _calculate_extension_beyond_intersection(
                                crossing_geom,
                                trench_geom,
                                intersection
                            )
                        
                            has_intersection_violation = True
                            violation_details.append(
                                f"Trench {trench_id}: crossing extends {extension_distance:.2f}m beyond intersection" # type: ignore
                            )
                        else:
                            # Check endpoints distance to trench
                            crossing_points = _get_line_points(crossing_geom)
                            if len(crossing_points) >= 2:
                                start_point = crossing_points[0]
                                end_point = crossing_points[-1]
                                
                                # Create point geometries for distance calculation
                                start_geom = QgsGeometry.fromPointXY(start_point)
                                end_geom = QgsGeometry.fromPointXY(end_point)
                                
                                start_distance = start_geom.distance(trench_geom)
                                end_distance = end_geom.distance(trench_geom)
                                
                                # If either endpoint is very close to trench, it's a violation
                                if start_distance < min_extension or end_distance < min_extension:
                                    has_intersection_violation = True
                                    violation_details.append(
                                        f"Trench {trench_id}: endpoint {start_distance:.2f}m from trench"
                                    )

            if has_intersection_violation:
                crossing_length = crossing_geom.length()
                
                violation_info = {
                    "violation_type": "crossing_intersects_sidewalk_trench",
                    "feature_id": crossing_id,
                    "geometry": crossing_geom,
                    "layer": "IN_Crossings",
                    "crossing_length": crossing_length,
                    "required_extension": min_extension,
                    "violation_reason": f"Crossing (ID: {crossing_id}) intersects sidewalk trench "
                                    f"and should not be more than {min_extension}m.\n"
                                    f"Crossing length: {crossing_length:.2f}m.\n"
                                    f"{'; '.join(violation_details)}"
                }
                violations.append(violation_info)

        description = f"Crossings should not intersect sidewalk trenches, or must extend at least {min_extension}m beyond intersection"
        violation_count = len(violations)
        
        if violation_count > 0:
            message = f"Found {violation_count} crossings improperly intersecting sidewalk trenches."
        else:
            message = "All crossings are properly placed relative to sidewalk trenches."
        
        result = _create_result("CROSS_002", description, violations, message)
        self.violations.extend(violations)
        return result
    
    def validate_crossing_proximity(self, min_distance_meters: float = 50.0):
        """
        Rule 3: Crossings should not be close to each other
        
        Checks if two crossings are close to each other (configurable minimum distance)
        - If two crossings are within the minimum distance, it's a violation
        """
        print("Validating crossing proximity...")
    
        crossings_layer = get_layer_by_name("IN_Crossings")
        
        if not crossings_layer:
            return _create_error_result(
                "CROSS_003", "IN_Crossings layer not found."
            )
        
        # Check if layer has features
        if crossings_layer.featureCount() == 0:
            return _create_result(
                "CROSS_003",
                f"Crossings should be at least {min_distance_meters}m apart",
                [],
                "IN_Crossings layer has no features - validation skipped."
            )
        
        # Validate geometry type
        if crossings_layer.geometryType() != 1:  # 1 = Line geometry
            return _create_error_result(
                "CROSS_003", "IN_Crossings layer should contain line features."
            )
        
        # Get all crossing features
        crossing_features = list(crossings_layer.getFeatures())
        if len(crossing_features) < 2:
            return _create_result(
                "CROSS_003",
                f"Crossings should be at least {min_distance_meters}m apart",
                [],
                "Only one crossing found - no proximity check needed."
            )
        
        # Build spatial index for quick proximity checks
        crossings_index = QgsSpatialIndex(crossings_layer.getFeatures())
        
        # Store features by ID for quick lookup
        features_by_id = {feature.id(): feature for feature in crossing_features}
        
        violations = []
        processed_pairs = set()  # Track processed pairs to avoid duplicates
        
        for feature_id, feature in features_by_id.items():
            feature_geom = feature.geometry()
            if feature_geom.isEmpty():
                continue
            
            # Create search buffer around current feature
            # Use 1.5x min distance to catch nearby features
            search_buffer = min_distance_meters * 1.5
            
            # Create buffer geometry for search
            # Note: buffer distance is in layer units, might need CRS transformation
            try:
                buffered_geom = feature_geom.buffer(search_buffer, 5)
                if buffered_geom.isEmpty():
                    continue
            except:
                # If buffer fails, use bounding box expanded by search_buffer
                bbox = feature_geom.boundingBox()
                bbox.grow(search_buffer)
                buffered_geom = QgsGeometry.fromRect(bbox)
            
            # Find nearby crossings within search area
            nearby_feature_ids = crossings_index.intersects(buffered_geom.boundingBox())
            
            for nearby_id in nearby_feature_ids:
                if nearby_id == feature_id:
                    continue  # Skip self
                
                # Check if we've already processed this pair
                pair_key = tuple(sorted([feature_id, nearby_id]))
                if pair_key in processed_pairs:
                    continue
                
                nearby_feature = features_by_id.get(nearby_id)
                if not nearby_feature:
                    continue
                
                nearby_geom = nearby_feature.geometry()
                if nearby_geom.isEmpty():
                    continue
                
                # Calculate minimum distance between the two crossings
                min_distance = _calculate_min_distance_between_crossings(
                    feature_geom, 
                    nearby_geom,
                    min_distance_meters
                )
                
                # If distance is less than minimum required, it's a violation
                if min_distance is not None and min_distance < min_distance_meters:
                    # Get feature IDs for reporting
                    feature1_id = feature_id
                    feature2_id = nearby_id
                    
                    # Get some additional info for better reporting
                    feature1_type = feature.get("TYPE") if "TYPE" in feature.fields().names() else "N/A"
                    feature2_type = nearby_feature.get("TYPE") if "TYPE" in nearby_feature.fields().names() else "N/A"
                    
                    # Calculate centroids for distance display
                    centroid1 = feature_geom.centroid().asPoint()
                    centroid2 = nearby_geom.centroid().asPoint()
                    
                    violation_info = {
                        "violation_type": "crossings_too_close",
                        "feature_1_id": feature1_id,
                        "feature_2_id": feature2_id,
                        "geometry": feature_geom,  # Use first feature's geometry for display
                        "actual_distance": min_distance,
                        "required_distance": min_distance_meters,
                        "feature1_type": feature1_type,
                        "feature2_type": feature2_type,
                        "centroid1": (centroid1.x(), centroid1.y()),
                        "centroid2": (centroid2.x(), centroid2.y()),
                        "violation_reason": f"Crossings (ID: {feature1_id} and ID: {feature2_id}) are too close. "
                                        f"Distance: {min_distance:.1f}m (minimum required: {min_distance_meters}m). "
                                        f"Types: {feature1_type} & {feature2_type}"
                    }
                    violations.append(violation_info)
                    
                    # Mark this pair as processed
                    processed_pairs.add(pair_key)
        
        description = f"Crossings should be at least {min_distance_meters}m apart"
        violation_count = len(violations)
        
        if violation_count > 0:
            # Group violations by feature for summary
            feature_violations = {}
            for v in violations:
                feature_violations.setdefault(v["feature_1_id"], []).append(v["feature_2_id"])
                feature_violations.setdefault(v["feature_2_id"], []).append(v["feature_1_id"])
            
            offending_features = [fid for fid, nearby in feature_violations.items() if nearby]
            message = f"Found {violation_count} pairs of crossings too close together. " \
                    f"Affected crossings: {', '.join([str(fid) for fid in offending_features[:10]])}" + \
                    ("..." if len(offending_features) > 10 else "")
        else:
            message = f"All crossings are at least {min_distance_meters}m apart."
        
        result = _create_result("CROSS_003", description, violations, message)
        self.violations.extend(violations)
        return result

    def validate_crossings_in_narrow_areas(self):
        """
        Rule 4: Crossings should be where it's narrow

        Flag crossings that are located where 'GRB - WGO - wegopdeling' trenches 
        change directions in opposite ways (diverge from each other), 
        indicating wider road sections.
        """
        print("Validating crossings in narrow areas...")

        # Get crossings layer
        crossings_layer = get_layer_by_name("IN_Crossings")

        if not crossings_layer:
            return _create_error_result(
                "CROSS_004", "IN_Crossings layer not found."
            )

        if crossings_layer.featureCount() == 0:
            return _create_result(
                "CROSS_004",
                "Crossings should be in narrow road sections",
                [],
                "IN_Crossings layer has no features - validation skipped."
            )

        # Get GRB - WGO - wegopdeling layer from API
        try:
            grb_layer = get_layer_by_name('GRB - WGO - wegopdeling (clipped)')

            if not grb_layer:
                grb_layer = get_layer_from_API()

            if not grb_layer or grb_layer.featureCount() == 0:
                print("Warning: GRB - WGO - wegopdeling layer not found or empty.")
                return _create_result(
                    "CROSS_004",
                    "Crossings should be in narrow road sections",
                    [],
                    "GRB - WGO - wegopdeling layer not available - validation skipped."
                )
        except Exception as e:
            print(f"Error loading GRB layer: {e}")
            return _create_error_result(
                "CROSS_004", f"Failed to load GRB - WGO - wegopdeling layer: {str(e)}"
            )
        
        # Build spatial indices
        crossings_index = QgsSpatialIndex(crossings_layer.getFeatures())
        grb_index = QgsSpatialIndex(grb_layer.getFeatures())
        
        # Store features for quick access
        crossing_features = {feature.id(): feature for feature in crossings_layer.getFeatures()}
        grb_features = {feature.id(): feature for feature in grb_layer.getFeatures()}
        
        violations = []
        search_radius = 2.0  # meters to search for GRB features around crossings
        min_direction_change = 40.0  # Minimum angle change to consider as "changing direction"
        divergence_threshold = 20.0  # Minimum angle between diverging trenches
        
        # For each crossing, find nearby GRB trenches and check for divergence
        for crossing_id, crossing_feature in crossing_features.items():
            crossing_geom = crossing_feature.geometry()
            if crossing_geom.isEmpty():
                continue
            
            # Create search buffer around crossing
            search_buffer = crossing_geom.buffer(search_radius, 5)
            if search_buffer.isEmpty():
                continue
            
            # Find nearby GRB features
            nearby_grb_ids = grb_index.intersects(search_buffer.boundingBox())
            
            if len(nearby_grb_ids) < 2:
                continue  # Need at least 2 trenches to check for divergence
            
            # Analyze GRB features near this crossing
            grb_lines_near_crossing = []
            
            for grb_id in nearby_grb_ids:
                grb_feature = grb_features.get(grb_id)
                if not grb_feature:
                    continue
                
                grb_geom = grb_feature.geometry()
                if grb_geom.isEmpty():
                    continue
                
                # Only consider line geometries
                if grb_geom.type() != 1:  # 1 = Line geometry
                    continue
                
                # Get the segment of GRB line near the crossing
                nearest_point_geom = grb_geom.nearestPoint(crossing_geom.centroid())
                if nearest_point_geom.isEmpty():
                    continue
                
                nearest_point = nearest_point_geom.asPoint()
                
                # Get direction of GRB line at nearest point
                grb_direction = _get_grb_direction_at_point(grb_geom, nearest_point)
                if grb_direction is None:
                    continue
                
                # Get overall GRB line direction (start to end)
                overall_direction = _get_overall_line_direction(grb_geom)
                
                grb_lines_near_crossing.append({
                    'feature_id': grb_id,
                    'geometry': grb_geom,
                    'nearest_point': nearest_point,
                    'local_direction': grb_direction,
                    'overall_direction': overall_direction,
                    'distance_to_crossing': crossing_geom.centroid().distance(nearest_point_geom)
                })
            
            if len(grb_lines_near_crossing) < 2:
                continue
            
            # Check for diverging GRB lines (trenches going away from each other)
            diverging_pairs = _find_diverging_grb_pairs(
                grb_lines_near_crossing, 
                divergence_threshold
            )
            
            # Check for GRB lines that change direction near the crossing
            direction_changes = _find_grb_direction_changes(
                grb_lines_near_crossing,
                min_direction_change
            )
            
            # If we have both diverging pairs AND direction changes, it's likely a widening area
            if diverging_pairs and direction_changes:
                # This crossing is in a potentially wide area
                violation_info = _create_widening_area_violation(
                    crossing_feature, 
                    diverging_pairs, 
                    direction_changes
                )
                violations.append(violation_info)
        
        description = "Crossings should avoid road widening areas (where GRB trenches diverge)"
        violation_count = len(violations)
        
        if violation_count > 0:
            message = f"Found {violation_count} crossings in potential road widening areas."
        else:
            message = "No crossings found in road widening areas."
        
        result = _create_result("CROSS_004", description, violations, message)
        self.violations.extend(violations)
        return result
    
    def validate_crossing_rules(self, **kwargs):
        """
        Run all crossing validation rules with optional parameters
        """
        self.violations.clear()
        print("Running all Crossing validation rules...")
        
        results = []
        
        # Rule 1: Straightness
        results.append(self.validate_crossings_straight())

        lyr = get_layer_by_name("Feeder Clusters")

        # Rule 2: On sidewalks
        results.append(self.validate_crossings_on_sidewalks())
        
        # # Rule 3: Proximity (configurable distance)
        results.append(self.validate_crossing_proximity(min_distance_meters=3.0))
        
        # # Rule 4: Narrow areas (configurable max width)
        results.append(self.validate_crossings_in_narrow_areas())
        
        return results
