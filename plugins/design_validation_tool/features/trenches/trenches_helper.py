import math
from qgis.core import QgsPointXY  # type: ignore


def get_line_points(geometry):
    """Get points from a line geometry, handling both single and MultiLineString"""
    points = []
    if geometry.isMultipart():
        multi_line = geometry.asMultiPolyline()
        if multi_line and len(multi_line) > 0:
            for part in multi_line:
                points.extend([QgsPointXY(p) for p in part])
    else:
        points = [QgsPointXY(p) for p in geometry.asPolyline()]
    return points


def calculate_vertex_angle(p1, p2, p3):
    """
    Calculate the interior angle at vertex p2 formed by segments p1->p2 and p2->p3.
    Returns angle in degrees (0-180). A straight line gives 180 degrees.
    """
    try:
        dx1 = p1.x() - p2.x()
        dy1 = p1.y() - p2.y()
        dx2 = p3.x() - p2.x()
        dy2 = p3.y() - p2.y()

        len1 = math.sqrt(dx1 * dx1 + dy1 * dy1)
        len2 = math.sqrt(dx2 * dx2 + dy2 * dy2)

        if len1 == 0 or len2 == 0:
            return None

        cos_angle = (dx1 * dx2 + dy1 * dy2) / (len1 * len2)
        cos_angle = max(-1.0, min(1.0, cos_angle))

        return math.degrees(math.acos(cos_angle))
    except Exception:
        return None


def calculate_angle_at_intersection(drop_geom, dist_geom):
    """
    Calculate the acute angle (0-90 degrees) between drop cable and distribution cable
    at their intersection point. Uses the local direction of the distribution cable
    at the intersection rather than its overall direction.
    """
    try:
        intersection = drop_geom.intersection(dist_geom)
        if intersection.isEmpty():
            return None

        # Get intersection point
        if intersection.type() == 0:  # Point
            int_point = intersection.asPoint()
        else:
            int_point = intersection.centroid().asPoint()

        # Drop cable direction (overall - drop cables are short/straight)
        drop_dir = get_line_direction(drop_geom)
        if drop_dir is None:
            return None

        # Distribution cable direction at the intersection point
        dist_dir = get_direction_at_point(dist_geom, int_point)
        if dist_dir is None:
            return None

        # Calculate acute angle between the two directions
        dot_product = drop_dir.x() * dist_dir.x() + drop_dir.y() * dist_dir.y()
        dot_product = max(-1.0, min(1.0, dot_product))

        angle_deg = math.degrees(math.acos(dot_product))

        # Return acute angle (0-90)
        return min(angle_deg, 180 - angle_deg)
    except Exception:
        return None


def get_line_direction(line_geom):
    """Get normalized overall direction vector of a line (start to end)"""
    try:
        points = get_line_points(line_geom)
        if len(points) < 2:
            return None

        dx = points[-1].x() - points[0].x()
        dy = points[-1].y() - points[0].y()

        length = math.sqrt(dx * dx + dy * dy)
        if length == 0:
            return None

        return QgsPointXY(dx / length, dy / length)
    except Exception:
        return None


def get_direction_at_point(line_geom, point):
    """
    Get the direction of the line segment nearest to a given point.
    This gives the local direction rather than overall direction.
    """
    try:
        vertices = get_line_points(line_geom)
        if len(vertices) < 2:
            return None

        # Find the segment closest to the given point
        min_distance = float("inf")
        segment_start = None
        segment_end = None

        for i in range(len(vertices) - 1):
            start = vertices[i]
            end = vertices[i + 1]
            seg_dist = distance_point_to_segment(point, start, end)
            if seg_dist < min_distance:
                min_distance = seg_dist
                segment_start = start
                segment_end = end

        if segment_start is None or segment_end is None:
            return None

        dx = segment_end.x() - segment_start.x()
        dy = segment_end.y() - segment_start.y()

        length = math.sqrt(dx * dx + dy * dy)
        if length == 0:
            return None

        return QgsPointXY(dx / length, dy / length)
    except Exception:
        return None


def turn_direction(p1, p2, p3):
    """
    Determine the turn direction at vertex p2.
    Returns +1 for left turn, -1 for right turn, 0 for collinear.
    Uses the cross product of vectors (p1->p2) and (p2->p3).
    """
    cross = (p2.x() - p1.x()) * (p3.y() - p2.y()) - \
            (p2.y() - p1.y()) * (p3.x() - p2.x())
    if cross > 0:
        return 1   # left turn
    elif cross < 0:
        return -1  # right turn
    return 0       # collinear


def direction_vector(p1, p2):
    """Compute normalized direction vector from p1 to p2."""
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    length = math.sqrt(dx * dx + dy * dy)
    if length == 0:
        return None
    return QgsPointXY(dx / length, dy / length)


def check_drop_segment_angles(drop_geom, dist_geom):
    """
    Check every segment of a drop cable against the distribution cable.
    Each segment must be either parallel (0-15deg) or perpendicular (75-90deg acute)
    to the local direction of the distribution cable at that segment.
    Returns True if all segments have valid angles.
    """
    drop_points = get_line_points(drop_geom)
    if len(drop_points) < 2:
        return True

    for i in range(len(drop_points) - 1):
        seg_start = drop_points[i]
        seg_end = drop_points[i + 1]

        dx = seg_end.x() - seg_start.x()
        dy = seg_end.y() - seg_start.y()
        length = math.sqrt(dx * dx + dy * dy)
        if length == 0:
            continue

        seg_dir = QgsPointXY(dx / length, dy / length)

        # Get distribution cable direction at the midpoint of this segment
        mid_point = QgsPointXY(
            (seg_start.x() + seg_end.x()) / 2,
            (seg_start.y() + seg_end.y()) / 2
        )
        dist_dir = get_direction_at_point(dist_geom, mid_point)
        if dist_dir is None:
            continue

        # Calculate acute angle (0-90deg)
        dot = seg_dir.x() * dist_dir.x() + seg_dir.y() * dist_dir.y()
        dot = max(-1.0, min(1.0, dot))
        angle = min(math.degrees(math.acos(dot)), 180 - math.degrees(math.acos(dot)))

        is_parallel = angle <= 15.0
        is_perpendicular = angle >= 75.0

        if not is_parallel and not is_perpendicular:
            return False

    return True


def detect_u_shapes(cable_geom, angle_low=60.0, angle_high=120.0,
                    max_cross_length=30.0, reversal_threshold=150.0,
                    max_vertices_between=5):
    """
    Detect U-shape patterns in a cable geometry.

    A U-shape consists of two sharp turns (~90 degrees) close together with a
    short crossing segment between them, where the cable reverses direction.

    Returns a list of U-shape dicts with entry/exit points and midpoint.
    """
    points = get_line_points(cable_geom)
    if len(points) < 4:
        return []

    # Find all sharp turn vertices (angle between angle_low and angle_high)
    sharp_turns = []
    for i in range(1, len(points) - 1):
        angle = calculate_vertex_angle(points[i - 1], points[i], points[i + 1])
        if angle is not None and angle_low <= angle <= angle_high:
            sharp_turns.append((i, angle, points[i]))

    u_shapes = []

    for idx_a in range(len(sharp_turns)):
        for idx_b in range(idx_a + 1, len(sharp_turns)):
            i_a, angle_a, point_a = sharp_turns[idx_a]
            i_b, angle_b, point_b = sharp_turns[idx_b]

            # Two turns must be close together (few vertices apart)
            if i_b - i_a > max_vertices_between:
                break

            # Calculate path length between the two turns
            cross_length = 0.0
            for k in range(i_a, i_b):
                dx = points[k + 1].x() - points[k].x()
                dy = points[k + 1].y() - points[k].y()
                cross_length += math.sqrt(dx * dx + dy * dy)

            if cross_length > max_cross_length:
                continue

            # Check direction reversal: direction before entry vs after exit
            if i_a < 1 or i_b + 1 >= len(points):
                continue

            dir_before = direction_vector(points[i_a - 1], points[i_a])
            dir_after = direction_vector(points[i_b], points[i_b + 1])

            if dir_before is None or dir_after is None:
                continue

            dot = dir_before.x() * dir_after.x() + dir_before.y() * dir_after.y()
            dot = max(-1.0, min(1.0, dot))
            reversal_angle = math.degrees(math.acos(dot))

            if reversal_angle >= reversal_threshold:
                midpoint = QgsPointXY(
                    (point_a.x() + point_b.x()) / 2,
                    (point_a.y() + point_b.y()) / 2
                )
                u_shapes.append({
                    'entry_vertex_index': i_a,
                    'exit_vertex_index': i_b,
                    'entry_point': point_a,
                    'exit_point': point_b,
                    'cross_segment_length': cross_length,
                    'midpoint': midpoint,
                    'entry_angle': angle_a,
                    'exit_angle': angle_b,
                })

    return u_shapes


def distance_point_to_segment(point, seg_start, seg_end):
    """Calculate minimum distance from a point to a line segment"""
    line_dx = seg_end.x() - seg_start.x()
    line_dy = seg_end.y() - seg_start.y()
    length_sq = line_dx * line_dx + line_dy * line_dy

    if length_sq == 0:
        dx = point.x() - seg_start.x()
        dy = point.y() - seg_start.y()
        return math.sqrt(dx * dx + dy * dy)

    point_dx = point.x() - seg_start.x()
    point_dy = point.y() - seg_start.y()
    t = max(0, min(1, (point_dx * line_dx + point_dy * line_dy) / length_sq))

    proj_x = seg_start.x() + t * line_dx
    proj_y = seg_start.y() + t * line_dy

    dx = point.x() - proj_x
    dy = point.y() - proj_y
    return math.sqrt(dx * dx + dy * dy)
