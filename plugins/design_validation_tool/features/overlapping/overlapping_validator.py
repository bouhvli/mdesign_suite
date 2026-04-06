from qgis.core import QgsGeometry, QgsProject, QgsWkbTypes  # type: ignore
import math
from ...utils.layer_loader import get_layer_by_name

class OverlappingValidator:
    def __init__(self):
        self.violations = []


    def validate_parallel_overlap(self, min_overlap_length=50.0, max_separation=2.0, min_shared_route_length=20.0):
        """Validate parallel duct overlap
        STRICT: Detect only parallel ducts that run on top of each other
        NEW: Also detect ducts with same IDENTIFIER taking same route
        """
        print("Validating parallel overlap (strict mode)...")

        prim_ducts_layer = get_layer_by_name('Primary Distribution Ducts')
        dist_ducts_layer = get_layer_by_name('Distribution Ducts')

        available_layers = []
        if prim_ducts_layer:
            available_layers.append(prim_ducts_layer)
        else:
            print("Primary Distribution Ducts layer not found - skipping")
        
        if dist_ducts_layer:
            available_layers.append(dist_ducts_layer)
        else:
            print("Distribution Ducts layer not found - skipping")

        if not available_layers:
            return {
                'rule_id': 'OVERLAP_001',
                'Description': 'Parallel duct overlap detection',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'No duct layers found for overlap validation'
            }

        violations = []

        # Compare ducts only within the same layer
        for layer in available_layers:
            ducts = []
            for feature in layer.getFeatures():
                duct_geometry = feature.geometry()
                if not duct_geometry or duct_geometry.isEmpty():
                    continue

                duct_id = feature['DUCT_ID'] if 'DUCT_ID' in feature.fields().names() else feature.id()
                duct_group = feature['DUCT_GROUP'] if 'DUCT_GROUP' in feature.fields().names() else None
                identifier = feature['IDENTIFIER'] if 'IDENTIFIER' in feature.fields().names() else None

                duct_info = {
                    'feature': feature,
                    'geometry': duct_geometry,
                    'layer': layer.name(),
                    'type': feature['TYPE'] if 'TYPE' in feature.fields().names() else 'UNKNOWN',
                    'capacity': feature['CAPACITY'] if 'CAPACITY' in feature.fields().names() else 0,
                    'duct_group': duct_group,
                    'duct_id': duct_id,
                    'identifier': identifier,
                    'length': duct_geometry.length() if duct_geometry else 0
                }
                ducts.append(duct_info)

            # print(f"Loaded {len(ducts)} ducts from layer '{layer.name()}' for overlap analysis")

            # EXISTING CHECK: Parallel ducts with same capacity that physically overlap
            features = ducts
            for i, duct1 in enumerate(features):
                geom1 = duct1['geometry']
                cap1 = duct1['capacity']

                for j in range(i+1, len(features)):
                    duct2 = features[j]
                    geom2 = duct2['geometry']
                    cap2 = duct2['capacity']

                    # Only compare ducts with same capacity
                    if cap1 != cap2:
                        continue

                    # Check intersection
                    if geom1.intersects(geom2):
                        inter_geom = geom1.intersection(geom2)

                        # Only continue if it's a line (not just a point)
                        if inter_geom.isEmpty() or inter_geom.type() != QgsWkbTypes.LineGeometry:
                            continue

                        inter_len = inter_geom.length()

                        if inter_len > min_overlap_length:  # threshold
                            print(f"Parallel overlap found: Ducts {duct1['duct_id']} & {duct2['duct_id']}, Overlap: {inter_len:.1f}m, Capacity: {cap1}")

                            # Use the actual overlap line geometry for visualization
                            violation_geometry = inter_geom

                            violation_info = {
                                'duct1_id': duct1['duct_id'],
                                'duct2_id': duct2['duct_id'],
                                'duct1_layer': duct1['layer'],
                                'duct2_layer': duct2['layer'],
                                'duct1_type': duct1['type'],
                                'duct2_type': duct2['type'],
                                'duct1_capacity': cap1,
                                'duct2_capacity': cap2,
                                'overlap_length': inter_len,
                                'total_length1': duct1['length'],
                                'total_length2': duct2['length'],
                                'geometry': violation_geometry,
                                'violation_type': 'parallel_overlap',
                                'violation_reason': f"Parallel ducts overlap for {inter_len:.1f}m"
                            }
                            violations.append(violation_info)

            identifier_violations = self._check_same_identifier_routes(ducts, min_shared_route_length, max_separation)
            violations.extend(identifier_violations)

        result = {
            'rule_id': 'OVERLAP_001',
            'Description': f'Parallel duct overlap detection (min overlap: {min_overlap_length}m, min shared route: {min_shared_route_length}m)',
            'status': 'PASS' if not violations else 'FAIL',
            'violation_count': len(violations),
            'failed_features': ', '.join([f"Ducts_{'_'.join(map(str, sorted(v.get('duct_ids', [v['duct1_id'], v['duct2_id']]))))}" for v in violations]),
            'message': f'Found {len(violations)} parallel duct overlaps and same-identifier route violations'
        }

        self.violations.extend(violations)
        return result

    def _check_same_identifier_routes(self, ducts, min_shared_route_length=20.0, buffer_distance=2.0):
        """
        Check for ducts with same IDENTIFIER that are taking similar routes
        Conditions:
        1. Same IDENTIFIER value (non-empty string)
        2. Similar direction/orientation
        3. Close proximity (within reasonable distance)
        4. Shared route length >= minimum threshold
        """
        from collections import defaultdict
        
        violations = []
        
        # Group ducts by IDENTIFIER
        ducts_by_identifier = {}
        for duct in ducts:
            identifier = duct.get('identifier')
            if identifier and isinstance(identifier, str) and identifier.strip():
                if identifier not in ducts_by_identifier:
                    ducts_by_identifier[identifier] = []
                ducts_by_identifier[identifier].append(duct)
        
        # print(f"Found {len(ducts_by_identifier)} unique identifiers with ducts")
        
        # Check each identifier group
        for identifier, identifier_ducts in ducts_by_identifier.items():
            if len(identifier_ducts) < 2:
                continue
                
            # print(f"Checking identifier '{identifier}' with {len(identifier_ducts)} ducts")
            
            # Build graph and shared infos
            adj = defaultdict(set)
            shared_infos = {}
            
            # Sort ducts by duct_id for consistent order
            identifier_ducts.sort(key=lambda d: str(d['duct_id']))
            
            # Check all pairs within this identifier group
            for i in range(len(identifier_ducts)):
                for j in range(i + 1, len(identifier_ducts)):
                    duct1 = identifier_ducts[i]
                    duct2 = identifier_ducts[j]

                    # Skip if same duct
                    if duct1['duct_id'] == duct2['duct_id']:
                        continue

                    # Check if they share a significant route
                    shared_route_info = self._analyze_shared_route(duct1, duct2, min_shared_route_length, buffer_distance)

                    if shared_route_info['has_shared_route']:
                        id1 = duct1['duct_id']
                        id2 = duct2['duct_id']
                        key = tuple(sorted([id1, id2], key=str))
                        shared_infos[key] = shared_route_info
                        adj[id1].add(id2)
                        adj[id2].add(id1)

            # Find connected components
            visited = set()
            for duct in identifier_ducts:
                duct_id = duct['duct_id']
                if duct_id not in visited:
                    component = []
                    stack = [duct_id]
                    while stack:
                        current = stack.pop()
                        if current not in visited:
                            visited.add(current)
                            component.append(current)
                            for neighbor in adj[current]:
                                if neighbor not in visited:
                                    stack.append(neighbor)
                    
                    if len(component) >= 2:
                        # Process the component
                        component_ducts = [d for d in identifier_ducts if d['duct_id'] in component]
                        
                        # Collect edges in component
                        component_edges = []
                        for m in range(len(component)):
                            for n in range(m + 1, len(component)):
                                edge_key = tuple(sorted([component[m], component[n]], key=str))
                                if edge_key in shared_infos:
                                    component_edges.append(shared_infos[edge_key])
                        
                        if not component_edges:
                            continue
                        
                        # Aggregate metrics
                        shared_lengths = [e['shared_length'] for e in component_edges]
                        avg_dists = [e['avg_distance'] for e in component_edges]
                        angle_diffs = [e['angle_diff'] for e in component_edges]
                        
                        max_shared = max(shared_lengths)
                        min_dist = min(avg_dists)
                        avg_angle = sum(angle_diffs) / len(angle_diffs)
                        
                        # For geometry: union of intersection geometries
                        edge_geoms = [e['geometry'] for e in component_edges if e['geometry']]
                        if edge_geoms:
                            union_geom = QgsGeometry.unaryUnion(edge_geoms)
                            violation_geometry = union_geom
                        else:
                            violation_geometry = component_ducts[0]['geometry']
                        
                        # Assume same type, capacity, layer
                        type_ = component_ducts[0]['type']
                        cap = component_ducts[0]['capacity']
                        layer_ = component_ducts[0]['layer']
                        
                        # print(f"Same identifier route found: ID '{identifier}', Ducts {', '.join(map(str, sorted(component, key=str)))}, "
                        #       f"Max shared route: {max_shared:.1f}m, "
                        #       f"Min avg distance: {min_dist:.1f}m, "
                        #       f"Avg angle diff: {avg_angle:.1f}°")
                        
                        violation_info = {
                            'duct_ids': sorted(component, key=str),
                            'duct1_id': sorted(component, key=str)[0],
                            'duct2_id': sorted(component, key=str)[1] if len(component) > 1 else None,
                            'duct1_layer': layer_,
                            'duct2_layer': layer_,
                            'duct1_type': type_,
                            'duct2_type': type_,
                            'duct1_capacity': cap,
                            'duct2_capacity': cap,
                            'identifier': identifier,
                            'shared_route_length': max_shared,
                            'average_distance': min_dist,
                            'angle_difference': avg_angle,
                            'geometry': violation_geometry,
                            'violation_type': 'redundant_parallel_routes',
                            'violation_reason': f"{len(component)} ducts run parallel for {max_shared:.1f}m within {min_dist:.1f}m distance (redundant routing)"
                        }
                        violations.append(violation_info)
        
        return violations

    def _analyze_shared_route(self, duct1, duct2, min_shared_length, proximity_threshold=2.0):
        """
        Analyze if two ducts share a significant route
        Returns dict with analysis results
        """
        geom1 = duct1['geometry']
        geom2 = duct2['geometry']
        
        result = {
            'has_shared_route': False,
            'shared_length': 0.0,
            'avg_distance': float('inf'),
            'angle_diff': 180.0,
            'geometry': geom1  # fallback geometry
        }
        
        try:
            # Calculate basic metrics
            distance = geom1.distance(geom2)
            angle_diff = self._calculate_angle_difference(geom1, geom2)
            
            # Compute clipped length for geom1 within proximity of geom2
            buffer2 = geom2.buffer(proximity_threshold, 5)
            if buffer2.isEmpty():
                return result
            clipped_geom1 = geom1.intersection(buffer2)
            if clipped_geom1.isEmpty() or clipped_geom1.type() != QgsWkbTypes.LineGeometry:
                return result
            
            # Get parts
            clipped_parts1 = []
            if clipped_geom1.isMultipart():
                multi = clipped_geom1.constGet()
                for part in multi.parts():
                    clipped_parts1.append(QgsGeometry(part.clone()))
            else:
                clipped_parts1.append(clipped_geom1)
            
            if not clipped_parts1:
                return result
            
            # Find longest continuous part
            longest_part1 = max(clipped_parts1, key=lambda g: g.length())
            shared_length1 = longest_part1.length()
            
            # Symmetric for geom2
            buffer1 = geom1.buffer(proximity_threshold, 5)
            if buffer1.isEmpty():
                return result
            clipped_geom2 = geom2.intersection(buffer1)
            if clipped_geom2.isEmpty() or clipped_geom2.type() != QgsWkbTypes.LineGeometry:
                return result
            
            clipped_parts2 = []
            if clipped_geom2.isMultipart():
                multi = clipped_geom2.constGet()
                for part in multi.parts():
                    clipped_parts2.append(QgsGeometry(part.clone()))
            else:
                clipped_parts2.append(clipped_geom2)
            
            if not clipped_parts2:
                return result
            
            longest_part2 = max(clipped_parts2, key=lambda g: g.length())
            shared_length2 = longest_part2.length()
            
            # Take the min of the two longest shared lengths
            shared_length = min(shared_length1, shared_length2)
            
            if shared_length < min_shared_length:
                return result
            
            # Compute average distance using the longer of the two longest parts (for sampling)
            if shared_length1 >= shared_length2:
                sample_geom = longest_part1
                target_geom = geom2
            else:
                sample_geom = longest_part2
                target_geom = geom1
            
            # Sample points on sample_geom to compute average distance
            num_samples = 20
            avg_dist = 0.0
            count = 0
            len_part = sample_geom.length()
            if len_part > 0:
                step = len_part / (num_samples - 1) if num_samples > 1 else len_part
                for i in range(num_samples):
                    dist_along = min(i * step, len_part)
                    point = sample_geom.interpolate(dist_along)
                    if not point.isEmpty():
                        dist = point.distance(target_geom)
                        avg_dist += dist
                        count += 1
            
            average_distance = avg_dist / count if count > 0 else float('inf')
            
            result.update({
                'has_shared_route': True,
                'shared_length': shared_length,
                'avg_distance': average_distance,
                'angle_diff': angle_diff,
                'geometry': geom1
            })
            
            return result
            
        except Exception as e:
            print(f"Error analyzing shared route: {e}")
            return result

    def _calculate_angle_difference(self, geom1, geom2):
        """Calculate angle difference between two lines in degrees"""
        try:
            def get_average_direction(geometry):
                points = geometry.asPolyline()
                if len(points) < 2:
                    return 0.0
                sum_sin = 0.0
                sum_cos = 0.0
                total_length = 0.0
                for k in range(len(points) - 1):
                    p1 = points[k]
                    p2 = points[k + 1]
                    dx = p2.x() - p1.x()
                    dy = p2.y() - p1.y()
                    seg_len = math.sqrt(dx**2 + dy**2)
                    if seg_len == 0:
                        continue
                    angle = math.atan2(dy, dx)
                    sum_sin += math.sin(angle) * seg_len
                    sum_cos += math.cos(angle) * seg_len
                    total_length += seg_len
                if total_length == 0:
                    return 0.0
                return math.atan2(sum_sin / total_length, sum_cos / total_length)
            
            dir1 = get_average_direction(geom1)
            dir2 = get_average_direction(geom2)
            
            angle_diff = math.degrees(abs(dir1 - dir2)) % 180
            if angle_diff > 90:
                angle_diff = 180 - angle_diff
                
            return angle_diff
        except:
            return 180.0

    def validate_cluster_overlaps(self):
        """
        Validate overlaps between clusters in different cluster layers
        Implements rules OVERLAP_003, OVERLAP_004, OVERLAP_005
        """
        print("Validating cluster overlaps...")
        
        cluster_results = []
        
        # Rule OVERLAP_003: Primary Distribution Clusters
        overlap_003_result = self._validate_cluster_overlap(
            'Primary Distribution Clusters', 
            'OVERLAP_003',
            1
        )
        if overlap_003_result:
            cluster_results.append(overlap_003_result)
        
        # Rule OVERLAP_004: Distribution Clusters  
        overlap_004_result = self._validate_cluster_overlap(
            'Distribution Clusters',
            'OVERLAP_004',
            1
        )
        if overlap_004_result:
            cluster_results.append(overlap_004_result)
        
        # Rule OVERLAP_005: Drop Clusters
        overlap_005_result = self._validate_cluster_overlap(
            'Drop Clusters',
            'OVERLAP_005',
            1
        )
        if overlap_005_result:
            cluster_results.append(overlap_005_result)
        
        return cluster_results

    def _validate_cluster_overlap(self, layer_name, rule_id, min_overlap_area=10.0):
        """
        Checks for overlaps between polygons in the specified cluster layer.
        Flags violations if intersection area exceeds min_overlap_area.
        """
        cluster_layer = get_layer_by_name(layer_name)
        if not cluster_layer:
            return {
                'rule_id': rule_id,
                'Description': f'Cluster overlap detection for {layer_name}',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': f'Layer {layer_name} not found for cluster overlap validation'
            }

        features = list(cluster_layer.getFeatures())
        violations = []

        for i, feat1 in enumerate(features):
            geom1 = feat1.geometry()
            id1 = feat1['CLUSTER_ID'] if 'CLUSTER_ID' in feat1.fields().names() else feat1.id()
            for j in range(i+1, len(features)):
                feat2 = features[j]
                geom2 = feat2.geometry()
                id2 = feat2['CLUSTER_ID'] if 'CLUSTER_ID' in feat2.fields().names() else feat2.id()

                if geom1.intersects(geom2):
                    inter_geom = geom1.intersection(geom2)
                    if inter_geom.isEmpty() or inter_geom.type() != QgsWkbTypes.PolygonGeometry:
                        continue
                    inter_area = inter_geom.area()
                    if inter_area > min_overlap_area:
                        violation_info = {
                            'cluster1_id': id1,
                            'cluster2_id': id2,
                            'layer': layer_name,
                            'overlap_area': inter_area,
                            'geometry': inter_geom,
                            'violation_type': 'cluster_overlap',
                            'violation_reason': f"Clusters {id1} & {id2} overlap for {inter_area:.1f} m²"
                        }
                        violations.append(violation_info)

        result = {
            'rule_id': rule_id,
            'Description': f'Cluster overlap detection for {layer_name} (min area: {min_overlap_area} m²)',
            'status': 'PASS' if not violations else 'FAIL',
            'violation_count': len(violations),
            'failed_features': ', '.join([f"Clusters_{v['cluster1_id']}_{v['cluster2_id']}" for v in violations]),
            'message': f'Found {len(violations)} cluster overlaps in {layer_name}'
        }
        self.violations.extend(violations)
        return result

    def validate_primary_distribution_cluster_overlap(self, min_overlap_area=10.0):
        return self._validate_cluster_overlap(
            layer_name='Primary Distribution Clusters',
            rule_id='OVERLAP_003',
            min_overlap_area=min_overlap_area
        )

    def validate_distribution_cluster_overlap(self, min_overlap_area=10.0):
        return self._validate_cluster_overlap(
            layer_name='Distribution Clusters',
            rule_id='OVERLAP_004',
            min_overlap_area=min_overlap_area
        )

    def validate_drop_cluster_overlap(self, min_overlap_area=10.0):
        return self._validate_cluster_overlap(
            layer_name='Drop Clusters',
            rule_id='OVERLAP_005',
            min_overlap_area=min_overlap_area
        )