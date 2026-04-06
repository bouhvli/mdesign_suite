from qgis.core import QgsGeometry, QgsPointXY, QgsPoint  # type: ignore
from typing import List, Dict, Any, Optional, Tuple
import math
from .crossings_helper import (
    _get_line_points,
    _angle_between_vectors,
    _distance_point_to_segment,
)

def _get_grb_direction_at_point(line_geom, point):
    """
    Get direction of GRB line at a specific point
    Returns direction vector as QgsPointXY
    """
    try:
        # Find the segment containing or nearest to the point
        points = _get_line_points(line_geom)
        if len(points) < 2:
            return None
        
        # Find the segment closest to the point
        min_distance = float('inf')
        segment_start = None
        segment_end = None
        
        for i in range(len(points) - 1):
            start = points[i]
            end = points[i + 1]
            
            # Calculate distance from point to segment
            segment_distance = _distance_point_to_segment(point, start, end)
            
            if segment_distance < min_distance:
                min_distance = segment_distance
                segment_start = start
                segment_end = end
        
        if segment_start is None or segment_end is None:
            return None
        
        # Calculate direction vector
        dx = segment_end.x() - segment_start.x()
        dy = segment_end.y() - segment_start.y()
        
        length = math.sqrt(dx*dx + dy*dy)
        if length == 0:
            return None
        
        return QgsPointXY(dx/length, dy/length)
        
    except Exception as e:
        print(f"Error getting GRB direction at point: {e}")
        return None


def _get_overall_line_direction(line_geom):
    """
    Get overall direction of a line (from start to end)
    Returns direction vector as QgsPointXY
    """
    try:
        points = _get_line_points(line_geom)
        if len(points) < 2:
            return None
        
        start = points[0]
        end = points[-1]
        
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        
        length = math.sqrt(dx*dx + dy*dy)
        if length == 0:
            return None
        
        return QgsPointXY(dx/length, dy/length)
        
    except Exception as e:
        print(f"Error getting overall line direction: {e}")
        return None


def _find_diverging_grb_pairs(grb_lines, min_angle=20.0):
    """
    Find pairs of GRB lines that are diverging (going away from each other)
    Returns list of (grb1_idx, grb2_idx, angle_between)
    """
    diverging_pairs = []
    
    for i in range(len(grb_lines)):
        for j in range(i + 1, len(grb_lines)):
            dir1 = grb_lines[i]['local_direction']
            dir2 = grb_lines[j]['local_direction']
            
            if dir1 is None or dir2 is None:
                continue
            
            # Calculate angle between directions
            angle = _angle_between_vectors(dir1, dir2)
            if angle is None:
                continue
            
            # Check if lines are diverging (angle > threshold)
            if angle > min_angle:
                # Also check if they're moving away from each other
                # by comparing their positions relative to each other
                point1 = grb_lines[i]['nearest_point']
                point2 = grb_lines[j]['nearest_point']
                
                # Calculate vector from point1 to point2
                dx = point2.x() - point1.x()
                dy = point2.y() - point1.y()
                
                # Normalize
                length = math.sqrt(dx*dx + dy*dy)
                if length > 0:
                    separation_vector = QgsPointXY(dx/length, dy/length)
                    
                    # Check if lines are moving in directions that increase separation
                    dir1_dot_sep = dir1.x() * separation_vector.x() + dir1.y() * separation_vector.y()
                    dir2_dot_sep = dir2.x() * separation_vector.x() + dir2.y() * separation_vector.y()
                    
                    # If both have positive dot product with separation vector, they're diverging
                    if dir1_dot_sep > 0.1 and dir2_dot_sep > 0.1:
                        diverging_pairs.append({
                            'grb1_idx': i,
                            'grb2_idx': j,
                            'angle': angle,
                            'grb1_id': grb_lines[i]['feature_id'],
                            'grb2_id': grb_lines[j]['feature_id']
                        })
    
    return diverging_pairs


def _find_grb_direction_changes(grb_lines, min_change=30.0):
    """
    Find GRB lines that change direction significantly (indicating road curves/widening)
    Returns list of grb indices with significant direction changes
    """
    direction_changes = []
    
    for i, grb_line in enumerate(grb_lines):
        local_dir = grb_line['local_direction']
        overall_dir = grb_line['overall_direction']
        
        if local_dir is None or overall_dir is None:
            continue
        
        # Calculate angle between local and overall direction
        angle_change = _angle_between_vectors(local_dir, overall_dir)
        if angle_change is None:
            continue
        
        if angle_change > min_change:
            direction_changes.append({
                'grb_idx': i,
                'grb_id': grb_line['feature_id'],
                'angle_change': angle_change,
                'local_vs_overall': angle_change
            })
    
    return direction_changes


def _create_widening_area_violation(crossing_feature, diverging_pairs, direction_changes):
    """
    Create a violation record for crossing in widening area
    """
    crossing_id = crossing_feature.id()
    
    # Format details about diverging GRB pairs
    pair_details = []
    for pair in diverging_pairs[:3]:  # Limit to first 3 for brevity
        pair_details.append(
            f"GRB {pair['grb1_id']} & {pair['grb2_id']}: {pair['angle']:.1f}° apart"
        )
    
    # Format details about direction changes
    change_details = []
    for change in direction_changes[:3]:  # Limit to first 3
        change_details.append(
            f"GRB {change['grb_id']}: {change['angle_change']:.1f}° direction change"
        )
    
    violation_info = {
        "violation_type": "crossing_in_widening_area",
        "feature_id": crossing_id,
        "geometry": crossing_feature.geometry(),
        "layer": "IN_Crossings",
        "diverging_grb_pairs": len(diverging_pairs),
        "grb_direction_changes": len(direction_changes),
        "violation_reason": f"Crossing (ID: {crossing_id}) is located in a road widening area. "
                          f"Detected {len(diverging_pairs)} pairs of diverging GRB trenches and "
                          f"{len(direction_changes)} GRB lines with significant direction changes. "
                          f"Consider moving crossing to a narrower section of the road."
    }
    
    # Add detailed info if available
    if pair_details:
        violation_info["diverging_details"] = "; ".join(pair_details)
    if change_details:
        violation_info["direction_change_details"] = "; ".join(change_details)
    
    return violation_info


# Add this helper function to crossings_helper.py if not already there
def _distance_point_to_segment(point, segment_start, segment_end):
    """Calculate distance from point to line segment"""
    # Vector from segment start to end
    line_vec = QgsPointXY(segment_end.x() - segment_start.x(), 
                         segment_end.y() - segment_start.y())
    
    # Vector from segment start to point
    point_vec = QgsPointXY(point.x() - segment_start.x(), 
                          point.y() - segment_start.y())
    
    line_length_squared = line_vec.x()**2 + line_vec.y()**2
    
    if line_length_squared == 0:
        # Segment is a point
        return math.sqrt(point_vec.x()**2 + point_vec.y()**2)
    
    # Project point onto line
    t = max(0, min(1, (point_vec.x() * line_vec.x() + point_vec.y() * line_vec.y()) / line_length_squared))
    
    # Calculate projection point
    projection = QgsPointXY(
        segment_start.x() + t * line_vec.x(),
        segment_start.y() + t * line_vec.y()
    )
    
    # Distance from point to projection
    return math.sqrt((point.x() - projection.x())**2 + (point.y() - projection.y())**2)