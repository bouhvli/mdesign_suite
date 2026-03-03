from qgis.core import QgsSpatialIndex  # type: ignore
from ...utils.layer_loader import get_layer_by_name


class FeederValidator:
    def __init__(self):
        self.violations = []

    def validate_feeder_cable_length(self, max_distance=50.0):
        """
        Rule 1: Validate that each Feeder Cable's LENGTH attribute is <= 50m.
        """
        print("Validating feeder cable length...")
        cable_layer = get_layer_by_name("Feeder Cables")

        if not cable_layer:
            return self._create_error_result(
                "FEEDER_001", "Feeder Cables layer not found."
            )

        fields = cable_layer.fields().names()
        if "LENGTH" not in fields:
            return self._create_error_result(
                "FEEDER_001", "Feeder Cables layer missing LENGTH attribute."
            )
        if "CABLE_ID" not in fields:
            return self._create_error_result(
                "FEEDER_001", "Feeder Cables layer missing CABLE_ID attribute."
            )

        violations = []
        for cable_feature in cable_layer.getFeatures():
            cable_length = cable_feature["LENGTH"]
            if cable_length and cable_length > max_distance:
                cable_id = cable_feature["CABLE_ID"]
                violation_info = {
                    "violation_type": "feeder_cable_length",
                    "cable_id": cable_id,
                    "length": round(cable_length, 2),
                    "geometry": cable_feature.geometry(),
                    "violation_reason": f"Feeder Cable (ID: {cable_id}) has length {round(cable_length, 2)}m (max {max_distance}m).",
                }
                violations.append(violation_info)

        description = f"Feeder Cable length must be <= {max_distance}m"
        violation_count = len(violations)
        if violation_count > 0:
            message = f"Found {violation_count} feeder cables with length over {max_distance}m."
        else:
            message = "No violations found."

        result = self._create_result("FEEDER_001", description, violations, message)
        self.violations.extend(violations)
        return result

    def validate_feeder_street_crossing(self):
        """
        Rule 2: Validate that Feeder Cables do not intersect with Street Center Lines.
        """
        print("Validating feeder cable street crossing...")
        cable_layer = get_layer_by_name("Feeder Cables")
        street_layer = get_layer_by_name("Street Center Lines")

        if not cable_layer or not street_layer:
            return self._create_error_result(
                "FEEDER_002", "Feeder Cables or Street Center Lines layer not found."
            )

        if "CABLE_ID" not in cable_layer.fields().names():
            return self._create_error_result(
                "FEEDER_002", "Feeder Cables layer missing CABLE_ID attribute."
            )

        street_index = QgsSpatialIndex(street_layer.getFeatures())
        violations = []

        for cable_feature in cable_layer.getFeatures():
            cable_geom = cable_feature.geometry()
            if not cable_geom or cable_geom.isEmpty():
                continue

            candidate_street_ids = street_index.intersects(cable_geom.boundingBox())
            for street_id in candidate_street_ids:
                street_feature = street_layer.getFeature(street_id)
                if cable_geom.intersects(street_feature.geometry()):
                    cable_id = cable_feature["CABLE_ID"]
                    street_name = (
                        street_feature["STREETNAME"]
                        if "STREETNAME" in street_feature.fields().names()
                        else street_id
                    )
                    intersection_point = cable_geom.intersection(
                        street_feature.geometry()
                    )
                    violation_info = {
                        "violation_type": "feeder_street_crossing",
                        "cable_id": cable_id,
                        "street_name": street_name,
                        "geometry": intersection_point,
                        "violation_reason": f"Feeder Cable (ID: {cable_id}) crosses Street: {street_name}.",
                    }
                    violations.append(violation_info)
                    break

        description = "Feeder Cable must not cross Street Center Lines"
        violation_count = len(violations)
        if violation_count > 0:
            message = (
                f"Found {violation_count} feeder cables crossing street center lines."
            )
        else:
            message = "No violations found."

        result = self._create_result("FEEDER_002", description, violations, message)
        self.violations.extend(violations)
        return result

    def validate_feeder_cable_count(self, required_cables=6, fiber_count=192):
        """
        Rule 3: Validate that there are exactly 6 cables with a CABLEGRAN of 192.
        """
        print("Validating feeder cable count and granularity...")
        cable_layer = get_layer_by_name("Feeder Cables")
        co_layer = get_layer_by_name("Central Offices")

        if not cable_layer or not co_layer:
            return self._create_error_result(
                "FEEDER_003", "Feeder Cables or Central Offices layer not found."
            )

        fields = cable_layer.fields().names()
        if "CABLEGRAN" not in fields:
            return self._create_error_result(
                "FEEDER_003", "Feeder Cables layer missing CABLEGRAN attribute."
            )
        if "CABLE_ID" not in fields:
            return self._create_error_result(
                "FEEDER_003", "Feeder Cables layer missing CABLE_ID attribute."
            )

        violations = []
        actual_cable_count = 0
        violating_cables = []

        for cable_feature in cable_layer.getFeatures():
            if cable_feature["CABLEGRAN"] == fiber_count:
                actual_cable_count += 1
            else:
                violating_cables.append(cable_feature)

        if actual_cable_count != required_cables:
            co_geom = None
            if co_layer and co_layer.featureCount() > 0:
                co_feature = next(co_layer.getFeatures())
                co_geom = co_feature.geometry()

            violation_info = {
                "violation_type": "feeder_cable_count",
                "actual_count": actual_cable_count,
                "required_count": required_cables,
                "pop": co_feature["AGG_ID"],  # type: ignore
                "geometry": co_geom,
                "violation_reason": f"Found {actual_cable_count} feeder cables with {fiber_count}F (required: {required_cables}).",
            }
            violations.append(violation_info)

        for cable in violating_cables:
            cable_id = cable["CABLE_ID"]
            violations.append(
                {
                    "violation_type": "feeder_cable_granularity",
                    "cable_id": cable_id,
                    "actual_granularity": cable["CABLEGRAN"],
                    "geometry": cable.geometry(),
                    "violation_reason": f"Feeder Cable (ID: {cable_id}) has CABLEGRAN of {cable['CABLEGRAN']} (should be {fiber_count}).",
                }
            )

        description = (
            f"Feeder must have exactly {required_cables} cables of {fiber_count}F"
        )
        violation_count = len(violations)
        if violation_count > 0:
            message = f"Found {violation_count} violations related to feeder cable count and granularity."
        else:
            message = "No violations found."

        result = self._create_result("FEEDER_003", description, violations, message)
        self.violations.extend(violations)
        return result

    def validate_pop_capacity(self, max_homes=1024):
        """
        Rule 4: Validate that the Central Office HOMECOUNT is <= 1024.
        """
        print("Validating POP (Central Office) capacity...")
        co_layer = get_layer_by_name("Central Offices")

        if not co_layer:
            return self._create_error_result(
                "FEEDER_004", "Central Offices layer not found."
            )
        if "HOMECOUNT" not in co_layer.fields().names():
            return self._create_error_result(
                "FEEDER_004", "Central Offices layer missing HOMECOUNT attribute."
            )

        violations = []
        for co_feature in co_layer.getFeatures():
            home_count = co_feature["HOMECOUNT"]
            if home_count and home_count > max_homes:
                co_id = (
                    co_feature["AGG_ID"]
                    if "AGG_ID" in co_layer.fields().names()
                    else co_feature.id()
                )
                violation_info = {
                    "violation_type": "pop_capacity",
                    "co_id": co_id,
                    "home_count": home_count,
                    "geometry": co_feature.geometry(),
                    "violation_reason": f"Central Office (ID: {co_id}) HOMECOUNT is {home_count} (max {max_homes}).",
                }
                violations.append(violation_info)
            break

        description = f"POP cabinet must serve no more than {max_homes} homes"
        violation_count = len(violations)
        if violation_count > 0:
            message = f"Found {violation_count} POPs exceeding capacity."
        else:
            message = "No violations found."

        result = self._create_result("FEEDER_004", description, violations, message)
        self.violations.extend(violations)
        return result

    def validate_feeder_rules(self):
        """Run all feeder validation rules."""
        self.violations = []
        print("Running all feeder validation rules...")
        results = []
        results.append(self.validate_feeder_cable_length())
        results.append(self.validate_feeder_street_crossing())
        results.append(self.validate_feeder_cable_count())
        results.append(self.validate_pop_capacity())
        return results

    def _create_result(self, rule_id, description, violations, message):
        failed_ids = []
        for v in violations:
            if v.get("cable_id"):
                failed_ids.append(f"Cable_{v.get('cable_id')}")
            elif v.get("pop"):
                failed_ids.append(f"POP_{v.get('pop')}")
            elif v.get("violation_type") == "feeder_cable_count":
                failed_ids.append("Network Count")
        failed_features_str = ", ".join(failed_ids)

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
            "Description": "Feeder validation rule",
            "status": "ERROR",
            "violation_count": 0,
            "failed_features": "",
            "message": message,
        }
