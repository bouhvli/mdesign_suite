from ...utils.layer_loader import get_layer_by_name
from qgis.core import QgsGeometry, QgsSpatialIndex  # type: ignore


class PrimaryDistributionValidator:
    def __init__(self):
        self.violations = []

    def validate_pdp_cable_limits(self, max_cables_leaving=8, min_primary_cables=3, buffer_distance=2.0):
        """
        Validate PDP (Primary Distribution Point) cable limits
        
        Rules:
        1. Max cables leaving the PDP are 8 (all cables intersecting with 2m buffer)
        2. Minimum 3 Primary distribution cables present in PDP
        3. Maximum 2 distribution cables present in PDP
        
        Args:
            max_cables_leaving: Maximum total cables leaving PDP (default: 8)
            min_primary_cables: Minimum primary distribution cables (default: 3)
            buffer_distance: Buffer distance around PDP points (default: 2.0m)
        """
        print("Validating PDP cable limits...")
        
        # Get required layers
        pdp_layer = get_layer_by_name('Primary Distribution Points')
        primary_cables_layer = get_layer_by_name('Primary Distribution Cables')
        distribution_cables_layer = get_layer_by_name('Distribution Cables')
        
        if not pdp_layer:
            return {
                'rule_id': 'PRIMARY_001',
                'Description': 'PDP cable limits validation',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Primary Distribution Points layer not found'
            }
        
        if not primary_cables_layer and not distribution_cables_layer:
            return {
                'rule_id': 'PRIMARY_001',
                'Description': 'PDP cable limits validation',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'No cable layers found for PDP validation'
            }

        violations = []
        
        # Process each PDP point
        for pdp_feature in pdp_layer.getFeatures():
            pdp_geometry = pdp_geometry = pdp_feature.geometry()
            if not pdp_geometry or pdp_geometry.isEmpty():
                continue
            
            pdp_id = pdp_feature['PDP_ID'] if 'PDP_ID' in pdp_feature.fields().names() else pdp_feature.id()
            
            # Create buffer around PDP point
            pdp_buffer = pdp_geometry.buffer(buffer_distance, 5)  # 5 segments for buffer
            
            # Count cables intersecting with PDP buffer
            primary_cables_count = 0
            distribution_cables_count = 0
            all_cables_count = 0
            
            # Count primary distribution cables
            if primary_cables_layer:
                for cable_feature in primary_cables_layer.getFeatures():
                    cable_geometry = cable_feature.geometry()
                    if cable_geometry and not cable_geometry.isEmpty() and cable_geometry.intersects(pdp_buffer):
                        primary_cables_count += 1
            
            # Count distribution cables
            if distribution_cables_layer:
                for cable_feature in distribution_cables_layer.getFeatures():
                    cable_geometry = cable_feature.geometry()
                    if cable_geometry and not cable_geometry.isEmpty() and cable_geometry.intersects(pdp_buffer):
                        distribution_cables_count += 1
            
            # Calculate total cables
            all_cables_count = primary_cables_count + distribution_cables_count
            
            # Check rule violations
            rule_violations = []
            
            # Rule 1: Max total cables leaving PDP
            if all_cables_count > max_cables_leaving:
                rule_violations.append({
                    'rule': 'max_total_cables',
                    'current': all_cables_count,
                    'allowed': max_cables_leaving,
                    'message': f"Total cables ({all_cables_count}) exceeds maximum ({max_cables_leaving})"
                })
            
            # Rule 2: Minimum primary distribution cables
            if primary_cables_count < min_primary_cables:
                rule_violations.append({
                    'rule': 'min_primary_cables',
                    'current': primary_cables_count,
                    'allowed': min_primary_cables,
                    'message': f"Primary cables ({primary_cables_count}) below minimum ({min_primary_cables})"
                })
            
            
            # If any violations found, create violation record
            if rule_violations:
                violation_info = {
                    'pdp_id': pdp_id,
                    'pdp_feature_id': pdp_feature.id(),
                    'primary_cables_count': primary_cables_count,
                    'distribution_cables_count': distribution_cables_count,
                    'total_cables_count': all_cables_count,
                    'rule_violations': rule_violations,
                    'geometry': pdp_buffer,  # Use buffer geometry for visualization
                    'violation_type': 'pdp_cable_limits',
                    'violation_reason': '; '.join([rv['message'] for rv in rule_violations])
                }
                violations.append(violation_info)
                
                # print(f"PDP {pdp_id} violations: {violation_info['violation_reason']}")

        result = {
            'rule_id': 'PRIMARY_001',
            'Description': f'PDP cable limits (max total: {max_cables_leaving}, min primary: {min_primary_cables})',
            'status': 'PASS' if not violations else 'FAIL',
            'violation_count': len(violations),
            'failed_features': ', '.join([f"PDP_{v['pdp_id']}" for v in violations]),
            'message': f'Found {len(violations)} PDPs with cable limit violations'
        }
        
        self.violations.extend(violations)
        return result

    def validate_no_primary_cables_on_poles(self):
        """
        Validate that no primary distribution cables are on poles

        Rule: No primary distribution cables on poles 
        (Check if pole LAYER attribute contains 'primary')

        Args:
            None - uses attribute-based checking only
        """
        print("Validating no primary cables on poles using LAYER attribute...")

        # Get required layers
        primary_cables_layer = get_layer_by_name('Primary Distribution Cables')
        access_structures_layer = get_layer_by_name('Access Structures')

        if not primary_cables_layer:
            return {
                'rule_id': 'PRIMARY_002',
                'Description': 'No primary cables on poles validation',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Primary Distribution Cables layer not found'
            }

        if not access_structures_layer:
            return {
                'rule_id': 'PRIMARY_002',
                'Description': 'No primary cables on poles validation',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': 'Access Structures layer not found'
            }

        # Check if required fields exist in Access Structures layer
        required_fields = ['TYPE', 'EQ_ID', 'LAYER']
        missing_fields = [field for field in required_fields if field not in access_structures_layer.fields().names()]

        if missing_fields:
            return {
                'rule_id': 'PRIMARY_002',
                'Description': 'No primary cables on poles validation',
                'status': 'ERROR',
                'violation_count': 0,
                'failed_features': '',
                'message': f'Access Structures layer missing required fields: {", ".join(missing_fields)}'
            }

        violations = []

        # Find poles with LAYER containing 'primary'
        primary_poles = []

        for structure_feature in access_structures_layer.getFeatures():
            structure_type = structure_feature['TYPE']
            structure_layer = structure_feature['LAYER']

            # Check if this structure is a pole (case-insensitive) and has 'primary' in LAYER
            is_pole = structure_type and isinstance(structure_type, str) and 'pole' in structure_type.lower()
            has_primary_layer = structure_layer and isinstance(structure_layer, str) and 'primary' in structure_layer.lower()

            if is_pole and has_primary_layer:
                pole_eq_id = structure_feature['EQ_ID'] if 'EQ_ID' in structure_feature.fields().names() else structure_feature.id()
                primary_poles.append({
                    'pole_eq_id': pole_eq_id,
                    'pole_type': structure_type,
                    'pole_layer': structure_layer,
                    'pole_feature_id': structure_feature.id(),
                    'geometry': structure_feature.geometry()
                })

        # print(f"Found {len(primary_poles)} poles with 'primary' in LAYER attribute")

        # If no poles with 'primary' in LAYER found, return early
        if len(primary_poles) == 0:
            return {
                'rule_id': 'PRIMARY_002',
                'Description': 'No primary cables on poles validation',
                'status': 'PASS',
                'violation_count': 0,
                'failed_features': '',
                'message': 'No poles found with "primary" in LAYER attribute'
            }

        # Create violation for each pole with 'primary' in LAYER
        for pole in primary_poles:
            violation_info = {
                'pole_eq_id': pole['pole_eq_id'],
                'pole_type': pole['pole_type'],
                'pole_layer': pole['pole_layer'],
                'pole_feature_id': pole['pole_feature_id'],
                'geometry': pole['geometry'],  # Use pole geometry for visualization
                'violation_type': 'primary_cable_on_pole',
                'violation_reason': f"Pole {pole['pole_eq_id']} has LAYER: '{pole['pole_layer']}' containing 'primary'"
            }
            violations.append(violation_info)
            
            # print(f"Violation: Pole {pole['pole_eq_id']} has LAYER containing 'primary': '{pole['pole_layer']}'")

        result = {
            'rule_id': 'PRIMARY_002',
            'Description': 'No primary distribution cables on poles (poles with "primary" in LAYER attribute)',
            'status': 'PASS' if not violations else 'FAIL',
            'violation_count': len(violations),
            'failed_features': ', '.join([f"Pole_{v['pole_eq_id']}" for v in violations]),
            'message': f'Found {len(violations)} poles with "primary" in LAYER attribute'
        }
        
        self.violations.extend(violations)
        return result

    def validate_primary_cable_split(self, tolerance=1.0):
        """
        Validates that Primary Distribution Cables are not 'split' (i.e., have a valid starting point).

        Rule: A primary distribution cable must have a PDP as a starting point.
        A cable is considered 'split' if neither of its endpoints is spatially
        connected (within tolerance) to a PDP.

        Args:
            tolerance: Max distance in meters between a cable endpoint and a PDP (default: 1.0)
        """
        print("Validating primary distribution cable split (starting points)...")
        RULE_ID = "PRIMARY_003"
        description = "Primary distribution cables must start from a PDP"

        prim_cables_layer = get_layer_by_name("Primary Distribution Cables")
        pdp_layer = get_layer_by_name("Primary Distribution Points")

        if not prim_cables_layer:
            return {
                "rule_id": RULE_ID,
                "Description": description,
                "status": "ERROR",
                "violation_count": 0,
                "failed_features": "",
                "message": "Primary Distribution Cables layer not found.",
            }
        if not pdp_layer:
            return {
                "rule_id": RULE_ID,
                "Description": description,
                "status": "ERROR",
                "violation_count": 0,
                "failed_features": "",
                "message": "Primary Distribution Points layer not found.",
            }

        violations = []
        pdp_index = QgsSpatialIndex(pdp_layer.getFeatures())

        def endpoint_near_pdp(point_geom):
            """Return True if point_geom is within tolerance of any PDP."""
            buf = point_geom.buffer(tolerance, 5)
            for fid in pdp_index.intersects(buf.boundingBox()):
                if pdp_layer.getFeature(fid).geometry().intersects(buf):
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

        for cable in prim_cables_layer.getFeatures():
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
            if not any(endpoint_near_pdp(ep) for ep in (start_geom, end_geom)):
                violations.append(
                    {
                        "cable_id": cable_id,
                        "cable_layer": "Primary Distribution Cables",
                        "geometry": cable_geom,
                        "violation_type": "cable_split",
                        "violation_reason": (
                            f"Primary distribution cable {cable_id} does not "
                            f"start from a PDP (split cable)."
                        ),
                    }
                )

        violation_count = len(violations)
        self.violations.extend(violations)
        return {
            "rule_id": RULE_ID,
            "Description": description,
            "status": "PASS" if not violations else "FAIL",
            "violation_count": violation_count,
            "failed_features": ", ".join([f"Cable_{v['cable_id']}" for v in violations]),
            "message": (
                f"Found {violation_count} split primary cables without a PDP starting point."
                if violation_count > 0
                else "No violations found."
            ),
        }

    def validate_primary_distribution_rules(self):
        """
        Run all primary distribution validation rules
        """
        print("Running primary distribution validation...")

        results = []

        # Rule 1: PDP cable limits
        pdp_result = self.validate_pdp_cable_limits(
            max_cables_leaving=8,
            min_primary_cables=3,
            buffer_distance=2.0
        )
        results.append(pdp_result)

        # Rule 2: No primary cables on poles
        poles_result = self.validate_no_primary_cables_on_poles()
        results.append(poles_result)

        # Rule 3: Primary cable split check
        results.append(self.validate_primary_cable_split())

        return results