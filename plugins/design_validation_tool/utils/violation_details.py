def get_violation_details(violation):
    """Generate concise label for map display. Full details are in the attribute table."""
    violation_type = violation.get("violation_type", "unknown")

    if violation_type == "max_pocs_per_cable":
        return {
            "rule_id": "POC_001",
            "description": "Maximum POCs in line =< 11",
            "violation_type": violation_type,
            "details": f"Cable {violation.get('cable_id', 'N/A')} - {violation.get('poc_count', 0)} POCs (max 11)",
        }

    elif violation_type == "max_connections_per_poc":
        return {
            "rule_id": "POC_002",
            "description": "Max connections per POC =< 8",
            "violation_type": violation_type,
            "details": f"POC {violation.get('poc_id', 'N/A')} - {violation.get('connection_count', 0)} connections",
        }

    elif violation_type == "ug_facade_connections":
        return {
            "rule_id": "POC_003",
            "description": violation.get("description", "UG/Facade connections"),
            "violation_type": violation_type,
            "details": f"POC {violation.get('poc_id', 'N/A')} - {violation.get('left_count', 0)}L/{violation.get('right_count', 0)}R connections",
        }

    elif violation_type == "poc_single_cluster":
        return {
            "rule_id": "POC_004",
            "description": violation.get("description", "POC single cluster"),
            "violation_type": violation_type,
            "details": f"POC {violation.get('poc_id', 'N/A')} - {violation.get('cluster_count', 0)} clusters",
        }

    elif violation_type == "proximity_home_count_cable_length":
        return {
            "rule_id": "POC_005",
            "description": "Proximity, home count, and drop cable length validation",
            "violation_type": violation_type,
            "details": (
                f"POCs {violation.get('poc1_id', 'N/A')} & {violation.get('poc2_id', 'N/A')} - "
                f"{violation.get('distance', 0):.1f}m apart, "
                f"{violation.get('total_home_count', 0)} homes"
            ),
        }

    elif violation_type == "parallel_overlap":
        return {
            "rule_id": "OVERLAP_001",
            "description": "Parallel duct overlap detection",
            "violation_type": violation_type,
            "details": (
                f"Ducts {violation.get('duct1_id', 'N/A')} & {violation.get('duct2_id', 'N/A')} - "
                f"overlap {violation.get('overlap_length', 0):.1f}m"
            ),
        }

    elif violation_type == "same_identifier_route":
        return {
            "rule_id": "OVERLAP_001",
            "description": "Same identifier route detection",
            "violation_type": violation_type,
            "details": (
                f"Ducts {violation.get('duct1_id', 'N/A')} & {violation.get('duct2_id', 'N/A')} - "
                f"shared route {violation.get('shared_route_length', 0):.1f}m"
            ),
        }

    elif violation_type == "redundant_parallel_routes":
        return {
            "rule_id": "OVERLAP_001",
            "description": "Redundant parallel routes detection",
            "violation_type": violation_type,
            "details": (
                f"Ducts {violation.get('duct1_id', 'N/A')} & {violation.get('duct2_id', 'N/A')} - "
                f"parallel {violation.get('shared_route_length', 0):.1f}m"
            ),
        }

    elif violation_type == "oversized_duct":
        return {
            "rule_id": "OVERLAP_002",
            "description": "Oversized ducts detection (capacity > 2)",
            "violation_type": violation_type,
            "details": (
                f"Duct {violation.get('duct_id', 'N/A')} - "
                f"capacity {violation.get('capacity', 0)}, "
                f"{violation.get('homes_served', 0)} demand points"
            ),
        }

    elif violation_type == "cluster_overlap":
        return {
            "rule_id": violation.get("rule_id", "OVERLAP_003"),
            "description": f"Cluster overlap in {violation.get('layer_name', 'Unknown')}",
            "violation_type": violation_type,
            "details": (
                f"Clusters {violation.get('cluster1_id', 'N/A')} & {violation.get('cluster2_id', 'N/A')} - "
                f"overlap {violation.get('overlap_percentage', 0):.1f}%"
            ),
        }

    elif violation_type == "pdp_cable_limits":
        return {
            "rule_id": "PRIMARY_001",
            "description": "PDP cable limits validation",
            "violation_type": violation_type,
            "details": f"PDP {violation.get('pdp_id', 'N/A')} - {violation.get('total_cables_count', 0)} cables",
        }

    elif violation_type == "primary_cable_on_pole":
        return {
            "rule_id": "PRIMARY_002",
            "description": "No primary distribution cables on poles",
            "violation_type": violation_type,
            "details": f"Pole {violation.get('pole_eq_id', 'N/A')} - primary cable on pole",
        }

    elif violation_type == "feeder_cable_length":
        return {
            "rule_id": "FEEDER_001",
            "description": "Feeder Cable length validation",
            "violation_type": violation_type,
            "details": f"Feeder {violation.get('cable_id', 'N/A')} - {violation.get('length', 0):.0f}m (too long)",
        }

    elif violation_type == "feeder_street_crossing":
        return {
            "rule_id": "FEEDER_002",
            "description": "Feeder Cable street crossing validation",
            "violation_type": violation_type,
            "details": f"Feeder {violation.get('cable_id', 'N/A')} - crosses street {violation.get('street_id', 'N/A')}",
        }

    elif violation_type == "feeder_cable_count":
        return {
            "rule_id": "FEEDER_003",
            "description": "Feeder Cable count validation",
            "violation_type": violation_type,
            "details": f"Feeder count: {violation.get('actual_count', 0)} (need {violation.get('required_count', 0)})",
        }

    elif violation_type == "feeder_cable_granularity":
        return {
            "rule_id": "FEEDER_003",
            "description": "Feeder Cable granularity validation",
            "violation_type": violation_type,
            "details": f"Feeder {violation.get('cable_id', 'N/A')} - wrong granularity ({violation.get('actual_granularity', 'N/A')})",
        }

    elif violation_type == "pop_capacity":
        return {
            "rule_id": "FEEDER_004",
            "description": "POP cabinet capacity validation",
            "violation_type": violation_type,
            "details": f"CO {violation.get('co_id', 'N/A')} - {violation.get('home_count', 0)} homes (over capacity)",
        }

    elif violation_type == "max_cables_leaving_dp":
        return {
            "rule_id": "DISTRIBUTION_001",
            "description": "Maximum distribution cables leaving DP",
            "violation_type": violation_type,
            "details": f"DP {violation.get('dp_id', 'N/A')} - {violation.get('cable_count', 0)} cables (max {violation.get('max_allowed', 5)})",
        }

    elif violation_type == "facade_cable_max_length":
        return {
            "rule_id": "DISTRIBUTION_002",
            "description": "Facade cable maximum length",
            "violation_type": violation_type,
            "details": f"Facade cable {violation.get('cable_id', 'N/A')} - {violation.get('cable_length', 0):.0f}m (max {violation.get('max_allowed', 500)}m)",
        }

    elif violation_type == "aerial_cable_poc_limit":
        return {
            "rule_id": "DISTRIBUTION_003",
            "description": "Aerial distribution cable POC limit",
            "violation_type": violation_type,
            "details": f"Aerial cable {violation.get('cable_id', 'N/A')} - {violation.get('poc_count', 0)} POCs (max {violation.get('max_allowed', 22)})",
        }

    elif violation_type == "parallel_poc_connection":
        return {
            "rule_id": "DISTRIBUTION_004",
            "description": "Parallel cable POC connection",
            "violation_type": violation_type,
            "details": f"POC {violation.get('poc_id', 'N/A')} - should connect to cable {violation.get('longest_cable_id', 'N/A')}",
        }

    elif violation_type == "facade_underground_length":
        return {
            "rule_id": "DISTRIBUTION_005",
            "description": "Facade underground section length",
            "violation_type": violation_type,
            "details": f"Cable {violation.get('cable_id', 'N/A')} - UG section {violation.get('length', 0):.1f}m (too long)",
        }

    elif violation_type == "parallel_aerial_limit":
        return {
            "rule_id": "DISTRIBUTION_006",
            "description": "Parallel aerial cable limit",
            "violation_type": violation_type,
            "details": f"Group {violation.get('cable_group', 'N/A')} - {violation.get('cable_count', 0)} parallel aerial cables",
        }

    elif violation_type == "underground_drop_mismatch":
        return {
            "rule_id": "DISTRIBUTION_007",
            "description": "Underground drop consistency",
            "violation_type": violation_type,
            "details": f"Drop cable {violation.get('drop_cable_id', 'N/A')} - not underground (parent is)",
        }

    elif violation_type == "facade_total_underground_length":
        return {
            "rule_id": "DISTRIBUTION_008",
            "description": "Facade total underground length",
            "violation_type": violation_type,
            "details": f"Facade cable {violation.get('cable_id', 'N/A')} - UG total {violation.get('length', 0):.1f}m (too long)",
        }

    elif violation_type == "dp_inside_cluster":
        return {
            "rule_id": "DISTRIBUTION_009",
            "description": "DP should not be inside a drop cluster",
            "violation_type": violation_type,
            "details": f"DP {violation.get('dp_id', 'N/A')} - inside drop cluster",
        }

    elif violation_type == "dp_in_private_domain":
        return {
            "rule_id": "DISTRIBUTION_010",
            "description": "DP should not be in private domain",
            "violation_type": violation_type,
            "details": f"DP {violation.get('dp_id', 'N/A')} - in private domain",
        }

    elif violation_type == "mini_dp_on_facade":
        return {
            "rule_id": "DISTRIBUTION_011",
            "description": "Mini-DP on facade without proper config",
            "violation_type": violation_type,
            "details": f"Mini-DP {violation.get('mini_dp_id', 'N/A')} - facade config issue",
        }

    elif violation_type == "aerial_drop_cable_length":
        return {
            "rule_id": "POC_006",
            "description": "Aerial drop cable length validation",
            "violation_type": violation_type,
            "details": f"Drop cable {violation.get('drop_cable_id', 'N/A')} - {violation.get('cable_length', 0):.1f}m (max 40m)",
        }

    elif violation_type == "facade_cable_crosses_gap":
        return {
            "rule_id": "POC_007",
            "description": "Façade drop cables crossing gaps",
            "violation_type": violation_type,
            "details": f"Drop cable {violation.get('drop_cable_id', 'N/A')} - crosses an open span",
        }

    elif violation_type == "cable_split":
        cable_layer = violation.get("cable_layer", "Distribution Cables")
        if "Primary" in cable_layer:
            return {
                "rule_id": "DISTRIBUTION_012",
                "description": "Primary distribution cable must start from a PDP",
                "violation_type": violation_type,
                "details": f"Primary cable {violation.get('cable_id', 'N/A')} - no PDP at start point (split cable)",
            }
        else:
            return {
                "rule_id": "DISTRIBUTION_012",
                "description": "Distribution cable must start from a DP or PDP",
                "violation_type": violation_type,
                "details": f"Cable {violation.get('cable_id', 'N/A')} - no DP or PDP at start point (split cable)",
            }

    elif violation_type == "invalid_subtype":
        return {
            "rule_id": "DATA_Q_001",
            "description": "Invalid SUBTYPE",
            "violation_type": violation_type,
            "details": f"Feature {violation.get('feature_id', 'N/A')} - invalid subtype '{violation.get('subtype', 'N/A')}'",
        }

    elif violation_type == "subtype_empty":
        return {
            "rule_id": "DATA_Q_001",
            "description": "Empty SUBTYPE",
            "violation_type": violation_type,
            "details": f"Feature {violation.get('feature_id', 'N/A')} ({violation.get('layer_name', 'N/A')}) - subtype empty",
        }

    elif violation_type == "subtype_invalid":
        return {
            "rule_id": "DATA_Q_001",
            "description": "Invalid SUBTYPE",
            "violation_type": violation_type,
            "details": f"Feature {violation.get('feature_id', 'N/A')} ({violation.get('layer_name', 'N/A')}) - invalid '{violation.get('subtype', 'N/A')}'",
        }

    elif violation_type == "subtype_length_exceeded":
        return {
            "rule_id": "DATA_Q_001",
            "description": "SUBTYPE length exceeded",
            "violation_type": violation_type,
            "details": f"Feature {violation.get('feature_id', 'N/A')} - Doorsteek >8m, use Gestuurde boring",
        }

    elif violation_type == "subtype_missing":
        return {
            "rule_id": "DATA_Q_001",
            "description": "Missing SUBTYPE",
            "violation_type": violation_type,
            "details": f"Feature {violation.get('feature_id', 'N/A')} - subtype missing",
        }

    elif violation_type == "feature_unlocked":
        return {
            "rule_id": "DATA_Q_003",
            "description": "Features must be locked",
            "violation_type": violation_type,
            "details": f"{violation.get('layer', 'Unknown')} - {violation.get('unlocked_count', 'N/A')} unlocked",
        }

    elif violation_type == "facade_on_monument":
        return {
            "rule_id": "DATA_Q_002",
            "description": "Facade on protected monument",
            "violation_type": violation_type,
            "details": f"Facade cable {violation.get('cable_id', 'N/A')} - on protected monument",
        }

    elif violation_type == "multiple_boms":
        return {
            "rule_id": "DATA_Q_004",
            "description": "Multiple BOM files",
            "violation_type": violation_type,
            "details": f"BOM: {violation.get('bom_file', 'N/A')}",
        }

    elif violation_type == "existing_pipe_wrong_trench_subtype":
        return {
            "rule_id": "DATA_Q_005",
            "description": "Trench near existing pipe has wrong subtype",
            "violation_type": violation_type,
            "details": f"Trench {violation.get('feature_id', 'N/A')} - should be 'Existing Pipes' (pipe {violation.get('pipe_id', 'N/A')})",
        }
    elif violation_type == "ducts_layer_empty":
        return {
            "rule_id": "DATA_Q_006",
            "description": "Duct layers must contain features",
            "violation_type": violation_type,
            "details": (
                f"Layer: {violation.get('layer_name', 'N/A')}; "
                f"Status: Empty (0 features)"
            ),
        }
    elif violation_type == "crossing_invalid_angle":
        return {
            "rule_id": "CROSS_001",
            "description": "Crossing angle invalid",
            "violation_type": violation_type,
            "details": f"Crossing {violation.get('feature_id', 'N/A')} - invalid angle to trench",
        }

    elif violation_type == "crossing_intersects_sidewalk_trench":
        return {
            "rule_id": "CROSS_002",
            "description": "Crossing intersects trench",
            "violation_type": violation_type,
            "details": f"Crossing {violation.get('feature_id', 'N/A')} - intersects sidewalk trench",
        }

    elif violation_type == "crossings_too_close":
        return {
            "rule_id": "CROSS_003",
            "description": "Crossings too close",
            "violation_type": violation_type,
            "details": (
                f"Crossings {violation.get('feature_1_id', 'N/A')} & {violation.get('feature_2_id', 'N/A')} - "
                f"{violation.get('actual_distance', 0):.1f}m apart (min {violation.get('required_distance', 50)}m)"
            ),
        }

    elif violation_type == "crossing_in_widening_area":
        return {
            "rule_id": "CROSS_004",
            "description": "Crossing in widening area",
            "violation_type": violation_type,
            "details": f"Crossing {violation.get('feature_id', 'N/A')} - in road widening area",
        }

    elif violation_type == "distribution_cable_not_on_sidewalk":
        return {
            "rule_id": "TRENCH_001",
            "description": "Cable not on sidewalk",
            "violation_type": violation_type,
            "details": f"Cable {violation.get('cable_id', 'N/A')} - not on sidewalk",
        }

    elif violation_type == "drop_cable_not_perpendicular":
        return {
            "rule_id": "TRENCH_001",
            "description": "Drop cable not perpendicular",
            "violation_type": violation_type,
            "details": f"Drop cable {violation.get('cable_id', 'N/A')} - not perpendicular",
        }

    elif violation_type == "sharp_trenching_angle":
        return {
            "rule_id": "TRENCH_002",
            "description": "Sharp trenching angle",
            "violation_type": violation_type,
            "details": f"Cable {violation.get('cable_id', 'N/A')} - sharp angle ({violation.get('angle', 0):.0f}deg)",
        }

    elif violation_type == "missing_trench":
        return {
            "rule_id": "TRENCH_003",
            "description": "Missing trench",
            "violation_type": violation_type,
            "details": f"Drop cable {violation.get('cable_id', 'N/A')} - no distribution cable",
        }

    elif violation_type == "u_shape_detour":
        return {
            "rule_id": "TRENCH_004",
            "description": "U-shape detour",
            "violation_type": violation_type,
            "details": f"Cable {violation.get('cable_id', 'N/A')} - U-shape detour",
        }

    elif violation_type == "cable_overextension":
        return {
            "rule_id": "TRENCH_004",
            "description": "Cable overextension",
            "violation_type": violation_type,
            "details": f"Cable {violation.get('cable_id', 'N/A')} - extends {violation.get('extension_length', 0):.1f}m past last drop point",
        }

    else:
        return {
            "rule_id": "UNKNOWN",
            "description": "Unknown violation type",
            "violation_type": "unknown",
            "details": "Unknown violation",
        }
