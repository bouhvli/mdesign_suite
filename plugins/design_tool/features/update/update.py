from qgis.core import (  # type: ignore
    QgsGeometry, QgsProject, QgsWkbTypes, QgsSpatialIndex, QgsDefaultValue, 
    QgsVectorLayer, QgsFeature, QgsVectorFileWriter, QgsMarkerSymbol, QgsPointXY,
    QgsSingleSymbolRenderer, QgsFields, QgsField
)
from qgis.PyQt.QtCore import QVariant # type: ignore
from qgis import processing  # type: ignore
from qgis.core import QgsExpression  # type: ignore
from qgis.core import QgsFeature  # type: ignore

import random
import re
import traceback
import os
from datetime import datetime
import processing


from ...utils.layer_loader import get_layer_by_name
from ...utils.external_map_loader import add_external_wfs_layers


class UpdateDesign:
    def __init__(self, update_addresses=False, point_layer=None, surveyed_addresses_file=None, analyze_intersections=False, trenches_layer_name=None, assign_clusters_by_distribution=False):
        self.changes = []
        self.update_addresses = update_addresses
        self.point_layer = point_layer
        self.surveyed_addresses_file = surveyed_addresses_file
        self.analyze_intersections = analyze_intersections
        self.trenches_layer_name = trenches_layer_name
        self.assign_clusters_by_distribution = assign_clusters_by_distribution

    def updatedesign(self):
        """
        Run all updates
        """
        self.changes = []
        print("Running changes...")
        results = []
        results.append(self.auto_increment_agg_id())
        
        # Add the new address synchronization if requested
        if self.update_addresses and self.surveyed_addresses_file:
            results.append(self.sync_addresses_from_survey())

        if self.analyze_intersections:
            results.append(self.analyze_sidewalk_intersections())
        
        # Add cluster assignment if requested
        if self.assign_clusters_by_distribution:
            results.append(self.assign_clusters_by_distribution_cables())
        
        return results

    def sync_addresses_from_survey(self):
        """
        Synchronize In_homepoints layer with surveyed Address point layer based on P2P_HOMES values.
        """
        from datetime import datetime
        import traceback
        
        # Initialize counters
        demand_groups_processed = 0
        demand_groups_adjusted = 0
        total_added = 0
        total_deactivated = 0
        orphaned_count = 0
        detailed_logs = []
        
        # Debug tracking
        address_p2p_debug = []
        missing_addresses = []
        
        try:
            # Get the layers
            address_layer = self._load_surveyed_layer()
            if not address_layer:
                return {
                    'operation': 'sync_addresses_from_survey',
                    'status': 'failed',
                    'error': 'Could not load surveyed addresses layer'
                }
            
            print(f"Loaded surveyed layer: {address_layer.name()} with {address_layer.featureCount()} features")
            
            homepoints_layer = get_layer_by_name("In_homepoints")
            
            if not address_layer or not homepoints_layer:
                error_msg = f"Required layers not found. Address point: {bool(address_layer)}, In_homepoints: {bool(homepoints_layer)}"
                detailed_logs.append(f"ERROR: {error_msg}")
                return {
                    'operation': 'sync_addresses_from_survey',
                    'status': 'failed',
                    'error': error_msg,
                    'detailed_logs': detailed_logs
                }
            
            # Helper function to safely get BOX as integer
            def get_box_as_int(feature):
                """Safely get BOX value as integer, handling None, empty strings, and conversion errors"""
                box_value = feature["BOX"]
                if box_value is None:
                    return 0
                try:
                    # Handle string to int conversion
                    if isinstance(box_value, str):
                        # Try to convert string to int, handle empty strings
                        return int(box_value) if box_value.strip() else 0
                    # If already a number
                    return int(box_value)
                except (ValueError, TypeError):
                    # If conversion fails, return 0
                    return 0
            
            # Start edit session
            homepoints_layer.startEditing()
            
            # Build index for faster lookups
            detailed_logs.append("INFO: Building address point index...")
            address_data = {}
            
            # Track all address points for debugging
            address_point_details = []
            
            # Group address points by matching criteria
            for feature in address_layer.getFeatures():
                demand = feature["DEMAND"]
                city = feature["CITY"]
                street = feature["STREETNAME"]
                addr_num = feature["ADDRESS_NU"]
                
                # Create unique key for grouping
                key = f"{demand}_{city}_{street}_{addr_num}"
                
                # Safely get P2P_HOMES as integer
                p2p_value = feature["P2P_HOMES"]
                p2p_int = 0
                if p2p_value is not None:
                    try:
                        if isinstance(p2p_value, str):
                            p2p_int = int(p2p_value) if p2p_value.strip() else 0
                        else:
                            p2p_int = int(p2p_value)
                    except (ValueError, TypeError):
                        p2p_int = 0
                        detailed_logs.append(f"WARNING: Invalid P2P_HOMES value for {key}: {p2p_value}")
                
                # Track for debugging
                address_point_details.append({
                    'key': key,
                    'p2p_original': p2p_value,
                    'p2p_int': p2p_int,
                    'fid': feature.id(),
                    'demand': demand,
                    'city': city,
                    'street': street,
                    'addr_num': addr_num
                })
                
                if key not in address_data:
                    address_data[key] = {
                        'p2p_homes': p2p_int,
                        'features': [],
                        'demand': demand,
                        'city': city,
                        'street': street,
                        'addr_num': addr_num,
                        'original_p2p': p2p_value,
                        'address_fid': feature.id()
                    }
                else:
                    # Handle duplicate address points (same key)
                    detailed_logs.append(f"WARNING: Duplicate address point for key {key}")

                address_data[key]['features'].append(feature)

            detailed_logs.append(f"INFO: Found {len(address_data)} unique address groups")

            # Debug: Count total P2P_HOMES
            total_p2p_sum = sum(info['p2p_homes'] for info in address_data.values())
            detailed_logs.append(f"DEBUG: Total P2P_HOMES sum from unique groups: {total_p2p_sum}")

            # Debug: List addresses with P2P_HOMES > 0
            addresses_with_p2p = [(k, v['p2p_homes'], v['address_fid']) for k, v in address_data.items() if v['p2p_homes'] > 0]
            detailed_logs.append(f"DEBUG: Addresses with P2P_HOMES > 0: {len(addresses_with_p2p)}")

            # Process each demand group
            for key, address_info in address_data.items():
                demand_groups_processed += 1
                group_logs = []

                # Get all homepoints for this group
                demand = address_info['demand']
                city = address_info['city']
                street = address_info['street']
                addr_num = address_info['addr_num']
                target_p2p = address_info['p2p_homes']

                # Skip if P2P_HOMES is 0
                if target_p2p == 0:
                    group_logs.append(f"Group {key}: P2P_HOMES=0, skipping")
                    if len(group_logs) > 1:
                        detailed_logs.extend(group_logs)
                    continue

                # Build expression to find matching homepoints
                expr = f"\"DEMAND\" = '{demand}' AND \"CITY\" = '{city}' AND \"STREETNAME\" = '{street}' AND \"ADDRESS_NU\" = '{addr_num}'"

                # Get active and inactive homepoints
                active_homepoints = []
                inactive_homepoints = []

                for homepoint in homepoints_layer.getFeatures(expr):
                    if homepoint["INCLUDE"]:
                        active_homepoints.append(homepoint)
                    else:
                        inactive_homepoints.append(homepoint)

                current_active_count = len(active_homepoints)

                group_logs.append(f"Group {key}: P2P_HOMES={target_p2p}, Current active={current_active_count}, Inactive available={len(inactive_homepoints)}")

                # Track for debugging
                if current_active_count == 0 and target_p2p > 0:
                    missing_addresses.append({
                        'key': key,
                        'p2p_homes': target_p2p,
                        'address_fid': address_info['address_fid'],
                        'reason': 'No existing homepoints'
                    })

                # Case 1: Need to add/activate homepoints
                if target_p2p > current_active_count:
                    demand_groups_adjusted += 1
                    needed = target_p2p - current_active_count
                    group_logs.append(f"Need to add/activate {needed} homepoint(s)")
                    
                    # Sort homepoints by BOX number (descending) using safe integer conversion
                    all_homepoints = active_homepoints + inactive_homepoints
                    all_homepoints.sort(key=lambda x: get_box_as_int(x), reverse=True)
                    
                    for i in range(needed):
                        # First check for inactive features to reactivate
                        if inactive_homepoints:
                            # Sort inactive homepoints by BOX to reactivate the one with highest BOX
                            inactive_homepoints.sort(key=lambda x: get_box_as_int(x), reverse=True)
                            homepoint = inactive_homepoints.pop(0)
                            fid = homepoint.id()
                            
                            # Reactivate the feature
                            homepoints_layer.changeAttributeValue(fid, homepoints_layer.fields().lookupField("INCLUDE"), True)
                            total_added += 1
                            group_logs.append(f"Reactivated feature FID={fid} with BOX={get_box_as_int(homepoint)}")
                        
                        # If no inactive features, duplicate the one with highest BOX
                        elif all_homepoints:
                            # Get feature with highest BOX
                            source_feature = all_homepoints[0]
                            
                            # Create new feature by duplication
                            new_feature = QgsFeature(source_feature)
                            
                            # Update BOX number (increment by 1)
                            current_max_box = max([get_box_as_int(f) for f in all_homepoints])
                            new_box = current_max_box + 1
                            
                            # Set attributes for new feature
                            fields = homepoints_layer.fields()
                            for field_idx in range(fields.count()):
                                field_name = fields.field(field_idx).name()
                                if field_name == "BOX":
                                    new_feature.setAttribute(field_idx, new_box)
                                elif field_name == "INCLUDE":
                                    new_feature.setAttribute(field_idx, True)
                                else:
                                    # Copy other attributes from source
                                    new_feature.setAttribute(field_idx, source_feature[field_idx])
                            
                            # Add the new feature
                            homepoints_layer.addFeature(new_feature)
                            total_added += 1
                            
                            # Update our lists
                            all_homepoints.append(new_feature)
                            active_homepoints.append(new_feature)
                            
                            group_logs.append(f"Added new feature with BOX={new_box} (duplicated from BOX={get_box_as_int(source_feature)})")
                        
                        else:
                            # No existing features to duplicate - create from address point
                            if address_info['features']:
                                address_feature = address_info['features'][0]
                                new_feature = QgsFeature(homepoints_layer.fields())
                                
                                # Check if address has valid geometry
                                if not address_feature.hasGeometry():
                                    group_logs.append(f"ERROR: Address point has no geometry, cannot create homepoint")
                                    continue
                                
                                # Copy geometry from address point
                                new_feature.setGeometry(address_feature.geometry())
                                
                                # Set attributes
                                fields = homepoints_layer.fields()
                                for field_idx in range(fields.count()):
                                    field_name = fields.field(field_idx).name()
                                    if field_name in ["DEMAND", "CITY", "STREETNAME", "ADDRESS_NU", "POSTCODE", "LAT", "LON"]:
                                        new_feature.setAttribute(field_idx, address_feature[field_name])
                                    elif field_name == "BOX":
                                        new_feature.setAttribute(field_idx, 1)
                                    elif field_name == "INCLUDE":
                                        new_feature.setAttribute(field_idx, True)
                                    elif field_name == "P2P_HOMES":
                                        new_feature.setAttribute(field_idx, target_p2p)
                                    else:
                                        # Try to copy other matching fields
                                        if field_name in address_feature.fields().names():
                                            new_feature.setAttribute(field_idx, address_feature[field_name])
                                
                                homepoints_layer.addFeature(new_feature)
                                total_added += 1
                                group_logs.append(f"Created new feature from address point with BOX=1 (FID: {address_feature.id()})")
                
                # Case 2: Need to deactivate homepoints
                elif target_p2p < current_active_count:
                    demand_groups_adjusted += 1
                    to_deactivate = current_active_count - target_p2p
                    group_logs.append(f"Need to deactivate {to_deactivate} homepoint(s)")
                    
                    # Sort active homepoints by BOX number (descending) using safe integer conversion
                    active_homepoints.sort(key=lambda x: get_box_as_int(x), reverse=True)
                    
                    for i in range(to_deactivate):
                        if i < len(active_homepoints):
                            homepoint = active_homepoints[i]
                            fid = homepoint.id()
                            
                            # Deactivate the feature
                            homepoints_layer.changeAttributeValue(fid, homepoints_layer.fields().lookupField("INCLUDE"), False)
                            total_deactivated += 1
                            group_logs.append(f"Deactivated feature FID={fid} with BOX={get_box_as_int(homepoint)}")
                
                # Add group logs to detailed logs if adjustments were made
                if len(group_logs) > 1:  # More than just the initial status line
                    detailed_logs.extend(group_logs)
            
            # Remove orphaned homepoints (those with no matching address point)
            detailed_logs.append("INFO: Checking for orphaned homepoints...")
            
            for feature in homepoints_layer.getFeatures():
                # Check if this homepoint matches any address point
                demand = feature["DEMAND"]
                city = feature["CITY"]
                street = feature["STREETNAME"]
                addr_num = feature["ADDRESS_NU"]
                
                key = f"{demand}_{city}_{street}_{addr_num}"
                
                if key not in address_data:
                    # This is an orphaned feature - deactivate it
                    fid = feature.id()
                    homepoints_layer.changeAttributeValue(fid, homepoints_layer.fields().lookupField("INCLUDE"), False)
                    orphaned_count += 1
                    detailed_logs.append(f"Deactivated orphaned feature FID={fid} ({key})")
            
            # Commit changes
            homepoints_layer.commitChanges()
            
            # VERIFICATION WITH DETAILED DEBUGGING
            detailed_logs.append("INFO: Verifying synchronization with detailed debugging...")
            
            # Calculate aggregate P2P_HOMES from Address point
            address_p2p_sum = 0
            verification_issues = []
            
            # Debug: List all address points with their P2P_HOMES
            address_p2p_details = []
            for feature in address_layer.getFeatures():
                p2p_value = feature["P2P_HOMES"]
                p2p_int = 0
                if p2p_value is not None:
                    try:
                        if isinstance(p2p_value, str):
                            p2p_int = int(p2p_value) if p2p_value.strip() else 0
                        else:
                            p2p_int = int(p2p_value)
                    except (ValueError, TypeError):
                        p2p_int = 0
                
                address_p2p_sum += p2p_int
                address_p2p_details.append({
                    'fid': feature.id(),
                    'demand': feature["DEMAND"],
                    'city': feature["CITY"],
                    'street': feature["STREETNAME"],
                    'addr_num': feature["ADDRESS_NU"],
                    'p2p': p2p_int,
                    'p2p_original': p2p_value
                })
            
            # Count active homepoints
            active_homepoints_count = 0
            active_homepoint_details = []
            
            for feature in homepoints_layer.getFeatures():
                if feature["INCLUDE"]:
                    active_homepoints_count += 1
                    active_homepoint_details.append({
                        'fid': feature.id(),
                        'demand': feature["DEMAND"],
                        'city': feature["CITY"],
                        'street': feature["STREETNAME"],
                        'addr_num': feature["ADDRESS_NU"],
                        'box': feature["BOX"]
                    })
            
            # Compare
            if address_p2p_sum != active_homepoints_count:
                verification_issues.append(f"MISMATCH: Address point P2P_HOMES sum ({address_p2p_sum}) != Active homepoints count ({active_homepoints_count})")
                verification_issues.append(f"Difference: {address_p2p_sum - active_homepoints_count}")
                
                # Find addresses with P2P_HOMES > 0 that have no active homepoints
                addresses_without_homepoints = []
                for addr in address_p2p_details:
                    if addr['p2p'] > 0:
                        # Check if this address has any active homepoints
                        has_homepoint = False
                        for homepoint in active_homepoint_details:
                            if (addr['demand'] == homepoint['demand'] and 
                                addr['city'] == homepoint['city'] and 
                                addr['street'] == homepoint['street'] and 
                                addr['addr_num'] == homepoint['addr_num']):
                                has_homepoint = True
                                break
                        
                        if not has_homepoint:
                            addresses_without_homepoints.append(addr)
                
                if addresses_without_homepoints:
                    verification_issues.append(f"Found {len(addresses_without_homepoints)} addresses with P2P_HOMES > 0 but no active homepoints:")
                    for addr in addresses_without_homepoints[:5]:  # Show first 5
                        verification_issues.append(f"  - FID:{addr['fid']} {addr['city']} {addr['street']} {addr['addr_num']} (P2P_HOMES={addr['p2p']})")
                
                # Count homepoints per address group
                homepoint_counts = {}
                for homepoint in active_homepoint_details:
                    key = f"{homepoint['demand']}_{homepoint['city']}_{homepoint['street']}_{homepoint['addr_num']}"
                    homepoint_counts[key] = homepoint_counts.get(key, 0) + 1
                
                # Find addresses where homepoint count doesn't match P2P_HOMES
                for addr in address_p2p_details:
                    if addr['p2p'] > 0:
                        key = f"{addr['demand']}_{addr['city']}_{addr['street']}_{addr['addr_num']}"
                        homepoint_count = homepoint_counts.get(key, 0)
                        if addr['p2p'] != homepoint_count:
                            verification_issues.append(f"  - {key}: P2P_HOMES={addr['p2p']}, Homepoints={homepoint_count}")
            
            # Export added and deactivated features if needed
            added_export_result = self.export_features_by_status(homepoints_layer, "added", 
                                                            [f for f in homepoints_layer.getFeatures() if f["INCLUDE"]])
            deleted_export_result = self.export_features_by_status(homepoints_layer, "deactivated", 
                                                                [f for f in homepoints_layer.getFeatures() if not f["INCLUDE"]])
            
            # Prepare result
            result = {
                'operation': 'sync_addresses_from_survey',
                'status': 'completed',
                'demand_groups_processed': demand_groups_processed,
                'demand_groups_adjusted': demand_groups_adjusted,
                'addresses_added': total_added,
                'addresses_deactivated': total_deactivated,
                'orphaned_removed': orphaned_count,
                'final_count': homepoints_layer.featureCount(),
                'active_count': active_homepoints_count,
                'address_p2p_sum': address_p2p_sum,
                'verification_issues': verification_issues,
                'verification_passed': len(verification_issues) == 0,
                'detailed_logs': detailed_logs[:50],  # Return more logs for debugging
                'surveyed_file': self.surveyed_addresses_file,
                'added_export_result': added_export_result,
                'deleted_export_result': deleted_export_result,
                'timestamp': datetime.now().isoformat(),
                'debug_info': {
                    'addresses_with_p2p_gt_0': len(addresses_with_p2p),
                    'missing_addresses': missing_addresses[:10],  # First 10
                    'address_point_count': address_layer.featureCount(),
                    'unique_address_groups': len(address_data)
                }
            }
            
            # Add verification summary
            if verification_issues:
                result['verification_summary'] = f"Found {len(verification_issues)} issues"
                detailed_logs.extend([f"VERIFICATION ISSUE: {issue}" for issue in verification_issues[:10]])
            else:
                result['verification_summary'] = "All values match correctly"
                detailed_logs.append("VERIFICATION: SUCCESS - P2P_HOMES sum matches active homepoints count")
            
            return result
            
        except Exception as e:
            # Rollback changes on error
            if 'homepoints_layer' in locals() and homepoints_layer.isEditable():
                homepoints_layer.rollBack()
            
            error_details = {
                'operation': 'sync_addresses_from_survey',
                'status': 'failed',
                'error': str(e),
                'traceback': traceback.format_exc(),
                'demand_groups_processed': demand_groups_processed,
                'addresses_added': total_added,
                'addresses_deactivated': total_deactivated,
                'detailed_logs': detailed_logs[-20:]  # Last 20 logs
            }
            
            detailed_logs.append(f"ERROR: {str(e)}")
            detailed_logs.append(f"TRACEBACK: {traceback.format_exc()}")
            
            return error_details
        
    def export_features_by_status(self, layer, status, features):
        """Export features to a temporary file"""
        import tempfile
        
        if not features:
            return {'exported': False, 'count': 0, 'message': f'No {status} features to export'}
        
        # Create temporary file
        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"homepoints_{status}_{timestamp}.shp"
        filepath = os.path.join(temp_dir, filename)
        
        try:
            # Create new layer with same schema
            writer = QgsVectorFileWriter(
                filepath, 
                'UTF-8', 
                layer.fields(), 
                layer.wkbType(), 
                layer.crs(), 
                'ESRI Shapefile'
            )
            
            for feature in features:
                writer.addFeature(feature)
            
            del writer
            
            return {
                'exported': True,
                'count': len(features),
                'filepath': filepath,
                'filename': filename
            }
            
        except Exception as e:
            return {
                'exported': False,
                'count': len(features),
                'error': str(e)
            }
    
    def _create_homepoint_from_surveyed(self, surveyed_feature, target_fields):
        """Create a new homepoint feature from surveyed data"""
        new_feature = QgsFeature(target_fields)
        
        # Copy geometry from surveyed feature - FIXED
        if surveyed_feature.geometry():
            # Use QgsGeometry() constructor to create a copy
            new_feature.setGeometry(QgsGeometry(surveyed_feature.geometry()))
        
        # Field mapping between surveyed and homepoints
        field_mapping = {
            'DEMAND': 'DEMAND',
            'PON_HOMES': 'PON_HOMES',
            'P2P_HOMES': 'P2P_HOMES',
            'INCLUDE': 'INCLUDE',
            'LOCKED': 'LOCKED',
            'CONNECTION': 'CONNECTION',
            'IDENTIFIER': 'IDENTIFIER',
            'PON_M_REV': 'PON_M_REV',
            'P2P_M_REV': 'P2P_M_REV',
            'BLDG_ID': 'BLDG_ID',
            'HEIGHT': 'HEIGHT',
            'FLOORCOUNT': 'FLOORCOUNT',
            'CITY': 'CITY',
            'STREETNAME': 'STREETNAME',
            'NUMBER': 'NUMBER',
            'ADDRESS_SU': 'ADDRESS_SU',
            'LAT': 'LAT',
            'LON': 'LON',
            'POSTCODE': 'POSTCODE',
            'AGGR_ID': 'AGGR_ID',
            'TINA_UUID': 'TINA_UUID',
            'IDENTIFI_1': 'IDENTIFIER_1',
            'EXC_REASON': 'EXC_REASON',
            'STREETNA_1': 'STREETNAME_1',
            'ADDRESS': 'ADDRESS',
            'DEMAND1': 'DEMAND1',
            'GISTOOL_ID': 'GISTOOL_ID',
            'ADDRESS_NU': 'ADDRESS_NU'
        }
        
        # Copy mapped attributes
        for surveyed_field, homepoint_field in field_mapping.items():
            if surveyed_field in surveyed_feature.fields().names():
                field_index = target_fields.indexOf(homepoint_field)
                if field_index >= 0 and surveyed_feature[surveyed_field] is not None:
                    new_feature.setAttribute(field_index, surveyed_feature[surveyed_field])
        
        return new_feature

    def _duplicate_homepoint(self, base_feature, target_fields):
        """Duplicate a homepoint feature"""
        new_feature = QgsFeature(target_fields)
        
        # Copy geometry - FIXED
        if base_feature.geometry():
            # Use QgsGeometry() constructor to create a copy
            new_feature.setGeometry(QgsGeometry(base_feature.geometry()))
        
        # Copy all attributes
        for i in range(target_fields.count()):
            field_name = target_fields.field(i).name()
            if field_name in base_feature.fields().names() and base_feature[field_name] is not None:
                new_feature.setAttribute(i, base_feature[field_name])
        
        return new_feature

    def _extract_box_number(self, box_value):
        """Extract the highest numeric value from BOX string"""
        if not box_value:
            return 0
        
        # Find all numbers in the string
        numbers = re.findall(r'\d+', str(box_value))
        
        if numbers:
            # Return the largest number found
            return max(int(num) for num in numbers)
        
        return 0

    def _get_max_box_number(self, features):
        """Get the maximum box number from a list of features"""
        max_num = 0
        for feature in features:
            box_num = self._extract_box_number(feature['BOX'])
            if box_num > max_num:
                max_num = box_num
        return max_num

    def _export_features_to_shapefile(self, features, crs, layer_type):
        """
        Export a list of features to a shapefile and load it to QGIS
        """
        try:
            if not features:
                return {'status': 'skipped', 'message': f'No features to export for {layer_type}'}
            
            import tempfile
            import os
            
            # Create output directory
            output_dir = tempfile.gettempdir()
            shapefile_dir = os.path.join(output_dir, "design_tool_addresses")
            os.makedirs(shapefile_dir, exist_ok=True)
            
            # Create shapefile path with timestamp
            import time
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            shapefile_name = f"In_homepoints_{layer_type}_{timestamp}"
            shapefile_path = os.path.join(shapefile_dir, f"{shapefile_name}.shp")
            
            print(f"Exporting {layer_type} to shapefile: {shapefile_path}")
            
            # Get fields from first feature
            first_feature = features[0]
            fields = first_feature.fields()
            
            # Create in-memory layer with these fields
            memory_layer = QgsVectorLayer(f"Point?crs={crs.authid()}", shapefile_name, "memory")
            memory_layer.dataProvider().addAttributes(fields)
            memory_layer.updateFields()
            
            # Add all features to memory layer
            memory_layer.dataProvider().addFeatures(features)
            
            # Save to shapefile
            error = QgsVectorFileWriter.writeAsVectorFormat(
                memory_layer,
                shapefile_path,
                "utf-8",
                crs,
                "ESRI Shapefile"
            )
            
            if error[0] != QgsVectorFileWriter.NoError:
                error_msg = f"Failed to export {layer_type} shapefile: {error[1]}"
                print(error_msg)
                return {
                    'status': 'failed',
                    'error': error_msg
                }
            
            print(f"Shapefile exported successfully to: {shapefile_path}")
            
            # Load the shapefile back into QGIS
            exported_layer = QgsVectorLayer(shapefile_path, shapefile_name, "ogr")
            
            if not exported_layer.isValid():
                error_msg = f"Failed to load exported shapefile: {exported_layer.lastError()}"
                print(error_msg)
                return {
                    'status': 'failed',
                    'error': error_msg
                }
            
            # Add the layer to QGIS project
            QgsProject.instance().addMapLayer(exported_layer)
            print(f"Shapefile loaded to QGIS: {shapefile_name}")
            
            return {
                'status': 'completed',
                'shapefile_path': shapefile_path,
                'layer_name': shapefile_name,
                'feature_count': len(features),
                'message': f'{layer_type} exported and loaded as layer: {shapefile_name}'
            }
            
        except Exception as e:
            error_msg = f"Error exporting {layer_type} to shapefile: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            
            return {
                'status': 'failed',
                'error': error_msg
            }

    def auto_increment_agg_id(self):
        drop_points = get_layer_by_name("Drop Points")
        drop_clusters = get_layer_by_name("Drop Clusters")

        self.configure_agg_id_autofill(drop_points, 'AGG_ID')
        self.configure_agg_id_autofill(drop_clusters, 'AGG_ID')
        
        return {
            'operation': 'auto_increment_agg_id',
            'status': 'completed',
            'message': 'AGG_ID auto-increment configured'
        }

    def configure_agg_id_autofill(self, layer, field:str):
        """Set default AGG_ID = next highest value."""
        if not layer:
            return

        pr = layer.dataProvider()
        idx = pr.fieldNameIndex(field)
        if idx == -1:
            print(f"Layer {layer.name()} has no {field} field")
            return

        # QGIS expression for next max ID
        expr = f'coalesce(maximum("{field}") + 1, 1)'

        # Apply default value expression
        layer.setDefaultValueDefinition(idx, QgsDefaultValue(expr, True))

        print(f"{field} auto-fill configured for: {layer.name()}")

    def move_homepoints(self):
        """ Move Demand Points to the edge of buidings """
        p = QgsProject.instance()
        dp = get_layer_by_name("Demand Points")
        cables = get_layer_by_name("Drop Cables")
        blds = get_layer_by_name("IN_Buildings")
        # Create backup of original positions
        snap = QgsVectorLayer(f"Point?crs={dp.crs().authid()}", "Demand Points Original Positions", "memory") # type: ignore
        snap.dataProvider().addAttributes(dp.fields()) # type: ignore
        snap.updateFields()
    
        # Build indices for performance
        b_idx = QgsSpatialIndex(blds.getFeatures()) # type: ignore
        cable_feats = [f for f in cables.getFeatures()] # type: ignore
    
        dp.startEditing() # type: ignore
        moved = skipped = 0
    
        for f in dp.getFeatures(): # type: ignore
            g, pt, id_drop, sub = f.geometry(), f.geometry().asPoint(), f['ID_DROP'], f['SUBCLUSTER']
        
            # Find building
            target = next((blds.getFeature(bid) for bid in b_idx.intersects(g.boundingBox()) # type: ignore
                      if g.intersects(blds.getFeature(bid).geometry())), None) # type: ignore
            if not target: 
                skipped += 1
                continue
        
            # Find ALL matching cables for this specific Demand point
            bgeom, buf = target.geometry(), target.geometry().buffer(0.5, 5)
            best = None
        
            for c in cable_feats:
                # Skip cables that don't match THIS Demand Point attributes
                if str(id_drop) != str(c['TOP_AGG_ID']) and str(sub) != str(c['CAB_GROUP']): 
                    continue
                
                if not c.geometry().intersects(buf): 
                    continue
            
                # Find intersection point for THIS cable
                inter = c.geometry().intersection(bgeom)
                if inter and not inter.isEmpty():
                    if inter.type() == QgsWkbTypes.PointGeometry:
                        pts = inter.asMultiPoint() if inter.isMultipart() else [inter.asPoint()]
                        for candidate_point in pts:
                            if not best or pt.distance(candidate_point) < pt.distance(best):
                                best = candidate_point
                    else:
                        nearest = inter.nearestPoint(QgsGeometry.fromPointXY(pt)).asPoint()
                        if not best or pt.distance(nearest) < pt.distance(best):
                            best = nearest
                else:
                    nearest = c.geometry().nearestPoint(bgeom).asPoint()
                    if not best or pt.distance(nearest) < pt.distance(best):
                        best = nearest
        
            # Move Demand Point if intersection found
            if best:
                # Save original position
                sf = QgsFeature(snap.fields())
                sf.setGeometry(QgsGeometry.fromPointXY(pt))
                sf.setAttributes(f.attributes())
                snap.dataProvider().addFeatures([sf])
            
                # Move demand point to new position
                dp.changeGeometry(f.id(), QgsGeometry.fromPointXY(best)) # type: ignore
                moved += 1
            else:
                skipped += 1
    
        dp.commitChanges() # type: ignore
        if snap.featureCount() > 0:
            p.addMapLayer(snap)
    
        # final output
        print(f"Demand Points movement completed.")
        print(f" Moved:  {moved}, Skipped:  {skipped} ")
        return {'moved': moved, 'skipped': skipped}
    
    def _load_surveyed_layer(self):
        """Load the surveyed addresses layer from file"""
        try:
            print(f"Attempting to load surveyed layer from: {self.surveyed_addresses_file}")
            # Load the external layer - ogr provider supports both shapefiles and geopackages
            surveyed_layer = QgsVectorLayer(
                self.surveyed_addresses_file,
                "surveyed_addresses_temp",
                "ogr"
            )
            
            if not surveyed_layer.isValid():
                print(f"Failed to load layer: {self.surveyed_addresses_file}")
                print(f"Layer error: {surveyed_layer.lastError()}")
                return None
            
            print(f"Layer loaded successfully: {surveyed_layer.name()}")
            print(f"Layer type: {surveyed_layer.providerType()}")
            print(f"Feature count: {surveyed_layer.featureCount()}")
            print(f"Fields: {[field.name() for field in surveyed_layer.fields()]}")
            
            # Verify required fields exist - updated based on actual fields
            required_fields = ['DEMAND', 'P2P_HOMES']  # Only absolutely required fields
            recommended_fields = ['CITY', 'STREETNAME', 'POSTCODE']  # Nice to have but not critical
            
            existing_fields = [field.name() for field in surveyed_layer.fields()]
            
            missing_required = []
            for field in required_fields:
                if field not in existing_fields:
                    missing_required.append(field)

            if missing_required:
                print(f"Missing required fields: {missing_required}")
                return None

            # Check recommended fields
            missing_recommended = []
            for field in recommended_fields:
                if field not in existing_fields:
                    missing_recommended.append(field)

            if missing_recommended:
                print(f"Warning: Missing recommended fields: {missing_recommended}")
                print("Will proceed but address details may be incomplete")
            
            print("All required fields found in surveyed layer")
            return surveyed_layer
            
        except Exception as e:
            print(f"Error loading surveyed layer: {e}")
            return None

    def analyze_sidewalk_intersections(self):
        """
        Complete workflow: Clip sidewalk geometries to feeder_cluster extent,
        then find intersections with trenches layer using UI-imported layers
        """
        try:
            print("Starting sidewalk intersection analysis...")
            
            # Check if trenches layer name is provided from UI
            if not self.trenches_layer_name:
                return {
                    'operation': 'analyze_sidewalk_intersections',
                    'status': 'failed',
                    'error': "No trenches layer selected. Please select a trenches layer from the UI first."
                }
            
            print(f"Looking for trenches layer from UI: '{self.trenches_layer_name}'")
            
            # Get the trenches layer from UI selection
            trenches_layer = self._get_layer_by_name_with_fallback(self.trenches_layer_name)
            if not trenches_layer:
                all_layer_names = [layer.name() for layer in QgsProject.instance().mapLayers().values()]
                return {
                    'operation': 'analyze_sidewalk_intersections',
                    'status': 'failed',
                    'error': f"Trenches layer '{self.trenches_layer_name}' not found. Available layers: {all_layer_names}"
                }
            
            print(f"Found trenches layer: {trenches_layer.name()} ({trenches_layer.featureCount()} features)")
            
            # Step 1: Load and clip the sidewalk layer
            sidewalk_layer_name = "GRB - WGO - wegopdeling"
            print(f"Looking for sidewalk layer: '{sidewalk_layer_name}'")
            
            sidewalk_layer = self._get_or_load_sidewalk_layer(sidewalk_layer_name)
            if not sidewalk_layer:
                return {
                    'operation': 'analyze_sidewalk_intersections',
                    'status': 'failed',
                    'error': f"Could not load sidewalk layer '{sidewalk_layer_name}'."
                }
            
            print(f"Found sidewalk layer: {sidewalk_layer.name()} ({sidewalk_layer.featureCount()} features)")
            
            # Get feeder_cluster layer (from UI)
            print("Loading feeder_cluster layer for clipping...")
            feeder_cluster = get_layer_by_name("feeder_cluster")
            
            if not feeder_cluster or not feeder_cluster.isValid():
                return {
                    'operation': 'analyze_sidewalk_intersections',
                    'status': 'failed',
                    'error': "feeder_cluster layer not found or invalid. Please ensure it's loaded in the UI."
                }
            
            print(f"Found feeder_cluster layer: {feeder_cluster.name()} ({feeder_cluster.featureCount()} features)")
            
            # Step 2: Clip sidewalk layer using the provided clip method
            clipped_layer_name = "Clipped GRB - WGO - wegopdeling"
            print(f"\nClipping sidewalk layer to feeder_cluster extent...")
            
            # Use the clip method from your example
            result = self._clip_lines_with_polygon(
                line_layer=sidewalk_layer,
                polygon_layer=feeder_cluster,
                output_layer_name=clipped_layer_name
            )
            
            if not result or not result.get('success', False):
                return {
                    'operation': 'analyze_sidewalk_intersections',
                    'status': 'failed',
                    'error': f"Clipping failed: {result.get('error', 'Unknown error')}"
                }
            
            # Get the clipped layer
            clipped_sidewalk_layer = result.get('layer')
            if not clipped_sidewalk_layer or not clipped_sidewalk_layer.isValid():
                return {
                    'operation': 'analyze_sidewalk_intersections',
                    'status': 'failed',
                    'error': "Clipped layer is invalid or could not be loaded."
                }
            
            print(f"Clipping successful!")
            print(f"Original sidewalk features: {sidewalk_layer.featureCount()}")
            print(f"Clipped sidewalk features: {clipped_sidewalk_layer.featureCount()}")
            print(f"Clipped layer name: '{clipped_sidewalk_layer.name()}'")
            
            # Step 3: Find intersections using the clipped layer
            print(f"\nFinding intersections between clipped sidewalk and trenches layers...")
            print(f"Using layer 1: {clipped_sidewalk_layer.name()}")
            print(f"Using layer 2: {trenches_layer.name()}")
            
            # Find intersections using Line Intersections algorithm
            params = {
                'INPUT': clipped_sidewalk_layer,
                'INTERSECT': trenches_layer,
                'INPUT_FIELDS': [],  # Optional: include fields from layer1
                'INTERSECT_FIELDS': [],  # Optional: include fields from layer2
                'OUTPUT': 'memory:intersection_points'
            }
            
            print("Running intersection analysis...")
            intersection_result = processing.run("native:lineintersections", params)
            
            if not intersection_result or 'OUTPUT' not in intersection_result:
                return {
                    'operation': 'analyze_sidewalk_intersections',
                    'status': 'failed',
                    'error': "Intersection algorithm returned no output"
                }
            
            intersection_layer = intersection_result['OUTPUT']
            intersection_layer_name = f"Intersections_{clipped_layer_name}_{self.trenches_layer_name}"
            intersection_layer.setName(intersection_layer_name)
            
            # Style the intersection points with red circles
            symbol = QgsMarkerSymbol.createSimple({
                'name': 'circle',
                'color': 'red',
                'size': '3',
                'outline_color': 'black',
                'outline_width': '0.5'
            })
            
            # Correct way to set the symbol
            renderer = QgsSingleSymbolRenderer(symbol)
            intersection_layer.setRenderer(renderer)
            
            # Add to project
            QgsProject.instance().addMapLayer(intersection_layer)
            
            intersection_count = intersection_layer.featureCount()
            print(f"Found {intersection_count} intersection points")
            print(f"Layer added: {intersection_layer.name()}")
            
            # Step 4: Save the intersection layer to shapefile
            project_path = QgsProject.instance().fileName()
            if project_path:
                base_dir = os.path.dirname(project_path)
                clipped_folder = os.path.join(base_dir, "clipped")
                os.makedirs(clipped_folder, exist_ok=True)
                
                intersection_filename = "possible_trenches_intersection_points.shp"
                intersection_path = os.path.join(clipped_folder, intersection_filename)
                
                # Save the layer to shapefile
                save_result = self._save_layer_to_shapefile(
                    intersection_layer, 
                    intersection_path, 
                    "Possible Trenches Intersection Points"
                )
                
                if save_result.get('status') == 'success':
                    print(f"Intersection points saved to: {intersection_path}")
                else:
                    print(f"Warning: Could not save intersection points: {save_result.get('error')}")
            else:
                print("Warning: Project not saved, intersection layer not saved to disk")
            
            # Step 5: Return results
            result = {
                'operation': 'analyze_sidewalk_intersections',
                'status': 'completed',
                'message': 'Intersection analysis completed successfully',
                'intersection_layer_name': intersection_layer_name,
                'intersection_count': intersection_count,
                'sidewalk_original_features': sidewalk_layer.featureCount(),
                'sidewalk_clipped_features': clipped_sidewalk_layer.featureCount(),
                'trenches_features': trenches_layer.featureCount(),
                'clipped_layer_used': clipped_sidewalk_layer.name(),
                'trenches_layer_used': trenches_layer.name()
            }
            
            # Print summary
            print("\n" + "="*60)
            print("SIDEWALK INTERSECTION ANALYSIS - COMPLETED")
            print("="*60)
            print(f"Sidewalk layer (original): {sidewalk_layer.name()} ({result['sidewalk_original_features']} features)")
            print(f"Sidewalk layer (clipped): {result['clipped_layer_used']} ({result['sidewalk_clipped_features']} features)")
            print(f"Trenches layer: {result['trenches_layer_used']} ({result['trenches_features']} features)")
            print(f"Intersection points found: {result['intersection_count']}")
            print(f"Intersection layer: {result['intersection_layer_name']}")
            print("="*60)
            
            return result
            
        except Exception as e:
            print(f"Error in sidewalk intersection analysis: {e}")
            traceback.print_exc()
            return {
                'operation': 'analyze_sidewalk_intersections',
                'status': 'failed',
                'error': str(e)
            }

    def _get_layer_by_name_with_fallback(self, layer_name):
        """Get layer by name with case-insensitive fallback"""
        layers = QgsProject.instance().mapLayersByName(layer_name)
        if not layers:
            all_layers = QgsProject.instance().mapLayers()
            for layer in all_layers.values():
                if layer.name().lower() == layer_name.lower():
                    return layer
            return None
        return layers[0]

    def _get_or_load_sidewalk_layer(self, layer_name):
        """Get sidewalk layer, loading from WFS if necessary"""
        layers = QgsProject.instance().mapLayersByName(layer_name)
        if not layers:
            print(f"Sidewalk layer '{layer_name}' not found, attempting to load external WFS layers...")
            if hasattr(self, 'add_external_wfs_layers'):
                add_external_wfs_layers(lambda msg, msg_type: print(f"[{msg_type}] {msg}"))
            else:
                try:
                    add_external_wfs_layers(lambda msg, msg_type: print(f"[{msg_type}] {msg}"))
                except Exception:
                    print("Warning: Could not load WFS layers function")
            
            # Check again after loading
            layers = QgsProject.instance().mapLayersByName(layer_name)
            if not layers:
                return None
        return layers[0]

    def _clip_lines_with_polygon(self, line_layer, polygon_layer, output_layer_name):
        """
        Clip a line layer using a polygon layer
        Modified version of the provided clip method
        """
        try:
            print(f"Clipping '{line_layer.name()}' with '{polygon_layer.name()}'...")
            
            # Validate line layer geometry type
            geom_type = line_layer.wkbType()
            if QgsWkbTypes.geometryType(geom_type) != QgsWkbTypes.LineGeometry:
                return {
                    'success': False,
                    'error': "Selected layer is not a line layer."
                }
            
            if not line_layer.isValid():
                return {
                    'success': False,
                    'error': "Line layer is not valid."
                }
            
            if not polygon_layer.isValid():
                return {
                    'success': False,
                    'error': "Polygon layer is not valid."
                }
            
            # CRS handling - reproject polygon to match line layer if needed
            if line_layer.crs() != polygon_layer.crs():
                print("⚠️ CRS mismatch! Reprojecting polygon layer to match line layer...")
                params = {
                    'INPUT': polygon_layer,
                    'TARGET_CRS': line_layer.crs(),
                    'OUTPUT': 'memory:Reprojected_Polygon'
                }
                reproj = processing.run("native:reprojectlayer", params)
                clip_layer = reproj['OUTPUT']
            else:
                clip_layer = polygon_layer
            
            # Perform clip using "native:clip" algorithm
            params = {
                'INPUT': line_layer,
                'OVERLAY': clip_layer,
                'OUTPUT': 'memory:'
            }
            
            try:
                result = processing.run("native:clip", params)
                clipped_layer = result['OUTPUT']
                
                if not clipped_layer or not clipped_layer.isValid():
                    return {
                        'success': False,
                        'error': "Clip operation produced invalid layer."
                    }
                
                # Set the output name
                clipped_layer.setName(output_layer_name)
                
                # Add to project
                QgsProject.instance().addMapLayer(clipped_layer)
                
                print(f"✅ Successfully added clipped layer: '{output_layer_name}'")
                
                return {
                    'success': True,
                    'layer': clipped_layer,
                    'message': f"Clipped layer '{output_layer_name}' created successfully"
                }
                
            except Exception as e:
                print(f"❌ Clipping failed: {str(e)}")
                
                # Try alternative clip method if native:clip fails
                try:
                    print("Trying alternative clip method...")
                    params = {
                        'INPUT': line_layer,
                        'MASK': clip_layer,
                        'OUTPUT': 'memory:'
                    }
                    result = processing.run("native:clipvectorbymask", params) # type: ignore
                    clipped_layer = result['OUTPUT']
                    
                    if clipped_layer and clipped_layer.isValid():
                        clipped_layer.setName(output_layer_name)
                        QgsProject.instance().addMapLayer(clipped_layer)
                        
                        return {
                            'success': True,
                            'layer': clipped_layer,
                            'message': f"Clipped layer '{output_layer_name}' created using alternative method"
                        }
                except Exception as e2:
                    print(f"Alternative method also failed: {str(e2)}")
                
                return {
                    'success': False,
                    'error': f"Clipping failed: {str(e)}"
                }
                
        except Exception as e:
            print(f"Error in clip operation: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _save_layer_to_shapefile(self, layer, output_path, layer_name=None):
        """Save a layer to shapefile"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Remove existing file if it exists
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            
            # Save options
            save_options = QgsVectorFileWriter.SaveVectorOptions()
            save_options.driverName = "ESRI Shapefile"
            save_options.fileEncoding = "UTF-8"
            
            # Transform context
            transform_context = QgsProject.instance().transformContext()
            
            # Write to shapefile
            error = QgsVectorFileWriter.writeAsVectorFormatV3(
                layer,
                output_path,
                transform_context,
                save_options
            )
            
            if error[0] == QgsVectorFileWriter.NoError:
                return {
                    'status': 'success',
                    'path': output_path,
                    'message': f"Layer saved to {output_path}"
                }
            else:
                return {
                    'status': 'failed',
                    'error': f"Failed to save layer: {error[1]}"
                }
                
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e)
            }

    def _cleanup_temporary_layers(self):
        """Clean up temporary memory layers (optional)"""
        try:
            memory_layers = []
            for layer in QgsProject.instance().mapLayers().values():
                if layer.dataProvider().name() == 'memory':
                    memory_layers.append(layer.id())
            
            for layer_id in memory_layers:
                QgsProject.instance().removeMapLayer(layer_id)
            
            if memory_layers:
                print(f"Cleaned up {len(memory_layers)} memory layers")
        except Exception as e:
            print(f"Error cleaning up layers: {e}")

    def assign_clusters_by_distribution_cables(self):
        """
        Assign drop points to clusters based on distribution cable groups.
        
        Steps:
        1. Group cables by cable_group (CAB_GROUP or similar field)
        2. For each cable_group:
           - Merge all cables with same cable_group
           - Find associated drop points (topology or proximity)
           - Order drop points along cable path
           - Split into clusters (max 11 per cluster, max 22 total)
        3. Create cluster output
        """
        try:
            print("\n" + "="*70)
            print("STARTING: assign_clusters_by_distribution_cables()")
            print("="*70)
            
            # Get required layers
            print("\nLooking for required layers...")
            distribution_cables = get_layer_by_name("Distribution Cables")
            drop_points = get_layer_by_name("Drop Points")
            distribution_points = get_layer_by_name("Distribution Points")
            
            print(f"Distribution Cables: {distribution_cables}")
            print(f"Drop Points: {drop_points}")
            print(f"Distribution Points: {distribution_points}")
            
            # Validate layers
            if not distribution_cables:
                print("ERROR: Distribution Cables layer not found")
                return {
                    'operation': 'assign_clusters_by_distribution_cables',
                    'status': 'failed',
                    'error': "Distribution Cables layer not found"
                }
            
            if not drop_points:
                print("ERROR: Drop Points layer not found")
                return {
                    'operation': 'assign_clusters_by_distribution_cables',
                    'status': 'failed',
                    'error': "Drop Points layer not found"
                }
            
            print(f"✓ Distribution Cables: {distribution_cables.featureCount()} features")
            print(f"✓ Drop Points: {drop_points.featureCount()} features")

            # Step 1: Group cables by cable_group
            print("\nStep 1: Grouping cables by cable_group...")
            cables_by_group = self._group_cables_by_group(distribution_cables)
            print(f"Found {len(cables_by_group)} unique cable groups")
            
            # Step 2: Process each cable group
            print("\nStep 2: Processing each cable group...")
            cluster_results = []
            errors = []
            
            for cable_group_id, cable_features in cables_by_group.items():
                print(f"\n  Processing cable_group: {cable_group_id}")
                
                # Merge cables with same cable_group
                merged_geometry = self._merge_cable_geometries(cable_features)
                if not merged_geometry:
                    errors.append(f"Could not merge geometries for cable_group {cable_group_id}")
                    continue
                
                # Find associated drop points
                associated_drops = self._find_associated_drop_points(
                    cable_group_id,
                    cable_features,
                    drop_points,
                    distribution_cables
                )
                
                print(f"    Found {len(associated_drops)} drop points")
                
                if len(associated_drops) == 0:
                    print(f"    Warning: No drop points associated with cable_group {cable_group_id}")
                    continue
                
                # Order drop points along cable path
                ordered_drops = self._order_drops_along_cable(associated_drops, merged_geometry)
                print(f"    Ordered {len(ordered_drops)} drop points along cable path")
                
                # Validate drop point count
                if len(ordered_drops) > 22:
                    errors.append(f"cable_group {cable_group_id}: {len(ordered_drops)} drop points exceeds maximum of 22")
                    continue
                
                # Split into clusters
                clusters = self._split_into_clusters(cable_group_id, ordered_drops)
                print(f"    Created {len(clusters)} cluster(s)")
                
                cluster_results.extend(clusters)
            
            # Step 3: Create output layers
            print(f"\nStep 3: Creating output layers ({len(cluster_results)} clusters)...")
            output_result = self._create_cluster_output_layers(cluster_results, drop_points.crs())
            
            # Compile results
            result = {
                'operation': 'assign_clusters_by_distribution_cables',
                'status': 'completed' if not errors else 'completed_with_errors',
                'message': f"Processed {len(cables_by_group)} cable groups, created {len(cluster_results)} clusters",
                'cable_groups_processed': len(cables_by_group),
                'total_clusters_created': len(cluster_results),
                'drop_points_assigned': sum(len(c['drop_points']) for c in cluster_results),
                'errors': errors,
                'output_layers': output_result.get('layers', [])
            }
            
            if errors:
                result['error_details'] = errors
            
            print(f"\n=== Cluster Assignment Summary ===")
            print(f"Cable groups processed: {result['cable_groups_processed']}")
            print(f"Clusters created: {result['total_clusters_created']}")
            print(f"Drop points assigned: {result['drop_points_assigned']}")
            if errors:
                print(f"Errors: {len(errors)}")
                for error in errors:
                    print(f"  - {error}")
            print("==================================")
            
            return result
            
        except Exception as e:
            print(f"Error in assign_clusters_by_distribution_cables: {e}")
            traceback.print_exc()
            
            return {
                'operation': 'assign_clusters_by_distribution_cables',
                'status': 'failed',
                'error': str(e)
            }

    def _group_cables_by_group(self, cables_layer):
        """
        Group cable features by their cable_group field (CAB_GROUP, cable_group, etc.)
        Returns dictionary: {cable_group_id: [cable_features]}
        """
        cables_by_group = {}
        
        # Find the cable group field name
        field_names = [field.name() for field in cables_layer.fields()]
        cable_group_field = None
        
        for field_name in ['CAB_GROUP', 'cable_group', 'CableGroup', 'CABLE_GROUP']:
            if field_name in field_names:
                cable_group_field = field_name
                break
        
        if not cable_group_field:
            print(f"Warning: Could not find cable_group field. Available fields: {field_names}")
            # Use first field as fallback
            cable_group_field = field_names[0] if field_names else None
        
        if not cable_group_field:
            return cables_by_group
        
        print(f"Using field '{cable_group_field}' for grouping cables")
        
        # Group cables
        for feature in cables_layer.getFeatures():
            group_id = feature[cable_group_field]
            
            if group_id not in cables_by_group:
                cables_by_group[group_id] = []
            
            cables_by_group[group_id].append(feature)
        
        return cables_by_group

    def _merge_cable_geometries(self, cable_features):
        """
        Merge multiple cable geometries (may be disjoint) into single logical path.
        Returns merged QgsGeometry
        """
        if not cable_features:
            return None
        
        # Collect all geometries
        geometries = [f.geometry() for f in cable_features if f.geometry() and f.geometry().isGeosValid()]
        
        if not geometries:
            return None
        
        if len(geometries) == 1:
            return geometries[0]
        
        # Use dissolve/union to merge
        try:
            merged = geometries[0]
            for geom in geometries[1:]:
                merged = merged.combine(geom)
            
            return merged
        except Exception as e:
            print(f"Error merging geometries: {e}")
            return geometries[0]  # Fallback to first geometry

    def _find_associated_drop_points(self, cable_group_id, cable_features, drop_points_layer, cables_layer):
        """
        Find drop points associated with this cable_group.
        Uses topology (intersects/touches) as preferred method, proximity as fallback.
        Returns list of drop point features
        """
        associated = []
        
        # Get cable geometries
        cable_geoms = [f.geometry() for f in cable_features if f.geometry()]
        if not cable_geoms:
            return associated
        
        # Build merged cable geometry for spatial operations
        merged_cable = cable_geoms[0]
        for geom in cable_geoms[1:]:
            merged_cable = merged_cable.combine(geom)
        
        # Buffer cable slightly for proximity matching (fallback method)
        cable_buffer = merged_cable.buffer(10, 5)  # 10 unit buffer
        
        # Find associated drop points
        for drop_feature in drop_points_layer.getFeatures():
            drop_geom = drop_feature.geometry()
            if not drop_geom:
                continue
            
            # Method 1: Topology (preferred)
            if drop_geom.intersects(merged_cable) or drop_geom.touches(merged_cable):
                associated.append(drop_feature)
            # Method 2: Proximity (fallback)
            elif drop_geom.intersects(cable_buffer):
                associated.append(drop_feature)
        
        return associated

    def _order_drops_along_cable(self, drop_features, cable_geometry):
        """
        Order drop points along the cable path by distance from start.
        Returns list of drop features ordered along cable
        """
        if not drop_features or not cable_geometry:
            return drop_features
        
        # Get cable start point
        start_point = cable_geometry.asPolyline()[0] if cable_geometry.isMultipart() else cable_geometry.asPolyline()[0]
        
        # Calculate distance from start for each drop
        drops_with_distance = []
        for feature in drop_features:
            drop_geom = feature.geometry()
            if drop_geom:
                # Distance along line (approximate using nearest point)
                nearest_point = cable_geometry.nearestPoint(drop_geom)
                distance = start_point.distance(nearest_point.asPoint())
                drops_with_distance.append((distance, feature))
        
        # Sort by distance
        drops_with_distance.sort(key=lambda x: x[0])
        
        return [f for _, f in drops_with_distance]

    def _split_into_clusters(self, cable_group_id, ordered_drops):
        """
        Split ordered drop points into clusters.
        Rules:
        - If N ≤ 11 → 1 cluster
        - If 12 ≤ N ≤ 22 → 2 clusters
        - If N > 22 → ERROR (handled elsewhere)
        
        Returns list of cluster dictionaries
        """
        clusters = []
        n = len(ordered_drops)
        
        if n <= 11:
            # Single cluster with all drops
            clusters.append({
                'cable_group': cable_group_id,
                'cluster_id': f"{cable_group_id}_C1",
                'cluster_number': 1,
                'total_clusters': 1,
                'drop_points': ordered_drops,
                'drop_count': len(ordered_drops)
            })
        
        elif 12 <= n <= 22:
            # Two clusters: split as specified
            split_point = n - 11  # First cluster gets (N - 11) drops
            
            # Cluster 1: first (N - 11) drops
            clusters.append({
                'cable_group': cable_group_id,
                'cluster_id': f"{cable_group_id}_C1",
                'cluster_number': 1,
                'total_clusters': 2,
                'drop_points': ordered_drops[:split_point],
                'drop_count': split_point
            })
            
            # Cluster 2: remaining drops
            clusters.append({
                'cable_group': cable_group_id,
                'cluster_id': f"{cable_group_id}_C2",
                'cluster_number': 2,
                'total_clusters': 2,
                'drop_points': ordered_drops[split_point:],
                'drop_count': len(ordered_drops) - split_point
            })
        
        return clusters

    def _create_cluster_output_layers(self, clusters, crs):
        """
        Create output layers for clusters.
        Returns dictionary with created layer information
        """
        try:
            output_info = {
                'status': 'success',
                'layers': []
            }
            
            if not clusters:
                return output_info
            
            # Create in-memory layer for cluster points
            cluster_layer = QgsVectorLayer(f"Point?crs={crs.authid()}", "Distribution_Clusters", "memory")
            
            # Add fields
            fields = QgsFields()
            fields.append(QgsField("cluster_id", QVariant.String))
            fields.append(QgsField("cable_group", QVariant.String))
            fields.append(QgsField("cluster_number", QVariant.Int))
            fields.append(QgsField("total_clusters", QVariant.Int))
            fields.append(QgsField("drop_count", QVariant.Int))
            
            cluster_layer.dataProvider().addAttributes(fields)
            cluster_layer.updateFields()
            
            # Add cluster features (using centroid of drop points)
            for cluster in clusters:
                drop_geoms = [f.geometry() for f in cluster['drop_points'] if f.geometry()]
                
                if drop_geoms:
                    # Calculate centroid
                    xs = [g.asPoint().x() for g in drop_geoms]
                    ys = [g.asPoint().y() for g in drop_geoms]
                    centroid_x = sum(xs) / len(xs)
                    centroid_y = sum(ys) / len(ys)
                    
                    feature = QgsFeature()
                    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(centroid_x, centroid_y)))
                    feature.setAttributes([
                        cluster['cluster_id'],
                        cluster['cable_group'],
                        cluster['cluster_number'],
                        cluster['total_clusters'],
                        cluster['drop_count']
                    ])
                    
                    cluster_layer.dataProvider().addFeature(feature)
            
            # Add to project
            QgsProject.instance().addMapLayer(cluster_layer)
            
            output_info['layers'].append({
                'name': 'Distribution_Clusters',
                'feature_count': cluster_layer.featureCount(),
                'crs': crs.authid()
            })
            
            print(f"Created output layer: Distribution_Clusters with {cluster_layer.featureCount()} features")
            
            return output_info
            
        except Exception as e:
            print(f"Error creating cluster output layers: {e}")
            traceback.print_exc()
            
            return {
                'status': 'failed',
                'error': str(e),
                'layers': []
            }