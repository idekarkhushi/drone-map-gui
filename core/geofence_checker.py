import math


def is_inside_circle(point, center, radius):
    lat1, lon1 = point
    lat2, lon2 = center

    # Approx distance in meters
    dx = (lon1 - lon2) * 111320 * math.cos(math.radians(lat1))
    dy = (lat1 - lat2) * 111320

    distance = math.sqrt(dx * dx + dy * dy)
    return distance <= radius


def is_inside_polygon(point, polygon):
    x, y = point[1], point[0]  # lon, lat
    inside = False

    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i][1], polygon[i][0]
        x2, y2 = polygon[(i + 1) % n][1], polygon[(i + 1) % n][0]

        if ((y1 > y) != (y2 > y)):
            x_intersect = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-9) + x1
            if x < x_intersect:
                inside = not inside

    return inside


def is_inside_geofence(app, point):
    for shape in app.geofence_shapes:
        # Detect polygon
        if hasattr(shape, "position_list"):
            if is_inside_polygon(point, shape.position_list):
                return True

        # Detect circle (if you later store it properly)
        if hasattr(shape, "center") and hasattr(shape, "radius"):
            if is_inside_circle(point, shape.center, shape.radius):
                return True

    return False