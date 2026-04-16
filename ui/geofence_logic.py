import math


def handle_map_click(app, coords):
    lat, lon = coords

    # ===== POLYGON MODE =====
    if app.geofence_mode == "polygon":
        app.geofence_points.append((lat, lon))

        app.map_widget.set_marker(lat, lon)

        if len(app.geofence_points) > 1:
            app.map_widget.set_path(app.geofence_points)

        return True  # handled

    # ===== CIRCLE MODE =====
    elif app.geofence_mode == "circle":
        app.geofence_points = [(lat, lon)]
        app.map_widget.set_marker(lat, lon)

        draw_circle(app, lat, lon, radius=200)

        app.geofence_mode = None
        return True

    return False  # not handled


def draw_circle(app, lat, lon, radius=200):
    points = []

    for i in range(36):
        angle = math.radians(i * 10)

        dx = radius * math.cos(angle)
        dy = radius * math.sin(angle)

        new_lat = lat + (dy / 111320)
        new_lon = lon + (dx / (111320 * math.cos(math.radians(lat))))

        points.append((new_lat, new_lon))

    polygon = app.map_widget.set_polygon(points)
    app.geofence_shapes.append(polygon)