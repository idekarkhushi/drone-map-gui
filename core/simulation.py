from core.calculations import calculate_distance, get_angle


class DroneSimulation:
    def __init__(self, app):
        self.app = app

    def start(self):
        app = self.app

        if len(app.points) < 2:
            app.message_label.configure(text="Add at least 2 points")
            return

        # ===== SPEED INPUT =====
        try:
            app.speed = float(app.speed_entry.get())
            if app.speed <= 0:
                raise ValueError
        except:
            app.speed = 5

        # ===== RESET VALUES =====
        self.sim_index = 0
        self.step = 0
        app.total_distance = 0

        # ===== TELEMETRY RESET =====
        app.telemetry_status.configure(text="Status: Running")
        app.telemetry_speed.configure(text=f"Speed: {app.speed} m/s")
        app.telemetry_distance.configure(text="Distance: 0 m")

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

        # ===== END CONDITION =====
        if self.sim_index >= len(app.points) - 1:
            app.telemetry_status.configure(text="Status: Completed")
            return

        start = app.points[self.sim_index]
        end = app.points[self.sim_index + 1]

        # ===== DISTANCE & STEPS =====
        distance = calculate_distance(start, end)
        steps = max(int((distance / app.speed) / 0.025), 1)

        t = self.step / steps

        lat = start[0] + (end[0] - start[0]) * t
        lon = start[1] + (end[1] - start[1]) * t

        # ===== UPDATE TOTAL DISTANCE =====
        step_distance = distance / steps
        app.total_distance += step_distance

        # ===== UPDATE RIGHT PANEL (existing) =====
        if app.total_distance < 1000:
            app.distance_label.configure(
                text=f"Distance: {app.total_distance:.2f} m"
            )
            telemetry_text = f"Distance: {app.total_distance:.2f} m"
        else:
            app.distance_label.configure(
                text=f"Distance: {app.total_distance/1000:.2f} km"
            )
            telemetry_text = f"Distance: {app.total_distance/1000:.2f} km"

        # ===== TELEMETRY BAR UPDATE =====
        app.telemetry_distance.configure(text=telemetry_text)
        app.telemetry_speed.configure(text=f"Speed: {app.speed} m/s")

        # ===== ROTATION =====
        angle = get_angle(start, end)

        # ===== MOVE DRONE =====
        app.drone_marker.set_position(lat, lon)
        app.drone_marker.change_icon(app.get_rotated_drone(angle))

        app.map_widget.set_position(lat, lon)

        self.step += 1

        if self.step > steps:
            self.step = 0
            self.sim_index += 1

        # ===== LOOP =====
        app.after(25, self.animate)