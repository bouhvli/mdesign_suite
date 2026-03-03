from qgis.core import *
from qgis.PyQt.QtCore import QCoreApplication, QSettings, QTranslator, QVariant
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.PyQt.QtWidgets import QAction
import math
import re
import uuid as uuid_lib
from .layer_loader import get_layer_by_name

def check_and_split_demand_points(iface):
    """Check for demand points with multiple different house numbers and split them.
    Creates a copy of the demand layer, makes edits to the copy, and returns it.
    The original layer is not modified.
    Places new points on the same building wall as original point."""
    
    # Get the layers by exact name
    original_demand_layer = get_layer_by_name('IN_DemandPoints')
    homepoints_layer = get_layer_by_name('IN_HomePoints')
    buildings_layer = get_layer_by_name('IN_Buildings')
    
    if not original_demand_layer or not homepoints_layer:
        iface.messageBar().pushMessage(
            "Error", 
            "Could not find IN_DemandPoints and/or IN_HomePoints layers", 
            level=Qgis.Critical
        )
        return None
    
    print(f"Processing: {original_demand_layer.name()} and {homepoints_layer.name()}")
    if buildings_layer:
        print(f"Found buildings layer: {buildings_layer.name()}")
    else:
        print("WARNING: IN_Buildings layer not found")
        iface.messageBar().pushMessage(
            "Warning",
            "IN_Buildings layer not found - points will be offset horizontally",
            level=Qgis.Warning,
            duration=5
        )
    
    # Create a copy of the demand layer in memory
    print("Creating memory copy of demand layer for editing...")
    demand_layer = QgsVectorLayer(
        QgsWkbTypes.displayString(original_demand_layer.wkbType()),
        f"temp_{original_demand_layer.name()}",
        "memory"
    )
    demand_layer.setCrs(original_demand_layer.crs())

    # Copy all fields and features
    demand_layer.startEditing()
    data_provider = demand_layer.dataProvider()
    data_provider.addAttributes(original_demand_layer.fields())
    demand_layer.updateFields()

    # Copy all features
    features_to_copy = []
    for feature in original_demand_layer.getFeatures():
        new_feature = QgsFeature(demand_layer.fields())
        new_feature.setGeometry(feature.geometry())
        for field in original_demand_layer.fields():
            new_feature.setAttribute(field.name(), feature[field.name()])
        features_to_copy.append(new_feature)

    if features_to_copy:
        data_provider.addFeatures(features_to_copy)

    demand_layer.commitChanges()
    print(f"Created memory layer with {demand_layer.featureCount()} features")
    
    # Get fields
    demand_fields = demand_layer.fields()
    home_fields = homepoints_layer.fields()
    
    # Check required fields
    required_fields = ['P2P_HOMES', 'CITY', 'STREETNAME', 'ADDRESS_NU', 'DEMAND', 'POSTCODE']
    if any(demand_fields.indexFromName(f) == -1 for f in required_fields):
        iface.messageBar().pushMessage(
            "Error",
            "Missing required fields in demand layer",
            level=Qgis.Critical
        )
        return None
    
    # Check if INCLUDE field exists
    include_index = home_fields.indexFromName('INCLUDE')
    if include_index == -1:
        print("WARNING: No INCLUDE field found - will process all homepoints")
    
    # Check if NUMBER field exists
    number_index_demand = demand_fields.indexFromName('NUMBER')
    number_index_home = home_fields.indexFromName('NUMBER')
    copy_number = number_index_demand != -1 and number_index_home != -1
    
    try:
        # Start editing the copy
        demand_layer.startEditing()
        
        # Group homepoints by DEMAND value - filter by INCLUDE = True
        homepoints_by_demand = {}
        for feature in homepoints_layer.getFeatures():
            # Check INCLUDE field
            if include_index != -1:
                include_value = feature['INCLUDE']
                if not include_value:
                    continue
            
            demand_value = feature['DEMAND']
            if demand_value:
                if demand_value not in homepoints_by_demand:
                    homepoints_by_demand[demand_value] = []
                homepoints_by_demand[demand_value].append(feature)
        
        print(f"Found {len(homepoints_by_demand)} demand groups")
        
        # Process each demand point
        new_demand_features = []
        
        for demand_feature in demand_layer.getFeatures():
            demand_value = demand_feature['DEMAND']
            
            if not demand_value or demand_value not in homepoints_by_demand:
                continue
            
            homepoints = homepoints_by_demand[demand_value]
            
            # Group by unique address
            unique_combinations = {}
            for homepoint in homepoints:
                key = (
                    str(homepoint['CITY'] or ''),
                    str(homepoint['STREETNAME'] or ''),
                    str(homepoint['ADDRESS_NU'] or '')
                )
                if key not in unique_combinations:
                    unique_combinations[key] = []
                unique_combinations[key].append(homepoint)
            
            # If only one unique address, skip
            if len(unique_combinations) <= 1:
                continue
            
            print(f"\nSplitting demand {demand_value} with {len(unique_combinations)} addresses")
            
            # Keep first, split others
            sorted_combinations = sorted(unique_combinations.items())
            keep_key, keep_homepoints = sorted_combinations[0]
            other_combinations = sorted_combinations[1:]
            
            # Update original in copy
            current_p2p = demand_feature['P2P_HOMES'] or 0
            homes_to_reduce = sum(len(hps) for _, hps in other_combinations)
            new_p2p = max(0, current_p2p - homes_to_reduce)
            
            demand_layer.changeAttributeValue(
                demand_feature.id(),
                demand_fields.indexFromName('P2P_HOMES'),
                new_p2p
            )
            
            # Get original point
            original_point = demand_feature.geometry().asPoint()
            
            # Find building wall for original point
            wall_info = None
            if buildings_layer:
                wall_info = find_closest_wall(original_point, buildings_layer)
            
            # Create new demand points
            point_index = 0
            for combo_key, combo_homepoints in other_combinations:
                sample = combo_homepoints[0]
                
                # Create new feature
                new_feature = QgsFeature(demand_fields)
                
                # Set geometry on same wall
                if wall_info:
                    # Place on same wall
                    new_point = place_on_wall(wall_info, point_index, len(other_combinations))
                    new_feature.setGeometry(QgsGeometry.fromPointXY(new_point))
                    print(f"    Point {point_index}: placed on building wall")
                else:
                    # Simple horizontal offset if no wall found
                    offset = 3.0 * (point_index + 1)
                    new_point = QgsPointXY(
                        original_point.x() + offset,
                        original_point.y()
                    )
                    new_feature.setGeometry(QgsGeometry.fromPointXY(new_point))
                    print(f"    Point {point_index}: horizontal offset {offset}m")
                
                # Copy attributes
                for i in range(demand_fields.count()):
                    field_name = demand_fields.field(i).name()
                    new_feature.setAttribute(field_name, demand_feature[field_name])
                
                # Update address
                new_feature.setAttribute('CITY', sample['CITY'] or '')
                new_feature.setAttribute('STREETNAME', sample['STREETNAME'] or '')
                new_feature.setAttribute('ADDRESS_NU', sample['ADDRESS_NU'] or '')
                
                # New DEMAND value
                new_demand_value = generate_new_demand_value(demand_layer, new_demand_features)
                new_feature.setAttribute('DEMAND', new_demand_value)
                
                # Set P2P_HOMES
                new_feature.setAttribute('P2P_HOMES', len(combo_homepoints))
                
                # Copy NUMBER
                if copy_number and sample['NUMBER']:
                    new_feature.setAttribute('NUMBER', sample['NUMBER'])
                
                new_demand_features.append(new_feature)
                point_index += 1
        
        # Add new features to copy layer
        if new_demand_features:
            demand_layer.addFeatures(new_demand_features)
        
        # Commit changes to copy
        demand_layer.commitChanges()
        
        result_msg = f"Created {len(new_demand_features)} new demand points"
        print(f"\n{result_msg}")
        
        iface.messageBar().pushMessage(
            "Success",
            result_msg,
            level=Qgis.Success,
            duration=10
        )
        
        print(f"Returning edited demand layer copy with {demand_layer.featureCount()} total features")
        return demand_layer
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        
        # Rollback on error
        if demand_layer.isEditable():
            demand_layer.rollBack()
            
        iface.messageBar().pushMessage(
            "Error", 
            f"Failed to process demand points: {str(e)}", 
            level=Qgis.Critical
        )
        return None

def find_closest_wall(point, buildings_layer):
    """Find the closest wall segment from IN_Buildings."""
    closest_wall = None
    closest_distance = float('inf')
    
    for building in buildings_layer.getFeatures():
        building_geom = building.geometry()
        
        # Extract polygon vertices to get walls
        try:
            if building_geom.isMultipart():
                polygons = building_geom.asMultiPolygon()
                for polygon in polygons:
                    for ring in polygon:
                        if len(ring) > 1:
                            for i in range(len(ring) - 1):
                                segment_start = ring[i]
                                segment_end = ring[i + 1]
                                
                                # Create segment geometry
                                segment_geom = QgsGeometry.fromPolylineXY([segment_start, segment_end])
                                
                                # Calculate distance from point to segment
                                distance = segment_geom.distance(QgsGeometry.fromPointXY(point))
                                
                                if distance < closest_distance:
                                    closest_distance = distance
                                    closest_wall = {
                                        'start': segment_start,
                                        'end': segment_end,
                                        'length': math.sqrt((segment_end.x() - segment_start.x())**2 + 
                                                          (segment_end.y() - segment_start.y())**2),
                                        'distance': distance
                                    }
            else:
                polygon = building_geom.asPolygon()
                for ring in polygon:
                    if len(ring) > 1:
                        for i in range(len(ring) - 1):
                            segment_start = ring[i]
                            segment_end = ring[i + 1]
                            
                            segment_geom = QgsGeometry.fromPolylineXY([segment_start, segment_end])
                            distance = segment_geom.distance(QgsGeometry.fromPointXY(point))
                            
                            if distance < closest_distance:
                                closest_distance = distance
                                closest_wall = {
                                    'start': segment_start,
                                    'end': segment_end,
                                    'length': math.sqrt((segment_end.x() - segment_start.x())**2 + 
                                                      (segment_end.y() - segment_start.y())**2),
                                    'distance': distance
                                }
        except:
            # Fallback method for complex geometries
            continue
    
    if closest_wall and closest_wall['distance'] < 5.0:  # Within 5 meters
        print(f"  Found wall {closest_wall['distance']:.1f}m away, length: {closest_wall['length']:.1f}m")
        return closest_wall
    
    return None

def place_on_wall(wall_info, point_index, total_points, min_spacing=2.0):
    """Place point on wall with proper spacing."""
    start = wall_info['start']
    end = wall_info['end']
    wall_length = wall_info['length']
    
    if wall_length == 0:
        # Return midpoint if zero length
        return QgsPointXY((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
    
    # Wall direction
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    dx /= wall_length
    dy /= wall_length
    
    # Calculate spacing - leave some margin at ends
    margin = min(2.0, wall_length * 0.1)  # 2m or 10% of wall length
    available_length = wall_length - (2 * margin)
    
    if available_length <= 0:
        # Wall too short, use midpoint
        return QgsPointXY((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
    
    # Calculate spacing between points
    if total_points <= 1:
        spacing = available_length / 2  # Place in middle
    else:
        spacing = available_length / (total_points + 1)
    
    # Ensure minimum spacing
    spacing = max(spacing, min_spacing)
    
    # Calculate position along wall (0 to wall_length)
    # Points will be at: margin + spacing, margin + 2*spacing, etc.
    position = margin + (point_index + 1) * spacing
    
    # Clamp to wall bounds
    position = max(0, min(wall_length, position))
    
    # Calculate coordinates
    x = start.x() + dx * position
    y = start.y() + dy * position
    
    return QgsPointXY(x, y)

def generate_new_demand_value(demand_layer, new_features):
    """Generate a new unique DEMAND value."""
    existing_values = set()
    
    for feature in demand_layer.getFeatures():
        value = feature['DEMAND']
        if value:
            existing_values.add(value)
    
    for feature in new_features:
        value = feature['DEMAND']
        if value:
            existing_values.add(value)
    
    # Find max number
    max_val = 0
    for v in existing_values:
        try:
            num = int(v)
            max_val = max(max_val, num)
        except:
            pass
    
    return max_val + 1
def add_missing_addresses_from_gov(iface):
    """Find addresses in government data (WFS layer) that don't exist in demand points and create them.
    Returns the edited demand layer with new addresses added."""
    
    # Step 0: Check if OUT_FeederClusters exists
    project = QgsProject.instance()
    feeder_clusters_layer = get_layer_by_name('OUT_FeederClusters')
    
    if not feeder_clusters_layer:
        print("ERROR: OUT_FeederClusters layer not found")
        iface.messageBar().pushMessage(
            "Error", 
            "OUT_FeederClusters layer not found. Cannot proceed.", 
            level=Qgis.Critical
        )
        return None
    
    print(f"Found OUT_FeederClusters layer: {feeder_clusters_layer.name()} with {feeder_clusters_layer.featureCount()} features")
    
    # Step 1: Load government address data from WFS API
    print("\nStep 1: Loading government address data from WFS API...")
    gov_wfs_url = "https://geo.api.vlaanderen.be/Adressenregister/wfs"
    gov_layer_name = "Adressenregister:Adres"
    
    # Create the WFS connection string
    wfs_uri = (f"pagingEnabled='default' "
               f"preferCoordinatesForWfsT11='false' "
               f"restrictToRequestBBOX='1' "
               f"srsname='EPSG:31370' "
               f"typename='{gov_layer_name}' "
               f"url='{gov_wfs_url}' "
               f"version='auto'")
    
    # Load the WFS layer
    gov_wfs_layer = QgsVectorLayer(wfs_uri, "Government Addresses (WFS)", "WFS")
    
    if not gov_wfs_layer.isValid():
        print(f"ERROR: Failed to load WFS layer: {gov_wfs_layer.error().message()}")
        iface.messageBar().pushMessage(
            "Error", 
            f"Failed to load government WFS data: {gov_wfs_layer.error().message()}", 
            level=Qgis.Critical
        )
        return None
    
    print(f"Successfully loaded WFS layer with {gov_wfs_layer.featureCount()} features (before clipping)")
    print(f"WFS layer CRS: {gov_wfs_layer.crs().authid()}")
    print(f"WFS layer fields: {[field.name() for field in gov_wfs_layer.fields()]}")
    
    # Step 2: Clip the WFS layer to OUT_FeederClusters
    print("\nStep 2: Clipping government data to OUT_FeederClusters...")
    from qgis import processing
    
    try:
        # Run the clip operation
        clipped_result = processing.run("native:clip", {
            'INPUT': gov_wfs_layer,
            'OVERLAY': feeder_clusters_layer,
            'OUTPUT': 'memory:'
        })
        
        gov_layer = clipped_result['OUTPUT']
        
        if not gov_layer or not gov_layer.isValid():
            print("ERROR: Failed to clip government data")
            iface.messageBar().pushMessage(
                "Error", 
                "Failed to clip government data to feeder clusters", 
                level=Qgis.Critical
            )
            return None
        
        print(f"Successfully clipped WFS layer to {gov_layer.featureCount()} features")
        
    except Exception as e:
        print(f"ERROR: Clip operation failed: {e}")
        import traceback
        traceback.print_exc()
        iface.messageBar().pushMessage(
            "Error", 
            f"Clip operation failed: {str(e)}", 
            level=Qgis.Critical
        )
        return None
    
    # Now continue with the rest of the function...
    # Get the original demand layer
    original_demand_layer = get_layer_by_name('IN_DemandPoints')
    homepoints_layer = get_layer_by_name('IN_HomePoints')
    
    if not original_demand_layer:
        print("ERROR: Could not find IN_DemandPoints layer")
        iface.messageBar().pushMessage(
            "Error", 
            "Could not find IN_DemandPoints layer", 
            level=Qgis.Critical
        )
        return None
    
    # Check if homepoints layer exists
    if homepoints_layer:
        print(f"Found homepoints layer: {homepoints_layer.name()}")
    else:
        print("WARNING: IN_HomePoints layer not found. Skipping homepoints check.")
    
    # Create a memory copy of the demand layer
    print("\nCreating memory copy of demand layer for editing...")
    demand_layer = QgsVectorLayer(
        QgsWkbTypes.displayString(original_demand_layer.wkbType()),
        f"temp_{original_demand_layer.name()}",
        "memory"
    )
    demand_layer.setCrs(original_demand_layer.crs())
    
    # Copy all fields and features
    demand_layer.startEditing()
    data_provider = demand_layer.dataProvider()
    data_provider.addAttributes(original_demand_layer.fields())
    demand_layer.updateFields()
    
    # Copy all features
    features_to_copy = []
    for feature in original_demand_layer.getFeatures():
        new_feature = QgsFeature(demand_layer.fields())
        new_feature.setGeometry(feature.geometry())
        for field in original_demand_layer.fields():
            new_feature.setAttribute(field.name(), feature[field.name()])
        features_to_copy.append(new_feature)
    
    if features_to_copy:
        data_provider.addFeatures(features_to_copy)
    
    demand_layer.commitChanges()
    print(f"Created memory layer with {demand_layer.featureCount()} features")
    
    # Get field information for ADDRESS_NU
    demand_fields = demand_layer.fields()
    address_nu_index = demand_fields.indexFromName('ADDRESS_NU')
    if address_nu_index == -1:
        print("ERROR: ADDRESS_NU field not found in demand layer")
        iface.messageBar().pushMessage("Error", "ADDRESS_NU field not found in demand layer", level=Qgis.Critical)
        return None
    
    address_nu_field = demand_fields.field(address_nu_index)
    print(f"ADDRESS_NU field type: {address_nu_field.typeName()}")
    
    def extract_house_number_base(house_num_str):
        """Extract the base house number from a string, removing any suffix."""
        if not house_num_str:
            return None, None
        
        house_num_str = str(house_num_str).strip()
        
        # Common patterns for house numbers with suffixes
        patterns = [
            r'^(\d+)\s*([a-zA-Z])$',
            r'^(\d+)\s*[-_/\.]\s*(\d+|[a-zA-Z])$',
            r'^(\d+)\s*[-_/\.]\s*(\d+[a-zA-Z]?|[a-zA-Z])$',
            r'^(\d+)$'
        ]
        
        for pattern in patterns:
            match = re.match(pattern, house_num_str, re.IGNORECASE)
            if match:
                base_number = match.group(1)
                return int(base_number), house_num_str
        
        # If no pattern matches, try to extract just the numeric part
        match = re.search(r'(\d+)', house_num_str)
        if match:
            return int(match.group(1)), house_num_str
        
        # If no numeric part found
        try:
            return int(house_num_str), house_num_str
        except (ValueError, TypeError):
            return None, house_num_str
    
    def convert_house_number(house_num_str):
        """Convert house number string to appropriate type for ADDRESS_NU field."""
        if not house_num_str:
            return None
        
        house_num_str = str(house_num_str).strip()
        base_number, _ = extract_house_number_base(house_num_str)
        
        if base_number is None:
            return None
        
        field_type = address_nu_field.type()
        
        if field_type in [QVariant.Int, QVariant.LongLong, QVariant.UInt, QVariant.ULongLong]:
            return base_number
        elif field_type in [QVariant.String, QVariant.Char]:
            return str(base_number)
        else:
            return str(base_number)
    
    def address_in_homepoints_with_false_include(city, street, house_num_str):
        """Check if address exists in homepoints layer with INCLUDE = False."""
        if not homepoints_layer:
            return False
        
        home_fields = homepoints_layer.fields()
        
        city_field_idx = home_fields.indexFromName('CITY')
        street_field_idx = home_fields.indexFromName('STREETNAME')
        address_field_idx = home_fields.indexFromName('ADDRESS_NU')
        include_field_idx = home_fields.indexFromName('INCLUDE')
        
        if city_field_idx == -1 or street_field_idx == -1 or address_field_idx == -1 or include_field_idx == -1:
            print("WARNING: Homepoints layer missing required fields")
            return False
        
        search_city = city.upper()
        search_street = street.upper()
        search_address = str(house_num_str).strip().upper()
        
        for feature in homepoints_layer.getFeatures():
            feat_city = str(feature['CITY'] or '').strip().upper()
            feat_street = str(feature['STREETNAME'] or '').strip().upper()
            feat_address = str(feature['ADDRESS_NU'] or '').strip().upper()
            feat_include = feature['INCLUDE']
            
            if (feat_city == search_city and 
                feat_street == search_street and 
                feat_address == search_address):
                return feat_include is False
        
        return False
    
    # Get CRS for transformation
    source_crs = gov_layer.crs()
    target_crs_wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
    
    transform_to_wgs84 = None
    if source_crs != target_crs_wgs84:
        transform_to_wgs84 = QgsCoordinateTransform(source_crs, target_crs_wgs84, QgsProject.instance())
    
    # Get fields
    gov_fields = gov_layer.fields()
    
    # Check if required fields exist in government layer
    # Note: WFS field names might be different, adjust as needed
    required_gov_fields = ['Gemeentenaam', 'Straatnaam', 'Huisnummer', 'PostinfoObjectId', 'AdresStatus']
    
    # First check what fields are actually available
    available_fields = [field.name() for field in gov_fields]
    print(f"Available fields in clipped government layer: {available_fields}")
    
    # Try to find field names - WFS might use different naming
    # You may need to adjust these based on actual field names
    gemeentenaam_field = None
    straatnaam_field = None
    huisnummer_field = None
    postcode_field = None
    adresstatus_field = None
    
    for field in available_fields:
        field_lower = field.lower()
        if 'gemeente' in field_lower or 'municipality' in field_lower:
            gemeentenaam_field = field
        elif 'straat' in field_lower or 'street' in field_lower:
            straatnaam_field = field
        elif 'huisnummer' in field_lower or 'housenumber' in field_lower:
            huisnummer_field = field
        elif 'post' in field_lower or 'zip' in field_lower:
            postcode_field = field
        elif 'status' in field_lower:
            adresstatus_field = field
    
    print(f"Detected fields: Gemeentenaam='{gemeentenaam_field}', Straatnaam='{straatnaam_field}', "
          f"Huisnummer='{huisnummer_field}', Postcode='{postcode_field}', AdresStatus='{adresstatus_field}'")
    
    # Check if we found all required fields
    if not all([gemeentenaam_field, straatnaam_field, huisnummer_field, postcode_field, adresstatus_field]):
        missing_fields = []
        if not gemeentenaam_field: missing_fields.append('Gemeentenaam')
        if not straatnaam_field: missing_fields.append('Straatnaam')
        if not huisnummer_field: missing_fields.append('Huisnummer')
        if not postcode_field: missing_fields.append('Postcode')
        if not adresstatus_field: missing_fields.append('AdresStatus')
        
        print(f"ERROR: Missing required fields in government layer: {', '.join(missing_fields)}")
        print(f"Available fields: {available_fields}")
        iface.messageBar().pushMessage(
            "Error",
            f"Missing required fields in government layer: {', '.join(missing_fields)}",
            level=Qgis.Critical
        )
        return None
    
    # Check if required fields exist in demand layer
    required_demand_fields = ['CITY', 'STREETNAME', 'ADDRESS_NU', 'POSTCODE', 'P2P_HOMES', 'INCLUDE', 'LAT', 'LON']
    missing_demand_fields = [f for f in required_demand_fields if demand_fields.indexFromName(f) == -1]
    if missing_demand_fields:
        print(f"ERROR: Missing required fields in demand layer: {', '.join(missing_demand_fields)}")
        iface.messageBar().pushMessage(
            "Error",
            f"Missing required fields in demand layer: {', '.join(missing_demand_fields)}",
            level=Qgis.Critical
        )
        return None
    
    try:
        # Start editing
        demand_layer.startEditing()
        
        # Get existing addresses from demand layer (normalized)
        existing_addresses = set()
        for feature in demand_layer.getFeatures():
            city = str(feature['CITY'] or '').strip().upper()
            street = str(feature['STREETNAME'] or '').strip().upper()
            address_num = feature['ADDRESS_NU']
            
            if address_num is not None:
                address_num_str = str(address_num).strip()
                if city and street and address_num_str:
                    base_num_match = re.search(r'(\d+)', address_num_str)
                    if base_num_match:
                        base_num = base_num_match.group(1)
                        address_key = f"{city}|{street}|{base_num}"
                        existing_addresses.add(address_key)
        
        print(f"Found {len(existing_addresses)} unique addresses in demand layer")
        
        # Group government addresses by address
        gov_addresses = {}
        
        for feature in gov_layer.getFeatures():
            # Use the detected field names
            adres_status = str(feature[adresstatus_field] or '')
            if adres_status.upper() != 'INGEBRUIK':
                continue
            
            city = str(feature[gemeentenaam_field] or '').strip().upper()
            street = str(feature[straatnaam_field] or '').strip().upper()
            house_num_str = str(feature[huisnummer_field] or '').strip()
            
            if not city or not street or not house_num_str:
                continue
            
            base_number, full_house_num = extract_house_number_base(house_num_str)
            
            if base_number is None:
                print(f"Warning: Could not extract base number from '{house_num_str}'")
                continue
            
            address_key = f"{city}|{street}|{base_number}"
            
            if address_key not in gov_addresses:
                gov_addresses[address_key] = {
                    'city_orig': str(feature[gemeentenaam_field] or ''),
                    'street_orig': str(feature[straatnaam_field] or ''),
                    'house_num_str': house_num_str,
                    'base_number': base_number,
                    'full_house_num': full_house_num,
                    'postcode': str(feature[postcode_field] or ''),
                    'count': 0,
                    'geometry': None
                }
            
            gov_addresses[address_key]['count'] += 1
            
            if gov_addresses[address_key]['geometry'] is None:
                gov_addresses[address_key]['geometry'] = feature.geometry()
        
        print(f"Found {len(gov_addresses)} unique addresses in government data (InGebruik only)")
        
        # Find addresses that exist in government data but not in demand layer
        missing_addresses = {}
        for address_key, address_info in gov_addresses.items():
            if address_key not in existing_addresses:
                missing_addresses[address_key] = address_info
        
        print(f"Found {len(missing_addresses)} addresses in government data that are missing from demand layer")
        
        # Create new demand points for missing addresses
        new_features = []
        skipped_due_to_homepoints = 0
        
        for address_key, address_info in missing_addresses.items():
            print(f"Processing missing address: {address_info['city_orig']} {address_info['street_orig']} {address_info['house_num_str']}")
            
            # Check if this address exists in homepoints layer with INCLUDE = False
            if address_in_homepoints_with_false_include(
                address_info['city_orig'], 
                address_info['street_orig'], 
                address_info['house_num_str']
            ):
                print(f"  SKIPPING: Address exists in homepoints with INCLUDE = False")
                skipped_due_to_homepoints += 1
                continue
            
            # Create new feature
            new_feature = QgsFeature(demand_fields)
            
            # Set geometry
            if address_info['geometry']:
                new_feature.setGeometry(address_info['geometry'])
            
            # Set address fields from government data
            new_feature.setAttribute('CITY', address_info['city_orig'])
            new_feature.setAttribute('STREETNAME', address_info['street_orig'])
            
            converted_address_num = convert_house_number(str(address_info['base_number']))
            new_feature.setAttribute('ADDRESS_NU', converted_address_num)
            
            new_feature.setAttribute('POSTCODE', address_info['postcode'])
            new_feature.setAttribute('P2P_HOMES', address_info['count'])
            new_feature.setAttribute('INCLUDE', True)
            
            # Set optional fields
            if demand_fields.indexFromName('PON_HOMES') != -1:
                new_feature.setAttribute('PON_HOMES', 0)
            
            if demand_fields.indexFromName('PON_M_REV') != -1:
                new_feature.setAttribute('PON_M_REV', 0)
            
            if demand_fields.indexFromName('HEIGHT') != -1:
                new_feature.setAttribute('HEIGHT', 0)
            
            if demand_fields.indexFromName('FLOORCOUNT') != -1:
                new_feature.setAttribute('FLOORCOUNT', 0)
            
            if demand_fields.indexFromName('LOCKED') != -1:
                new_feature.setAttribute('LOCKED', False)
            
            # Set LAT and LON by transforming geometry to WGS84
            if address_info['geometry'] and transform_to_wgs84:
                try:
                    point_geom = address_info['geometry'].centroid()
                    if point_geom:
                        point_geom.transform(transform_to_wgs84)
                        point = point_geom.asPoint()
                        new_feature.setAttribute('LAT', point.y())
                        new_feature.setAttribute('LON', point.x())
                except Exception as e:
                    print(f"Error transforming coordinates: {e}")
                    new_feature.setAttribute('LAT', None)
                    new_feature.setAttribute('LON', None)
            
            # Generate a new DEMAND value if field exists
            if demand_fields.indexFromName('DEMAND') != -1:
                new_demand_value = generate_new_demand_value(demand_layer, new_features)
                new_feature.setAttribute('DEMAND', new_demand_value)
            
            # Set UUID if field exists
            if demand_fields.indexFromName('UUID') != -1:
                new_feature.setAttribute('UUID', str(uuid_lib.uuid4()))
            
            # Set SURVEYED to False if field exists
            if demand_fields.indexFromName('SURVEYED') != -1:
                new_feature.setAttribute('SURVEYED', False)
            
            new_features.append(new_feature)
            print(f"  Created demand point for: {address_info['city_orig']} {address_info['street_orig']} {address_info['house_num_str']}")
        
        # Add all new features
        if new_features:
            print(f"\nAdding {len(new_features)} new features...")
            success = demand_layer.addFeatures(new_features)
            if not success:
                print("ERROR: Failed to add features to layer")
        
        # Commit changes
        if demand_layer.commitChanges():
            print(f"✓ Successfully committed changes to demand layer")
            
            summary_parts = []
            summary_parts.append(f"Added {len(new_features)} new addresses from government data")
            if skipped_due_to_homepoints > 0:
                summary_parts.append(f"Skipped {skipped_due_to_homepoints} addresses (found in homepoints with INCLUDE=False)")
            
            summary = "; ".join(summary_parts)
            iface.messageBar().pushMessage(
                "Success", 
                summary, 
                level=Qgis.Success,
                duration=10
            )
        else:
            print(f"✗ Error committing changes to demand layer")
            errors = demand_layer.commitErrors()
            for error in errors:
                print(f"  Commit error: {error}")
            demand_layer.rollBack()
            iface.messageBar().pushMessage(
                "Error",
                "Failed to commit changes to demand layer.",
                level=Qgis.Critical
            )
            return None
        
        demand_layer.triggerRepaint()
        
        print("\nDone!")
        print(f"Summary: Added {len(new_features)} addresses, Skipped {skipped_due_to_homepoints} addresses due to homepoints")
        print(f"Returning edited demand layer with {demand_layer.featureCount()} total features")
        return demand_layer
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        
        if demand_layer.isEditable():
            demand_layer.rollBack()
            
        iface.messageBar().pushMessage(
            "Error", 
            f"Failed to add missing addresses: {str(e)}", 
            level=Qgis.Critical
        )
        return None