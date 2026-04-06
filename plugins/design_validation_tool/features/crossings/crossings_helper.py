from qgis.core import QgsGeometry, QgsPointXY, QgsPoint  # type: ignore
from typing import List, Dict, Any, Optional, Tuple
import math


def _extract_points_from_geometry(geometry: QgsGeometry):
    """Extract points from various geometry types"""
    points = []

    if geometry.isMultipart():
        multi_geom = geometry.asGeometryCollection()
        for geom in multi_geom:
            if geom.type() == 0:  # Point
                points.append(geom.asPoint())
            elif geom.type() == 1:  # Line
                # Handle both single lines and MultiLineString within the multipart
                if geom.isMultipart():
                    multi_line = geom.asMultiPolyline()
                    for line_part in multi_line:
                        points.extend([QgsPointXY(p) for p in line_part])
                else:
                    points.extend([QgsPointXY(p) for p in geom.asPolyline()])
            elif geom.type() == 2:  # Polygon
                # Get exterior ring points
                polygon = geom.asPolygon()
                if polygon:
                    points.extend([QgsPointXY(p) for p in polygon[0]])
    else:
        if geometry.type() == 0:  # Point
            points.append(geometry.asPoint())
        elif geometry.type() == 1:  # Line
            # Handle both single lines and MultiLineString
            if geometry.isMultipart():
                multi_line = geometry.asMultiPolyline()
                for line_part in multi_line:
                    points.extend([QgsPointXY(p) for p in line_part])
            else:
                points.extend([QgsPointXY(p) for p in geometry.asPolyline()])
        elif geometry.type() == 2:  # Polygon
            polygon = geometry.asPolygon()
            if polygon:
                points.extend([QgsPointXY(p) for p in polygon[0]])

    return points


def _get_line_direction_at_point(line_geom: QgsGeometry, point: QgsPointXY):
    """
    Get direction vector of a line at a given point
    Handles both single lines and MultiLineString geometries
    """
    try:
        if not line_geom or line_geom.isEmpty():
            return None

        # Use nearestPoint to find the closest point on the line
        point_geom = QgsGeometry.fromPointXY(point)
        nearest_geom = line_geom.nearestPoint(point_geom)

        if nearest_geom.isEmpty():
            return None

        nearest_point = nearest_geom.asPoint()

        # Get all vertices from the line geometry
        vertices = []

        # Handle MultiLineString geometries
        if line_geom.isMultipart():
            multi_line = line_geom.asMultiPolyline()
            for part in multi_line:
                vertices.extend([QgsPointXY(p) for p in part])
        else:
            # Single line
            vertices = [QgsPointXY(p) for p in line_geom.asPolyline()]

        if len(vertices) < 2:
            return None

        # Find the segment closest to the nearest point
        min_distance = float("inf")
        segment_start = None
        segment_end = None

        for i in range(len(vertices) - 1):
            start = vertices[i]
            end = vertices[i + 1]

            # Calculate distance from nearest_point to segment
            segment_distance = _distance_point_to_segment(nearest_point, start, end)

            if segment_distance < min_distance:
                min_distance = segment_distance
                segment_start = start
                segment_end = end

        if segment_start is None or segment_end is None:
            return None

        # Calculate direction vector (normalized)
        dx = segment_end.x() - segment_start.x()
        dy = segment_end.y() - segment_start.y()

        # Normalize
        length = math.sqrt(dx * dx + dy * dy)
        if length == 0:
            return None

        return QgsPointXY(dx / length, dy / length)

    except Exception as e:
        print(f"Error getting line direction: {e}")
        import traceback

        print(traceback.format_exc())
        return None


def _distance_point_to_segment(
    point: QgsPointXY, segment_start: QgsPointXY, segment_end: QgsPointXY
) -> float:
    """Calculate distance from point to line segment"""
    # Vector from segment start to end
    line_vec = QgsPointXY(
        segment_end.x() - segment_start.x(), segment_end.y() - segment_start.y()
    )

    # Vector from segment start to point
    point_vec = QgsPointXY(point.x() - segment_start.x(), point.y() - segment_start.y())

    line_length_squared = line_vec.x() ** 2 + line_vec.y() ** 2

    if line_length_squared == 0:
        # Segment is a point
        return math.sqrt(point_vec.x() ** 2 + point_vec.y() ** 2)

    # Project point onto line
    t = max(
        0,
        min(
            1,
            (point_vec.x() * line_vec.x() + point_vec.y() * line_vec.y())
            / line_length_squared,
        ),
    )

    # Calculate projection point
    projection = QgsPointXY(
        segment_start.x() + t * line_vec.x(), segment_start.y() + t * line_vec.y()
    )

    # Distance from point to projection
    return math.sqrt(
        (point.x() - projection.x()) ** 2 + (point.y() - projection.y()) ** 2
    )


def _get_geometry_direction_at_point(geometry: QgsGeometry, point: QgsPointXY):
    """
    Get direction vector of geometry (line or polygon boundary) at a point
    """
    try:
        if geometry.type() == 1:  # Line
            return _get_line_direction_at_point(geometry, point)
        elif geometry.type() == 2:  # Polygon
            # For polygon, get direction of boundary at point
            boundary = geometry.convertToType(1, False)  # Convert to line (boundary)
            if boundary:
                return _get_line_direction_at_point(boundary, point)
        return None
    except Exception as e:
        print(f"Error getting geometry direction: {e}")
        import traceback

        print(traceback.format_exc())
        return None


def _project_point_to_geometry(point: QgsPointXY, geometry: QgsGeometry):
    """
    Project a point onto a geometry (line or polygon boundary)
    Returns the projected point on the geometry as QgsPointXY
    """
    try:
        if geometry.isEmpty():
            return None

        # Create a point geometry from the input point
        point_geom = QgsGeometry.fromPointXY(point)

        # Find the nearest point on the geometry
        projected_geom = geometry.nearestPoint(point_geom)

        if not projected_geom.isEmpty():
            return projected_geom.asPoint()
        else:
            return None

    except Exception as e:
        print(f"Error projecting point to geometry: {e}")
        import traceback

        print(traceback.format_exc())
        return None


def _calculate_angle_at_point(
    crossing_geom: QgsGeometry, trench_geom: QgsGeometry, point: QgsPointXY
):
    """
    Calculate angle between crossing and trench at intersection point
    """
    try:
        # Get crossing direction at point
        crossing_direction = _get_line_direction_at_point(crossing_geom, point)
        if crossing_direction is None:
            return None

        # Get trench direction at point
        trench_direction = _get_geometry_direction_at_point(trench_geom, point)
        if trench_direction is None:
            return None

        # Calculate angle between directions
        angle = _angle_between_vectors(crossing_direction, trench_direction)
        return angle

    except Exception as e:
        print(f"Error calculating angle at point: {e}")
        import traceback

        print(traceback.format_exc())
        return None


def _calculate_angle_at_projected_point(
    crossing_geom: QgsGeometry,
    trench_geom: QgsGeometry,
    crossing_point: QgsPointXY,
    projected_point: QgsPointXY,
):
    """
    Calculate angle between crossing and trench at projected point
    """
    try:
        # Get crossing direction at the original point
        crossing_direction = _get_line_direction_at_point(crossing_geom, crossing_point)
        if crossing_direction is None:
            return None

        # Get trench direction at projected point
        trench_direction = _get_geometry_direction_at_point(
            trench_geom, projected_point
        )
        if trench_direction is None:
            return None

        # Calculate angle between directions
        angle = _angle_between_vectors(crossing_direction, trench_direction)
        return angle

    except Exception as e:
        print(f"Error calculating angle at projected point: {e}")
        import traceback

        print(traceback.format_exc())
        return None


def _angle_between_vectors(v1: QgsPointXY, v2: QgsPointXY):
    """
    Calculate angle between two vectors in degrees
    """
    try:
        dot_product = v1.x() * v2.x() + v1.y() * v2.y()

        # Handle floating point errors
        dot_product = max(-1.0, min(1.0, dot_product))

        angle_rad = math.acos(dot_product)
        angle_deg = math.degrees(angle_rad)

        # Return acute angle (0-90 degrees)
        if angle_deg > 90:
            angle_deg = 180 - angle_deg

        return angle_deg
    except Exception as e:
        print(f"Error calculating angle between vectors: {e}")
        return None


def _is_perpendicular(angle: float, tolerance: float = 5.0):
    """
    Check if angle is within tolerance of 90 degrees
    """
    if angle is None:
        return False
    return abs(angle - 90.0) <= tolerance


def _is_point_near(point1: QgsPointXY, point2: QgsPointXY, max_distance: float = 10.0):
    """
    Check if two points are within a specified distance
    """
    dx = point1.x() - point2.x()
    dy = point1.y() - point2.y()
    distance = math.sqrt(dx * dx + dy * dy)
    return distance <= max_distance


def _create_result(rule_id: str, description: str, violations: List, message: str):
    """Create a standardized result dictionary"""
    failed_ids = []

    for v in violations:
        if isinstance(v, dict):
            if v.get("feature_id") is not None:
                if v.get("feature_2_id") is not None:
                    # For proximity violations with two features
                    failed_ids.append(
                        f"Crossings_{v.get('feature_1_id')}&{v.get('feature_2_id')}"
                    )
                else:
                    failed_ids.append(f"Crossing_{v.get('feature_id')}")
            elif v.get("layer") is not None:
                failed_ids.append(f"{v.get('layer')}_feature")
        else:
            failed_ids.append(str(v))

    failed_features_str = ", ".join(failed_ids) if failed_ids else ""

    return {
        "rule_id": rule_id,
        "Description": description,
        "status": "PASS" if not violations else "FAIL",
        "violation_count": len(violations),
        "failed_features": failed_features_str,
        "message": message,
    }


def _create_error_result(rule_id: str, message: str):
    return {
        "rule_id": rule_id,
        "Description": "Crossings validation rule",
        "status": "ERROR",
        "violation_count": 0,
        "failed_features": "",
        "message": message,
    }


# Add this helper function for getting line points
def _get_line_points(geometry: QgsGeometry):
    """Get points from a line geometry, handling both single and MultiLineString"""
    points = []
    if geometry.isMultipart():
        multi_line = geometry.asMultiPolyline()
        if multi_line and len(multi_line) > 0:
            # Take first line part
            points = [QgsPointXY(p) for p in multi_line[0]]
    else:
        points = [QgsPointXY(p) for p in geometry.asPolyline()]
    return points


def _calculate_line_angle(
    line1_geom: QgsGeometry, line2_geom: QgsGeometry
) -> Optional[float]:
    """
    Calculate the acute angle between two lines (0-90°)
    """
    try:
        # Get direction vectors of both lines (using first segments)
        dir1 = _get_line_direction(line1_geom)
        dir2 = _get_line_direction(line2_geom)

        if dir1 is None or dir2 is None:
            return None

        # Calculate angle between vectors
        dot_product = dir1.x() * dir2.x() + dir1.y() * dir2.y()
        dot_product = max(-1.0, min(1.0, dot_product))

        angle_rad = math.acos(dot_product)
        angle_deg = math.degrees(angle_rad)

        # Return the acute angle (0-90°)
        return min(angle_deg, 180 - angle_deg)

    except Exception as e:
        print(f"Error calculating line angle: {e}")
        return None


def _get_line_direction(line_geom: QgsGeometry) -> Optional[QgsPointXY]:
    """
    Get overall direction of a line (using first and last points)
    """
    try:
        points = _get_line_points(line_geom)
        if len(points) < 2:
            return None

        # Use vector from start to end (overall direction)
        start = points[0]
        end = points[-1]

        dx = end.x() - start.x()
        dy = end.y() - start.y()

        length = math.sqrt(dx * dx + dy * dy)
        if length == 0:
            return None

        return QgsPointXY(dx / length, dy / length)

    except Exception as e:
        print(f"Error getting line direction: {e}")
        return None


def _get_line_direction_simple(line_geom):
    """
    Get overall direction of a line (using first and last points)
    Simplified version that always works
    """
    try:
        points = _get_line_points(line_geom)
        if len(points) < 2:
            return None

        # Use vector from start to end (overall direction)
        start = points[0]
        end = points[-1]

        dx = end.x() - start.x()
        dy = end.y() - start.y()

        length = math.sqrt(dx * dx + dy * dy)
        if length == 0:
            return None

        from qgis.core import QgsPointXY  # type: ignore

        return QgsPointXY(dx / length, dy / length)

    except Exception as e:
        print(f"Error getting line direction: {e}")
        return None


def _calculate_min_distance(geom1, geom2):
    """
    Calculate minimum distance between two geometries in meters
    Simplified version - returns distance in map units
    """
    try:
        # Use QGIS distance calculation
        return geom1.distance(geom2)
    except Exception as e:
        print(f"Error calculating distance: {e}")
        # Fallback: calculate centroid distance
        centroid1 = geom1.centroid().asPoint()
        centroid2 = geom2.centroid().asPoint()
        dx = centroid1.x() - centroid2.x()
        dy = centroid1.y() - centroid2.y()
        return math.sqrt(dx * dx + dy * dy)


def _calculate_min_distance_between_crossings(
    geom1, geom2, max_search_distance=None
):
    """
    Calculate minimum distance between two crossing geometries
    Optimized to stop early if distance exceeds max_search_distance
    """
    try:
        # Method 1: Use QGIS distance calculation (most accurate)
        distance = geom1.distance(geom2)

        # If we have a max search distance and we're already above it, return early
        if max_search_distance is not None and distance > max_search_distance:
            return distance

        # Method 2: For lines, we might want to check vertex-to-vertex or segment distances
        # This is more computationally expensive but more accurate for complex geometries

        # Get vertices from both geometries
        points1 = _get_line_points(geom1)
        points2 = _get_line_points(geom2)

        if len(points1) == 0 or len(points2) == 0:
            return distance  # Return the QGIS distance as fallback

        # Calculate minimum distance between any point in geom1 and any point in geom2
        min_point_distance = float("inf")

        for p1 in points1:
            for p2 in points2:
                dx = p1.x() - p2.x()
                dy = p1.y() - p2.y()
                point_distance = math.sqrt(dx * dx + dy * dy)

                if point_distance < min_point_distance:
                    min_point_distance = point_distance

                # Early exit if we found a distance less than threshold
                if (
                    max_search_distance is not None
                    and min_point_distance <= max_search_distance
                ):
                    return min_point_distance

        # Return the minimum of QGIS distance and point-to-point distance
        return min(distance, min_point_distance)

    except Exception as e:
        print(f"Error calculating distance between crossings: {e}")
        # Fallback: centroid distance
        try:
            centroid1 = geom1.centroid().asPoint()
            centroid2 = geom2.centroid().asPoint()
            dx = centroid1.x() - centroid2.x()
            dy = centroid1.y() - centroid2.y()
            return math.sqrt(dx * dx + dy * dy)
        except:
            return float("inf")
