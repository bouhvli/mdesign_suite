from qgis.core import (  # type: ignore
    QgsSpatialIndex,
    QgsGeometry,
    QgsPointXY,
)
from ...utils.layer_loader import get_layer_by_name, get_layer_from_API
from .trenches_helper import (
    get_line_points,
    calculate_vertex_angle,
    get_direction_at_point,
    turn_direction,
    detect_u_shapes,
)
import math


class Trenches:
    def __init__(self):
        self.trenches_violations = []
        self.violations = []


    def validate_subtype_exists(self):
        """
        Validate that all features have SUBTYPE values from the known subtypes list

        Rule: SUBTYPE must exist in the known subtypes list

        Args:
            None - uses SUBTYPE attribute validation
        """
        print("Validating SUBTYPE values against known subtypes list...")

        # Known valid SUBTYPE values
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
            'Dummy'
        ]

        # Get the layer
        possible_trenches_layer = get_layer_by_name('Possible trench routes')

        if not possible_trenches_layer:
            return {
                'rule_id': 'SUBTYPE_01',
                'Description': 'SUBTYPE validation - check if subtypes exist in known list',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Possible trench routes layer not found'
            }

        if 'SUBTYPE' not in possible_trenches_layer.fields().names():
            return {
                'rule_id': 'SUBTYPE_01',
                'Description': 'SUBTYPE validation - check if subtypes exist in known list',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Possible trench routes layer missing SUBTYPE field'
            }

        violations = []

        # Check each feature for invalid SUBTYPE
        for feature in possible_trenches_layer.getFeatures():
            subtype_value = feature['SUBTYPE']

            # Skip None/empty values
            if not subtype_value:
                continue

            # Convert to string and strip whitespace for comparison
            subtype_str = str(subtype_value).strip()

            # Check if subtype exists in valid list
            if subtype_str not in VALID_SUBTYPES:
                feature_id = feature.id()
                geometry = feature.geometry()

                # Create violation info with field names that match violation_details.py expectations
                violation_info = {
                    'feature_id': feature_id,
                    'layer_name': 'Possible trench routes',  # Add layer name
                    'subtype': subtype_str,  # Use 'subtype' instead of 'subtype_value'
                    'geometry': geometry,
                    'violation_type': 'invalid_subtype',  # This matches the violation_details.py check
                    'rule_id': 'SUBTYPE_01',  # Add rule_id to violation info
                    'violation_reason': f"SUBTYPE '{subtype_str}' is not in the known subtypes list"
                }
                violations.append(violation_info)

                # print(f"Violation: Feature {feature_id} has invalid SUBTYPE: '{subtype_str}'")

        result = {
            'rule_id': 'SUBTYPE_01',
            'Description': 'SUBTYPE validation - check if subtypes exist in known list',
            'status': 'PASS' if not violations else 'FAIL',
            'violation_count': len(violations),
            'failed_features': ', '.join([f"Feature_{v['feature_id']}" for v in violations]),
            'message': f'Found {len(violations)} features with invalid SUBTYPE values'
        }

        self.trenches_violations.extend(violations)
        return result

    def validate_trenches_not_well_placed(self, crossing_tolerance=5.0):
        """
        Rule TRENCH_001: Trenches not well-placed

        Distribution cables should be on the sidewalk ('GRB - WGO - wegopdeling (clipped)')
        If a distribution cable does NOT intersect the sidewalk layer, it's a violation.

        Exception: If the cable leaves the sidewalk to go through a crossing
        (IN_Crossings layer), that exit is expected and not counted.
        """
        print("Validating trenches placement...")

        distribution_cables_layer = get_layer_by_name("Distribution Cables")
        sidewalk_layer = get_layer_by_name('GRB - WGO - wegopdeling (clipped)')

        if not sidewalk_layer:
            sidewalk_layer = get_layer_from_API()

        if not distribution_cables_layer:
            return {
                'rule_id': 'TRENCH_001',
                'Description': 'Trenches placement validation',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Distribution Cables layer not found'
            }

        # Load crossings layer for exception checking
        crossings_layer = get_layer_by_name("IN_Crossings")
        crossings_index = None
        crossings_features = {}
        if crossings_layer and crossings_layer.featureCount() > 0:
            crossings_index = QgsSpatialIndex(crossings_layer.getFeatures())
            crossings_features = {f.id(): f for f in crossings_layer.getFeatures()}

        violations = []

        if sidewalk_layer and sidewalk_layer.featureCount() > 0:
            sidewalk_index = QgsSpatialIndex(sidewalk_layer.getFeatures())
            sidewalk_features = {f.id(): f for f in sidewalk_layer.getFeatures()}

            # Determine if sidewalk layer is polygon or line
            is_polygon = sidewalk_layer.geometryType() == 2  # QgsWkbTypes.PolygonGeometry

            for cable in distribution_cables_layer.getFeatures():
                cable_geom = cable.geometry()
                if not cable_geom or cable_geom.isEmpty():
                    continue

                cable_id = cable["CABLE_ID"] if "CABLE_ID" in cable.fields().names() else cable.id()
                candidate_ids = sidewalk_index.intersects(cable_geom.boundingBox())

                # Collect non-crossing gap geometries for highlighting
                violation_geometries = []

                if is_polygon:
                    # Polygon sidewalk: merge nearby polygons, then check if
                    # the cable intersection produces multiple separate segments
                    # (cable left and re-entered the sidewalk area).
                    merged_sidewalk = QgsGeometry()
                    for sid in candidate_ids:
                        sidewalk_feature = sidewalk_features.get(sid)
                        if not sidewalk_feature:
                            continue
                        sidewalk_geom = sidewalk_feature.geometry()
                        if sidewalk_geom.isEmpty():
                            continue
                        if merged_sidewalk.isEmpty():
                            merged_sidewalk = sidewalk_geom
                        else:
                            merged_sidewalk = merged_sidewalk.combine(sidewalk_geom)

                    if merged_sidewalk.isEmpty():
                        continue
                    if not cable_geom.intersects(merged_sidewalk):
                        continue

                    intersection = cable_geom.intersection(merged_sidewalk)
                    if intersection.isEmpty():
                        continue

                    parts = intersection.asGeometryCollection() if intersection.isMultipart() else [intersection]
                    significant_parts = [p for p in parts if p.length() > 1.0]

                    # Check gaps between significant parts: if a gap coincides
                    # with a crossing, that exit is expected and not counted.
                    if len(significant_parts) >= 2 and crossings_index is not None:
                        # Get the portion of the cable outside the sidewalk
                        outside = cable_geom.difference(merged_sidewalk)
                        if not outside.isEmpty():
                            gap_parts = outside.asGeometryCollection() if outside.isMultipart() else [outside]
                            crossing_gaps = 0
                            for gap in gap_parts:
                                if gap.isEmpty() or gap.length() < 0.5:
                                    continue
                                # Check if this gap overlaps with a crossing
                                gap_search = gap.buffer(crossing_tolerance, 5).boundingBox()
                                gap_candidates = crossings_index.intersects(gap_search)
                                is_crossing_gap = False
                                for cid in gap_candidates:
                                    crossing_feat = crossings_features.get(cid)
                                    if not crossing_feat:
                                        continue
                                    crossing_geom = crossing_feat.geometry()
                                    if crossing_geom and not crossing_geom.isEmpty():
                                        if gap.distance(crossing_geom) <= crossing_tolerance:
                                            crossing_gaps += 1
                                            is_crossing_gap = True
                                            break
                                if not is_crossing_gap:
                                    violation_geometries.append(gap)
                            # Each gap through a crossing accounts for one
                            # "legitimate" extra segment, so reduce count
                            crossing_count = len(significant_parts) - crossing_gaps
                        else:
                            crossing_count = len(significant_parts)
                    else:
                        crossing_count = len(significant_parts)
                        # All gaps are violations (no crossings layer)
                        if crossing_count >= 2:
                            outside = cable_geom.difference(merged_sidewalk)
                            if not outside.isEmpty():
                                gap_parts = outside.asGeometryCollection() if outside.isMultipart() else [outside]
                                for gap in gap_parts:
                                    if not gap.isEmpty() and gap.length() >= 0.5:
                                        violation_geometries.append(gap)
                else:
                    # Line sidewalk: check each sidewalk feature individually.
                    # At each crossing point, compare the angle between the
                    # sidewalk line and the cable. Only count crossings where
                    # the sidewalk runs roughly parallel to the cable (< 45°),
                    # meaning the cable is crossing an actual sidewalk edge.
                    # Perpendicular crossings are just boundary seams between
                    # adjacent sidewalk sections and should be ignored.
                    parallel_crossings = 0
                    for sid in candidate_ids:
                        sidewalk_feature = sidewalk_features.get(sid)
                        if not sidewalk_feature:
                            continue
                        sw_geom = sidewalk_feature.geometry()
                        if sw_geom.isEmpty() or not cable_geom.intersects(sw_geom):
                            continue

                        crossing = cable_geom.intersection(sw_geom)
                        if crossing.isEmpty():
                            continue

                        crossing_parts = crossing.asGeometryCollection() if crossing.isMultipart() else [crossing]
                        for cp in crossing_parts:
                            if cp.isEmpty():
                                continue
                            # Get the crossing point
                            cp_point = QgsPointXY(cp.asPoint()) if cp.type() == 0 else QgsPointXY(cp.centroid().asPoint())

                            # Get directions at the crossing point
                            cable_dir = get_direction_at_point(cable_geom, cp_point)
                            sw_dir = get_direction_at_point(sw_geom, cp_point)
                            if cable_dir is None or sw_dir is None:
                                continue

                            # Calculate acute angle between directions
                            dot = cable_dir.x() * sw_dir.x() + cable_dir.y() * sw_dir.y()
                            dot = max(-1.0, min(1.0, dot))
                            angle = math.degrees(math.acos(abs(dot)))

                            # Parallel crossing (< 45°) = actual sidewalk edge
                            if angle < 45.0:
                                # Exception: skip if this point is near an IN_Crossings feature
                                if crossings_index is not None:
                                    pt_geom = QgsGeometry.fromPointXY(cp_point)
                                    search_rect = pt_geom.buffer(crossing_tolerance, 5).boundingBox()
                                    near_crossing = False
                                    for cid in crossings_index.intersects(search_rect):
                                        crossing_feat = crossings_features.get(cid)
                                        if not crossing_feat:
                                            continue
                                        crossing_geom = crossing_feat.geometry()
                                        if crossing_geom and not crossing_geom.isEmpty():
                                            if pt_geom.distance(crossing_geom) <= crossing_tolerance:
                                                near_crossing = True
                                                break
                                    if near_crossing:
                                        continue
                                parallel_crossings += 1
                                violation_geometries.append(
                                    QgsGeometry.fromPointXY(cp_point)
                                )

                    crossing_count = parallel_crossings

                threshold = 2 if is_polygon else 4

                if crossing_count >= threshold:
                    # Merge all violation area geometries into one highlight
                    if violation_geometries:
                        combined = violation_geometries[0]
                        for vg in violation_geometries[1:]:
                            combined = combined.combine(vg)
                        highlight_geom = combined
                    else:
                        highlight_geom = cable_geom

                    violations.append({
                        'feature_id': cable.id(),
                        'cable_id': cable_id,
                        'intersection_count': crossing_count,
                        'geometry': highlight_geom,
                        'violation_type': 'distribution_cable_not_on_sidewalk',
                        'violation_reason': f"Distribution cable (ID: {cable_id}) leaves and re-enters "
                                            f"the sidewalk ({crossing_count} parallel crossings detected)"
                    })

        violation_count = len(violations)
        result = {
            'rule_id': 'TRENCH_001',
            'Description': 'Trenches not well-placed - distribution cables should be on sidewalk',
            'status': 'PASS' if not violations else 'FAIL',
            'violation_count': violation_count,
            'failed_features': ', '.join([f"Feature_{v['feature_id']}" for v in violations]),
            'message': f'Found {violation_count} trenches placement violations'
                       if violations else 'All trenches are well-placed'
        }

        self.trenches_violations.extend(violations)
        return result

    def validate_trenching_angles_curved(self, min_angle=140.0, crossing_tolerance=3.0,
                                         point_tolerance=2.0):
        """
        Rule TRENCH_002: Trenching angles have to be curved

        Checks that vertex angles in distribution cable geometries are smooth (not sharp).
        A straight line has 180 degree angles at vertices. Sharp turns have smaller angles.
        Angles below min_angle are flagged as violations.

        Exceptions (sharp angle is NOT flagged if):
        - The vertex is near a crossing (IN_Crossings layer)
        - The vertex is on top of a Drop Point or Distribution Point
        - The sharp angle is part of a soft Z/S-shape (two consecutive opposite turns)
        """
        print("Validating trenching angles...")

        distribution_cables_layer = get_layer_by_name("Distribution Cables")

        if not distribution_cables_layer:
            return {
                'rule_id': 'TRENCH_002',
                'Description': 'Trenching angles should be curved',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Distribution Cables layer not found'
            }

        if distribution_cables_layer.featureCount() == 0:
            return {
                'rule_id': 'TRENCH_002',
                'Description': f'Trenching angles should be curved (minimum {min_angle} degrees)',
                'status': 'PASS',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Distribution Cables layer has no features - validation skipped.'
            }

        # Load exception layers and build spatial indexes
        crossings_layer = get_layer_by_name("IN_Crossings")
        drop_points_layer = get_layer_by_name("Drop Points")
        distribution_points_layer = get_layer_by_name("Distribution Points")

        crossings_index = None
        crossings_features = {}
        if crossings_layer and crossings_layer.featureCount() > 0:
            crossings_index = QgsSpatialIndex(crossings_layer.getFeatures())
            crossings_features = {f.id(): f for f in crossings_layer.getFeatures()}

        dp_index = None
        if drop_points_layer and drop_points_layer.featureCount() > 0:
            dp_index = QgsSpatialIndex(drop_points_layer.getFeatures())

        dist_pt_index = None
        if distribution_points_layer and distribution_points_layer.featureCount() > 0:
            dist_pt_index = QgsSpatialIndex(distribution_points_layer.getFeatures())

        violations = []
        has_type_field = "TYPE" in distribution_cables_layer.fields().names()

        for cable in distribution_cables_layer.getFeatures():
            # Facade cables are allowed to have sharp angles — skip them
            if has_type_field:
                cable_type = str(cable["TYPE"]).upper().strip()
                if "FACADE" in cable_type:
                    continue

            cable_geom = cable.geometry()
            if not cable_geom or cable_geom.isEmpty():
                continue

            points = get_line_points(cable_geom)
            if len(points) < 3:
                continue  # Need at least 3 points to form an angle

            cable_id = cable["CABLE_ID"] if "CABLE_ID" in cable.fields().names() else cable.id()

            # Pre-compute angles and turn directions for Z-shape detection
            angles = []
            turn_dirs = []
            for i in range(1, len(points) - 1):
                angle = calculate_vertex_angle(points[i - 1], points[i], points[i + 1])
                turn_dir = turn_direction(points[i - 1], points[i], points[i + 1])
                angles.append(angle)
                turn_dirs.append(turn_dir)

            # Identify vertices that are part of a soft Z/S-shape:
            # Two consecutive sharp angles with opposite turn directions
            z_shape_vertices = set()
            for j in range(len(angles) - 1):
                a1 = angles[j]
                a2 = angles[j + 1]
                if a1 is None or a2 is None:
                    continue
                if a1 < min_angle and a2 < min_angle:
                    # Opposite turn directions = Z/S-shape
                    if turn_dirs[j] != 0 and turn_dirs[j + 1] != 0:
                        if turn_dirs[j] != turn_dirs[j + 1]:
                            # vertex indices in the points array are j+1 and j+2
                            z_shape_vertices.add(j + 1)
                            z_shape_vertices.add(j + 2)

            for i in range(1, len(points) - 1):
                angle_idx = i - 1  # index into the angles list
                angle = angles[angle_idx]
                if angle is None or angle >= min_angle:
                    continue

                vertex_point = points[i]
                point_geom = QgsGeometry.fromPointXY(vertex_point)

                # Exception 1: vertex is part of a soft Z/S-shape
                if i in z_shape_vertices:
                    continue

                # Exception 2: vertex is near a crossing
                if crossings_index is not None:
                    search_rect = point_geom.buffer(crossing_tolerance, 5).boundingBox()
                    candidate_ids = crossings_index.intersects(search_rect)
                    near_crossing = False
                    for cid in candidate_ids:
                        crossing_feat = crossings_features.get(cid)
                        if not crossing_feat:
                            continue
                        crossing_geom = crossing_feat.geometry()
                        if crossing_geom and not crossing_geom.isEmpty():
                            if point_geom.distance(crossing_geom) <= crossing_tolerance:
                                near_crossing = True
                                break
                    if near_crossing:
                        continue

                # Exception 3: vertex is on top of a Drop Point
                if dp_index is not None:
                    search_rect = point_geom.buffer(point_tolerance, 5).boundingBox()
                    if dp_index.intersects(search_rect):
                        continue

                # Exception 4: vertex is on top of a Distribution Point
                if dist_pt_index is not None:
                    search_rect = point_geom.buffer(point_tolerance, 5).boundingBox()
                    if dist_pt_index.intersects(search_rect):
                        continue

                # No exception applies — flag this sharp angle
                violations.append({
                    'feature_id': cable.id(),
                    'cable_id': cable_id,
                    'geometry': point_geom,
                    'angle': angle,
                    'violation_type': 'sharp_trenching_angle',
                    'violation_reason': f"Distribution cable (ID: {cable_id}) has a sharp angle "
                                        f"of {angle:.1f} degrees at vertex {i} "
                                        f"(minimum required: {min_angle} degrees)"
                })

        violation_count = len(violations)
        result = {
            'rule_id': 'TRENCH_002',
            'Description': f'Trenching angles should be curved (minimum {min_angle} degrees)',
            'status': 'PASS' if not violations else 'FAIL',
            'violation_count': violation_count,
            'failed_features': ', '.join([f"Feature_{v['feature_id']}" for v in violations]),
            'message': f'Found {violation_count} sharp trenching angles'
                       if violations else 'All trenching angles are properly curved'
        }

        self.trenches_violations.extend(violations)
        return result

    def validate_missing_trenches(self):
        """
        Rule TRENCH_003: Missing trenches

        If drop cables exist but don't intersect with any distribution cable,
        it means the distribution cable (trench) is missing.
        The relationship is spatial intersection.
        """
        print("Validating missing trenches...")

        drop_cables_layer = get_layer_by_name("Drop Cables")
        distribution_cables_layer = get_layer_by_name("Distribution Cables")

        if not drop_cables_layer:
            return {
                'rule_id': 'TRENCH_003',
                'Description': 'Missing trenches - drop cables without distribution cable',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Drop Cables layer not found'
            }

        if not distribution_cables_layer:
            return {
                'rule_id': 'TRENCH_003',
                'Description': 'Missing trenches - drop cables without distribution cable',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Distribution Cables layer not found'
            }

        if drop_cables_layer.featureCount() == 0:
            return {
                'rule_id': 'TRENCH_003',
                'Description': 'Missing trenches - drop cables without distribution cable',
                'status': 'PASS',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Drop Cables layer has no features - validation skipped.'
            }

        violations = []

        # Build spatial index for distribution cables
        dist_index = QgsSpatialIndex(distribution_cables_layer.getFeatures())
        dist_features = {f.id(): f for f in distribution_cables_layer.getFeatures()}

        for drop_cable in drop_cables_layer.getFeatures():
            drop_geom = drop_cable.geometry()
            if not drop_geom or drop_geom.isEmpty():
                continue

            # Use a small buffer to account for near-misses
            search_geom = drop_geom.buffer(0.5, 5)
            candidate_ids = dist_index.intersects(search_geom.boundingBox())

            has_intersection = False
            for did in candidate_ids:
                dist_feature = dist_features.get(did)
                if not dist_feature:
                    continue
                dist_geom = dist_feature.geometry()
                if not dist_geom or dist_geom.isEmpty():
                    continue
                if drop_geom.intersects(dist_geom):
                    has_intersection = True
                    break

            if not has_intersection:
                drop_id = drop_cable["CABLE_ID"] if "CABLE_ID" in drop_cable.fields().names() else drop_cable.id()
                violations.append({
                    'feature_id': drop_cable.id(),
                    'cable_id': drop_id,
                    'geometry': drop_geom,
                    'violation_type': 'missing_trench',
                    'violation_reason': f"Drop cable (ID: {drop_id}) has no intersection "
                                        f"with any distribution cable - missing trench"
                })

        violation_count = len(violations)
        result = {
            'rule_id': 'TRENCH_003',
            'Description': 'Missing trenches - drop cables should intersect with distribution cables',
            'status': 'PASS' if not violations else 'FAIL',
            'violation_count': violation_count,
            'failed_features': ', '.join([f"Feature_{v['feature_id']}" for v in violations]),
            'message': f'Found {violation_count} drop cables without distribution cable (missing trenches)'
                    if violations else 'All drop cables have corresponding distribution cables'
        }

        self.trenches_violations.extend(violations)
        return result

    def validate_u_shape_detours(self, min_detour_ratio=2.5, crossing_search_radius=25.0,
                                 dp_tolerance=5.0):
        """
        Rule TRENCH_004: U-Shape Detour & Cable Overextension

        Two sub-checks:
        a) Detects distribution cables that make U-shape detours (two ~90-degree turns
           with a short crossing segment) when a nearby crossing from IN_Crossings exists.
        b) Detects distribution cables that extend past their last connected drop point.
           The cable start is always at a Distribution Point, so the segment from cable
           start to the first drop point is expected. If no Distribution Point is found
           at the cable start, the head extension is also flagged.

        Layers:
        - Distribution Cables (field TOP_AGG_ID links to drop points)
        - Drop Points (field ID_DISTRIB links to cable)
        - Distribution Points (to verify cable start)
        - IN_Crossings (line features for existing crossings)
        """
        print("Validating U-shape detours and cable overextension...")

        distribution_cables_layer = get_layer_by_name("Distribution Cables")
        drop_points_layer = get_layer_by_name("Drop Points")
        crossings_layer = get_layer_by_name("IN_Crossings")
        distribution_points_layer = get_layer_by_name("Distribution Points")

        if not distribution_cables_layer:
            return {
                'rule_id': 'TRENCH_004',
                'Description': 'U-shape detour and cable overextension detection',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Distribution Cables layer not found'
            }

        if not drop_points_layer:
            return {
                'rule_id': 'TRENCH_004',
                'Description': 'U-shape detour and cable overextension detection',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Drop Points layer not found'
            }

        violations = []

        # Build crossings spatial index (may be None if layer missing)
        crossings_features = {}
        crossings_index = None
        if crossings_layer and crossings_layer.featureCount() > 0:
            crossings_index = QgsSpatialIndex(crossings_layer.getFeatures())
            crossings_features = {f.id(): f for f in crossings_layer.getFeatures()}

        # Build Distribution Points spatial index to verify cable start
        dist_pt_index = None
        if distribution_points_layer and distribution_points_layer.featureCount() > 0:
            dist_pt_index = QgsSpatialIndex(distribution_points_layer.getFeatures())

        # Build mapping: TOP_AGG_ID -> list of drop point features
        has_link_cable = "TOP_AGG_ID" in distribution_cables_layer.fields().names()
        has_link_drop = "ID_DISTRIB" in drop_points_layer.fields().names()

        if not has_link_cable or not has_link_drop:
            return {
                'rule_id': 'TRENCH_004',
                'Description': 'U-shape detour and cable overextension detection',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Required link fields (TOP_AGG_ID / ID_DISTRIB) not found'
            }

        dp_by_link = {}
        for dp in drop_points_layer.getFeatures():
            link_val = dp["ID_DISTRIB"]
            if link_val is None or str(link_val).strip() == '':
                continue
            link_key = str(link_val).strip()
            if link_key not in dp_by_link:
                dp_by_link[link_key] = []
            dp_by_link[link_key].append(dp)

        # Process each distribution cable
        for cable in distribution_cables_layer.getFeatures():
            cable_geom = cable.geometry()
            if not cable_geom or cable_geom.isEmpty():
                continue

            cable_id = cable["CABLE_ID"] if "CABLE_ID" in cable.fields().names() else cable.id()
            top_agg_id = cable["TOP_AGG_ID"]
            if top_agg_id is None or str(top_agg_id).strip() == '':
                continue

            link_key = str(top_agg_id).strip()
            connected_dps = dp_by_link.get(link_key, [])
            if not connected_dps:
                continue

            cable_length = cable_geom.length()

            # Project each drop point onto the cable to get its position along the cable
            dp_positions = []
            for dp in connected_dps:
                dp_geom = dp.geometry()
                if not dp_geom or dp_geom.isEmpty():
                    continue
                pos = cable_geom.lineLocatePoint(dp_geom)
                dp_id = dp["ID"] if "ID" in dp.fields().names() else dp.id()
                dp_positions.append((pos, dp, dp_geom, dp_id))

            if not dp_positions:
                continue

            dp_positions.sort(key=lambda x: x[0])

            # --- Sub-check b: Cable overextension ---
            # Check if a Distribution Point exists near the cable start or end.
            # If DP is at the start → head extension is expected.
            # If DP is at the end → tail extension is expected (cable connects to DP).
            cable_points = get_line_points(cable_geom)
            has_dp_at_start = False
            has_dp_at_end = False
            if dist_pt_index is not None and cable_points:
                start_geom = QgsGeometry.fromPointXY(cable_points[0])
                search_rect = start_geom.buffer(dp_tolerance, 5).boundingBox()
                if dist_pt_index.intersects(search_rect):
                    has_dp_at_start = True

                end_geom = QgsGeometry.fromPointXY(cable_points[-1])
                search_rect = end_geom.buffer(dp_tolerance, 5).boundingBox()
                if dist_pt_index.intersects(search_rect):
                    has_dp_at_end = True

            # Tail overextension: cable extends past its last drop point
            # Exception: if the cable end connects to a Distribution Point,
            # the tail extension is expected and should not be flagged.
            last_dp_pos = dp_positions[-1][0]
            last_dp_id = dp_positions[-1][3]
            extension_length = cable_length - last_dp_pos

            if extension_length > 5.0 and not has_dp_at_end:
                # Build geometry for only the overextended tail portion
                tail_points = []
                last_dp_point = cable_geom.interpolate(last_dp_pos)
                if not last_dp_point.isEmpty():
                    tail_points.append(QgsPointXY(last_dp_point.asPoint()))
                for pt in cable_points:
                    pt_pos = cable_geom.lineLocatePoint(QgsGeometry.fromPointXY(pt))
                    if pt_pos > last_dp_pos:
                        tail_points.append(pt)
                if len(tail_points) >= 2:
                    tail_geom = QgsGeometry.fromPolylineXY(tail_points)
                else:
                    tail_geom = QgsGeometry.fromPointXY(tail_points[0]) if tail_points else cable_geom

                violations.append({
                    'feature_id': cable.id(),
                    'cable_id': cable_id,
                    'geometry': tail_geom,
                    'violation_type': 'cable_overextension',
                    'rule_id': 'TRENCH_004',
                    'extension_length': extension_length,
                    'last_dp_id': last_dp_id,
                    'violation_reason': (
                        f"Distribution cable (ID: {cable_id}) extends "
                        f"{extension_length:.1f}m past its last connected "
                        f"drop point (ID: {last_dp_id})"
                    )
                })

            # Head overextension: if no Distribution Point at cable start,
            # the segment before the first drop point is also a violation
            if not has_dp_at_start:
                first_dp_pos = dp_positions[0][0]
                first_dp_id = dp_positions[0][3]
                if first_dp_pos > 5.0:
                    # Build geometry for only the overextended head portion
                    head_points = []
                    for pt in cable_points:
                        pt_pos = cable_geom.lineLocatePoint(QgsGeometry.fromPointXY(pt))
                        if pt_pos < first_dp_pos:
                            head_points.append(pt)
                    first_dp_point = cable_geom.interpolate(first_dp_pos)
                    if not first_dp_point.isEmpty():
                        head_points.append(QgsPointXY(first_dp_point.asPoint()))
                    if len(head_points) >= 2:
                        head_geom = QgsGeometry.fromPolylineXY(head_points)
                    else:
                        head_geom = QgsGeometry.fromPointXY(head_points[0]) if head_points else cable_geom

                    violations.append({
                        'feature_id': cable.id(),
                        'cable_id': cable_id,
                        'geometry': head_geom,
                        'violation_type': 'cable_overextension',
                        'rule_id': 'TRENCH_004',
                        'extension_length': first_dp_pos,
                        'first_dp_id': first_dp_id,
                        'violation_reason': (
                            f"Distribution cable (ID: {cable_id}) extends "
                            f"{first_dp_pos:.1f}m before its first connected "
                            f"drop point (ID: {first_dp_id}) with no "
                            f"Distribution Point at cable start"
                        )
                    })

            # --- Sub-check a: U-shape detour ---
            if len(dp_positions) < 2:
                continue

            if crossings_index is None:
                continue

            u_shapes = detect_u_shapes(cable_geom)
            if not u_shapes:
                continue

            for u_shape in u_shapes:
                # Find the U-shape position along the cable
                entry_pos = cable_geom.lineLocatePoint(
                    QgsGeometry.fromPointXY(u_shape['entry_point'])
                )
                exit_pos = cable_geom.lineLocatePoint(
                    QgsGeometry.fromPointXY(u_shape['exit_point'])
                )
                u_start = min(entry_pos, exit_pos)
                u_end = max(entry_pos, exit_pos)

                # Find closest drop point before and after the U-shape
                dp_before = None
                dp_after = None

                for pos, dp, dp_geom, dp_id in dp_positions:
                    if pos <= u_start:
                        dp_before = (pos, dp, dp_geom, dp_id)
                    elif pos >= u_end and dp_after is None:
                        dp_after = (pos, dp, dp_geom, dp_id)
                        break

                if dp_before is None or dp_after is None:
                    continue

                # Detour ratio check
                cable_path_distance = abs(dp_after[0] - dp_before[0])
                straight_distance = dp_before[2].distance(dp_after[2])

                if straight_distance == 0:
                    continue

                detour_ratio = cable_path_distance / straight_distance
                if detour_ratio < min_detour_ratio:
                    continue

                # Check for nearby crossing
                search_geom = QgsGeometry.fromPointXY(u_shape['midpoint']).buffer(
                    crossing_search_radius, 5
                )
                candidate_ids = crossings_index.intersects(search_geom.boundingBox())

                has_nearby_crossing = False
                for cid in candidate_ids:
                    crossing_feat = crossings_features.get(cid)
                    if not crossing_feat:
                        continue
                    crossing_geom = crossing_feat.geometry()
                    if not crossing_geom or crossing_geom.isEmpty():
                        continue
                    dist = QgsGeometry.fromPointXY(u_shape['midpoint']).distance(crossing_geom)
                    if dist <= crossing_search_radius:
                        has_nearby_crossing = True
                        break

                if not has_nearby_crossing:
                    continue

                # Create violation geometry — line between entry and exit points
                u_line = QgsGeometry.fromPolylineXY([u_shape['entry_point'], u_shape['exit_point']])

                violations.append({
                    'feature_id': cable.id(),
                    'cable_id': cable_id,
                    'geometry': u_line,
                    'violation_type': 'u_shape_detour',
                    'rule_id': 'TRENCH_004',
                    'dp_before_id': dp_before[3],
                    'dp_after_id': dp_after[3],
                    'detour_ratio': detour_ratio,
                    'cross_segment_length': u_shape['cross_segment_length'],
                    'violation_reason': (
                        f"Distribution cable (ID: {cable_id}) has a U-shape detour "
                        f"between drop points {dp_before[3]} and {dp_after[3]}. "
                        f"Detour ratio: {detour_ratio:.1f}x "
                        f"(cable path vs. straight line). "
                        f"A crossing exists nearby."
                    )
                })

        violation_count = len(violations)
        result = {
            'rule_id': 'TRENCH_004',
            'Description': 'U-shape detour and cable overextension detection',
            'status': 'PASS' if not violations else 'FAIL',
            'violation_count': violation_count,
            'failed_features': ', '.join([f"Feature_{v['feature_id']}" for v in violations]),
            'message': (
                f'Found {violation_count} U-shape detour / overextension violations'
                if violations else 'No U-shape detours or cable overextensions detected'
            )
        }

        self.trenches_violations.extend(violations)
        return result

    def validate_trenches_rules(self, **kwargs):
        """
        Run all trench validation rules with optional parameters
        """
        self.violations.clear()
        print("Running all Trench validation rules...")

        results = []

        # Rule 1: Subtype validation
        results.append(self.validate_subtype_exists())

        # Rule 2: Trenches not well-placed
        results.append(self.validate_trenches_not_well_placed())

        # Rule 3: Trenching angles should be curved
        results.append(self.validate_trenching_angles_curved())

        # Rule 4: Missing trenches
        results.append(self.validate_missing_trenches())

        # Rule 5: U-shape detours and cable overextension
        results.append(self.validate_u_shape_detours())

        return results
