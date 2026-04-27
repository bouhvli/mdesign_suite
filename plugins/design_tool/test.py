from qgis.core import ( # type: ignore
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsField, QgsFields, QgsSpatialIndex,
)
from qgis.PyQt.QtCore import QVariant, QElapsedTimer, QCoreApplication # type: ignore
import networkx as nx
from shapely import wkt
from shapely.geometry import LineString, Point
from shapely.ops import linemerge, unary_union
from collections import defaultdict
import math

# -------------------------------
# CONFIGURATION
# -------------------------------
LAYER_NAMES = {
    'dp': 'OUT_DistributionPoints',
    'distribution_points': 'OUT_DistributionPoints',
    'drops': 'OUT_DropPoints',
    'trenches': 'IN_PossibleTrenches',
    'crossings': 'IN_Crossings',
    'facade': 'IN_FacadeLines',
    'transitions': 'IN_Transitions',
    'demand': 'IN_DemandPoints',
    'clusters': 'OUT_DistributionClusters'
}
TARGET_CRS = "EPSG:31370"  # Belgian Lambert 72
MAX_DROPS_PER_CLUSTER = 11
MAX_DROPS_PER_ROUTE = 22
MAX_CABLES_PER_DIRECTION = 4
SNAP_TOLERANCE = 10.0  # meters
CROSSING_CONNECTION_TOLERANCE = 15.0
MIN_EDGE_LENGTH = 0.1  # meters
COORDINATE_PRECISION = 3  # decimal places for EPSG:31370
CLUSTER_BUFFER = 10.0  # meters buffer for cluster boundary operations
MAX_WORKERS = 4  # For parallel processing of clusters

# -------------------------------
# HELPER FUNCTIONS
# -------------------------------
class Timer:
    """Context manager for timing operations."""
    def __init__(self, message=""):
        self.message = message
        self.timer = QElapsedTimer()
    
    def __enter__(self):
        if self.message:
            print(f"⏱️ {self.message}...")
        self.timer.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = self.timer.elapsed() / 1000.0
        if exc_type is None:
            if self.message:
                print(f"   ✓ {self.message} completed in {elapsed:.2f}s")
        return False

def validate_crs(layer, layer_name):
    """Validate and transform layer CRS to target CRS."""
    if layer is None:
        return False
    
    layer_crs = layer.crs()
    
    if not layer_crs.isValid():
        print(f" ⚠️ Layer '{layer_name}' has invalid CRS")
        return False
    
    crs_authid = layer_crs.authid()
    if not crs_authid:
        print(f" ⚠️ Layer '{layer_name}' has no CRS set")
        return False
    
    if crs_authid != TARGET_CRS:
        print(f" ⚠️ Layer '{layer_name}' CRS is {crs_authid}, expected {TARGET_CRS}")
        return False
    
    return True

def layer_from_name(name, required=True):
    """Get layer by name with validation and error handling."""
    try:
        layers = QgsProject.instance().mapLayersByName(name)
        if not layers:
            if required:
                raise ValueError(f"Layer '{name}' not found in QGIS project.")
            print(f"   ⚠️ Layer '{name}' not found")
            return None
        
        layer = layers[0]
        
        # Check if layer is empty
        if layer.featureCount() == 0:
            print(f"   ⚠️ Layer '{name}' is empty")
        
        return layer
    except Exception as e:
        if required:
            raise
        print(f"   ⚠️ Could not load layer '{name}': {e}")
        return None

def safe_geometry_conversion(func):
    """Decorator for safe geometry conversion."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f" ⚠️ Geometry conversion error in {func.__name__}: {e}")
            return None
    return wrapper

@safe_geometry_conversion
def qgs_geometry_to_shapely(geom):
    """Convert QgsGeometry to Shapely."""
    if geom is None or geom.isEmpty():
        return None
    wkt_str = geom.asWkt()
    if not wkt_str or 'EMPTY' in wkt_str.upper():
        return None
    return wkt.loads(wkt_str)

@safe_geometry_conversion
def shapely_to_qgs_geometry(shapely_geom):
    """Convert Shapely to QgsGeometry."""
    if shapely_geom is None or shapely_geom.is_empty:
        return QgsGeometry()
    return QgsGeometry.fromWkt(shapely_geom.wkt)

def round_coord(coord, precision=COORDINATE_PRECISION):
    """Round coordinate to specified precision."""
    return tuple(round(c, precision) for c in coord)

def create_spatial_index(layer):
    """Create spatial index for layer."""
    if layer is None:
        return None
    index = QgsSpatialIndex()
    for feature in layer.getFeatures():
        index.addFeature(feature)
    return index

def assign_points_to_clusters(points_layer, clusters_layer, buffer_distance=0.0):
    """
    Assign points to clusters using spatial intersection.
    Returns dict: {cluster_id: [point_features]}
    """
    if points_layer is None or clusters_layer is None:
        return {}
    
    with Timer(f"Assigning {points_layer.featureCount()} points to clusters"):
        assignments = defaultdict(list)
        clusters_index = create_spatial_index(clusters_layer)
        
        if clusters_index is None:
            return assignments
        
        for point_feat in points_layer.getFeatures():
            point_geom = point_feat.geometry()
            if point_geom.isEmpty():
                continue
            
            # Find clusters that intersect the point (or buffered point)
            if buffer_distance > 0:
                search_geom = point_geom.buffer(buffer_distance, 5)
            else:
                search_geom = point_geom
            
            # Get candidate cluster IDs
            candidate_ids = clusters_index.intersects(search_geom.boundingBox())
            
            # Check exact intersection
            for cluster_id in candidate_ids:
                cluster_feat = clusters_layer.getFeature(cluster_id)
                if cluster_feat is None:
                    continue
                    
                cluster_geom = cluster_feat.geometry()
                
                if search_geom.intersects(cluster_geom):
                    assignments[cluster_id].append(point_feat)
                    break  # Point belongs to first matching cluster
        
        return assignments

def extract_features_within_cluster(source_layer, cluster_geometry):
    """
    Extract features from source_layer that are within cluster boundary.
    """
    features = []
    
    if source_layer is None:
        return features
    
    cluster_poly = qgs_geometry_to_shapely(cluster_geometry)
    if not cluster_poly:
        return features
    
    # Create buffered polygon for inclusion
    buffered_poly = cluster_poly.buffer(CLUSTER_BUFFER, 5)
    
    for feat in source_layer.getFeatures():
        feat_geom = feat.geometry()
        if feat_geom.isEmpty():
            continue
        
        shp_geom = qgs_geometry_to_shapely(feat_geom)
        if shp_geom and shp_geom.intersects(buffered_poly):
            features.append(feat)
    
    return features

def snap_point_to_graph(G, point, tolerance):
    """Snap a point to the nearest edge in graph."""
    min_dist = float('inf')
    best_proj = None
    best_edge = None
    
    for u, v, data in G.edges(data=True):
        if 'geom' in data:
            line = data['geom']
            dist = point.distance(line)
            if dist < min_dist:
                min_dist = dist
                proj = line.interpolate(line.project(point))
                best_proj = proj
                best_edge = (u, v, data)
    
    if min_dist <= tolerance and best_proj and best_edge:
        u, v, data = best_edge
        new_node = round_coord((best_proj.x, best_proj.y))
        
        # Check if projection is essentially on u or v
        EPS = 0.001
        if Point(new_node).distance(Point(u)) < EPS:
            return u
        elif Point(new_node).distance(Point(v)) < EPS:
            return v
        else:
            # Split the edge
            G.remove_edge(u, v)
            G.add_node(new_node)
            
            geom1 = LineString([u, new_node])
            len1 = geom1.length
            G.add_edge(u, new_node, geom=geom1, length=len1, original_length=len1,
                      fid=data.get('fid', -1), source=data.get('source', 'split'))
            
            geom2 = LineString([new_node, v])
            len2 = geom2.length
            G.add_edge(new_node, v, geom=geom2, length=len2, original_length=len2,
                      fid=data.get('fid', -1), source=data.get('source', 'split'))
            return new_node
    
    return None

def ensure_cluster_connectivity(G, dp_nodes, drop_nodes, tolerance):
    """Ensure all points are connected within cluster."""
    all_terminals = [n[0] for n in dp_nodes] + [n[0] for n in drop_nodes]
    
    for terminal in all_terminals:
        if terminal not in G:
            # Try to connect to nearest node
            nearest_node = None
            min_dist = float('inf')
            terminal_point = Point(terminal)
            
            for node in G.nodes():
                node_point = Point(node)
                dist = terminal_point.distance(node_point)
                if dist < min_dist and dist <= tolerance:
                    min_dist = dist
                    nearest_node = node
            
            if nearest_node:
                edge_geom = LineString([terminal, nearest_node])
                G.add_edge(terminal, nearest_node,
                          geom=edge_geom,
                          length=min_dist,
                          original_length=min_dist,
                          fid=-2,
                          source='cluster_connection')
    
    return G

def union_network_layers(layers_dict):
    """
    Union all network layers (trenches, crossings, facade, transitions) into a single layer.
    Returns a temporary memory layer with all network features merged.
    """
    print("\n🔗 UNIONING NETWORK LAYERS...")
    
    # Create a temporary memory layer for the union
    union_layer = QgsVectorLayer(f"MultiLineString?crs={TARGET_CRS}", "unified_network", "memory")
    union_provider = union_layer.dataProvider()
    
    # Add fields to track original source
    union_fields = QgsFields()
    union_fields.append(QgsField("original_id", QVariant.Int))
    union_fields.append(QgsField("source_layer", QVariant.String))
    union_fields.append(QgsField("source_fid", QVariant.Int))
    union_provider.addAttributes(union_fields)
    union_layer.updateFields()
    
    total_features = 0
    
    # Add features from each network layer
    layer_order = ['trenches', 'crossings', 'facade', 'transitions']
    
    for layer_name in layer_order:
        if layer_name in layers_dict and layers_dict[layer_name] is not None:
            layer = layers_dict[layer_name]
            if layer.featureCount() > 0:
                print(f"   Adding {layer.featureCount()} features from {layer_name}")
                
                for feat in layer.getFeatures():
                    geom = feat.geometry()
                    if not geom.isEmpty():
                        new_feat = QgsFeature(union_fields)
                        new_feat.setGeometry(geom)
                        new_feat.setAttributes([
                            total_features + 1,
                            layer_name,
                            feat.id()
                        ])
                        union_provider.addFeature(new_feat)
                        total_features += 1
    
    print(f"   Created unified network with {total_features} features")
    
    # Optional: Perform geometric union to merge overlapping lines
    # This is computationally expensive but creates a cleaner network
    if total_features > 0:
        print("   Performing geometric union to merge overlapping segments...")
        try:
            # Collect all geometries
            all_geoms = []
            for feat in union_layer.getFeatures():
                geom = qgs_geometry_to_shapely(feat.geometry())
                if geom:
                    all_geoms.append(geom)
            
            # Union all geometries
            if all_geoms:
                unioned = unary_union(all_geoms)
                
                # Create new layer with unioned geometries
                final_layer = QgsVectorLayer(f"MultiLineString?crs={TARGET_CRS}", "unified_network_merged", "memory")
                final_provider = final_layer.dataProvider()
                final_provider.addAttributes(union_fields)
                final_layer.updateFields()
                
                # Add unioned geometries
                if unioned.geom_type == 'LineString':
                    features = [unioned]
                elif unioned.geom_type == 'MultiLineString':
                    features = list(unioned.geoms)
                else:
                    features = []
                
                for i, geom in enumerate(features):
                    if geom.length >= MIN_EDGE_LENGTH:
                        new_feat = QgsFeature(union_fields)
                        new_feat.setGeometry(shapely_to_qgs_geometry(geom))
                        new_feat.setAttributes([i+1, 'union', i+1])
                        final_provider.addFeature(new_feat)
                
                print(f"   Created {len(features)} merged segments")
                return final_layer
                
        except Exception as e:
            print(f"   ⚠️ Could not perform geometric union: {e}")
            print("   Using original features instead")
    
    return union_layer

def build_cluster_network_graph(cluster_id, cluster_geometry, unified_network_layer, dp_features, drop_features):
    """
    Build network graph for a specific cluster from unified network layer.
    DPs are added as nodes in the graph (not just terminals).
    """
    with Timer(f"Building network for cluster {cluster_id}"):
        # Extract network features within cluster boundary from unified layer
        network_features = extract_features_within_cluster(unified_network_layer, cluster_geometry)
        
        if not network_features:
            print(f" ⚠️ No network features in cluster {cluster_id}")
            return None, [], []
        
        # Filter out invalid geometries
        valid_lines = []
        for feat in network_features:
            geom = qgs_geometry_to_shapely(feat.geometry())
            if geom is None or geom.is_empty:
                continue
            if geom.geom_type == 'LineString' and geom.length > MIN_EDGE_LENGTH:
                valid_lines.append((geom, feat))
            elif geom.geom_type == 'MultiLineString':
                for part in geom.geoms:
                    if part.length > MIN_EDGE_LENGTH:
                        # Create a virtual feature for each part
                        virtual_feat = QgsFeature(feat.fields())
                        virtual_feat.setAttributes(feat.attributes())
                        valid_lines.append((part, virtual_feat))
        
        if not valid_lines:
            print(f" ⚠️ No valid network lines in cluster {cluster_id}")
            return None, [], []
        
        # Build graph from split segments
        G = nx.Graph()
        for line, feat in valid_lines:
            coords = list(line.coords)
            for i in range(len(coords) - 1):
                n1 = round_coord(coords[i])
                n2 = round_coord(coords[i+1])
                if n1 == n2:
                    continue
                seg = LineString([n1, n2])
                weight = seg.length
                
                # Get source information from feature attributes
                source_layer = feat.attribute('source_layer') if feat.fields().indexFromName('source_layer') >= 0 else 'unknown'
                source_fid = feat.attribute('source_fid') if feat.fields().indexFromName('source_fid') >= 0 else -1
                
                G.add_edge(n1, n2, geom=seg, length=weight, original_length=seg.length,
                          fid=source_fid, source=source_layer)
        
        print(f"   Graph has {G.number_of_nodes()} nodes and {G.number_of_edges()} edges")
        
        # Add DPs as SPECIAL NODES in the graph
        dp_nodes = []
        for dp_feat in dp_features:
            pt_geom = dp_feat.geometry()
            if pt_geom.isEmpty():
                continue
            pt = pt_geom.asPoint()
            dp_coord = round_coord((pt.x(), pt.y()))
            
            # Check if DP coordinate already exists as a network node
            if dp_coord in G.nodes():
                # DP is already a network node (e.g., on a crossing endpoint)
                G.nodes[dp_coord]['is_dp'] = True
                G.nodes[dp_coord]['dp_feature'] = dp_feat
                G.nodes[dp_coord]['dp_id'] = dp_feat.id()
                dp_nodes.append((dp_coord, 'dp', dp_feat.id(), dp_feat))
                print(f"   DP {dp_feat.id()} is at existing network node {dp_coord}")
            else:
                # Snap DP to nearest edge
                shp_pt = Point(pt.x(), pt.y())
                snapped_node = snap_point_to_graph(G, shp_pt, SNAP_TOLERANCE)
                if snapped_node:
                    # Mark the snapped node as a DP
                    G.nodes[snapped_node]['is_dp'] = True
                    G.nodes[snapped_node]['dp_feature'] = dp_feat
                    G.nodes[snapped_node]['dp_id'] = dp_feat.id()
                    dp_nodes.append((snapped_node, 'dp', dp_feat.id(), dp_feat))
                else:
                    print(f" ⚠️ Could not snap DP {dp_feat.id()} in cluster {cluster_id}")
        
        # Add drops as terminal nodes
        drop_nodes = []
        for drop_feat in drop_features:
            pt_geom = drop_feat.geometry()
            if pt_geom.isEmpty():
                continue
            pt = pt_geom.asPoint()
            shp_pt = Point(pt.x(), pt.y())
            
            snapped_node = snap_point_to_graph(G, shp_pt, SNAP_TOLERANCE)
            if snapped_node:
                G.nodes[snapped_node]['terminal'] = ('drop', drop_feat.id(), drop_feat)
                drop_nodes.append((snapped_node, 'drop', drop_feat.id(), drop_feat))
            else:
                print(f" ⚠️ Could not snap drop {drop_feat.id()} in cluster {cluster_id}")
        
        if not dp_nodes or not drop_nodes:
            print(f" ⚠️ Cluster {cluster_id}: Missing DPs or drops")
            return None, [], []
        
        # Debug: Check if any DP is on a crossing
        print(f"   Checking DP locations:")
        for dp_node, dp_tag, dp_fid, dp_feat in dp_nodes:
            # Check edges connected to DP
            crossing_edges = 0
            for neighbor in G.neighbors(dp_node):
                edge_data = G.get_edge_data(dp_node, neighbor)
                if edge_data and 'crossing' in edge_data.get('source', '').lower():
                    crossing_edges += 1
            
            print(f"      DP {dp_fid} at {dp_node}: connected to {crossing_edges} crossing edges")
        
        return G, dp_nodes, drop_nodes

def calculate_angle(point1, point2):
    """Calculate angle in degrees from point1 to point2."""
    dx = point2[0] - point1[0]
    dy = point2[1] - point1[1]
    angle = math.degrees(math.atan2(dy, dx))
    return angle % 360

def angle_difference(angle1, angle2):
    """Calculate smallest difference between two angles."""
    diff = abs(angle1 - angle2) % 360
    return min(diff, 360 - diff)

def shortest_path_geometry(G, source, target):
    """Reconstruct path geometry from actual edge geometries."""
    try:
        nodes = nx.shortest_path(G, source=source, target=target, weight='length')
        if len(nodes) < 2:
            return None
        
        geoms = []
        for i in range(len(nodes) - 1):
            edge_data = G.get_edge_data(nodes[i], nodes[i+1])
            if edge_data and 'geom' in edge_data:
                geoms.append(edge_data['geom'])
            else:
                geoms.append(LineString([nodes[i], nodes[i+1]]))
        
        if not geoms:
            return None
        
        if len(geoms) == 1:
            return geoms[0]
        
        merged = linemerge(geoms)
        if merged.geom_type == 'LineString':
            return merged
        elif merged.geom_type == 'MultiLineString':
            merged2 = linemerge(list(merged.geoms))
            if merged2.geom_type == 'LineString':
                return merged2
            coords = []
            for line in merged.geoms:
                coords.extend(list(line.coords))
            return LineString(coords)
        
        return None
    except nx.NetworkXNoPath:
        return None
    except Exception as e:
        print(f" ⚠️ Path geometry error: {e}")
        return None

def find_paths_in_cluster(G, dp_nodes, drop_nodes):
    """Find shortest paths within cluster."""
    all_paths = defaultdict(dict)
    
    for dp_node, dp_tag, dp_fid, dp_feat in dp_nodes:
        try:
            paths = nx.single_source_dijkstra_path(G, dp_node, weight='length')
            lengths = nx.single_source_dijkstra_path_length(G, dp_node, weight='length')
            
            drop_paths = {}
            for target_node, path in paths.items():
                if target_node in G.nodes and 'terminal' in G.nodes[target_node]:
                    tag, fid, feat = G.nodes[target_node]['terminal']
                    if tag == 'drop':
                        drop_paths[fid] = {
                            'path': path,
                            'distance': lengths[target_node],
                            'node': target_node,
                            'feature': feat
                        }
            
            all_paths[dp_fid] = drop_paths
            
        except Exception as e:
            print(f" Error finding paths for DP {dp_fid}: {e}")
            all_paths[dp_fid] = {}
    
    return all_paths

def assign_drops_to_dps(all_paths, dp_fids, drop_fids):
    """Assign each drop to its nearest DP within cluster."""
    dp_assignments = defaultdict(list)
    unassigned_drops = set(drop_fids)
    
    for drop_fid in drop_fids:
        nearest_dp = None
        min_distance = float('inf')
        best_path_info = None
        
        for dp_fid in dp_fids:
            if dp_fid in all_paths and drop_fid in all_paths[dp_fid]:
                path_info = all_paths[dp_fid][drop_fid]
                if path_info['distance'] < min_distance:
                    min_distance = path_info['distance']
                    nearest_dp = dp_fid
                    best_path_info = path_info
        
        if nearest_dp is not None:
            dp_assignments[nearest_dp].append({
                'drop_fid': drop_fid,
                'distance': min_distance,
                'path': best_path_info['path'],
                'node': best_path_info['node'],
                'feature': best_path_info['feature']
            })
            unassigned_drops.remove(drop_fid)
    
    return dp_assignments, unassigned_drops

def group_drops_by_direction(G, dp_node, drops_assigned, max_cables_per_dir):
    """Group drops by direction from DP."""
    if not drops_assigned:
        return {}
    
    drop_directions = {}
    for drop in drops_assigned:
        path = drop['path']
        if len(path) >= 2:
            angle = calculate_angle(path[0], path[1])
            drop_directions[drop['drop_fid']] = angle
    
    direction_groups = defaultdict(list)
    processed = set()
    
    # Group drops with similar angles (within 30 degrees)
    for drop1_fid, angle1 in drop_directions.items():
        if drop1_fid in processed:
            continue
        
        drop1_info = next(d for d in drops_assigned if d['drop_fid'] == drop1_fid)
        group = [drop1_info]
        processed.add(drop1_fid)
        
        for drop2_fid, angle2 in drop_directions.items():
            if drop2_fid in processed:
                continue
            if angle_difference(angle1, angle2) < 30:
                drop2_info = next(d for d in drops_assigned if d['drop_fid'] == drop2_fid)
                group.append(drop2_info)
                processed.add(drop2_fid)
        
        avg_angle = sum(drop_directions[d['drop_fid']] for d in group) / len(group)
        direction_groups[round(avg_angle)].extend(group)
    
    # Sort drops by distance within each direction
    for angle in direction_groups:
        direction_groups[angle].sort(key=lambda x: x['distance'])
    
    return direction_groups

def create_cables_for_direction(G, dp_node, dp_fid, direction_drops, direction_angle, max_drops_per_cable):
    """Create cables for drops in a specific direction, allowing cables to pass through DP if needed."""
    cables = []
    if not direction_drops:
        return cables
    
    uncovered = set(d['drop_fid'] for d in direction_drops)
    cable_idx = 1
    
    while uncovered and cable_idx <= MAX_CABLES_PER_DIRECTION:
        remaining_drops = [d for d in direction_drops if d['drop_fid'] in uncovered]
        if not remaining_drops:
            break
        
        # SPECIAL CASE: If DP is on a crossing, we might want to create a cable
        # that goes THROUGH the DP along the crossing
        
        # Check if DP is on a crossing edge
        dp_on_crossing = False
        crossing_neighbors = []
        for neighbor in G.neighbors(dp_node):
            edge_data = G.get_edge_data(dp_node, neighbor)
            if edge_data and 'crossing' in edge_data.get('source', '').lower():
                dp_on_crossing = True
                crossing_neighbors.append(neighbor)
        
        if dp_on_crossing and len(crossing_neighbors) >= 1:
            print(f"   DP {dp_fid} is on a crossing - exploring crossing path...")
            
            # Try to find drops reachable by going along the crossing
            for crossing_dir in crossing_neighbors:
                # Find farthest drop in this crossing direction
                drops_in_direction = []
                for drop in remaining_drops:
                    try:
                        # Check if path goes through this crossing direction
                        path = nx.shortest_path(G, source=dp_node, target=drop['node'], weight='length')
                        if len(path) >= 2 and path[1] == crossing_dir:
                            drops_in_direction.append(drop)
                    except:
                        continue
                
                if drops_in_direction:
                    # Create cable along this crossing direction
                    farthest_drop = max(drops_in_direction, key=lambda x: x['distance'])
                    path_nodes = set(farthest_drop['path'])
                    
                    on_path_drops = [d for d in drops_in_direction if d['node'] in path_nodes]
                    on_path_drops.sort(key=lambda x: x['distance'], reverse=True)
                    
                    num_to_assign = min(MAX_DROPS_PER_CLUSTER, len(on_path_drops))
                    assigned_drops = on_path_drops[:num_to_assign]
                    
                    if assigned_drops:
                        farthest_assigned = assigned_drops[0]
                        trunk_geom = shortest_path_geometry(G, dp_node, farthest_assigned['node'])
                        
                        if trunk_geom and not trunk_geom.is_empty:
                            cables.append({
                                'dp_fid': dp_fid,
                                'dp_node': dp_node,
                                'farthest_drop': farthest_assigned,
                                'trunk_geom': trunk_geom,
                                'cluster_size': len(assigned_drops),
                                'drop_fids': [d['drop_fid'] for d in assigned_drops],
                                'drop_nodes': [d['node'] for d in assigned_drops],
                                'direction_angle': direction_angle,
                                'cable_index': cable_idx,
                                'total_drops_in_direction': len(drops_in_direction),
                                'uses_crossing': True  # This cable uses the crossing
                            })
                            
                            for d in assigned_drops:
                                if d['drop_fid'] in uncovered:
                                    uncovered.remove(d['drop_fid'])
                            
                            cable_idx += 1
        
        # Original logic for non-crossing cables
        if uncovered:
            remaining_drops = [d for d in direction_drops if d['drop_fid'] in uncovered]
            if remaining_drops:
                farthest_drop = max(remaining_drops, key=lambda x: x['distance'])
                path_nodes = set(farthest_drop['path'])
                
                on_path_drops = [d for d in remaining_drops if d['node'] in path_nodes]
                on_path_drops.sort(key=lambda x: x['distance'], reverse=True)
                
                num_to_assign = min(MAX_DROPS_PER_CLUSTER, len(on_path_drops))
                assigned_drops = on_path_drops[:num_to_assign]
                
                if assigned_drops:
                    farthest_assigned = assigned_drops[0]
                    trunk_geom = shortest_path_geometry(G, dp_node, farthest_assigned['node'])
                    
                    if trunk_geom and not trunk_geom.is_empty:
                        cables.append({
                            'dp_fid': dp_fid,
                            'dp_node': dp_node,
                            'farthest_drop': farthest_assigned,
                            'trunk_geom': trunk_geom,
                            'cluster_size': len(assigned_drops),
                            'drop_fids': [d['drop_fid'] for d in assigned_drops],
                            'drop_nodes': [d['node'] for d in assigned_drops],
                            'direction_angle': direction_angle,
                            'cable_index': cable_idx,
                            'total_drops_in_direction': len(direction_drops),
                            'uses_crossing': False
                        })
                        
                        for d in assigned_drops:
                            uncovered.remove(d['drop_fid'])
                        
                        cable_idx += 1
    
    return cables

def process_cluster(cluster_feat, dp_assignments, drop_assignments, unified_network_layer):
    """
    Process a single cluster and return cables.
    """
    cluster_id = cluster_feat.id()
    cluster_geom = cluster_feat.geometry()
    
    try:
        # Extract DPs and drops for this cluster
        cluster_dps = dp_assignments.get(cluster_id, [])
        cluster_drops = drop_assignments.get(cluster_id, [])
        
        if not cluster_dps:
            print(f" ⚠️ Cluster {cluster_id}: No DPs assigned")
            return []
        if not cluster_drops:
            print(f" ⚠️ Cluster {cluster_id}: No drops assigned")
            return []
        
        # Build cluster-specific network from unified layer
        G, dp_nodes, drop_nodes = build_cluster_network_graph(
            cluster_id, cluster_geom, unified_network_layer, cluster_dps, cluster_drops
        )
        
        if G is None or len(dp_nodes) == 0 or len(drop_nodes) == 0:
            print(f" ⚠️ Cluster {cluster_id}: Invalid network or no snapped points")
            return []
        
        # Find paths within cluster
        all_paths = find_paths_in_cluster(G, dp_nodes, drop_nodes)
        
        # Assign drops to nearest DP within cluster
        dp_fids = [d[2] for d in dp_nodes]
        drop_fids = [d[2] for d in drop_nodes]
        dp_assignments_cluster, _ = assign_drops_to_dps(all_paths, dp_fids, drop_fids)
        
        # Create cables for each DP in cluster
        cluster_cables = []
        for dp_node, dp_tag, dp_fid, dp_feat in dp_nodes:
            if dp_fid not in dp_assignments_cluster:
                continue
            
            assigned_drops = dp_assignments_cluster[dp_fid]
            if not assigned_drops:
                continue
            
            # Group by direction and create cables
            direction_groups = group_drops_by_direction(G, dp_node, assigned_drops, MAX_CABLES_PER_DIRECTION)
            
            for direction_angle, direction_drops in direction_groups.items():
                cables = create_cables_for_direction(
                    G, dp_node, dp_fid, direction_drops, direction_angle, MAX_DROPS_PER_CLUSTER
                )
                
                for cable in cables:
                    cable['cluster_id'] = cluster_id
                    cluster_cables.append(cable)
        
        print(f" ✓ Cluster {cluster_id}: {len(cluster_cables)} cables created")
        return cluster_cables
        
    except Exception as e:
        print(f" ❌ Error processing cluster {cluster_id}: {e}")
        import traceback
        traceback.print_exc()
        return []

def create_output_layers(all_cables, demand_layer=None):
    """Create output layers with cables and cluster information."""
    
    # Create cable layer
    cable_fields = QgsFields()
    cable_fields.append(QgsField("cluster_id", QVariant.Int))
    cable_fields.append(QgsField("dp_id", QVariant.Int))
    cable_fields.append(QgsField("cluster_size", QVariant.Int))
    cable_fields.append(QgsField("end_drop_id", QVariant.Int))
    cable_fields.append(QgsField("direction", QVariant.Int))
    cable_fields.append(QgsField("cable_idx", QVariant.Int))
    cable_fields.append(QgsField("total_drops", QVariant.Int))
    cable_fields.append(QgsField("drop_ids", QVariant.String))
    cable_fields.append(QgsField("length_m", QVariant.Double))
    
    cable_layer = QgsVectorLayer(f"MultiLineString?crs={TARGET_CRS}", "cluster_cables", "memory")
    cable_dp = cable_layer.dataProvider()
    cable_dp.addAttributes(cable_fields)
    cable_layer.updateFields()
    
    # Add cable features
    cable_features = []
    for cable in all_cables:
        feat = QgsFeature(cable_fields)
        feat.setGeometry(shapely_to_qgs_geometry(cable['trunk_geom']))
        
        drop_ids_str = ','.join(str(fid) for fid in cable['drop_fids'])
        cable_length = cable['trunk_geom'].length if hasattr(cable['trunk_geom'], 'length') else 0
        
        feat.setAttributes([
            int(cable.get('cluster_id', 0)),
            int(cable['dp_fid']),
            int(cable['cluster_size']),
            int(cable['farthest_drop']['drop_fid']),
            int(cable['direction_angle']),
            int(cable['cable_index']),
            cable['total_drops_in_direction'],
            drop_ids_str,
            round(cable_length, 2)
        ])
        cable_features.append(feat)
    
    if cable_features:
        cable_dp.addFeatures(cable_features)
        QgsProject.instance().addMapLayer(cable_layer)
        print(f" ✓ Created 'cluster_cables' layer with {len(cable_features)} cables")
    
    return cable_layer

def generate_cluster_report(cluster_id, cables):
    """Generate report for a cluster."""
    report = {
        'cluster_id': cluster_id,
        'num_cables': len(cables),
        'total_drops': sum(len(c['drop_fids']) for c in cables),
        'total_length': sum(c['trunk_geom'].length for c in cables if hasattr(c['trunk_geom'], 'length')),
        'dp_ids': list(set(c['dp_fid'] for c in cables)),
        'cable_stats': []
    }
    
    for cable in cables:
        report['cable_stats'].append({
            'dp_id': cable['dp_fid'],
            'num_drops': len(cable['drop_fids']),
            'length': cable['trunk_geom'].length if hasattr(cable['trunk_geom'], 'length') else 0,
            'direction': cable['direction_angle']
        })
    
    return report

def identify_problematic_crossing(cluster_id, cables, unified_network_layer, clusters_layer):
    """Identify which crossings aren't being used by cables."""
    print(f"\n🔍 IDENTIFYING UNUSED CROSSINGS IN CLUSTER {cluster_id}...")
    
    # Get cluster geometry
    cluster_feat = clusters_layer.getFeature(cluster_id)
    if not cluster_feat:
        return
    
    cluster_geom = cluster_feat.geometry()
    
    # Get all crossing features in cluster
    crossing_features = []
    for feat in unified_network_layer.getFeatures():
        source = feat.attribute('source_layer') if feat.fields().indexFromName('source_layer') >= 0 else 'unknown'
        if 'crossing' in str(source).lower():
            geom = feat.geometry()
            if not geom.isEmpty() and geom.intersects(cluster_geom):
                crossing_features.append(feat)
    
    print(f"   Found {len(crossing_features)} crossings in cluster")
    
    # Check which crossings are used by cables
    used_crossings = set()
    for cable in cables:
        cable_geom = cable['trunk_geom']
        for crossing_feat in crossing_features:
            cross_geom = qgs_geometry_to_shapely(crossing_feat.geometry())
            if cross_geom and cable_geom.distance(cross_geom) < 1.0:  # Within 1m
                used_crossings.add(crossing_feat.id())
    
    unused_crossings = [f for f in crossing_features if f.id() not in used_crossings]
    
    if unused_crossings:
        print(f"   ⚠️ {len(unused_crossings)} crossings NOT used by cables:")
        for crossing in unused_crossings[:5]:  # Show first 5
            geom = qgs_geometry_to_shapely(crossing.geometry())
            if geom and geom.geom_type == 'LineString':
                print(f"      Crossing {crossing.id()}: {geom.length:.1f}m from {geom.coords[0]} to {geom.coords[-1]}")
    else:
        print(f"   ✓ All crossings are being used")
    
    return unused_crossings

# -------------------------------
# MAIN EXECUTION
# -------------------------------
def main():
    try:
        print("=" * 60)
        print("STARTING CLUSTER-BASED CABLE NETWORK OPTIMIZATION")
        print(f"Target CRS: {TARGET_CRS}")
        print("=" * 60)
        
        overall_timer = QElapsedTimer()
        overall_timer.start()
        
        # DEBUG: Check all layers before starting
        print("\n🔍 Checking available layers...")
        for name in LAYER_NAMES.values():
            layers_found = QgsProject.instance().mapLayersByName(name)
            if layers_found:
                layer = layers_found[0]
                crs = layer.crs().authid() if layer.crs().isValid() else "NO CRS"
                print(f"   {name}: {layer.featureCount()} features, CRS: {crs}")
            else:
                print(f"   {name}: NOT FOUND")
        
        # Step 1: Load distribution clusters layer
        print("\n1️⃣ Loading distribution clusters layer...")
        clusters_layer = layer_from_name(LAYER_NAMES['clusters'], required=True)
        if clusters_layer is None or clusters_layer.featureCount() == 0:
            raise ValueError("Clusters layer is empty or not found")
        
        # Step 2: Load ALL layers first (with validation)
        print("\n2️⃣ Loading and validating all required layers...")
        layers = {}
        
        # Load required layers
        required_layers = ['dp', 'drops', 'trenches', 'crossings', 'facade']
        for key in required_layers:
            layer = layer_from_name(LAYER_NAMES[key], required=True)
            if layer is None:
                raise ValueError(f"Required layer '{key}' failed to load")
            layers[key] = layer
            print(f"   ✓ Loaded {key}: {layer.featureCount()} features")
        
        # Load optional layers
        optional_layers = ['transitions', 'demand']
        for key in optional_layers:
            layer = layer_from_name(LAYER_NAMES[key], required=False)
            if layer and layer.featureCount() > 0:
                layers[key] = layer
                print(f"   ✓ Loaded {key}: {layer.featureCount()} features")
            else:
                print(f"   ⚠️ Optional layer '{key}' not available or empty")
                layers[key] = None
        
        # Step 3: UNION ALL NETWORK LAYERS
        print("\n🔗 UNIONING NETWORK LAYERS...")
        unified_network_layer = union_network_layers(layers)
        
        if unified_network_layer is None or unified_network_layer.featureCount() == 0:
            raise ValueError("Unified network layer is empty")
        
        print(f"   ✓ Created unified network with {unified_network_layer.featureCount()} features")
        
        # Optional: Add the unified layer to the map for debugging
        QgsProject.instance().addMapLayer(unified_network_layer)
        print("   ✓ Added unified network layer to map (for debugging)")
        
        # Step 4 & 5: Assign points to clusters
        print("\n3️⃣ Assigning DPs to clusters...")
        dp_assignments = assign_points_to_clusters(layers['dp'], clusters_layer)
        total_dps_assigned = sum(len(dps) for dps in dp_assignments.values())
        print(f"   ✓ Assigned {total_dps_assigned}/{layers['dp'].featureCount()} DPs to {len(dp_assignments)} clusters")
        
        print("\n4️⃣ Assigning drops to clusters...")
        drop_assignments = assign_points_to_clusters(layers['drops'], clusters_layer)
        total_drops_assigned = sum(len(drops) for drops in drop_assignments.values())
        print(f"   ✓ Assigned {total_drops_assigned}/{layers['drops'].featureCount()} drops to {len(drop_assignments)} clusters")
        
        # Check if any clusters have both DPs and drops
        valid_clusters = []
        for cluster_id in dp_assignments.keys():
            if cluster_id in drop_assignments and len(drop_assignments[cluster_id]) > 0:
                valid_clusters.append(cluster_id)
        
        if not valid_clusters:
            print(" ⚠️ No clusters have both DPs and drops assigned!")
            print("   Debug info:")
            for cluster_id in set(list(dp_assignments.keys()) + list(drop_assignments.keys())):
                dp_count = len(dp_assignments.get(cluster_id, []))
                drop_count = len(drop_assignments.get(cluster_id, []))
                print(f"   Cluster {cluster_id}: {dp_count} DPs, {drop_count} drops")
            return
        
        print(f"\n   Found {len(valid_clusters)} clusters with both DPs and drops")
        
        # Step 6: Process each valid cluster using unified network
        print(f"\n5️⃣ Processing {len(valid_clusters)} valid clusters with unified network...")
        all_cables = []
        cluster_reports = []
        
        # Get cluster features for valid clusters
        cluster_features = []
        for cluster_feat in clusters_layer.getFeatures():
            if cluster_feat.id() in valid_clusters:
                cluster_features.append(cluster_feat)
        
        # Always use sequential processing for debugging first
        print("   Using sequential processing for reliability")
        for cluster_feat in cluster_features:
            cluster_id = cluster_feat.id()
            try:
                cluster_cables = process_cluster(
                    cluster_feat,
                    dp_assignments,
                    drop_assignments,
                    unified_network_layer
                )
                
                if cluster_cables:
                    all_cables.extend(cluster_cables)
                    report = generate_cluster_report(cluster_id, cluster_cables)
                    cluster_reports.append(report)
                    print(f"   ✓ Cluster {cluster_id}: {len(cluster_cables)} cables created")
                    unused = identify_problematic_crossing(cluster_id, cluster_cables, unified_network_layer, clusters_layer)
                    
                    if unused and len(unused) > 0:
                        print(f"   ⚠️ Some crossings not used. Possible reasons:")
                        print(f"      1. Crossing not connected to network")
                        print(f"      2. No drops in that direction")
                        print(f"      3. Alternative route is shorter")
                else:
                    print(f"   ⚠️ Cluster {cluster_id}: No cables created (check network connectivity)")
                    
            except Exception as e:
                print(f"   ❌ Error processing cluster {cluster_id}: {e}")
        
        # Step 7: Combine results and create output layers
        print(f"\n6️⃣ Combining results from {len(all_cables)} cables...")
        if not all_cables:
            print("   ⚠️ No cables were created")
            print("\n   Possible reasons:")
            print("   1. Network layers don't intersect with clusters")
            print("   2. DPs/drops cannot snap to network (increase SNAP_TOLERANCE)")
            print("   3. Network is not connected within clusters")
            print("   4. No paths between DPs and drops")
            return
        
        cable_layer = create_output_layers(all_cables, layers.get('demand'))
        
        # Step 8: Generate reports
        print(f"\n7️⃣ Generating reports for {len(cluster_reports)} clusters...")
        print("\n" + "=" * 60)
        print("FINAL REPORT")
        print("=" * 60)
        
        total_cables = len(all_cables)
        total_drops_connected = sum(len(c['drop_fids']) for c in all_cables)
        total_length = sum(c['trunk_geom'].length for c in all_cables if hasattr(c['trunk_geom'], 'length'))
        
        print(f"\n📊 OVERALL STATISTICS:")
        print(f" • Total clusters processed: {len(cluster_reports)}/{len(valid_clusters)}")
        print(f" • Total cables created: {total_cables}")
        print(f" • Total drops connected: {total_drops_connected}")
        print(f" • Total cable length: {total_length:.2f}m")
        if total_cables > 0:
            print(f" • Average cable length: {total_length/total_cables:.2f}m")
        
        print(f"\n📈 CLUSTER DETAILS:")
        for report in cluster_reports[:10]:  # Show first 10 clusters
            print(f" • Cluster {report['cluster_id']}: {report['num_cables']} cables, "
                  f"{report['total_drops']} drops, {report['total_length']:.2f}m")
        
        if len(cluster_reports) > 10:
            print(f"   ... and {len(cluster_reports) - 10} more clusters")
        
        # Validation
        violations = 0
        for cable in all_cables:
            if len(cable['drop_fids']) > MAX_DROPS_PER_CLUSTER:
                print(f" ⚠️ Cable in cluster {cable.get('cluster_id')} exceeds drop limit: "
                      f"{len(cable['drop_fids'])} > {MAX_DROPS_PER_CLUSTER}")
                violations += 1
        
        if violations == 0:
            print(f"\n✅ All cables respect configuration limits")
        
        elapsed = overall_timer.elapsed() / 1000.0
        print(f"\n⏱️ Total execution time: {elapsed:.2f}s")
        print(f"\n" + "=" * 60)
        print("CLUSTER OPTIMIZATION COMPLETE")
        print("=" * 60)
        
    except ValueError as ve:
        print(f"\n💥 VALIDATION ERROR: {str(ve)}")
        print(" Please check your input data and try again.")
    except Exception as e:
        print(f"\n💥 UNEXPECTED ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        print("\n If this persists, check:")
        print(" 1. All layers exist with correct names")
        print(" 2. All layers have valid geometries")
        print(" 3. Network layers have features that intersect with clusters")
        print(" 4. DPs and drops are within SNAP_TOLERANCE of network")

# Run the main function
if __name__ == "__main__":
    main()
