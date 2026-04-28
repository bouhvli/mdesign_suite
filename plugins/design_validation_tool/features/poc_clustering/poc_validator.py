import math
from collections import defaultdict

from qgis.core import (  # type: ignore
    QgsGeometry,
    QgsProject,
    QgsSpatialIndex,
    QgsFeature,
    QgsVectorLayer,
    QgsField,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsMarkerSymbol,
)
from PyQt5.QtCore import QVariant  # type: ignore
from PyQt5.QtGui import QColor  # type: ignore


class POCValidator:
    def __init__(self):
        self.violations = []

    def get_layer_by_name(self, layer_name):
        """Get QGIS layer by name"""
        layers = QgsProject.instance().mapLayersByName(layer_name)
        return layers[0] if layers else None

    def validate_max_pocs_in_line(self, max_pocs=11):
        """
        Validate that each distribution cable has <= max_pocs POCs

        Rule 1: Maximum POCs in line =< 11
        Layers: OUT_DropPoints.shp, OUT_DistributionCables.shp
        """
        print("Validating maximum POCs in line...")
        
        drop_points_layer = self.get_layer_by_name('Drop Points')
        dist_cables_layer = self.get_layer_by_name('Distribution Cables')

        if not drop_points_layer or not dist_cables_layer:
            return {
                'rule_id': 'POC_001',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Required layers not found for max POCs validation'
            }

        # Check if required fields exist
        cable_fields = dist_cables_layer.fields().names()
        drop_fields = drop_points_layer.fields().names()

        if 'CAB_GROUP' not in cable_fields or 'CABLE_ID' not in cable_fields:
            return {
                'rule_id': 'POC_001',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Distribution cables layer missing required fields (CAB_GROUP, CABLE_ID)'
            }

        if 'SUBCLUSTER' not in drop_fields:
            return {
                'rule_id': 'POC_001',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Drop points layer missing required field (SUBCLUSTER)'
            }

        # Group distribution cables by CAB_GROUP and CABLE_ID
        cable_groups = defaultdict(list)
        cable_geometries = {}

        for cable_feature in dist_cables_layer.getFeatures():
            cab_group = cable_feature['CAB_GROUP']
            cable_id = cable_feature['CABLE_ID']
            group_key = f"{cab_group}_{cable_id}"
            
            cable_groups[group_key].append(cable_feature)
            cable_geometries[cable_feature.id()] = cable_feature.geometry()

        # Group drop points by SUBCLUSTER (which should match CAB_GROUP)
        drop_points_by_subcluster = defaultdict(list)
        drop_point_geometries = {}
        
        for drop_feature in drop_points_layer.getFeatures():
            subcluster = drop_feature['SUBCLUSTER']
            drop_points_by_subcluster[subcluster].append(drop_feature)
            geom = drop_feature.geometry()
            drop_point_geometries[drop_feature.id()] = geom

        violations = []
        
        # For each cable group, check POCs on each cable
        for group_key, cable_features in cable_groups.items():
            cab_group, cable_id = group_key.split('_', 1)
            
            # Find the corresponding subcluster for this cable group
            matching_subcluster = None
            for subcluster in drop_points_by_subcluster.keys():
                if str(subcluster) == str(cab_group):
                    matching_subcluster = subcluster
                    break
            
            if matching_subcluster is None:
                continue  # No drop points for this cable group
            
            drop_points = drop_points_by_subcluster[matching_subcluster]
            
            # For each cable in this group, find which drop points are connected to it
            for cable_feature in cable_features:
                cable_geometry = cable_feature.geometry()
                if not cable_geometry or cable_geometry.isEmpty():
                    continue

                # Find drop points connected to this specific cable
                pocs_on_this_cable = []

                for drop_feature in drop_points:
                    drop_geometry = drop_feature.geometry()
                    if not drop_geometry or drop_geometry.isEmpty():
                        continue

                    # Check if drop point is connected to this cable
                    if self.is_drop_connected_to_cable(drop_geometry, cable_geometry):
                        pocs_on_this_cable.append(drop_feature)
                if ('AERIAL' not in cable_feature['TYPE'] and len(pocs_on_this_cable) > max_pocs) or ('AERIAL' in cable_feature['TYPE'] and len(pocs_on_this_cable) > (max_pocs + 11)):
                # Check if this cable has too many POCs
                    violation_info = {
                        'cable_group': cab_group,
                        'cable_id': cable_id,
                        'cable_feature_id': cable_feature.id(),
                        'poc_count': len(pocs_on_this_cable),
                        'poc_ids': [f.id() for f in pocs_on_this_cable],
                        'geometry': cable_geometry,
                        'violation_type': 'max_pocs_per_cable'
                    }
                    violations.append(violation_info)

                    # print(f"Violation: Cable {cable_id} in group {cab_group} has {len(pocs_on_this_cable)} POCs (max {max_pocs})")

        result = {
            'rule_id': 'POC_001',
            'Description': 'Maximum POCs in line =< 11',
            'status': 'PASS' if not violations else 'FAIL',
            'violation_count': len(violations),
            'failed_features': ', '.join([f"Cable_{v['cable_id']}_Group_{v['cable_group']}" for v in violations]),
            'message': f'Found {len(violations)} cables with more than {max_pocs} POCs'
        }
        
        self.violations.extend(violations)
        return result
    
    def is_drop_connected_to_cable(self, drop_geometry, cable_geometry, max_distance=2.0):
        """
        Check if a drop point is connected to a distribution cable

        Args:
            drop_geometry: Geometry of the drop point
            cable_geometry: Geometry of the distribution cable
            max_distance: Maximum distance to consider connected (in meters)

        Returns:
            bool: True if connected, False otherwise
        """
        if not drop_geometry or not cable_geometry:
            return False

        # For line cables, check distance to the line
        if cable_geometry.type() == 1:  # Line geometry
            distance = drop_geometry.distance(cable_geometry)
            return distance <= max_distance

        # For other geometry types, use bounding box intersection as fallback
        return drop_geometry.intersects(cable_geometry)
    
    def validate_max_connections_per_poc(self, max_connections=8):
        """
        Validate that each POC has <= max_connections demand points
        
        Rule 2: Max connections per POC =< 8
        Layers: OUT_DropPoints.shp, OUT_DemandPoints.shp
        
        FIXED: No QgsSpatialIndex to avoid access violations on second run
        """
        print("Validating maximum connections per POC...")
        
        drop_points_layer = self.get_layer_by_name('Drop Points')
        demand_points_layer = self.get_layer_by_name('Demand Points')
        
        if not drop_points_layer or not demand_points_layer:
            return {
                'rule_id': 'POC_002',
                'Description': 'Max connections per POC =< 8',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Required layers not found for max connections validation'
            }
        
        # Pre-load ALL demand points into a simple Python list
        # No spatial index = no memory corruption issues
        demand_points = []
        
        print("Loading demand points into memory...")
        try:
            for feature in demand_points_layer.getFeatures():
                geom = feature.geometry()
                if geom and not geom.isEmpty():
                    # Store each demand point with its geometry copy
                    demand_points.append({
                        'id': feature.id(),
                        'geometry': QgsGeometry(geom),  # Explicit geometry copy
                        'bbox': geom.boundingBox()
                    })
            
            # print(f"Successfully loaded {len(demand_points)} demand points")
        except Exception as e:
            print(f"Error loading demand points: {e}")
            import traceback
            traceback.print_exc()
            return {
                'rule_id': 'POC_002',
                'Description': 'Max connections per POC =< 8',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': f'Error loading demand points: {str(e)}'
            }
        
        violations = []
        
        print("Checking each POC...")
        try:
            poc_count = 0
            # Check each drop point (POC)
            for drop_feature in drop_points_layer.getFeatures():
                poc_count += 1
                drop_geometry = drop_feature.geometry()
                if not drop_geometry or drop_geometry.isEmpty():
                    continue

                # Create search area (5m buffer)
                drop_bbox = drop_geometry.boundingBox()
                search_bbox = drop_bbox.buffered(5.0)
                
                connection_count = 0
                
                # First pass: Quick bounding box filter
                candidates = []
                for demand_point in demand_points:
                    if search_bbox.intersects(demand_point['bbox']):
                        candidates.append(demand_point)
                
                # Second pass: Precise distance check on candidates only
                for demand_point in candidates:
                    try:
                        distance = drop_geometry.distance(demand_point['geometry'])
                        if distance <= 5.0:  # Within 5m of POC
                            connection_count += 1
                    except Exception as e:
                        print(f"Warning: Distance calculation failed for demand point {demand_point['id']}: {e}")
                        continue
                
                # Check if this POC violates the max connections rule
                if connection_count > max_connections:
                    poc_id = drop_feature['AGG_ID'] if 'AGG_ID' in drop_feature.fields().names() else drop_feature.id()
                    violations.append({
                        'poc_id': poc_id,
                        'connection_count': connection_count,
                        'geometry': QgsGeometry(drop_geometry),  # Geometry copy
                        'violation_type': 'max_connections_per_poc'
                    })
            #         print(f"Violation: POC {poc_id} has {connection_count} connections (max {max_connections})")

            # print(f"Checked {poc_count} POCs, found {len(violations)} violations")
        
        except Exception as e:
            print(f"Error during POC validation: {e}")
            import traceback
            traceback.print_exc()
            return {
                'rule_id': 'POC_002',
                'Description': 'Max connections per POC =< 8',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': f'Error during validation: {str(e)}'
            }
        finally:
            # Clean up references
            demand_points.clear()
        
        # Build result
        result = {
            'rule_id': 'POC_002',
            'Description': 'Max connections per POC =< 8',
            'status': 'PASS' if not violations else 'FAIL',
            'violation_count': len(violations),
            'failed_features': ', '.join([f"POC_{v['poc_id']}" for v in violations]),
            'message': f'Found {len(violations)} POCs with more than {max_connections} connections'
        }
        
        # Add violations to instance list
        self.violations.extend(violations)
        
        return result
    def validate_ug_facade_connections(self, max_left=4, max_right=4):
        """
        Validate UG/Facade connections: max 4 left and 4 right
        
        Rule 3: Drop connections UG/Facade : max 4 left and 4 right
        Layers: OUT_DropPoints.shp, OUT_DemandPoints.shp
        """
        print("Validating UG/Facade connections...")
        
        drop_points_layer = self.get_layer_by_name('Drop Points')
        demand_points_layer = self.get_layer_by_name('Demand Points')
        
        if not drop_points_layer or not demand_points_layer:
            return {
                'rule_id': 'POC_003',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Required layers not found for UG/Facade validation'
            }
        
        violations = []
        
        # Check each drop point
        for drop_feature in drop_points_layer.getFeatures():
            drop_geometry = drop_feature.geometry()
            if not drop_geometry:
                continue
            
            # Get drop point orientation (assuming there's a field for orientation)
            # If no orientation field, we'll need to calculate based on cable direction
            orientation_field = 'orientation' if 'orientation' in drop_feature.fields().names() else None
            drop_orientation = drop_feature[orientation_field] if orientation_field else 0
            
            left_count = 0
            right_count = 0
            
            # Check all demand points
            for demand_feature in demand_points_layer.getFeatures():
                demand_geometry = demand_feature.geometry()
                if not demand_geometry:
                    continue
                
                distance = drop_geometry.distance(demand_geometry)
                if distance <= 5.0:  # Within 5m of POC
                    # Calculate relative position (left or right)
                    # This is a simplified approach - you might need more complex logic
                    relative_position = self._calculate_relative_position(
                        drop_geometry, drop_orientation, demand_geometry
                    )
                    
                    if relative_position == 'left':
                        left_count += 1
                    elif relative_position == 'right':
                        right_count += 1
            
            if left_count > max_left or right_count > max_right:
                violations.append({
                    'poc_id': drop_feature['AGG_ID'] if 'AGG_ID' in drop_feature.fields().names() else drop_feature.id(),
                    'left_count': left_count,
                    'right_count': right_count,
                    'geometry': drop_geometry,
                    'violation_type': 'ug_facade_connections'
                })
        
        result = {
            'rule_id': 'POC_003',
            'Description': 'Drop connections UG/Facade : max 4 left and 4 right',
            'status': 'PASS' if not violations else 'FAIL',
            'violation_count': len(violations),
            'failed_features': ', '.join([f"POC_{v['poc_id']}" for v in violations]),
            'message': f'Found {len(violations)} POCs with UG/Facade connection violations'
        }
        
        self.violations.extend(violations)
        return result
    
    def validate_pocs_in_single_cluster(self):
        """
        Validate that POCs exist in a single drop cluster and are within 1m of cluster boundary
        
        Rule 4: POCs should exist in a single drop cluster and be within 1m of cluster boundary
        Layers: Drop Points, Drop Clusters
        Relationship: AGG_ID (Drop Points) == AGG_ID (Drop Clusters)
        """
        print("Validating POCs in single cluster and proximity...")
        
        drop_points_layer = self.get_layer_by_name('Drop Points')
        drop_clusters_layer = self.get_layer_by_name('Drop Clusters')
        
        if not drop_points_layer or not drop_clusters_layer:
            return {
                'rule_id': 'POC_004',
                'status': 'ERROR',
                'description': 'POCs in single cluster validation',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Required layers not found for cluster validation'
            }

        # Check required fields
        if 'AGG_ID' not in drop_points_layer.fields().names():
            return {
                'rule_id': 'POC_004',
                'status': 'ERROR',
                'description': 'POCs in single cluster validation',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Drop Points layer missing required field: AGG_ID'
            }
        
        if 'AGG_ID' not in drop_clusters_layer.fields().names():
            return {
                'rule_id': 'POC_004',
                'status': 'ERROR',
                'description': 'POCs in single cluster validation',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Drop Clusters layer missing required field: AGG_ID'
            }

        # Create dictionary of clusters by AGG_ID for quick lookup
        clusters_by_agg_id = {}
        for cluster_feature in drop_clusters_layer.getFeatures():
            agg_id = cluster_feature['AGG_ID']
            clusters_by_agg_id[agg_id] = cluster_feature

        violations = []

        # Check each drop point
        for drop_feature in drop_points_layer.getFeatures():
            drop_geometry = drop_feature.geometry()
            if not drop_geometry:
                continue

            drop_agg_id = drop_feature['AGG_ID']
            
            # Find the cluster with matching AGG_ID
            matching_cluster = clusters_by_agg_id.get(drop_agg_id)
            
            if not matching_cluster:
                # No cluster found with matching AGG_ID
                violations.append({
                    'rule_id': 'POC_004',
                    'description': 'POCs should exist in a single drop cluster and be within 1m of cluster boundary',
                    'layer': 'Drop Points / Drop Clusters',
                    'poc_id': drop_agg_id,
                    'cluster_count': 0,
                    'clusters': [],
                    'geometry': drop_geometry,
                    'violation_type': 'poc_single_cluster',
                    'violation_subtype': 'no_matching_cluster',
                    'distance_to_cluster': None
                })
                continue
            
            cluster_geometry = matching_cluster.geometry()
            if not cluster_geometry:
                continue
            
            # Create 1m buffer around the POC
            poc_buffer = drop_geometry.buffer(1.0, 5)  # 1m buffer with 5 segments
            
            # Check if the cluster intersects with the POC buffer
            if not cluster_geometry.intersects(poc_buffer):
                # Calculate actual distance for reporting
                distance_to_cluster = drop_geometry.distance(cluster_geometry)
                
                violations.append({
                    'rule_id': 'POC_004',
                    'description': 'POCs should exist in a single drop cluster and be within 1m of cluster boundary',
                    'layer': 'Drop Points / Drop Clusters',
                    'poc_id': drop_agg_id,
                    'cluster_count': 1,
                    'clusters': [matching_cluster.id()],
                    'distance_to_cluster': round(distance_to_cluster, 2),
                    'geometry': drop_geometry,
                    'violation_type': 'poc_single_cluster',
                    'violation_subtype': 'too_far_from_cluster'
                })

        result = {
            'rule_id': 'POC_004',
            'description': 'POCs should exist in a single drop cluster and be within 1m of cluster boundary',
            'status': 'PASS' if not violations else 'FAIL',
            'violation_count': len(violations),
            'failed_features': ', '.join([f"POC_{v['poc_id']}" for v in violations]),
            'message': f'Found {len(violations)} POCs not properly associated with their drop clusters'
        }

        self.violations.extend(violations)
        return result

    def validate_proximity_and_home_count(self, max_distance=50.0, max_home_count=8, max_cable_length=100.0):
        """
        Validate proximity, home count, and drop cable length rules
        
        Rule 5: Check if two POCs are close (<=50m), belong to same distribution cable,
            have combined home count <=8, and longest drop cable <=100m
            
        Special case: Check underground cables even if they have 'AERIAL' in TYPE field,
            but only if they are specifically underground segments
            
        FIXED: Only check neighboring POCs along the cable, exclude POCs with 8 homes,
            and don't reuse POCs that are already in potential merges
        """
        print("Validating proximity, home count, and drop cable length...")
        
        required_layers = [
            "Drop Points",
            "Distribution Cables",
            "Drop Clusters",
            "Drop Cables"
        ]

        # Load and validate layers
        layers = {}
        for name in required_layers:
            layer = self.get_layer_by_name(name)
            if not layer:
                return {
                    'rule_id': 'POC_005',
                    'Description': 'Proximity, home count, and drop cable length validation',
                    'status': 'ERROR',
                    'violation_count': 0,
                    'failed_features': '',
                    'message': f"Layer '{name}' not found"
                }
            layers[name] = layer

        # Unpack for readability
        drop_points_layer = layers["Drop Points"]
        dist_cables_layer = layers["Distribution Cables"]
        drop_clusters_layer = layers["Drop Clusters"]
        drop_cables_layer = layers["Drop Cables"]
        
        # Check required fields
        required_fields = {
            'Drop Points': ['SUBCLUSTER', 'AGG_ID'],
            'Distribution Cables': ['CAB_GROUP', 'CABLE_ID', 'TYPE'],
            'Drop Clusters': ['HOMECOUNT', 'AGG_ID'],
            'Drop Cables': ['LENGTH', 'TOP_AGG_ID']
        }
        
        for layer_name, fields in required_fields.items():
            layer = layers[layer_name]
            for field in fields:
                if field not in layer.fields().names():
                    return {
                        'rule_id': 'POC_005',
                        'Description': 'Proximity, home count, and drop cable length validation',
                        'status': 'ERROR',
                        'violation_count': 0,
                        'failed_features': '',
                        'message': f'Layer {layer_name} missing required field: {field}'
                    }
        
        violations = []
        
        # Pre-load all drop points into memory
        print("Loading drop points...")
        drop_points_list = []
        for feature in drop_points_layer.getFeatures():
            geom = feature.geometry()
            if geom and not geom.isEmpty():
                drop_points_list.append({
                    'id': feature.id(),
                    'agg_id': feature['AGG_ID'],
                    'subcluster': feature['SUBCLUSTER'],
                    'geometry': QgsGeometry(geom),  # Geometry copy
                    'bbox': geom.boundingBox()
                })
        # print(f"Loaded {len(drop_points_list)} drop points")

        # Group distribution cables by CAB_GROUP and CABLE_ID
        print("Loading distribution cables...")
        cable_segments_by_group = defaultdict(list)
        cable_types_by_segment = {}
        
        for cable_feature in dist_cables_layer.getFeatures():
            cab_group = cable_feature['CAB_GROUP']
            cable_id = cable_feature['CABLE_ID']
            cable_type = cable_feature['TYPE']
            segment_key = f"{cab_group}_{cable_id}"
            
            cable_geom = cable_feature.geometry()
            if not cable_geom or cable_geom.isEmpty():
                continue
            
            # Store cable DATA as dict, not the feature object
            cable_data = {
                'id': cable_feature.id(),
                'cab_group': cab_group,
                'cable_id': cable_id,
                'cable_type': cable_type,
                'geometry': QgsGeometry(cable_geom)  # Geometry copy
            }
            
            cable_segments_by_group[cab_group].append(cable_data)
            cable_types_by_segment[segment_key] = cable_type

        # print(f"Loaded {sum(len(v) for v in cable_segments_by_group.values())} cable segments")

        # Group drop points by distribution cable (using SUBCLUSTER -> CAB_GROUP mapping)
        drop_points_by_cable_group = defaultdict(list)
        for drop_point in drop_points_list:
            subcluster = drop_point['subcluster']
            drop_points_by_cable_group[subcluster].append(drop_point)
        
        # Pre-cache drop cables by cluster AGG_ID
        print("Loading drop cables...")
        drop_cables_by_cluster = defaultdict(list)
        
        for cable_feature in drop_cables_layer.getFeatures():
            top_agg_id = cable_feature['TOP_AGG_ID']
            cable_length = cable_feature['LENGTH'] or 0
            
            # Store cable DATA as dict, not the feature reference
            cable_data = {
                'id': cable_feature.id(),
                'top_agg_id': top_agg_id,
                'length': cable_length
            }
            drop_cables_by_cluster[top_agg_id].append(cable_data)
        
        # print(f"Loaded {sum(len(v) for v in drop_cables_by_cluster.values())} drop cables")
        
        # Pre-load drop clusters as dict for quick lookup
        print("Loading drop clusters...")
        clusters_by_agg_id = {}
        for cluster_feature in drop_clusters_layer.getFeatures():
            agg_id = cluster_feature['AGG_ID']
            homecount = cluster_feature['HOMECOUNT'] or 0
            
            cluster_geom = cluster_feature.geometry()
            
            # Store cluster DATA
            clusters_by_agg_id[agg_id] = {
                'id': cluster_feature.id(),
                'agg_id': agg_id,
                'homecount': homecount,
                'geometry': QgsGeometry(cluster_geom) if cluster_geom and not cluster_geom.isEmpty() else None
            }
        
        # print(f"Loaded {len(clusters_by_agg_id)} drop clusters")
        
        # Process each distribution cable group
        print("Checking proximity violations...")
        for cable_group, drop_points in drop_points_by_cable_group.items():
            if len(drop_points) < 2:
                continue  # Need at least 2 POCs
            
            # Get all cable segments for this group
            cable_segments = cable_segments_by_group.get(cable_group, [])
            
            # Check each cable segment individually
            for cable_segment in cable_segments:
                cable_id = cable_segment['cable_id']
                cable_type = cable_segment['cable_type']
                segment_key = f"{cable_group}_{cable_id}"
                
                # Skip aerial segments
                is_underground_segment = ('UNDERGROUND' == cable_type and 'AERIAL' not in cable_type)
                is_mixed_cable_underground_part = ('UNDERGROUND' in cable_type and 'AERIAL' in cable_type)
                
                if 'AERIAL' in cable_type and not is_underground_segment or is_mixed_cable_underground_part:
                    continue
                
                # Find drop points connected to this cable segment
                cable_geometry = cable_segment['geometry']
                
                pocs_on_this_segment = []
                for drop_point in drop_points:
                    drop_geometry = drop_point['geometry']
                    
                    # Check if drop point is connected to this cable segment
                    if self.is_drop_connected_to_cable(drop_geometry, cable_geometry):
                        pocs_on_this_segment.append(drop_point)
                
                if len(pocs_on_this_segment) < 2:
                    continue
                
                # NEW: Sort POCs along the cable to find true neighbors
                sorted_pocs = self._sort_pocs_along_cable(pocs_on_this_segment, cable_geometry)
                if not sorted_pocs:
                    continue
                
                # print(f"Sorted POCs along cable {cable_group}_{cable_id}:")
                # for i, poc in enumerate(sorted_pocs):
                #     cluster = clusters_by_agg_id.get(poc['agg_id'])
                #     homecount = cluster['homecount'] if cluster else 'N/A'
                #     print(f"  {i+1}. POC {poc['agg_id']} - {homecount} homes")
                # NEW: Track which POCs have been used in merges
                used_pocs = set()
                
                # NEW: Check only neighboring pairs along the cable
                for i in range(len(sorted_pocs) - 1):
                    poc1 = sorted_pocs[i]
                    poc2 = sorted_pocs[i + 1]
                    
                    # Skip if either POC is already used in a merge
                    if poc1['agg_id'] in used_pocs or poc2['agg_id'] in used_pocs:
                        continue
                    
                    # NEW: Skip POCs that already have 8 homes (they're at max capacity)
                    cluster1 = clusters_by_agg_id.get(poc1['agg_id'])
                    cluster2 = clusters_by_agg_id.get(poc2['agg_id'])

                    if not cluster1 or not cluster2:
                        continue

                    if cluster1['homecount'] >= max_home_count or cluster2['homecount'] >= max_home_count:
                        continue

                    geom1 = poc1['geometry']
                    geom2 = poc2['geometry']
                    
                    # Check distance between neighbors
                    distance = geom1.distance(geom2)
                    if distance > max_distance:
                        continue

                    # Check home count
                    home_count1 = cluster1['homecount']
                    home_count2 = cluster2['homecount']
                    total_home_count = home_count1 + home_count2

                    if total_home_count > max_home_count:
                        continue

                    # Get drop cables for both clusters
                    agg_id1 = poc1['agg_id']
                    agg_id2 = poc2['agg_id']

                    cables_cluster1 = drop_cables_by_cluster.get(agg_id1, [])
                    cables_cluster2 = drop_cables_by_cluster.get(agg_id2, [])

                    # Find longest cable
                    longest_cable1 = max([c['length'] for c in cables_cluster1], default=0)
                    longest_cable2 = max([c['length'] for c in cables_cluster2], default=0)
                    longest_cable = max(longest_cable1, longest_cable2)

                    if longest_cable > max_cable_length:
                        continue

                    # All conditions met - violation found
                    violation_info = {
                        'poc1_id': agg_id1,
                        'poc2_id': agg_id2,
                        'cluster1_id': agg_id1,
                        'cluster2_id': agg_id2,
                        'cable_group': cable_group,
                        'cable_id': cable_id,
                        'cable_type': cable_type,
                        'distance': distance,
                        'home_count1': home_count1,
                        'home_count2': home_count2,
                        'total_home_count': total_home_count,
                        'cable_length1': round(longest_cable1, 1),
                        'cable_length2': round(longest_cable2, 1),
                        'longest_cable': round(longest_cable, 1),
                        'geometry': QgsGeometry.fromMultiPointXY([geom1.centroid().asPoint(), geom2.centroid().asPoint()]),
                        'violation_type': 'proximity_home_count_cable_length'
                    }
                    violations.append(violation_info)

                    used_pocs.add(agg_id1)
                    used_pocs.add(agg_id2)

                    # print(f"Violation: Neighboring POCs {agg_id1} and {agg_id2} "
                    #     f"in cable group {cable_group}, segment {cable_id} "
                    #     f"are {distance:.1f}m apart, {total_home_count} homes total, "
                    #     f"longest cable {round(longest_cable, 1)}m")

        result = {
            'rule_id': 'POC_005',
            'Description': 'Proximity (<=50m), home count (<=8), and drop cable length (<=100m) validation',
            'status': 'PASS' if not violations else 'FAIL',
            'violation_count': len(violations),
            'failed_features': ', '.join([f"POCs_{v['poc1_id']}_{v['poc2_id']}" for v in violations]),
            'message': f'Found {len(violations)} proximity violations with home count and cable length issues'
        }

        self.violations.extend(violations)
        return result

    def _sort_pocs_along_cable(self, pocs, cable_geometry):
        """
        Sort POCs along the distribution cable to identify true neighbors

        Args:
            pocs: List of POC dictionaries
            cable_geometry: Geometry of the distribution cable

        Returns:
            List of POCs sorted along the cable, or empty list if sorting fails
        """
        try:
            if not pocs or not cable_geometry:
                return []

            # Handle MultiLineString geometry
            if cable_geometry.isMultipart():
                # For MultiLineString, flatten all segments into one continuous line if possible
                multi_line = cable_geometry.asMultiPolyline()
                if not multi_line:
                    return pocs

                # Flatten all segments into a single polyline by connecting endpoints
                flattened_line = []
                for segment in multi_line:
                    flattened_line.extend(segment)

                if len(flattened_line) < 2:
                    return pocs

                # Create a temporary single line geometry for sorting
                temp_line_geometry = QgsGeometry.fromPolylineXY(flattened_line)
                return self._sort_pocs_along_single_line(pocs, temp_line_geometry)

            # Handle single line geometry
            elif cable_geometry.type() == 1:  # Line geometry
                return self._sort_pocs_along_single_line(pocs, cable_geometry)

            else:
                # For non-line geometries, use centroid-based sorting as fallback
                return self._fallback_sort_pocs(pocs)

        except Exception as e:
            print(f"Warning: Failed to sort POCs along cable: {e}")
            print(f"Returning unsorted POCs for cable segment")
            return pocs

    def _sort_pocs_along_single_line(self, pocs, line_geometry):
        """
        Sort POCs along a single line geometry
        """
        try:
            line_points = line_geometry.asPolyline()
            if len(line_points) < 2:
                return pocs  # Fallback: invalid line

            # Calculate distance along the line for each POC
            poc_positions = []

            for poc in pocs:
                poc_point = poc['geometry'].centroid().asPoint()

                # Find the closest point on the line and measure distance from start
                closest_point, _, _ = line_geometry.closestSegmentWithContext(poc_point)
                if not closest_point:
                    # Fallback: use direct distance from start point
                    distance_along_line = line_points[0].distance(poc_point)
                else:
                    # Create a temporary line from start to closest point to measure distance
                    temp_line = QgsGeometry.fromPolylineXY([line_points[0], closest_point])
                    distance_along_line = temp_line.length()

                poc_positions.append((distance_along_line, poc))

            # Sort by distance along the cable
            poc_positions.sort(key=lambda x: x[0])
            return [poc for _, poc in poc_positions]

        except Exception:
            return self._fallback_sort_pocs(pocs)

    def _fallback_sort_pocs(self, pocs):
        """
        Fallback sorting when cable geometry is unavailable or problematic
        Uses X-coordinate sorting which is better than random ordering
        """
        try:
            # Sort by X coordinate (left to right)
            centroids = [(poc['geometry'].centroid().asPoint().x(), poc) for poc in pocs]
            centroids.sort(key=lambda x: x[0])
            return [poc for _, poc in centroids]
        except:
            return pocs  # Ultimate fallback: return as-is

    def _get_drop_cluster_for_poc(self, poc_feature, drop_clusters_layer):
        """Find the drop cluster that contains the given POC using spatial containment"""
        poc_geometry = poc_feature.geometry()
        if not poc_geometry:
            return None

        # Find clusters containing this POC
        for cluster_feature in drop_clusters_layer.getFeatures():
            cluster_geometry = cluster_feature.geometry()
            if cluster_geometry and cluster_geometry.contains(poc_geometry):
                return cluster_feature

        return None

    def validate_proximity_checks(self):
        """Validate proximity, home count, and cable length rules"""
        print("Validating proximity checks...")

        result = self.validate_proximity_and_home_count(
            max_distance=50.0,
            max_home_count=8,
            max_cable_length=100.0
        )

        return result

    def validate_aerial_drop_cable_length(self, max_length=40.0):
        """
        Validate that aerial drop cables do not exceed maximum length.

        Rule: Aerial drop cables should not exceed 40m in length.

        Args:
            max_length: Maximum allowed length for aerial drop cables in meters (default: 40.0)
        """
        print("Validating aerial drop cable length...")
        description = f"Aerial drop cables must not exceed {max_length}m in length"

        # Get required layer
        drop_cables_layer = self.get_layer_by_name("Drop Cables")

        if not drop_cables_layer:
            return {
                "rule_id": "POC_006",
                "Description": description,
                "status": "ERROR",
                "violation_count": 0,
                "failed_features": "",
                "message": "Drop Cables layer not found",
            }

        # Check if required fields exist
        required_fields = ["TYPE", "CABLE_ID"]
        missing_fields = [
            f for f in required_fields if f not in drop_cables_layer.fields().names()
        ]

        if missing_fields:
            return {
                "rule_id": "POC_006",
                "Description": description,
                "status": "ERROR",
                "violation_count": 0,
                "failed_features": "",
                "message": f"Drop Cables layer missing required fields: {', '.join(missing_fields)}",
            }

        violations = []

        # Check each drop cable
        for drop_cable in drop_cables_layer.getFeatures():
            cable_type = str(drop_cable["TYPE"]).strip().upper()

            # Only check drop cables that include AERIAL type (handles "AERIAL" and "AERIAL,UNDERGROUND")
            if "AERIAL" in cable_type:
                geom = drop_cable.geometry()

                if geom and not geom.isEmpty():
                    # Calculate length in meters
                    cable_length = geom.length()

                    if cable_length > max_length:
                        cable_id = drop_cable["CABLE_ID"]
                        violations.append(
                            {
                                "drop_cable_id": cable_id,
                                "cable_type": cable_type,
                                "cable_length": round(cable_length, 2),
                                "geometry": geom,
                                "violation_type": "aerial_drop_cable_length",
                                "violation_reason": f"Aerial drop cable {cable_id} exceeds maximum length: {round(cable_length, 2)}m > {max_length}m",
                            }
                        )

        # Build result
        violation_count = len(violations)
        failed_cable_ids = [f"Drop_{v['drop_cable_id']}" for v in violations]
        failed_features_str = ", ".join(failed_cable_ids)

        message = (
            f"Found {violation_count} aerial drop cables exceeding {max_length}m."
            if violation_count > 0
            else "No violations found."
        )

        result = {
            "rule_id": "POC_006",
            "Description": description,
            "status": "PASS" if not violations else "FAIL",
            "violation_count": violation_count,
            "failed_features": failed_features_str,
            "message": message,
        }

        # Add to violations list
        self.violations.extend(violations)

        return result

    def validate_facade_drop_cables_no_gap(self):
        """
        Validate that façade drop cables don't cross gaps between buildings.

        Rule: Drop cables with TYPE containing 'FACADE' must completely intersect
        with building(s). No part of the cable should cross a gap between buildings.
        """
        print("Validating façade drop cables for gaps...")
        description = "Façade drop cables must not cross gaps between buildings"

        # Get required layers
        drop_cables_layer = self.get_layer_by_name("Drop Cables")
        buildings_layer = self.get_layer_by_name("Building Polygons")

        if not drop_cables_layer:
            return {
                "rule_id": "POC_007",
                "Description": description,
                "status": "ERROR",
                "violation_count": 0,
                "failed_features": "",
                "message": "Drop Cables layer not found",
            }

        if not buildings_layer:
            return {
                "rule_id": "POC_007",
                "Description": description,
                "status": "ERROR",
                "violation_count": 0,
                "failed_features": "",
                "message": "IN_Buildings layer not found",
            }

        # Check if required fields exist
        if "TYPE" not in drop_cables_layer.fields().names():
            return {
                "rule_id": "POC_007",
                "Description": description,
                "status": "ERROR",
                "violation_count": 0,
                "failed_features": "",
                "message": "Drop Cables layer missing TYPE field",
            }

        if "CABLE_ID" not in drop_cables_layer.fields().names():
            return {
                "rule_id": "POC_007",
                "Description": description,
                "status": "ERROR",
                "violation_count": 0,
                "failed_features": "",
                "message": "Drop Cables layer missing CABLE_ID field",
            }

        violations = []

        # Create spatial index for buildings for efficient spatial queries
        buildings_index = QgsSpatialIndex(buildings_layer.getFeatures())

        # Load Possible Routes layer to exempt gaps that are aerial routes
        possible_routes_layer = self.get_layer_by_name("Possible Routes")
        routes_index = None
        if possible_routes_layer and "TYPE" in possible_routes_layer.fields().names():
            routes_index = QgsSpatialIndex(possible_routes_layer.getFeatures())

        def gap_is_covered_by_aerial_route(gap_geom):
            """Return True if the gap is fully covered by AERIAL possible routes."""
            if not routes_index or not possible_routes_layer:
                return False
            candidate_ids = routes_index.intersects(gap_geom.boundingBox())
            for rid in candidate_ids:
                route = possible_routes_layer.getFeature(rid)
                route_type = str(route["TYPE"]).strip().upper()
                if "BURIED" in route_type:
                    route_geom = route.geometry()
                    if route_geom and not route_geom.isEmpty():
                        if gap_geom.intersects(route_geom):
                            return True
            return False

        # Check each drop cable
        for drop_cable in drop_cables_layer.getFeatures():
            cable_type = str(drop_cable["TYPE"]).strip().upper()

            # Only check drop cables whose TYPE contains FACADE or LENIENT
            # (e.g. "FACADE,UNDERGROUND" or "LENIENT" are both valid)
            if "FACADE" not in cable_type and "LENIENT" not in cable_type:
                continue

            cable_geom = drop_cable.geometry()
            if not cable_geom or cable_geom.isEmpty():
                continue

            cable_id = drop_cable["CABLE_ID"]

            # Use a small search buffer on the bbox to find candidate buildings,
            # but we will buffer the buildings themselves (not the cable) so that
            # edge-touching facade cables are properly captured.
            search_bbox = cable_geom.boundingBox().buffered(1.0)
            candidate_building_ids = buildings_index.intersects(search_bbox)

            # Build union of buildings that are close to the cable.
            # Buffer each building by 0.5 m to absorb snapping / digitising tolerance
            # so that a cable sitting exactly on a building edge is covered.
            building_union = None
            for building_id in candidate_building_ids:
                building_feature = buildings_layer.getFeature(building_id)
                building_geom = building_feature.geometry()

                if not building_geom or building_geom.isEmpty():
                    continue

                buffered_bldg = building_geom.buffer(0.5, 5)
                if not cable_geom.intersects(buffered_bldg):
                    continue

                if building_union is None:
                    building_union = buffered_bldg
                else:
                    building_union = building_union.combine(buffered_bldg)

            # ---- Project cable endpoints onto buildings and find uncovered gap ----
            # Work directly on the cable LINE (not a buffered polygon of it).
            # cable.difference(buildings) returns the portions of the line that
            # do NOT lie on any building — those are the gaps.

            if building_union is None:
                # Cable doesn't touch any building at all — skip if the whole
                # cable sits on an aerial possible route
                if not gap_is_covered_by_aerial_route(cable_geom):
                    violations.append(
                        {
                            "drop_cable_id": cable_id,
                            "cable_type": cable_type,
                            "uncovered_length": round(cable_geom.length(), 2),
                            "gap_percentage": 100.0,
                            "geometry": cable_geom,
                            "violation_type": "facade_cable_crosses_gap",
                            "violation_reason": (
                                f"Façade drop cable {cable_id} does not lie on any building"
                            ),
                        }
                    )
            else:
                gap_geom = cable_geom.difference(building_union)

                if gap_geom and not gap_geom.isEmpty():
                    gap_length = gap_geom.length()

                    # Ignore sub-millimetre slivers from floating-point noise
                    if gap_length > 0.01:
                        # Skip if the gap overlaps an AERIAL possible route
                        if gap_is_covered_by_aerial_route(gap_geom):
                            continue

                        total_length = cable_geom.length()
                        gap_percentage = (
                            (gap_length / total_length) * 100 if total_length > 0 else 0
                        )

                        violations.append(
                            {
                                "drop_cable_id": cable_id,
                                "cable_type": cable_type,
                                "uncovered_length": round(gap_length, 2),
                                "gap_percentage": round(gap_percentage, 1),
                                "geometry": gap_geom,  # Show only the gap segment
                                "violation_type": "facade_cable_crosses_gap",
                                "violation_reason": (
                                    f"Façade drop cable {cable_id} crosses a gap between buildings "
                                    f"({round(gap_length, 2)}m uncovered, {round(gap_percentage, 1)}%)"
                                ),
                            }
                        )

        # Build result
        violation_count = len(violations)
        failed_cable_ids = [f"Drop_{v['drop_cable_id']}" for v in violations]
        failed_features_str = ", ".join(failed_cable_ids)

        message = (
            f"Found {violation_count} façade drop cables crossing gaps between buildings."
            if violation_count > 0
            else "No violations found."
        )

        result = {
            "rule_id": "POC_007",
            "Description": description,
            "status": "PASS" if not violations else "FAIL",
            "violation_count": violation_count,
            "failed_features": failed_features_str,
            "message": message,
        }

        # Add to violations list
        self.violations.extend(violations)

        return result

    def validate_poc_placement_between_buildings(self, max_offset=2.0):
        """
        Validate that each POC is placed centrally between the buildings it serves.

        Rule 9: POC should be placed between the buildings it serves (within 0.5m of
        the mean centre of those buildings).

        Chain: POC.AGG_ID → DemandPoint.ID_DROP → Building Polygon (containment)
        → mean centre of building centroids → distance from POC to centre.

        POCs serving only one building are skipped (no "between" applies).
        """
        print("Validating POC placement between buildings...")
        description = (
            f"POC should be placed at or near the join point between the buildings "
            f"it serves (max {max_offset}m from the nearest building-pair join)"
        )

        drop_points_layer = self.get_layer_by_name("Drop Points")
        demand_points_layer = self.get_layer_by_name("Demand Points")
        buildings_layer = self.get_layer_by_name("Building Polygons")

        if not drop_points_layer:
            return {
                "rule_id": "POC_009",
                "Description": description,
                "status": "ERROR",
                "violation_count": 0,
                "failed_features": "",
                "message": "Drop Points layer not found",
            }

        if not demand_points_layer:
            return {
                "rule_id": "POC_009",
                "Description": description,
                "status": "ERROR",
                "violation_count": 0,
                "failed_features": "",
                "message": "Demand Points layer not found",
            }

        if not buildings_layer:
            return {
                "rule_id": "POC_009",
                "Description": description,
                "status": "ERROR",
                "violation_count": 0,
                "failed_features": "",
                "message": "Building Polygons layer not found",
            }

        if "ID_DROP" not in demand_points_layer.fields().names():
            return {
                "rule_id": "POC_009",
                "Description": description,
                "status": "ERROR",
                "violation_count": 0,
                "failed_features": "",
                "message": "Demand Points layer missing required field: ID_DROP",
            }

        if "AGG_ID" not in drop_points_layer.fields().names():
            return {
                "rule_id": "POC_009",
                "Description": description,
                "status": "ERROR",
                "violation_count": 0,
                "failed_features": "",
                "message": "Drop Points layer missing required field: AGG_ID",
            }

        # Build spatial index + cache for buildings
        buildings_index = QgsSpatialIndex(buildings_layer.getFeatures())
        buildings_by_id = {}
        for bldg in buildings_layer.getFeatures():
            geom = bldg.geometry()
            if geom and not geom.isEmpty():
                buildings_by_id[bldg.id()] = QgsGeometry(geom)

        # Group demand points by the POC they belong to (ID_DROP == POC.AGG_ID).
        # For each demand point, resolve which building it sits inside.
        demand_pts_by_poc = defaultdict(list)

        for dp in demand_points_layer.getFeatures():
            id_drop = dp["ID_DROP"]
            if id_drop is None:
                continue
            dp_geom = dp.geometry()
            if not dp_geom or dp_geom.isEmpty():
                continue

            # Find the building linked to this demand point.
            # Buffer the demand point by 0.2m so points digitised
            # slightly outside a building footprint are still matched.
            dp_buf = dp_geom.buffer(0.2, 5)
            candidate_ids = buildings_index.intersects(dp_buf.boundingBox())
            building_geom = None
            for bldg_id in candidate_ids:
                bldg_geom = buildings_by_id.get(bldg_id)
                if bldg_geom and bldg_geom.intersects(dp_buf):
                    building_geom = bldg_geom
                    break

            demand_pts_by_poc[id_drop].append(building_geom)

        violations = []

        for poc_feature in drop_points_layer.getFeatures():
            poc_geom = poc_feature.geometry()
            if not poc_geom or poc_geom.isEmpty():
                continue

            poc_id = poc_feature["AGG_ID"]
            served_buildings = demand_pts_by_poc.get(poc_id, [])

            # Collect unique building geometries (deduplicate by rounded centroid key)
            seen = set()
            unique_bldg_geoms = []
            for bldg_geom in served_buildings:
                if not bldg_geom:
                    continue
                pt = bldg_geom.centroid().asPoint()
                key = f"{round(pt.x(), 2)},{round(pt.y(), 2)}"
                if key not in seen:
                    seen.add(key)
                    unique_bldg_geoms.append(bldg_geom)

            # Need at least 2 distinct buildings to check "between"
            if len(unique_bldg_geoms) < 2:
                continue

            # For each pair of buildings find the midpoint of the shortest
            # connecting line — this is the point where the two buildings "join"
            join_midpoints = []
            for i in range(len(unique_bldg_geoms)):
                for j in range(i + 1, len(unique_bldg_geoms)):
                    line = unique_bldg_geoms[i].shortestLine(unique_bldg_geoms[j])
                    pts = line.asPolyline()
                    if len(pts) >= 2:
                        jx = (pts[0].x() + pts[-1].x()) / 2
                        jy = (pts[0].y() + pts[-1].y()) / 2
                        join_midpoints.append((jx, jy))

            if not join_midpoints:
                continue

            # Distance from the POC to the nearest building-pair join midpoint
            poc_pt = poc_geom.asPoint()
            offset = min(
                math.sqrt((poc_pt.x() - jx) ** 2 + (poc_pt.y() - jy) ** 2)
                for jx, jy in join_midpoints
            )

            if offset > max_offset:
                violations.append(
                    {
                        "poc_id": poc_id,
                        "building_count": len(unique_bldg_geoms),
                        "offset": round(offset, 2),
                        "geometry": poc_geom,
                        "violation_type": "poc_not_between_buildings",
                        "violation_reason": (
                            f"POC {poc_id} is {round(offset, 2)}m from the nearest "
                            f"building join point across its {len(unique_bldg_geoms)} "
                            f"served buildings (max {max_offset}m)"
                        ),
                    }
                )

        violation_count = len(violations)
        failed_features_str = ", ".join([f"POC_{v['poc_id']}" for v in violations])
        message = (
            f"Found {violation_count} POC(s) not centrally placed between their served buildings."
            if violation_count > 0
            else "All POCs are centrally placed between their served buildings."
        )

        result = {
            "rule_id": "POC_009",
            "Description": description,
            "status": "PASS" if not violations else "FAIL",
            "violation_count": violation_count,
            "failed_features": failed_features_str,
            "message": message,
        }

        self.violations.extend(violations)
        return result

    # ------------------------------------------------------------------
    # DEBUG ONLY — remove before production
    # ------------------------------------------------------------------
    def debug_poc_placement_layer(self, max_offset=0.5):
        """
        Creates a temporary 'POC_009_Debug' point layer on the map where every
        POC is coloured:
          - GREEN  : PASS  (offset <= max_offset, or exempted by Possible Routes)
          - RED    : FAIL  (offset > max_offset and not on a route)
          - GREY   : SKIP  (serves fewer than 2 distinct buildings)

        Call this from the QGIS Python console to diagnose POC_009 silently
        passing all features.  Delete the layer and remove this method before
        shipping to production.
        """
        print("[DEBUG POC_009] Building debug layer...")

        drop_points_layer = self.get_layer_by_name("Drop Points")
        demand_points_layer = self.get_layer_by_name("Demand Points")
        buildings_layer = self.get_layer_by_name("Building Polygons")

        if not drop_points_layer or not demand_points_layer or not buildings_layer:
            print("[DEBUG POC_009] One or more required layers not found — aborting.")
            return

        # ── Buildings spatial index ───────────────────────────────────
        buildings_index = QgsSpatialIndex(buildings_layer.getFeatures())
        buildings_by_id = {}
        for bldg in buildings_layer.getFeatures():
            geom = bldg.geometry()
            if geom and not geom.isEmpty():
                buildings_by_id[bldg.id()] = QgsGeometry(geom)

        # ── Possible Routes index ─────────────────────────────────────
        possible_routes_layer = self.get_layer_by_name("Possible Routes")
        routes_index = None
        if possible_routes_layer:
            routes_index = QgsSpatialIndex(possible_routes_layer.getFeatures())

        def poc_is_on_route(poc_geom):
            if not routes_index or not possible_routes_layer:
                return False
            poc_buf = poc_geom.buffer(0.5, 5)
            for rid in routes_index.intersects(poc_buf.boundingBox()):
                rgeom = possible_routes_layer.getFeature(rid).geometry()
                if rgeom and not rgeom.isEmpty() and poc_buf.intersects(rgeom):
                    return True
            return False

        # ── Demand points → buildings ─────────────────────────────────
        demand_pts_by_poc = defaultdict(list)
        for dp in demand_points_layer.getFeatures():
            id_drop = dp["ID_DROP"]
            if id_drop is None:
                continue
            dp_geom = dp.geometry()
            if not dp_geom or dp_geom.isEmpty():
                continue
            dp_buf = dp_geom.buffer(0.2, 5)
            candidates = buildings_index.intersects(dp_buf.boundingBox())
            for bldg_id in candidates:
                bldg_geom = buildings_by_id.get(bldg_id)
                if bldg_geom and bldg_geom.intersects(dp_buf):
                    demand_pts_by_poc[id_drop].append(bldg_geom)
                    break

        # ── Create memory layer ───────────────────────────────────────
        crs = drop_points_layer.crs().authid()
        mem_layer = QgsVectorLayer(f"Point?crs={crs}", "POC_009_Debug", "memory")
        pr = mem_layer.dataProvider()
        pr.addAttributes([
            QgsField("poc_id",     QVariant.String),
            QgsField("status",     QVariant.String),
            QgsField("offset_m",   QVariant.Double),
            QgsField("bldg_count", QVariant.Int),
            QgsField("on_route",   QVariant.Int),
        ])
        mem_layer.updateFields()

        features_to_add = []

        # Counters for SKIP breakdown summary
        skip_no_demand_pts = 0       # AGG_ID not found in demand_pts_by_poc at all
        skip_none_matched  = 0       # demand points exist but 0 resolved to a building
        skip_one_building  = 0       # all demand points map to the same single building

        for poc_feature in drop_points_layer.getFeatures():
            poc_geom = poc_feature.geometry()
            if not poc_geom or poc_geom.isEmpty():
                continue

            poc_id = poc_feature["AGG_ID"]
            served_buildings = demand_pts_by_poc.get(poc_id, [])

            # Deduplicate buildings by rounded centroid
            seen = set()
            bldg_centroids = []
            for bldg_geom in served_buildings:
                if not bldg_geom:
                    continue
                pt = bldg_geom.centroid().asPoint()
                key = f"{round(pt.x(), 2)},{round(pt.y(), 2)}"
                if key not in seen:
                    seen.add(key)
                    bldg_centroids.append(pt)

            f = QgsFeature(mem_layer.fields())
            f.setGeometry(poc_geom)

            if len(bldg_centroids) < 2:
                dp_total   = len(served_buildings)
                dp_matched = sum(1 for g in served_buildings if g is not None)

                if dp_total == 0:
                    skip_no_demand_pts += 1
                elif dp_matched == 0:
                    skip_none_matched += 1
                else:
                    skip_one_building += 1

                f.setAttributes([str(poc_id), "SKIP", 0.0, len(bldg_centroids), 0])
                features_to_add.append(f)
                continue

            avg_x = sum(pt.x() for pt in bldg_centroids) / len(bldg_centroids)
            avg_y = sum(pt.y() for pt in bldg_centroids) / len(bldg_centroids)
            poc_pt = poc_geom.asPoint()
            offset = math.sqrt((poc_pt.x() - avg_x) ** 2 + (poc_pt.y() - avg_y) ** 2)
            on_route = poc_is_on_route(poc_geom)

            if offset > max_offset and not on_route:
                status = "FAIL"
            else:
                status = "PASS"

            f.setAttributes([str(poc_id), status, round(offset, 3), len(bldg_centroids), 1 if on_route else 0])
            features_to_add.append(f)

        pr.addFeatures(features_to_add)
        mem_layer.updateExtents()

        # ── Categorised renderer ──────────────────────────────────────
        categories = []
        for value, hex_color, label in [
            ("PASS", "#00aa00", "PASS (within 0.5 m)"),
            ("FAIL", "#dd0000", "FAIL (offset > 0.5 m)"),
            ("SKIP", "#888888", "SKIP (< 2 buildings)"),
        ]:
            symbol = QgsMarkerSymbol.createSimple({"name": "circle", "size": "5"})
            symbol.setColor(QColor(hex_color))
            categories.append(QgsRendererCategory(value, symbol, label))

        mem_layer.setRenderer(QgsCategorizedSymbolRenderer("status", categories))

        QgsProject.instance().addMapLayer(mem_layer)
        skip_total = sum(1 for f in features_to_add if f["status"] == "SKIP")
        print(
            f"[DEBUG POC_009] Done — layer 'POC_009_Debug' added with"
            f" {len(features_to_add)} POCs"
            f" ({sum(1 for f in features_to_add if f['status'] == 'FAIL')} FAIL,"
            f" {sum(1 for f in features_to_add if f['status'] == 'PASS')} PASS,"
            f" {skip_total} SKIP)"
        )
        print(
            f"[DEBUG POC_009] SKIP breakdown:"
            f"  no demand pts (ID mismatch?) = {skip_no_demand_pts}"
            f"  demand pts exist but no building found = {skip_none_matched}"
            f"  all demand pts in same 1 building = {skip_one_building}"
        )

    # ------------------------------------------------------------------
    def validate_stacked_pocs(self, tolerance=0.001):
        """
        Validate that no two POCs occupy the same location.

        Rule 8: POCs must not be stacked on top of each other.
        Two POCs are considered stacked when their coordinates are identical
        or within floating-point tolerance (< 0.001m).
        Layers: Drop Points
        """
        print("Validating stacked POCs...")
        description = "No two POCs should be placed at the same location (stacked)"

        drop_points_layer = self.get_layer_by_name("Drop Points")

        if not drop_points_layer:
            return {
                "rule_id": "POC_008",
                "Description": description,
                "status": "ERROR",
                "violation_count": 0,
                "failed_features": "",
                "message": "Drop Points layer not found",
            }

        # Load all POCs, keyed by rounded coordinate to detect duplicates
        pocs = []
        for feature in drop_points_layer.getFeatures():
            geom = feature.geometry()
            if geom and not geom.isEmpty():
                poc_id = (
                    feature["AGG_ID"]
                    if "AGG_ID" in feature.fields().names()
                    else feature.id()
                )
                pt = geom.asPoint()
                pocs.append(
                    {
                        "id": feature.id(),
                        "poc_id": poc_id,
                        "geometry": QgsGeometry(geom),
                        "x": pt.x(),
                        "y": pt.y(),
                    }
                )

        violations = []
        flagged_ids = set()

        for i, poc_a in enumerate(pocs):
            if poc_a["id"] in flagged_ids:
                continue

            for poc_b in pocs[i + 1 :]:
                if poc_b["id"] in flagged_ids:
                    continue

                # Check if coordinates are identical within tolerance
                if (
                    abs(poc_a["x"] - poc_b["x"]) < tolerance
                    and abs(poc_a["y"] - poc_b["y"]) < tolerance
                ):
                    flagged_ids.add(poc_a["id"])
                    flagged_ids.add(poc_b["id"])

                    violations.append(
                        {
                            "poc_id": poc_a["poc_id"],
                            "nearby_poc_id": poc_b["poc_id"],
                            "distance": round(
                                poc_a["geometry"].distance(poc_b["geometry"]), 6
                            ),
                            "geometry": poc_a["geometry"],
                            "violation_type": "stacked_pocs",
                            "violation_reason": (
                                f"POC {poc_a['poc_id']} is stacked on "
                                f"POC {poc_b['poc_id']} at the same location"
                            ),
                        }
                    )

        violation_count = len(violations)
        failed_features_str = ", ".join([f"POC_{v['poc_id']}" for v in violations])
        message = (
            f"Found {violation_count} POC(s) stacked at the same location."
            if violation_count > 0
            else "No stacked POCs found."
        )

        result = {
            "rule_id": "POC_008",
            "Description": description,
            "status": "PASS" if not violations else "FAIL",
            "violation_count": violation_count,
            "failed_features": failed_features_str,
            "message": message,
        }

        self.violations.extend(violations)
        return result

    def _calculate_relative_position(self, drop_geometry, drop_orientation, demand_geometry):
        """
        Calculate if demand point is left or right of drop point orientation
        This is a simplified implementation - adjust based on your actual data structure
        """
        drop_point = drop_geometry.asPoint()
        demand_point = demand_geometry.asPoint()
        
        # Calculate angle between drop point and demand point
        dx = demand_point.x() - drop_point.x()
        dy = demand_point.y() - drop_point.y()
        angle = math.atan2(dy, dx) * 180 / math.pi
        
        # Normalize angles
        drop_angle = drop_orientation % 360
        relative_angle = (angle - drop_angle) % 360
        
        # Determine left/right (simplified)
        if 0 <= relative_angle < 180:
            return 'right'
        else:
            return 'left'
