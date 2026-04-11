from core.calculations import calculate_distance, get_angle


class DroneSimulation:
    def __init__(self, app):
        self.app = app

    def start(self):
        app = self.app

        if len(app.points) < 2:
            app.message_label.configure(text="Add at least 2 points")
            return

        try:
            app.speed = float(app.speed_entry.get())
            if app.speed <= 0:
                raise ValueError
        except:
            app.speed = 5

        self.sim_index = 0
        self.step = 0
        app.total_distance = 0

        if app.drone_marker:
            app.drone_marker.delete()

        lat, lon = app.points[0]

        app.drone_marker = app.map_widget.set_marker(
            lat, lon,
            icon=app.get_rotated_drone(0)
        )

        self.animate()

    def animate(self):
        app = self.app

        if self.sim_index >= len(app.points) - 1:
            return

        start = app.points[self.sim_index]
        end = app.points[self.sim_index + 1]

        distance = calculate_distance(start, end)
        steps = max(int((distance / app.speed) / 0.025), 1)

        t = self.step / steps

        lat = start[0] + (end[0] - start[0]) * t
        lon = start[1] + (end[1] - start[1]) * t

        app.total_distance += distance / steps

        if app.total_distance < 1000:
            app.distance_label.configure(text=f"Distance: {app.total_distance:.2f} m")
        else:
            app.distance_label.configure(text=f"Distance: {app.total_distance/1000:.2f} km")

        angle = get_angle(start, end)

        app.drone_marker.set_position(lat, lon)
        app.drone_marker.change_icon(app.get_rotated_drone(angle))

        app.map_widget.set_position(lat, lon)

        self.step += 1

        if self.step > steps:
            self.step = 0
            self.sim_index += 1

        app.after(25, self.animate)