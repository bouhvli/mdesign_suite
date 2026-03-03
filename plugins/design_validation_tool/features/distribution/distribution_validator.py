from qgis.core import QgsGeometry, QgsProject, QgsWkbTypes, QgsSpatialIndex, QgsFeatureRequest  # type: ignore
from ...utils.layer_loader import get_layer_by_name
import traceback


class DistributionValidator:
    def __init__(self):
        self.violations = []

    def validate_max_cables_leaving_dp(self, max_cables=5):
        """
        Validate maximum distribution cables leaving Distribution Point

        Rule: Max 5 distribution cables leaving the DP
        Additional check: Cables intersecting DP buffer must be related to it

        Args:
            max_cables: Maximum number of distribution cables allowed per DP (default: 5)
        """
        print("Validating maximum distribution cables leaving DP...")
        description = f"Maximum distribution cables leaving DP (max {max_cables})"

        # Get required layers
        distribution_points_layer = get_layer_by_name("Distribution Points")
        distribution_cables_layer = get_layer_by_name("Distribution Cables")

        if not distribution_points_layer:
            return self._create_error_result(
                "DISTRIBUTION_001", description, "Distribution Points layer not found"
            )

        if not distribution_cables_layer:
            return self._create_error_result(
                "DISTRIBUTION_001", description, "Distribution Cables layer not found"
            )

        # Check if required fields exist
        if "AGG_ID" not in distribution_points_layer.fields().names():
            return self._create_error_result(
                "DISTRIBUTION_001",
                description,
                "Distribution Points layer missing AGG_ID field",
            )

        if "TOP_AGG_ID" not in distribution_cables_layer.fields().names():
            return self._create_error_result(
                "DISTRIBUTION_001",
                description,
                "Distribution Cables layer missing TOP_AGG_ID field",
            )

        violations = []

        # Build spatial index for distribution cables for efficient spatial queries
        cables_spatial_index = QgsSpatialIndex(distribution_cables_layer.getFeatures())

        # Count cables per DP and check for spatial-attribute mismatches
        dp_cable_counts = {}

        # Initialize all DPs
        for dp_feature in distribution_points_layer.getFeatures():
            dp_agg_id = dp_feature["AGG_ID"]
            dp_geometry = dp_feature.geometry()

            if not dp_geometry or dp_geometry.isEmpty():
                continue

            # Create 1m buffer around DP for spatial intersection check
            dp_buffer = dp_geometry.buffer(1.0, 5)  # 1m buffer with 5 segments

            # Find cables that intersect with the DP buffer
            spatial_cable_ids = cables_spatial_index.intersects(dp_buffer.boundingBox())

            related_cables = []
            unrelated_cables = []

            for cable_id in spatial_cable_ids:
                cable_feature = distribution_cables_layer.getFeature(cable_id)
                cable_geometry = cable_feature.geometry()

                if cable_geometry and not cable_geometry.isEmpty():
                    if cable_geometry.intersects(dp_buffer):
                        cable_top_agg_id = cable_feature["TOP_AGG_ID"]
                        cable_identifier = (
                            cable_feature["CABLE_ID"]
                            if "CABLE_ID" in cable_feature.fields().names()
                            else cable_feature.id()
                        )

                        # Check if cable is actually related to this DP
                        if cable_top_agg_id == dp_agg_id:
                            related_cables.append(cable_identifier)
                        else:
                            unrelated_cables.append(
                                {
                                    "cable_id": cable_identifier,
                                    "top_agg_id": cable_top_agg_id,
                                    "geometry": cable_geometry,
                                }
                            )

            dp_cable_counts[dp_agg_id] = {
                "related_count": len(related_cables),
                "unrelated_count": len(unrelated_cables),
                "dp_feature": dp_feature,
                "related_cables": related_cables,
                "unrelated_cables": unrelated_cables,
                "dp_buffer": dp_buffer,
            }

        # Check for two types of violations:
        # 1. Too many related cables leaving DP
        # 2. Cables spatially connected but not logically related to DP
        for dp_agg_id, dp_info in dp_cable_counts.items():
            dp_feature = dp_info["dp_feature"]
            dp_id = (
                dp_feature["DP_ID"]
                if "DP_ID" in dp_feature.fields().names()
                else dp_agg_id
            )

            # Violation type 1: Too many related cables
            if dp_info["related_count"] > max_cables:
                violation_info = {
                    "dp_id": dp_id,
                    "dp_agg_id": dp_agg_id,
                    "dp_feature_id": dp_feature.id(),
                    "cable_count": dp_info["related_count"],
                    "max_allowed": max_cables,
                    "cable_ids": dp_info["related_cables"],
                    "geometry": dp_feature.geometry(),
                    "violation_type": "max_cables_leaving_dp",
                    "violation_reason": f"DP {dp_id} has {dp_info['related_count']} related distribution cables (max {max_cables})",
                }
                violations.append(violation_info)

            # Violation type 2: Unrelated cables intersecting DP buffer
            if dp_info["unrelated_count"] > 0:
                # Create combined geometry for all unrelated cables
                unrelated_geoms = [
                    cable["geometry"] for cable in dp_info["unrelated_cables"]
                ]
                combined_geom = self._merge_line_geometries(unrelated_geoms)

                unrelated_cable_ids = [
                    cable["cable_id"] for cable in dp_info["unrelated_cables"]
                ]
                unrelated_top_agg_ids = [
                    cable["top_agg_id"] for cable in dp_info["unrelated_cables"]
                ]

                violation_info = {
                    "dp_id": dp_id,
                    "dp_agg_id": dp_agg_id,
                    "dp_feature_id": dp_feature.id(),
                    "unrelated_cable_count": dp_info["unrelated_count"],
                    "unrelated_cable_ids": unrelated_cable_ids,
                    "unrelated_top_agg_ids": unrelated_top_agg_ids,
                    "geometry": (
                        combined_geom
                        if combined_geom and not combined_geom.isEmpty()
                        else dp_feature.geometry()
                    ),
                    "violation_type": "unrelated_cables_at_dp",
                    "violation_reason": f"DP {dp_id} has {dp_info['unrelated_count']} unrelated cables intersecting it: {', '.join(unrelated_cable_ids)}",
                }
                violations.append(violation_info)

            # Clean up
            del dp_info["dp_buffer"]

        # Clean up spatial index
        cables_spatial_index = None

        violation_count = len(violations)
        if violation_count > 0:
            message = f"Found {violation_count} DP cable relationship violations"
        else:
            message = "No violations found."

        result = self._create_result(
            "DISTRIBUTION_001", description, violations, message
        )
        self.violations.extend(violations)

        return result

    def validate_facade_cable_max_length(self, max_length=500.0):
        """
        Validate façade cable maximum length

        Rule: Façade cable max length of 500m
        Check distribution cables with TYPE containing 'façade' or 'facade'

        Args:
            max_length: Maximum allowed length for façade cables in meters (default: 500.0)
        """
        print("Validating façade cable maximum length...")
        description = f"Façade cable maximum length (max {max_length}m)"

        # Get required layer
        distribution_cables_layer = get_layer_by_name("Distribution Cables")

        if not distribution_cables_layer:
            return self._create_error_result(
                "DISTRIBUTION_002", description, "Distribution Cables layer not found"
            )

        # Check if required fields exist
        if "TYPE" not in distribution_cables_layer.fields().names():
            return self._create_error_result(
                "DISTRIBUTION_002",
                description,
                "Distribution Cables layer missing TYPE field",
            )

        violations = []

        # Check each distribution cable
        for cable_feature in distribution_cables_layer.getFeatures():
            cable_type = cable_feature["TYPE"]
            cable_geometry = cable_feature.geometry()

            is_facade = (
                cable_type
                and isinstance(cable_type, str)
                and ("façade" in cable_type.lower() or "facade" in cable_type.lower())
            )

            if is_facade and cable_geometry and not cable_geometry.isEmpty():
                cable_length = cable_geometry.length()

                if cable_length > max_length:
                    cable_id = (
                        cable_feature["CABLE_ID"]
                        if "CABLE_ID" in cable_feature.fields().names()
                        else cable_feature.id()
                    )

                    violation_info = {
                        "cable_id": cable_id,
                        "cable_type": cable_type,
                        "cable_length": cable_length,
                        "max_allowed": max_length,
                        "cable_feature_id": cable_feature.id(),
                        "geometry": cable_geometry,
                        "violation_type": "facade_cable_max_length",
                        "violation_reason": f"Façade cable {cable_id} has length {cable_length:.1f}m (max {max_length}m)",
                    }
                    violations.append(violation_info)

        violation_count = len(violations)
        if violation_count > 0:
            message = f"Found {violation_count} façade cables exceeding {max_length}m maximum length"
        else:
            message = "No violations found."

        result = self._create_result(
            "DISTRIBUTION_002", description, violations, message
        )
        self.violations.extend(violations)
        return result

    def validate_aerial_cable_poc_limit(self, max_pocs=22, max_drops=4):
        """
        Validate that aerial distribution cables have maximum 22 POCs with 4 drops each

        Rule: Distribution cable with type Aerial - Max 22 POCs of 4 drops should be connected to it
        """
        print("Validating aerial distribution cable POC limit...")
        description = (
            f"Aerial distribution cable POC limit (max {max_pocs} POCs per cable group)"
        )

        # Get required layers
        distribution_cables_layer = get_layer_by_name("Distribution Cables")
        drop_points_layer = get_layer_by_name("Drop Points")
        drop_cables_layer = get_layer_by_name("Drop Cables")

        if not distribution_cables_layer:
            return self._create_error_result(
                "DISTRIBUTION_003", description, "Distribution Cables layer not found"
            )

        if not drop_points_layer:
            return self._create_error_result(
                "DISTRIBUTION_003", description, "Drop Points layer not found"
            )

        if not drop_cables_layer:
            return self._create_error_result(
                "DISTRIBUTION_003", description, "Drop Cables layer not found"
            )

        # Check if required fields exist
        required_fields_dist_cables = ["TYPE", "CAB_GROUP", "CABLE_ID"]
        missing_fields_dist = [
            field
            for field in required_fields_dist_cables
            if field not in distribution_cables_layer.fields().names()
        ]
        if missing_fields_dist:
            return self._create_error_result(
                "DISTRIBUTION_003",
                description,
                f'Distribution Cables layer missing required fields: {", ".join(missing_fields_dist)}',
            )

        required_fields_drop_points = ["SUBCLUSTER", "AGG_ID", "ID"]
        missing_fields_drop = [
            field
            for field in required_fields_drop_points
            if field not in drop_points_layer.fields().names()
        ]
        if missing_fields_drop:
            return self._create_error_result(
                "DISTRIBUTION_003",
                description,
                f'Drop Points layer missing required fields: {", ".join(missing_fields_drop)}',
            )

        if "TOP_AGG_ID" not in drop_cables_layer.fields().names():
            return self._create_error_result(
                "DISTRIBUTION_003",
                description,
                "Drop Cables layer missing required field: TOP_AGG_ID",
            )

        violations = []

        # Build POC to drop cable count mapping
        poc_drop_counts = {}
        for drop_cable_feature in drop_cables_layer.getFeatures():
            top_agg_id = drop_cable_feature["TOP_AGG_ID"]
            if top_agg_id not in poc_drop_counts:
                poc_drop_counts[top_agg_id] = 0
            poc_drop_counts[top_agg_id] += 1

        # Build distribution cable to POCs mapping
        aerial_dist_cables_by_group = {}
        for cable_feature in distribution_cables_layer.getFeatures():
            cable_type = cable_feature["TYPE"]
            if (
                cable_type
                and isinstance(cable_type, str)
                and "aerial" in cable_type.lower()
            ):
                cab_group = cable_feature["CAB_GROUP"]
                if cab_group not in aerial_dist_cables_by_group:
                    aerial_dist_cables_by_group[cab_group] = {"cables": [], "pocs": []}
                aerial_dist_cables_by_group[cab_group]["cables"].append(
                    {
                        "cable_feature": cable_feature,
                        "cable_id": cable_feature["CABLE_ID"],
                    }
                )

        # Find POCs connected to each aerial distribution cable group
        for poc_feature in drop_points_layer.getFeatures():
            poc_subcluster = poc_feature["SUBCLUSTER"]
            if poc_subcluster in aerial_dist_cables_by_group:
                poc_agg_id = poc_feature["AGG_ID"]
                drop_count = poc_drop_counts.get(poc_agg_id, 0)
                poc_info = {
                    "poc_feature": poc_feature,
                    "poc_agg_id": poc_agg_id,
                    "poc_id": poc_feature["ID"],
                    "drop_count": drop_count,
                }
                aerial_dist_cables_by_group[poc_subcluster]["pocs"].append(poc_info)

        # Check for violations
        for cab_group, group_info in aerial_dist_cables_by_group.items():
            poc_count = len(group_info["pocs"])
            if poc_count > max_pocs:
                for cable_info in group_info["cables"]:
                    pocs_with_4_drops = [
                        poc
                        for poc in group_info["pocs"]
                        if poc["drop_count"] == max_drops
                    ]
                    violation_info = {
                        "cable_id": cable_info["cable_id"],
                        "cable_group": cab_group,
                        "poc_count": poc_count,
                        "max_allowed": max_pocs,
                        "geometry": cable_info["cable_feature"].geometry(),
                        "violation_type": "aerial_cable_poc_limit",
                        "violation_reason": f"Aerial cable {cable_info['cable_id']} in group {cab_group} has {poc_count} POCs (max {max_pocs}), with {len(pocs_with_4_drops)} POCs having 4 drops",
                    }
                    violations.append(violation_info)

        violation_count = len(violations)
        if violation_count > 0:
            message = f"Found {violation_count} aerial distribution cables in groups with more than {max_pocs} POCs"
        else:
            message = "No violations found."

        result = self._create_result(
            "DISTRIBUTION_003", description, violations, message
        )
        self.violations.extend(violations)
        return result

    def validate_parallel_cable_poc_connection(self, num_pocs=11):
        """
        Rule: When 2 parallel UNDERGROUND cables exist, the furthest 11 POCs must be connected to the longest cable only.

        Parallel cables definition: One cable is completely inside another cable (intersection length equals shorter cable length)
        POC connection: A POC is connected to a cable if its SUBCLUSTER matches the cable's CAB_GROUP

        Args:
            num_pocs: Number of furthest POCs to check (default: 11)
        """
        print("Validating parallel cable POC connections...")
        description = f"Furthest {num_pocs} POCs on parallel underground cables must be served by longest cable only"

        dist_cables_layer = get_layer_by_name("Distribution Cables")
        pocs_layer = get_layer_by_name("Drop Points")
        dp_layer = get_layer_by_name("Distribution Points")

        if not all([dist_cables_layer, pocs_layer, dp_layer]):
            return self._create_error_result(
                "DISTRIBUTION_004",
                description,
                "One or more required layers are missing.",
            )

        # Check required fields
        required_fields_cables = ["CAB_GROUP", "TOP_AGG_ID", "CABLE_ID", "TYPE"]
        missing_fields = [
            f
            for f in required_fields_cables
            if f not in dist_cables_layer.fields().names()  # type: ignore
        ]
        if missing_fields:
            return self._create_error_result(
                "DISTRIBUTION_004",
                description,
                f'Distribution Cables layer missing fields: {", ".join(missing_fields)}',
            )

        required_fields_pocs = ["SUBCLUSTER", "AGG_ID", "ID"]
        missing_fields = [
            f for f in required_fields_pocs if f not in pocs_layer.fields().names()  # type: ignore
        ]
        if missing_fields:
            return self._create_error_result(
                "DISTRIBUTION_004",
                description,
                f'Drop Points layer missing fields: {", ".join(missing_fields)}',
            )

        violations = []

        # Get all UNDERGROUND distribution cables only
        underground_cables = []
        for cable in dist_cables_layer.getFeatures():  # type: ignore
            if "underground" == str(cable["TYPE"]).lower():
                underground_cables.append(cable)

        processed_cable_ids = set()

        # Find parallel cable pairs using the same logic as validate_parallel_aerial_cable_limit
        for i, cable_a in enumerate(underground_cables):
            cable_a_id = cable_a.id()
            if cable_a_id in processed_cable_ids:
                continue

            cable_a_geom = cable_a.geometry()
            if not cable_a_geom or cable_a_geom.isEmpty():
                continue

            cable_a_len = cable_a_geom.length()
            if cable_a_len == 0:
                continue

            # Start a new group with cable_a
            parallel_group = [cable_a]
            processed_cable_ids.add(cable_a_id)

            # Compare with all subsequent cables
            for j in range(i + 1, len(underground_cables)):
                cable_b = underground_cables[j]
                cable_b_id = cable_b.id()
                if cable_b_id in processed_cable_ids:
                    continue

                cable_b_geom = cable_b.geometry()
                if not cable_b_geom or cable_b_geom.isEmpty():
                    continue

                cable_b_len = cable_b_geom.length()
                if cable_b_len == 0:
                    continue

                # Check for significant overlap
                intersection = cable_a_geom.intersection(cable_b_geom)
                if not intersection or intersection.isEmpty():
                    continue

                intersection_len = intersection.length()

                # To be parallel, the intersection length must equal the shorter cable's length
                shorter_len = min(cable_a_len, cable_b_len)

                # Allow small tolerance (1%) for geometric imprecision
                if abs(intersection_len - shorter_len) / shorter_len < 0.01:
                    parallel_group.append(cable_b)
                    processed_cable_ids.add(cable_b_id)

            # Process groups with exactly 2 parallel cables
            if len(parallel_group) == 2:
                try:

                    # Determine which is longest and which is shortest
                    cable_a = parallel_group[0]
                    cable_b = parallel_group[1]

                    cable_a_geom = cable_a.geometry()
                    cable_b_geom = cable_b.geometry()

                    if cable_a_geom.length() >= cable_b_geom.length():
                        longest_cable = cable_a
                        shortest_cable = cable_b
                        longest_geom = cable_a_geom
                        shortest_geom = cable_b_geom
                    else:
                        longest_cable = cable_b
                        shortest_cable = cable_a
                        longest_geom = cable_b_geom
                        shortest_geom = cable_a_geom

                    longest_cab_group = longest_cable["CAB_GROUP"]
                    shortest_cab_group = shortest_cable["CAB_GROUP"]

                    # Find the DP for the longest cable
                    dp_agg_id = longest_cable["TOP_AGG_ID"]
                    request = QgsFeatureRequest().setFilterExpression(
                        f"\"AGG_ID\" = '{dp_agg_id}'"
                    )
                    dp_features = list(dp_layer.getFeatures(request))  # type: ignore

                    if not dp_features:
                        continue

                    dp_geom = dp_features[0].geometry()
                    if not dp_geom or dp_geom.isEmpty():
                        continue

                    # Get DP position on the longest cable
                    dp_position = longest_geom.lineLocatePoint(dp_geom)

                    # Get POCs connected to either cable (by SUBCLUSTER matching CAB_GROUP)
                    all_pocs = []

                    if longest_cab_group and shortest_cab_group:
                        poc_filter = f"\"SUBCLUSTER\" IN ('{longest_cab_group}', '{shortest_cab_group}')"
                        poc_request = QgsFeatureRequest().setFilterExpression(
                            poc_filter
                        )
                        for poc in pocs_layer.getFeatures(poc_request): # type: ignore
                            poc_geom = poc.geometry()
                            if not poc_geom or poc_geom.isEmpty():
                                continue

                            poc_subcluster = poc["SUBCLUSTER"]

                            # Determine which cable(s) this POC is connected to
                            connected_to_longest = poc_subcluster == longest_cab_group
                            connected_to_shortest = poc_subcluster == shortest_cab_group

                            all_pocs.append(
                                {
                                    "feature": poc,
                                    "geometry": poc_geom,
                                    "connected_to_longest": connected_to_longest,
                                    "connected_to_shortest": connected_to_shortest,
                                }
                            )

                    if not all_pocs:
                        continue

                    # Calculate distance along the longest cable for each POC from the DP
                    # We want absolute distance, so we measure the actual distance along the line
                    for poc_info in all_pocs:
                        position_on_cable = longest_geom.lineLocatePoint(
                            poc_info["geometry"]
                        )

                        # lineLocatePoint returns normalized position (0 to 1)
                        # Convert to absolute distance
                        distance_from_dp = (
                            abs(position_on_cable - dp_position) * longest_geom.length()
                        )
                        poc_info["distance_from_dp"] = distance_from_dp
                        poc_info["position_on_cable"] = position_on_cable

                    # Get the furthest N POCs from DP
                    pocs_to_check = min(num_pocs, len(all_pocs))
                    farthest_pocs = sorted(
                        all_pocs, key=lambda x: x["distance_from_dp"], reverse=True
                    )[:pocs_to_check]

                    # Re-sort for logical ordering in output
                    farthest_pocs_ordered = sorted(
                        farthest_pocs, key=lambda x: x["distance_from_dp"]
                    )

                    # Check if any of these furthest POCs are connected to the shortest cable
                    for poc_info in farthest_pocs_ordered:
                        poc = poc_info["feature"]
                        poc_geom = poc_info["geometry"]
                        distance = poc_info["distance_from_dp"]
                        position = poc_info["position_on_cable"]

                        # Violation: POC should only be connected to longest cable
                        if poc_info["connected_to_shortest"]:
                            violations.append(
                                {
                                    "poc_id": poc["ID"],
                                    "longest_cable_id": longest_cable["CABLE_ID"],
                                    "shortest_cable_id": shortest_cable["CABLE_ID"],
                                    "distance_from_dp": distance,
                                    "position_on_cable": position,
                                    "geometry": poc_geom,
                                    "violation_type": "parallel_poc_connection",
                                    "violation_reason": f"POC {poc['ID']} at distance {distance:.2f}m from DP (position {position:.3f}) is connected to shortest cable {shortest_cable['CABLE_ID']} but should only be connected to longest cable {longest_cable['CABLE_ID']}",
                                }
                            )
                except Exception as e:
                    print(f"Error processing parallel cable pair: {str(e)}")
                    import traceback

                    traceback.print_exc()
                    continue

        violation_count = len(violations)
        message = (
            f"Found {violation_count} violations for parallel underground POC connections."
            if violation_count > 0
            else "No violations found."
        )
        result = self._create_result(
            "DISTRIBUTION_004", description, violations, message
        )
        self.violations.extend(violations)
        return result

    def _merge_line_geometries(self, geometries):
        """Helper to merge multiple line geometries into a single multiline geometry."""
        valid_geoms = [g for g in geometries if g and not g.isEmpty()]
        if not valid_geoms:
            return None

        # Start with the first valid geometry
        merged_geom = QgsGeometry(valid_geoms[0])

        # Combine with the rest
        for g in valid_geoms[1:]:
            merged_geom = merged_geom.combine(g)

        return merged_geom

    def validate_facade_underground_length(self, max_distance=40.0):
        """
        Rule: Façade cable max 40m underground between 2 façade pieces.
        This is checked by analyzing 'Possible Routes' within a 'Distribution Cable'.
        """
        print("Validating facade underground cable length...")
        description = (
            f"Underground sections of facade cables must be <= {max_distance}m"
        )

        dist_cables_layer = get_layer_by_name("Distribution Cables")
        possible_routes_layer = get_layer_by_name("Possible Routes")

        if not dist_cables_layer:
            return self._create_error_result(
                "DISTRIBUTION_005", description, "Distribution Cables layer not found."
            )
        if not possible_routes_layer:
            return self._create_error_result(
                "DISTRIBUTION_005", description, "Possible Routes layer not found."
            )

        violations = []
        # Create a spatial index for efficient lookup of possible routes
        routes_index = QgsSpatialIndex(possible_routes_layer.getFeatures())

        for cable in dist_cables_layer.getFeatures():
            cable_geom = cable.geometry()
            if cable_geom.isEmpty():
                continue

            # Find candidate routes within the cable's bounding box
            candidate_ids = routes_index.intersects(cable_geom.boundingBox())

            # Filter to routes that are truly inside the cable's geometry
            inside_routes = []
            cable_buffer = cable_geom.buffer(0.1, 5)  # Small buffer for tolerance
            for route_id in candidate_ids:
                route = possible_routes_layer.getFeature(route_id)
                # Assign geometry to a variable to prevent garbage collection issues
                route_geom = route.geometry()
                if not route_geom or route_geom.isEmpty():
                    continue

                # Perform operations on the stable geometry variable
                if route_geom.buffer(0.01, 5).within(cable_buffer):
                    inside_routes.append(route)

            if not inside_routes:
                continue

            # Sort routes based on their position along the main cable
            route_positions = []
            for route in inside_routes:
                centroid = route.geometry().centroid().asPoint()
                pos = cable_geom.lineLocatePoint(QgsGeometry.fromPointXY(centroid))
                route_positions.append((pos, route))
            route_positions.sort(key=lambda x: x[0])

            # Identify the positions of facade aerial points
            facade_positions = [
                pos
                for pos, route in route_positions
                if "AERIAL" in str(route["TYPE"]).upper()
                and "FACADE" in str(route["AERIALTYPE"]).upper()
            ]
            if len(facade_positions) < 2:
                continue

            # Check the segments between each pair of facade points
            for i in range(len(facade_positions) - 1):
                start_pos = facade_positions[i]
                end_pos = facade_positions[i + 1]

                total_length = 0
                num_segments = 0
                violating_geoms = []

                # Sum lengths of Buried/Transition routes between the facade points
                for pos, route in route_positions:
                    if start_pos < pos < end_pos:
                        route_type = str(route["TYPE"]).upper()
                        if route_type in ["BURIED", "TRANSITION"]:
                            try:
                                length = float(route["LENGTH"])
                                total_length += length
                                num_segments += 1
                                violating_geoms.append(route.geometry())
                            except (ValueError, TypeError):
                                continue  # Skip if length is not a valid number

                if total_length > max_distance and violating_geoms:
                    merged_geom = self._merge_line_geometries(violating_geoms)
                    if not merged_geom or merged_geom.isEmpty():
                        continue
                    violations.append(
                        {
                            "cable_id": cable["CABLE_ID"],
                            "length": total_length,
                            "geometry": merged_geom,
                            "violation_type": "facade_underground_length",
                            "violation_reason": f"Underground section on cable {cable['CABLE_ID']} is {total_length:.1f}m (max {max_distance}m).",
                        }
                    )

        violation_count = len(violations)
        message = (
            f"Found {violation_count} underground facade sections over {max_distance}m."
            if violation_count > 0
            else "No violations found."
        )
        result = self._create_result(
            "DISTRIBUTION_005", description, violations, message
        )
        self.violations.extend(violations)
        return result

    def validate_parallel_aerial_cable_limit(self, max_parallel=2):
        """
        Rule: Max 2 Aerial cables in parallel.
        This is determined by geometric overlap, not by CAB_GROUP.
        """
        print("Validating parallel aerial cable limit...")
        description = f"Maximum {max_parallel} parallel aerial cables"

        dist_cables_layer = get_layer_by_name("Distribution Cables")
        if not dist_cables_layer:
            return self._create_error_result(
                "DISTRIBUTION_006", description, "Distribution Cables layer not found."
            )

        violations = []

        # Get all aerial cables first
        aerial_cables = []
        for cable in dist_cables_layer.getFeatures():
            if "aerial" in str(cable["TYPE"]).lower():
                aerial_cables.append(cable)

        processed_cable_ids = set()

        for i, cable_a in enumerate(aerial_cables):
            cable_a_id = cable_a.id()
            if cable_a_id in processed_cable_ids:
                continue

            cable_a_geom = cable_a.geometry()
            if not cable_a_geom or cable_a_geom.isEmpty():
                continue

            cable_a_len = cable_a_geom.length()
            if cable_a_len == 0:
                continue

            # Start a new group with cable_a
            parallel_group = [cable_a]
            processed_cable_ids.add(cable_a_id)

            # Compare with all subsequent cables
            for j in range(i + 1, len(aerial_cables)):
                cable_b = aerial_cables[j]
                cable_b_id = cable_b.id()
                if cable_b_id in processed_cable_ids:
                    continue

                cable_b_geom = cable_b.geometry()
                if not cable_b_geom or cable_b_geom.isEmpty():
                    continue

                cable_b_len = cable_b_geom.length()
                if cable_b_len == 0:
                    continue

                # Check for significant overlap
                intersection = cable_a_geom.intersection(cable_b_geom)
                if not intersection or intersection.isEmpty():
                    continue

                intersection_len = intersection.length()

                # To be parallel, the intersection must be a large percentage of BOTH cables' lengths
                if intersection_len == cable_a_len:
                    parallel_group.append(cable_b)
                    processed_cable_ids.add(cable_b_id)

            # After checking all other cables, see if the group violates the rule
            if len(parallel_group) > max_parallel:
                # Create one violation for the entire group
                # Use the longest cable as the representative feature
                longest_cable = max(parallel_group, key=lambda c: c.geometry().length())
                group_cable_ids = [str(c["CABLE_ID"]) for c in parallel_group]

                violations.append(
                    {
                        "cable_group_ids": ", ".join(group_cable_ids),
                        "cable_count": len(parallel_group),
                        "geometry": longest_cable.geometry(),
                        "violation_type": "parallel_aerial_limit",
                        "violation_reason": f"Found {len(parallel_group)} parallel aerial cables (max {max_parallel}): {', '.join(group_cable_ids)}.",
                    }
                )

        violation_count = len(violations)
        message = (
            f"Found {violation_count} groups with more than {max_parallel} parallel aerial cables."
            if violation_count > 0
            else "No violations found."
        )
        result = self._create_result(
            "DISTRIBUTION_006", description, violations, message
        )
        self.violations.extend(violations)
        return result

    def validate_underground_drop_consistency(self):
        """
        Rule: When Distribution is underground, Drop is also underground.
        """
        print("Validating underground drop consistency...")
        description = "Underground distribution must have underground drops"

        dist_cables_layer = get_layer_by_name("Distribution Cables")
        drop_cables_layer = get_layer_by_name("Drop Cables")
        pocs_layer = get_layer_by_name("Drop Points")

        if not all([dist_cables_layer, drop_cables_layer, pocs_layer]):
            return self._create_error_result(
                "DISTRIBUTION_007",
                description,
                "One or more required layers are missing.",
            )

        violations = []

        # Find all underground distribution cables and their connected POCs
        underground_dist_pocs = {}  # Key: POC AGG_ID, Value: dist cable
        for dist_cable in dist_cables_layer.getFeatures():  # type: ignore
            if "underground" == str(dist_cable["TYPE"]).lower():
                # Find POCs in the same subcluster
                group = dist_cable["CAB_GROUP"]
                pocs = pocs_layer.getFeatures(f"\"SUBCLUSTER\" = '{group}'")  # type: ignore
                for poc in pocs:
                    underground_dist_pocs[poc["AGG_ID"]] = dist_cable

        # Check drop cables connected to these POCs
        for drop_cable in drop_cables_layer.getFeatures():  # type: ignore
            poc_agg_id = drop_cable["TOP_AGG_ID"]
            if poc_agg_id in underground_dist_pocs:
                if "underground" != str(drop_cable["TYPE"]).lower():
                    violations.append(
                        {
                            "drop_cable_id": drop_cable["CABLE_ID"],
                            "poc_agg_id": poc_agg_id,
                            "geometry": drop_cable.geometry(),
                            "violation_type": "underground_drop_mismatch",
                            "violation_reason": f"Drop cable {drop_cable['CABLE_ID']} is not underground, but its distribution line is.",
                        }
                    )

        violation_count = len(violations)
        message = (
            f"Found {violation_count} drop cables that are not underground but should be."
            if violation_count > 0
            else "No violations found."
        )
        result = self._create_result(
            "DISTRIBUTION_007", description, violations, message
        )
        self.violations.extend(violations)
        return result

    def validate_facade_total_underground_length(self, max_length=60.0):
        """
        Rule: Façade cable start and end underground segments must be <= 60m each.

        Measures:
        - Start segment: Continuous underground length from cable start until transition to aerial façade
        - End segment: Continuous underground length from cable end backwards until transition to aerial façade
        """
        print("Validating facade cable start/end underground segments...")
        description = f"Facade cable start and end underground segments must be <= {max_length}m each"

        # Get required layers
        dist_cables_layer = get_layer_by_name("Distribution Cables")
        possible_routes_layer = get_layer_by_name("Possible Routes")

        if not dist_cables_layer:
            return self._create_error_result(
                "DISTRIBUTION_012", description, "Distribution Cables layer not found."
            )
        if not possible_routes_layer:
            return self._create_error_result(
                "DISTRIBUTION_012", description, "Possible Routes layer not found."
            )

        violations = []

        # Build spatial index for possible routes
        routes_index = QgsSpatialIndex(possible_routes_layer.getFeatures())

        # Process only facade cables
        for cable in dist_cables_layer.getFeatures():
            cable_type = str(cable["TYPE"]).lower()
            if "facade" not in cable_type:
                continue

            cable_geom = cable.geometry()
            if not cable_geom or cable_geom.isEmpty():
                continue

            cable_id = (
                cable["CABLE_ID"]
                if "CABLE_ID" in cable.fields().names()
                else cable.id()
            )

            # Find routes along this cable
            candidate_ids = routes_index.intersects(cable_geom.boundingBox())
            if not candidate_ids:
                continue

            # Collect and sort routes by position along cable
            route_positions = []
            cable_buffer = cable_geom.buffer(0.1, 5)

            for route_id in candidate_ids:
                route = possible_routes_layer.getFeature(route_id)
                route_geom = route.geometry()
                if not route_geom or route_geom.isEmpty():
                    continue

                if route_geom.buffer(0.01, 5).within(cable_buffer):
                    centroid = route_geom.centroid().asPoint()
                    pos = cable_geom.lineLocatePoint(QgsGeometry.fromPointXY(centroid))
                    route_type = str(route["TYPE"]).upper()
                    aerial_type = (
                        str(route["AERIALTYPE"]).upper()
                        if "AERIALTYPE" in route.fields().names()
                        else ""
                    )

                    route_positions.append(
                        {
                            "position": pos,
                            "type": route_type,
                            "aerial_type": aerial_type,
                            "length": (
                                float(route["LENGTH"]) if route["LENGTH"] else 0.0
                            ),
                            "geometry": route_geom,
                        }
                    )

            if not route_positions:
                continue

            # Sort routes by position along cable
            route_positions.sort(key=lambda x: x["position"])

            # Find start underground segment
            start_underground_length = 0.0
            start_violation_geoms = []

            for route in route_positions:
                if route["type"] in ["BURIED", "TRANSITION"]:
                    start_underground_length += route["length"]
                    start_violation_geoms.append(route["geometry"])
                elif route["type"] == "AERIAL" and "FACADE" in route["aerial_type"]:
                    # Reached aerial facade section, stop measuring start segment
                    break
                else:
                    # Other aerial types, stop measuring start segment
                    break

            # Find end underground segment (process backwards)
            end_underground_length = 0.0
            end_violation_geoms = []

            for route in reversed(route_positions):
                if route["type"] in ["BURIED", "TRANSITION"]:
                    end_underground_length += route["length"]
                    end_violation_geoms.append(route["geometry"])
                elif route["type"] == "AERIAL" and "FACADE" in route["aerial_type"]:
                    # Reached aerial facade section, stop measuring end segment
                    break
                else:
                    # Other aerial types, stop measuring end segment
                    break

            # Check for violations
            violation_reasons = []
            violation_geoms = []

            if start_underground_length > max_length:
                violation_reasons.append(
                    f"start underground segment {start_underground_length:.1f}m"
                )
                if start_violation_geoms:
                    merged_geom = self._merge_line_geometries(start_violation_geoms)
                    if merged_geom and not merged_geom.isEmpty():
                        violation_geoms.append(merged_geom)

            if end_underground_length > max_length:
                violation_reasons.append(
                    f"end underground segment {end_underground_length:.1f}m"
                )
                if end_violation_geoms:
                    merged_geom = self._merge_line_geometries(end_violation_geoms)
                    if merged_geom and not merged_geom.isEmpty():
                        violation_geoms.append(merged_geom)

            if violation_reasons:
                final_geom = (
                    self._merge_line_geometries(violation_geoms)
                    if violation_geoms
                    else cable_geom
                )

                violations.append(
                    {
                        "cable_id": cable_id,
                        "start_length": start_underground_length,
                        "end_length": end_underground_length,
                        "geometry": final_geom,
                        "violation_type": "facade_total_underground_length",
                        "violation_reason": f"Facade cable {cable_id} has {', '.join(violation_reasons)} (max {max_length}m each)",
                    }
                )

            # Clear variables for next iteration
            del (
                route_positions,
                start_violation_geoms,
                end_violation_geoms,
                violation_geoms,
            )
            candidate_ids = None

        # Clear spatial index and other variables
        routes_index = None
        cable_buffer = None

        violation_count = len(violations)
        message = (
            f"Found {violation_count} facade cables with underground segments over {max_length}m."
            if violation_count > 0
            else "No violations found."
        )

        result = self._create_result(
            "DISTRIBUTION_008", description, violations, message
        )
        self.violations.extend(violations)

        return result

    def validate_dp_placement(self):
        """
        Validates that Distribution Points are not located within Drop Clusters.
        """
        print("Validating DP placement in drop clusters...")
        
        # Get required layers
        dp_layer = get_layer_by_name("Distribution Points")
        drop_cluster_layer = get_layer_by_name("Drop Clusters")
        
        if not dp_layer:
            return self._create_error_result(
                "DISTRIBUTION_009", "DP placement validation", "Distribution Points layer not found."
            )
        
        if not drop_cluster_layer:
            return self._create_error_result(
                "DISTRIBUTION_009", "DP placement validation", "Drop Clusters layer not found."
            )
        
        # Create spatial index for drop clusters
        cluster_index = QgsSpatialIndex(drop_cluster_layer.getFeatures())
        violations = []
        
        # Check each distribution point
        for dp_feature in dp_layer.getFeatures():
            dp_geom = dp_feature.geometry()
            
            if not dp_geom or dp_geom.isEmpty():
                continue
            
            # Check if this DP is inside any drop cluster
            candidate_cluster_ids = cluster_index.intersects(dp_geom.boundingBox())
            for cluster_id in candidate_cluster_ids:
                cluster_feature = drop_cluster_layer.getFeature(cluster_id)
                if dp_geom.within(cluster_feature.geometry()):
                    dp_id = dp_feature.id()
                    violation_info = {
                        "dp_id": dp_id,
                        "layer_name": "Distribution Points",
                        "geometry": dp_geom,
                        "violation_type": "dp_inside_cluster",
                        "violation_reason": f"Distribution Point (ID: {dp_id}) is located inside a Drop Cluster."
                    }
                    violations.append(violation_info)
                    break
        
        description = "Distribution Point should not be inside a drop cluster"
        violation_count = len(violations)
        if violation_count > 0:
            message = f"Found {violation_count} distribution points inside drop clusters."
        else:
            message = "No violations found."
        
        result = self._create_result("DISTRIBUTION_009", description, violations, message)
        self.violations.extend(violations)
        return result

    def validate_dp_private_domain(self):
        """
        Validates that Distribution Points are not located on private land.
        Checks Distribution Points that intersect with private domain layers.
        """
        print("Validating DP placement in private domain...")
        
        # Get required layers
        dp_layer = get_layer_by_name("Distribution Points")
        private_domain_layer = get_layer_by_name("GRB - ADP - administratief perceel")
        
        if not dp_layer:
            return self._create_error_result(
                "DISTRIBUTION_010", "Distribution Points layer not found.",""
            )

        if not private_domain_layer:
            return self._create_error_result(
                "DISTRIBUTION_010", "Private Domain (ADP) layer not found.",""
            )
        
        # Create spatial index for private domain - JUST LIKE THE FIRST FUNCTION
        domain_index = QgsSpatialIndex(private_domain_layer.getFeatures())
        violations = []
        
        # Check each distribution point
        for dp_feature in dp_layer.getFeatures():
            dp_geom = dp_feature.geometry()
            
            if not dp_geom or dp_geom.isEmpty():
                continue
            
            # Check if this DP intersects with any private domain
            candidate_domain_ids = domain_index.intersects(dp_geom.boundingBox())
            
            for domain_id in candidate_domain_ids:
                domain_feature = private_domain_layer.getFeature(domain_id)
                domain_geom = domain_feature.geometry()
                
                if not domain_geom or domain_geom.isEmpty():
                    continue
                
                # Check if DP is within the domain (using within instead of intersects)
                if dp_geom.within(domain_geom):
                    # Get DP identifier
                    if "DP_ID" in dp_feature.fields().names():
                        dp_id = dp_feature["DP_ID"]
                    elif "IDENTIFIER" in dp_feature.fields().names():
                        dp_id = dp_feature["IDENTIFIER"]
                    else:
                        dp_id = dp_feature.id()
                    
                    violation_info = {
                        "violation_type": "dp_in_private_domain",
                        "dp_id": dp_id,
                        "layer_name": "Distribution Points",
                        "geometry": dp_geom,
                        "violation_reason": f"Distribution Point (ID: {dp_id}) is located in private domain."
                    }
                    violations.append(violation_info)
                    break  # Only report once per DP
        
        description = "Distribution Point should not be in private domain"
        violation_count = len(violations)
        if violation_count > 0:
            message = f"Found {violation_count} distribution points in private domain."
        else:
            message = "No violations found."
        
        result = self._create_result("DISTRIBUTION_010", description, violations, message)
        self.violations.extend(violations)
        return result  
    def validate_mini_dp_on_facade(self):
        """
        Validates that Mini-DPs have underground distribution cables and buried possible routes.
        Mini-DPs should only be used when both the distribution cable is underground 
        and the possible routes are buried.
        """
        print("Validating mini-DP on facade...")
        
        # Get required layers
        access_structures_layer = get_layer_by_name("Access Structures")
        dist_cables_layer = get_layer_by_name("Distribution Cables")
        possible_routes_layer = get_layer_by_name("Possible Routes")
        
        if not access_structures_layer:
            return self._create_error_result(
                "DISTRIBUTION_011", "Mini-DP validation", "Access Structures layer not found."
            )
        
        if not dist_cables_layer:
            return self._create_error_result(
                "DISTRIBUTION_011", "Mini-DP validation", "Distribution Cables layer not found."
            )
        
        if not possible_routes_layer:
            return self._create_error_result(
                "DISTRIBUTION_011", "Mini-DP validation", "Possible trench routes layer not found."
            )
        
        # Check if required fields exist
        if "IDENTIFIER" not in access_structures_layer.fields().names():
            return self._create_error_result(
                "DISTRIBUTION_011", "Mini-DP validation", "Access Structures layer missing IDENTIFIER field."
            )
        
        if "TYPE" not in dist_cables_layer.fields().names():
            return self._create_error_result(
                "DISTRIBUTION_011", "Mini-DP validation", "Distribution Cables layer missing TYPE field."
            )
        
        if "TYPE" not in possible_routes_layer.fields().names():
            return self._create_error_result(
                "DISTRIBUTION_011", "Mini-DP validation", "Possible trench routes layer missing TYPE field."
            )
        
        violations = []
        
        # Build spatial indexes for efficient lookups
        cables_index = QgsSpatialIndex(dist_cables_layer.getFeatures())
        routes_index = QgsSpatialIndex(possible_routes_layer.getFeatures())
        
        # Find all Mini-DPs in Access Structures
        for access_feature in access_structures_layer.getFeatures():
            identifier = access_feature["IDENTIFIER"] if "IDENTIFIER" in access_feature.fields().names() else None
            
            # Check if this is a Mini-DP
            if not identifier or "mini" not in str(identifier).lower():
                continue
            
            mini_dp_geom = access_feature.geometry()
            if not mini_dp_geom or mini_dp_geom.isEmpty():
                continue
            
            mini_dp_id = access_feature.id()
            
            # Find ALL distribution cables that intersect with this mini-DP
            candidate_cable_ids = cables_index.intersects(mini_dp_geom.boundingBox())
            
            # We need to find AT LEAST ONE valid configuration:
            # 1. Cable is underground AND intersects Mini-DP
            # 2. Route is buried AND intersects both Mini-DP AND that specific cable
            valid_configuration_found = False
            
            for cable_id in candidate_cable_ids:
                if valid_configuration_found:
                    break  # Stop checking once we find one valid configuration
                    
                dist_cable = dist_cables_layer.getFeature(cable_id)
                cable_geom = dist_cable.geometry()
                cable_type = dist_cable["TYPE"] if "TYPE" in dist_cable.fields().names() else None
                
                if not cable_geom or cable_geom.isEmpty():
                    continue
                
                # Check if cable actually intersects mini-DP (not just bounding box)
                if not cable_geom.intersects(mini_dp_geom):
                    continue
                
                # Check if cable is underground
                is_cable_underground = (
                    cable_type and isinstance(cable_type, str) and "underground" in cable_type.lower()
                )
                
                if not is_cable_underground:
                    continue  # Skip this cable, it's not underground
                
                # Now find routes that might work with this cable
                candidate_route_ids = routes_index.intersects(mini_dp_geom.boundingBox())
                
                for route_id in candidate_route_ids:
                    route_feature = possible_routes_layer.getFeature(route_id)
                    route_geom = route_feature.geometry()
                    route_type = route_feature["TYPE"] if "TYPE" in route_feature.fields().names() else None
                    
                    if not route_geom or route_geom.isEmpty():
                        continue
                    
                    # CRITICAL: Route must intersect BOTH the Mini-DP AND the specific cable
                    if not route_geom.intersects(mini_dp_geom) or not route_geom.intersects(cable_geom):
                        continue
                    
                    # Check if route is buried
                    is_route_buried = (
                        route_type and isinstance(route_type, str) and "buried" in route_type.lower()
                    )
                    
                    if is_route_buried:
                        # Found a valid configuration! This Mini-DP is OK
                        valid_configuration_found = True
                        break  # Break out of route loop
                
                if valid_configuration_found:
                    break  # Break out of cable loop
            
            # If we didn't find ANY valid configuration, flag as violation
            if not valid_configuration_found:
                # Determine why it failed for better error message
                cable_count = 0
                underground_cable_count = 0
                route_count = 0
                buried_route_count = 0
                
                # Count for diagnostic purposes
                for cable_id in candidate_cable_ids:
                    dist_cable = dist_cables_layer.getFeature(cable_id)
                    cable_geom = dist_cable.geometry()
                    cable_type = dist_cable["TYPE"] if "TYPE" in dist_cable.fields().names() else None
                    
                    if cable_geom and cable_geom.intersects(mini_dp_geom):
                        cable_count += 1
                        if cable_type and isinstance(cable_type, str) and "underground" in cable_type.lower():
                            underground_cable_count += 1
                
                for route_id in routes_index.intersects(mini_dp_geom.boundingBox()):
                    route_feature = possible_routes_layer.getFeature(route_id)
                    route_geom = route_feature.geometry()
                    
                    if route_geom and route_geom.intersects(mini_dp_geom):
                        route_count += 1
                        route_type = route_feature["TYPE"] if "TYPE" in route_feature.fields().names() else None
                        if route_type and isinstance(route_type, str) and "buried" in route_type.lower():
                            buried_route_count += 1
                
                violation_info = {
                    "mini_dp_id": mini_dp_id,
                    "layer_name": "Access Structures",
                    "geometry": mini_dp_geom,
                    "violation_type": "mini_dp_on_facade",
                    "violation_reason": f"Mini-DP (ID: {mini_dp_id}) is on Facade. "

                }
                violations.append(violation_info)
        
        description = "Mini-DP should only be on underground cables with buried routes"
        violation_count = len(violations)
        if violation_count > 0:
            message = f"Found {violation_count} mini-DPs on facade without proper underground/buried configuration."
        else:
            message = "No violations found."
        
        result = self._create_result("DISTRIBUTION_011", description, violations, message)
        self.violations.extend(violations)
        return result

    def validate_cable_split(self, tolerance=1.0):
        """
        Validates that Distribution Cables are not 'split' (i.e., have a valid starting point).

        Rule: A distribution cable must have a DP or PDP as a starting point.
        A cable is considered 'split' if neither of its endpoints is spatially
        connected (within tolerance) to a DP or PDP.

        Args:
            tolerance: Max distance in meters between a cable endpoint and a DP/PDP (default: 1.0)
        """
        print("Validating distribution cable split (starting points)...")
        RULE_ID = "DISTRIBUTION_012"
        description = "Distribution cables must start from a DP or PDP"

        dist_cables_layer = get_layer_by_name("Distribution Cables")
        dp_layer = get_layer_by_name("Distribution Points")
        pdp_layer = get_layer_by_name("Primary Distribution Points")

        if not dist_cables_layer:
            return self._create_error_result(
                RULE_ID, description, "Distribution Cables layer not found."
            )
        if not dp_layer:
            return self._create_error_result(
                RULE_ID, description, "Distribution Points layer not found."
            )
        if not pdp_layer:
            return self._create_error_result(
                RULE_ID, description, "Primary Distribution Points layer not found."
            )

        violations = []

        # Build spatial indexes for efficient proximity checks
        dp_index = QgsSpatialIndex(dp_layer.getFeatures())
        pdp_index = QgsSpatialIndex(pdp_layer.getFeatures())

        def endpoint_near_layer(point_geom, spatial_index, layer):
            """Return True if point_geom is within tolerance of any feature in layer."""
            buf = point_geom.buffer(tolerance, 5)
            for fid in spatial_index.intersects(buf.boundingBox()):
                if layer.getFeature(fid).geometry().intersects(buf):
                    return True
            return False

        def get_cable_endpoints(cable_geom):
            """Return (start_geom, end_geom) for a line geometry, or (None, None) on failure."""
            try:
                if cable_geom.isMultipart():
                    parts = cable_geom.asMultiPolyline()
                    if not parts or not parts[0]:
                        return None, None
                    start_pt = parts[0][0]
                    end_pt = parts[-1][-1]
                else:
                    polyline = cable_geom.asPolyline()
                    if not polyline:
                        return None, None
                    start_pt = polyline[0]
                    end_pt = polyline[-1]
                return (
                    QgsGeometry.fromPointXY(start_pt),
                    QgsGeometry.fromPointXY(end_pt),
                )
            except Exception:
                return None, None

        for cable in dist_cables_layer.getFeatures():
            cable_geom = cable.geometry() 
            if not cable_geom or cable_geom.isEmpty():
                continue
            cable_id = (
                cable["CABLE_ID"]
                if "CABLE_ID" in cable.fields().names()
                else cable.id()
            )
            start_geom, end_geom = get_cable_endpoints(cable_geom)
            if start_geom is None:
                continue  # Cannot assess — skip
            has_valid_start = any(
                endpoint_near_layer(ep, dp_index, dp_layer)
                or endpoint_near_layer(ep, pdp_index, pdp_layer)
                for ep in (start_geom, end_geom)
            )
            if not has_valid_start:
                violations.append(
                    {
                        "cable_id": cable_id,
                        "cable_layer": "Distribution Cables",
                        "geometry": cable_geom,
                        "violation_type": "cable_split",
                        "violation_reason": (
                            f"Distribution cable {cable_id} does not start from "
                            f"a DP or PDP (split cable)."
                        ),
                    }
                )

        violation_count = len(violations)
        message = (
            f"Found {violation_count} split distribution cables without a valid starting point."
            if violation_count > 0
            else "No violations found."
        )
        result = self._create_result(RULE_ID, description, violations, message)
        self.violations.extend(violations)
        return result

    def validate_distribution_rules(self):
        """
        Run all distribution validation rules
        """
        self.violations = []
        print("Running distribution validation...")
        results = []
        results.append(self.validate_max_cables_leaving_dp(max_cables=5))
        results.append(self.validate_facade_cable_max_length(max_length=500.0))
        results.append(self.validate_aerial_cable_poc_limit(max_pocs=22, max_drops=4))
        results.append(self.validate_parallel_cable_poc_connection())
        results.append(self.validate_facade_underground_length())
        results.append(self.validate_parallel_aerial_cable_limit())
        results.append(self.validate_underground_drop_consistency())
        results.append(self.validate_facade_total_underground_length())
        #results.append(self.validate_dp_private_domain())
        results.append(self.validate_dp_placement())
        results.append(self.validate_mini_dp_on_facade())
        results.append(self.validate_cable_split())
        return results

    def _create_result(self, rule_id, description, violations, message):
        failed_ids = []
        for v in violations:
            if v.get("dp_id"):
                failed_ids.append(f"DP_{v.get('dp_id')}")
            elif v.get("mini_dp_id"):
                failed_ids.append(f"MiniDP_{v.get('mini_dp_id')}")
            elif v.get("cable_id"):
                failed_ids.append(f"Cable_{v.get('cable_id')}")
            elif v.get("poc_id"):
                failed_ids.append(f"POC_{v.get('poc_id')}")
            elif v.get("cable_group"):
                failed_ids.append(f"Group_{v.get('cable_group')}")
            elif v.get("drop_cable_id"):
                failed_ids.append(f"Drop_{v.get('drop_cable_id')}")
        failed_features_str = ", ".join(failed_ids)

        return {
            "rule_id": rule_id,
            "Description": description,
            "status": "PASS" if not violations else "FAIL",
            "violation_count": len(violations),
            "failed_features": failed_features_str,
            "message": message,
        }

    def _create_error_result(self, rule_id, description, message):
        return {
            "rule_id": rule_id,
            "Description": description,
            "status": "ERROR",
            "violation_count": 0,
            "failed_features": "",
            "message": message,
        }
