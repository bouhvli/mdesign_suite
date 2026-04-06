def get_violation_details(violation):
    """Generate detailed description of the violation"""
    violation_type = violation.get("violation_type", "unknown")

    if violation_type == "max_pocs_per_cable":
        details = {
            "rule_id": "POC_001",
            "description": "Maximum POCs in line =< 11",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Cable {violation.get('cable_id', 'N/A')} in group {violation.get('cable_group', 'N/A')} "
                f"has {violation.get('poc_count', 0)} POCs"
            ),
        }
        return details

    elif violation_type == "max_connections_per_poc":
        return {
            "rule_id": "POC_002",
            "description": "Max connections per POC =< 8",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"POC {violation.get('poc_id', 'N/A')} has {violation.get('connection_count', 0)} connections"
            ),
        }

    elif violation_type == "ug_facade_connections":
        return {
            "rule_id": "POC_003",
            "description": violation.get("description", "No description"),
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"POC {violation.get('poc_id', 'N/A')} has "
                f"{violation.get('left_count', 0)} left and {violation.get('right_count', 0)} right connections"
            ),
        }

    elif violation_type == "poc_single_cluster":
        details_str = (
            f"Layer: {violation.get('layer', 'Drop Points / Drop Clusters')}; "
            f"POC ID: {violation.get('poc_id', 'N/A')}; "
            f"Cluster count: {violation.get('cluster_count', 0)}; "
            f"Cluster IDs: {violation.get('clusters', [])}; "
            f"Subtype: {violation.get('violation_subtype', 'N/A')}"
        )
        # Add distance if present
        if violation.get('distance_to_cluster') is not None:
            details_str += f"; Distance to cluster boundary: {violation.get('distance_to_cluster'):.2f} m"
        return {
            "rule_id": "POC_004",
            "description": violation.get("description", "No description"),
            "violation_type": violation.get("violation_type", "unknown"),
            "details": details_str,
        }

    elif violation_type == "proximity_home_count_cable_length":
        return {
            "rule_id": "POC_005",
            "description": "Proximity, home count, and drop cable length validation",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"POCs {violation.get('poc1_id', 'N/A')} and {violation.get('poc2_id', 'N/A')}\n"
                f"are {violation.get('distance', 0):.1f}m apart,\n"
                f"{violation.get('total_home_count', 0)} homes total,\n"
                f"longest cable {round(violation.get('longest_cable', 0), 1)}m,\n"
                f"cable type {violation.get('cable_type', 'UNKNOWN')}"
            ),
        }
    elif violation_type == "parallel_overlap":
        return {
            "rule_id": "OVERLAP_001",
            "description": "Parallel duct overlap detection",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Ducts {violation.get('duct1_id', 'N/A')} & {violation.get('duct2_id', 'N/A')} overlap\n"
                f"Layers: {violation.get('duct1_layer', 'N/A')} & {violation.get('duct2_layer', 'N/A')}\n"
                f"Overlap length: {violation.get('overlap_length', 0):.1f}m\n"
                f"Capacities: {violation.get('duct1_capacity', 0)} & {violation.get('duct2_capacity', 0)}"
            ),
        }

    elif violation_type == "same_identifier_route":
        return {
            "rule_id": "OVERLAP_001",
            "description": "Same identifier route detection",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Ducts {violation.get('duct1_id', 'N/A')} & {violation.get('duct2_id', 'N/A')} share route\n"
                f"Identifier: {violation.get('identifier', 'N/A')}\n"
                f"Shared route length: {violation.get('shared_route_length', 0):.1f}m\n"
                f"Average distance: {violation.get('average_distance', 0):.1f}m\n"
                f"Angle difference: {violation.get('angle_difference', 0):.1f}°\n"
                f"Layers: {violation.get('duct1_layer', 'N/A')} & {violation.get('duct2_layer', 'N/A')}"
            ),
        }
    elif violation_type == "redundant_parallel_routes":
        return {
            "rule_id": "OVERLAP_001",
            "description": "Redundant parallel routes detection",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Ducts {violation.get('duct1_id', 'N/A')} & {violation.get('duct2_id', 'N/A')} run parallel\n"
                f"Identifier: {violation.get('identifier', 'N/A')}\n"
                f"Shared route length: {violation.get('shared_route_length', 0):.1f}m\n"
                f"Average distance: {violation.get('average_distance', 0):.1f}m\n"
                f"Angle difference: {violation.get('angle_difference', 0):.1f}°\n"
                f"Layers: {violation.get('duct1_layer', 'N/A')} & {violation.get('duct2_layer', 'N/A')}"
            ),
        }
    elif violation_type == "oversized_duct":
        home_ids = violation.get("served_home_ids", [])
        home_list = ", ".join([str(hid) for hid in home_ids[:5]])  # Show first 5 homes
        if len(home_ids) > 5:
            home_list += f" and {len(home_ids) - 5} more"

        return {
            "rule_id": "OVERLAP_002",
            "description": "Oversized ducts detection (capacity > 2)",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Duct {violation.get('duct_id', 'N/A')} (capacity: {violation.get('capacity', 0)}) "
                f"intersects with {violation.get('homes_served', 0)} demand points\n"
                f"Buffer distance: {violation.get('buffer_distance', 0)}m\n"
                f"Demand points: {home_list}"
            ),
        }
    elif violation_type == "cluster_overlap":
        rule_id = violation.get("rule_id", "OVERLAP_003")
        layer_name = violation.get("layer_name", "Unknown Layer")

        return {
            "rule_id": rule_id,
            "description": f"Cluster overlap detection in {layer_name}",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Clusters {violation.get('cluster1_id', 'N/A')} & {violation.get('cluster2_id', 'N/A')} overlap\n"
                f"Cluster names: {violation.get('cluster1_name', 'N/A')} & {violation.get('cluster2_name', 'N/A')}\n"
                f"Overlap area: {violation.get('overlap_area', 0):.1f} m²\n"
                f"Overlap percentage: {violation.get('overlap_percentage', 0):.1f}%\n"
                f"Individual areas: {violation.get('cluster1_area', 0):.1f} m² & {violation.get('cluster2_area', 0):.1f} m²"
            ),
        }
    elif violation_type == "pdp_cable_limits":
        rule_violations = violation.get("rule_violations", [])
        violation_details = []
        
        for rule_viol in rule_violations:
            if rule_viol['rule'] == 'max_total_cables':
                violation_details.append(
                    f"Total cables ({rule_viol['current']}) exceeds maximum ({rule_viol['allowed']})"
                )
            elif rule_viol['rule'] == 'min_primary_cables':
                violation_details.append(
                    f"Primary cables ({rule_viol['current']}) below minimum ({rule_viol['allowed']})"
                )
            elif rule_viol['rule'] == 'max_distribution_cables':
                violation_details.append(
                    f"Distribution cables ({rule_viol['current']}) exceeds maximum ({rule_viol['allowed']})"
                )
        
        details_str = (
            f"PDP ID: {violation.get('pdp_id', 'N/A')}\n"
            f"Primary cables: {violation.get('primary_cables_count', 0)}\n"
            f"Distribution cables: {violation.get('distribution_cables_count', 0)}\n"
            f"Total cables: {violation.get('total_cables_count', 0)}\n"
            f"Violations: {'; '.join(violation_details)}"
        )
        
        return {
            "rule_id": "PRIMARY_001",
            "description": "PDP cable limits validation",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": details_str
        }

    elif violation_type == "primary_cable_on_pole":
        return {
            "rule_id": "PRIMARY_002",
            "description": "No primary distribution cables on poles",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Pole {violation.get('pole_eq_id', 'N/A')} has LAYER containing 'primary'\n"
                f"Pole Type: {violation.get('pole_type', 'N/A')}\n"
                f"Pole LAYER: '{violation.get('pole_layer', 'N/A')}'\n"
                f"Pole Feature ID: {violation.get('pole_feature_id', 'N/A')}\n"
                f"Violation: Pole LAYER attribute indicates primary cable installation"
            )
        }
    
    elif violation_type == "feeder_cable_length":
        return {
            "rule_id": "FEEDER_001",
            "description": "Feeder Cable length validation",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Feeder Cable (ID: {violation.get('cable_id', 'N/A')}) has a length of "
                f"{violation.get('length', 0):.2f}m, exceeding the maximum allowed."
            )
        }

    elif violation_type == "feeder_street_crossing":
        return {
            "rule_id": "FEEDER_002",
            "description": "Feeder Cable street crossing validation",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Feeder Cable (ID: {violation.get('cable_id', 'N/A')}) intersects with "
                f"a Street Center Line (ID: {violation.get('street_id', 'N/A')})."
            )
        }

    elif violation_type == "feeder_cable_count":
        return {
            "rule_id": "FEEDER_003",
            "description": "Feeder Cable count validation",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Found {violation.get('actual_count', 0)} feeder cables with the correct granularity, "
                f"but {violation.get('required_count', 0)} are required."
            )
        }
    
    elif violation_type == "feeder_cable_granularity":
        return {
            "rule_id": "FEEDER_003",
            "description": "Feeder Cable granularity validation",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Feeder Cable (ID: {violation.get('cable_id', 'N/A')}) has an incorrect granularity of "
                f"{violation.get('actual_granularity', 'N/A')}."
            )
        }

    elif violation_type == "pop_capacity":
        return {
            "rule_id": "FEEDER_004",
            "description": "POP cabinet capacity validation",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Central Office (ID: {violation.get('co_id', 'N/A')}) serves {violation.get('home_count', 0)} homes, "
                f"exceeding the maximum capacity."
            )
        }
    
    elif violation_type == "max_cables_leaving_dp":
        cable_ids = violation.get('cable_ids', [])
        cable_list = ", ".join([str(cid) for cid in cable_ids[:5]])  # Show first 5 cables
        if len(cable_ids) > 5:
            cable_list += f" and {len(cable_ids) - 5} more"
        
        return {
            "rule_id": "DISTRIBUTION_001",
            "description": "Maximum distribution cables leaving DP",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"DP {violation.get('dp_id', 'N/A')} has {violation.get('cable_count', 0)} distribution cables\n"
                f"Maximum allowed: {violation.get('max_allowed', 5)}\n"
                f"DP AGG_ID: {violation.get('dp_agg_id', 'N/A')}\n"
                f"Distribution cables: {cable_list}\n"
                f"Total cables: {violation.get('cable_count', 0)}"
            )
        }

    elif violation_type == "facade_cable_max_length":
        return {
            "rule_id": "DISTRIBUTION_002",
            "description": "Façade cable maximum length",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Façade cable {violation.get('cable_id', 'N/A')} exceeds maximum length\n"
                f"Cable Type: {violation.get('cable_type', 'N/A')}\n"
                f"Current length: {violation.get('cable_length', 0):.1f}m\n"
                f"Maximum allowed: {violation.get('max_allowed', 500)}m\n"
                f"Excess: {violation.get('cable_length', 0) - violation.get('max_allowed', 500):.1f}m"
            )
        }
    
    elif violation_type == "aerial_cable_poc_limit":
        poc_details = violation.get('poc_details', [])
        
        # Show first few POC details
        poc_list = []
        for i, poc in enumerate(poc_details[:5]):  # Show first 5 POCs
            poc_list.append(f"POC {poc['poc_id']} ({poc['drop_count']} drops)")
        
        poc_details_str = ", ".join(poc_list)
        if len(poc_details) > 5:
            poc_details_str += f" and {len(poc_details) - 5} more"
        
        return {
            "rule_id": "DISTRIBUTION_003",
            "description": "Aerial distribution cable POC limit",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Aerial cable {violation.get('cable_id', 'N/A')} exceeds POC limit\n"
                f"Cable Group: {violation.get('cable_group', 'N/A')}\n"
                f"Current POCs: {violation.get('poc_count', 0)} (max {violation.get('max_allowed', 22)})\n"
                f"Cables in group: {violation.get('cables_in_group', 1)}\n"
                f"POCs with 4 drops: {violation.get('pocs_with_4_drops', 0)}\n"
                f"POCs with other drop counts: {violation.get('pocs_with_other_drops', 0)}\n"
                f"Total drop connections: {violation.get('total_drop_connections', 0)}\n"
                f"POC details: {poc_details_str}"
            )
        }

    elif violation_type == "parallel_poc_connection":
        return {
            "rule_id": "DISTRIBUTION_004",
            "description": "Parallel cable POC connection",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"POC {violation.get('poc_id', 'N/A')} connected to distribution cable {violation.get('shortest_cable_id', 'N/A')} "
                f"is one of the furthest POCs. Should be connected to distribution cable {violation.get('longest_cable_id', 'N/A')}"
            )
        }

    elif violation_type == "facade_underground_length":
        return {
            "rule_id": "DISTRIBUTION_005",
            "description": "Facade underground section length",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Underground section on Distribution Cable {violation.get('cable_id', 'N/A')} is too long.\n"
                f"Measured length: {violation.get('length', 0):.1f}m"
            )
        }

    elif violation_type == "parallel_aerial_limit":
        return {
            "rule_id": "DISTRIBUTION_006",
            "description": "Parallel aerial cable limit",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Cable group {violation.get('cable_group', 'N/A')} has too many parallel aerial cables.\n"
                f"Count: {violation.get('cable_count', 0)}"
            )
        }

    elif violation_type == "underground_drop_mismatch":
        return {
            "rule_id": "DISTRIBUTION_007",
            "description": "Underground drop consistency",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Drop Cable {violation.get('drop_cable_id', 'N/A')} is not 'Underground' type, "
                f"but its parent Distribution Cable is."
            )
        }

    elif violation_type == "facade_total_underground_length":
        return {
            "rule_id": "DISTRIBUTION_008",
            "description": "Facade total underground length",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Facade cable {violation.get('cable_id', 'N/A')} exceeds total underground length.\n"
                f"Total underground length: {violation.get('length', 0):.1f}m"
            )
        }
    elif violation_type == "invalid_subtype":
        return {
            "rule_id": "SUBTYPE_01",
            "description": "SUBTYPE validation - check if subtypes exist in known list",
            "violation_type": violation.get("violation_type", "unknown"),
            "details": (
                f"Feature ID: {violation.get('feature_id', 'N/A')}; "
                f"Layer: {violation.get('layer_name', 'N/A')}; "
                f"Invalid SUBTYPE: '{violation.get('subtype', 'N/A')}'"
            ),
        }

    else:
        return {
            "rule_id": "UNKNOWN",
            "description": "Unknown violation type",
            "violation_type": "unknown",
            "details": "Unknown violation details",
        }
