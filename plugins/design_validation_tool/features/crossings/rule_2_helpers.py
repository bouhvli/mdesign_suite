from qgis.core import QgsGeometry, QgsPointXY, QgsPoint  # type: ignore
from .crossings_helper import (
    _get_line_points,
    _extract_points_from_geometry,
    _is_point_near,
)
import math

def _check_crossing_extends_beyond_intersection(crossing_geom, trench_geom, 
                                               intersection_geom, min_extension):
    """
    Check if crossing extends beyond trench intersection by at least min_extension
    
    Returns: True if crossing extends sufficiently beyond intersection, False otherwise
    """
    try:
        # Get all intersection points
        intersection_points = _extract_points_from_geometry(intersection_geom)
        if not intersection_points:
            return False
        
        # Get crossing points
        crossing_points = _get_line_points(crossing_geom)
        if len(crossing_points) < 2:
            return False
        
        # For each intersection point, check extension on both sides of crossing
        for intersect_point in intersection_points:
            # Find where along the crossing line the intersection occurs
            intersection_position = _find_position_on_line(crossing_points, intersect_point)
            if intersection_position is None:
                continue
            
            # Check extension before and after intersection
            extends_before = _check_extension_from_point(
                crossing_points, 
                intersect_point, 
                intersection_position,
                direction=-1,  # Backward direction
                min_distance=min_extension
            )
            
            extends_after = _check_extension_from_point(
                crossing_points,
                intersect_point,
                intersection_position,
                direction=1,   # Forward direction
                min_distance=min_extension
            )
            
            # Crossing must extend sufficiently in at least one direction
            if extends_before or extends_after:
                return True
        
        # No intersection point has sufficient extension
        return False
        
    except Exception as e:
        print(f"Error checking crossing extension: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def _find_position_on_line(line_points, target_point, tolerance=0.01):
    """
    Find the position of a point along a line (0 = start, 1 = end)
    Returns position as fraction of total length, or None if point not on line
    """
    try:
        # Check if point is close to any vertex
        for i, point in enumerate(line_points):
            if _is_point_near(point, target_point, tolerance):
                # Calculate position as fraction of total vertices
                return i / max(1, len(line_points) - 1)
        
        # Check if point is on any segment
        total_length = 0
        segment_lengths = []
        
        for i in range(len(line_points) - 1):
            start = line_points[i]
            end = line_points[i + 1]
            
            # Calculate segment length
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            segment_length = math.sqrt(dx*dx + dy*dy)
            segment_lengths.append(segment_length)
            total_length += segment_length
        
        if total_length == 0:
            return None
        
        # Find which segment contains the point
        accumulated_length = 0
        for i in range(len(line_points) - 1):
            start = line_points[i]
            end = line_points[i + 1]
            
            # Check if point is on this segment
            if _is_point_on_segment(target_point, start, end, tolerance):
                # Calculate distance from start of segment to point
                dx = target_point.x() - start.x()
                dy = target_point.y() - start.y()
                distance_from_start = math.sqrt(dx*dx + dy*dy)
                
                # Calculate position as fraction of total length
                position = (accumulated_length + distance_from_start) / total_length
                return position
            
            accumulated_length += segment_lengths[i]
        
        return None
        
    except Exception as e:
        print(f"Error finding position on line: {e}")
        return None


def _is_point_on_segment(point, segment_start, segment_end, tolerance=0.01):
    """Check if a point lies on a line segment within tolerance"""
    try:
        # Check if point is within bounding box of segment
        min_x = min(segment_start.x(), segment_end.x()) - tolerance
        max_x = max(segment_start.x(), segment_end.x()) + tolerance
        min_y = min(segment_start.y(), segment_end.y()) - tolerance
        max_y = max(segment_start.y(), segment_end.y()) + tolerance
        
        if not (min_x <= point.x() <= max_x and min_y <= point.y() <= max_y):
            return False
        
        # Check if point is collinear with segment
        area = abs(
            (segment_end.x() - segment_start.x()) * (point.y() - segment_start.y()) -
            (segment_end.y() - segment_start.y()) * (point.x() - segment_start.x())
        )
        
        if area > tolerance:
            return False
        
        # Check if point is between start and end
        dot_product = (
            (point.x() - segment_start.x()) * (segment_end.x() - segment_start.x()) +
            (point.y() - segment_start.y()) * (segment_end.y() - segment_start.y())
        )
        
        if dot_product < 0:
            return False
        
        squared_length = (
            (segment_end.x() - segment_start.x()) ** 2 +
            (segment_end.y() - segment_start.y()) ** 2
        )
        
        if dot_product > squared_length:
            return False
        
        return True
        
    except Exception as e:
        print(f"Error checking point on segment: {e}")
        return False


def _check_extension_from_point(line_points, from_point, position, 
                               direction, min_distance):
    """
    Check if line extends at least min_distance from a point in given direction
    
    direction: -1 for backward, 1 for forward
    """
    try:
        # Find the segment containing the point
        if direction == -1:  # Backward
            # Calculate distance from point to start of line
            total_distance = 0
            
            # Find which vertex the point is closest to
            vertex_idx = int(position * (len(line_points) - 1))
            vertex_idx = max(0, min(vertex_idx, len(line_points) - 1))
            
            # Add distance from point to current vertex
            dx = from_point.x() - line_points[vertex_idx].x()
            dy = from_point.y() - line_points[vertex_idx].y()
            total_distance += math.sqrt(dx*dx + dy*dy)
            
            # Add distances of previous vertices
            for i in range(vertex_idx - 1, -1, -1):
                dx = line_points[i+1].x() - line_points[i].x()
                dy = line_points[i+1].y() - line_points[i].y()
                total_distance += math.sqrt(dx*dx + dy*dy)
            
            return total_distance >= min_distance
            
        else:  # Forward (direction == 1)
            # Calculate distance from point to end of line
            total_distance = 0
            
            # Find which vertex the point is closest to
            vertex_idx = int(position * (len(line_points) - 1))
            vertex_idx = max(0, min(vertex_idx, len(line_points) - 1))
            
            # Add distance from point to current vertex
            dx = from_point.x() - line_points[vertex_idx].x()
            dy = from_point.y() - line_points[vertex_idx].y()
            total_distance += math.sqrt(dx*dx + dy*dy)
            
            # Add distances of subsequent vertices
            for i in range(vertex_idx, len(line_points) - 1):
                dx = line_points[i+1].x() - line_points[i].x()
                dy = line_points[i+1].y() - line_points[i].y()
                total_distance += math.sqrt(dx*dx + dy*dy)
            
            return total_distance >= min_distance
            
    except Exception as e:
        print(f"Error checking extension from point: {e}")
        return False


def _calculate_extension_beyond_intersection(crossing_geom, trench_geom, 
                                           intersection_geom):
    """
    Calculate how much the crossing extends beyond the intersection
    Returns the maximum extension distance in meters
    """
    try:
        crossing_points = _get_line_points(crossing_geom)
        if len(crossing_points) < 2:
            return 0.0
        
        intersection_points = _extract_points_from_geometry(intersection_geom)
        if not intersection_points:
            return 0.0
        
        max_extension = 0.0
        
        for intersect_point in intersection_points:
            # Find nearest point on crossing to intersection point
            nearest_geom = crossing_geom.nearestPoint(
                QgsGeometry.fromPointXY(intersect_point)
            )
            if nearest_geom.isEmpty():
                continue
            
            nearest_point = nearest_geom.asPoint()
            
            # Calculate distances to start and end of crossing
            start_dist = _calculate_distance_between_points(
                nearest_point, crossing_points[0]
            )
            end_dist = _calculate_distance_between_points(
                nearest_point, crossing_points[-1]
            )
            
            # Maximum extension is the larger of the two distances
            max_extension = max(max_extension, start_dist, end_dist)
        
        return max_extension
        
    except Exception as e:
        print(f"Error calculating extension beyond intersection: {e}")
        return 0.0


def _calculate_distance_between_points(point1, point2):
    """Calculate Euclidean distance between two points"""
    dx = point1.x() - point2.x()
    dy = point1.y() - point2.y()
    return math.sqrt(dx*dx + dy*dy)