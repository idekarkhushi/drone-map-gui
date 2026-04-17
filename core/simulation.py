from core.calculations import calculate_distance, get_angle
from core.geofence_checker import is_inside_geofence


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
        self.elapsed_time = 0  # NEW (for mission time)

        # ===== TELEMETRY RESET =====
        app.telemetry_status.configure(text="Status: Running")
        app.telemetry_data.configure(text=f"Speed: {app.speed} m/s| Distance: {app.total_distance:.2f} m")
        

        # Reset top bar sections
        app.wp_info.configure(
            text="Alt diff: 0 m | Azimuth: 0 | Gradient: 0% | Heading: 0 | Distance: 0 m"
        )
        app.mission_info.configure(
            text="Distance: 0 m | Time: 00:00 | Telem dist: 0 m"
        )

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

        
        # ================= GEOFENCE CHECK =================
        current_pos = (lat, lon)

        if app.geofence_shapes and not is_inside_geofence(app, current_pos):
            app.telemetry_status.configure(text="Status: GEOFENCE BREACH")
            app.message_label.configure(text="Drone exited GeoFence!")
            
            # 🔴 CHANGE FENCE COLOR
            for shape in app.geofence_shapes:
                try:
                    shape.set_color("red")
                except:
                    pass  # in case shape doesn't support color change


            return  # STOP simulation
                
        # ===== UPDATE TOTAL DISTANCE =====
        step_distance = distance / steps
        app.total_distance += step_distance

        # ===== TIME UPDATE =====
        self.elapsed_time += 0.025  # 25ms loop

        mins = int(self.elapsed_time) // 60
        secs = int(self.elapsed_time) % 60
        time_str = f"{mins:02d}:{secs:02d}"

        # ===== DISTANCE FORMAT =====
        if app.total_distance < 1000:
            dist_text = f"{app.total_distance:.2f} m"
        else:
            dist_text = f"{app.total_distance/1000:.2f} km"

        # ===== UPDATE RIGHT PANEL =====
        app.distance_label.configure(text=f"Distance: {dist_text}")

        # ===== TELEMETRY BAR (TOP RIGHT) =====
        app.telemetry_data.configure(text=f"Speed: {app.speed} m/s | Distance: {dist_text}")

        # ===== ANGLE =====
        angle = get_angle(start, end)

        # ===== SELECTED WAYPOINT (TOP LEFT) =====
        app.wp_info.configure(
            text=(
                f"Alt diff: 0 m | Azimuth: {int(angle)} | Gradient: 0% | "
                f"Heading: {int(angle)} | Distance: {distance:.1f} m"
            )
        )

        # ===== TOTAL MISSION (TOP RIGHT BLOCK) =====
        app.mission_info.configure(
            text=(
                f"Distance: {dist_text} | Time: {time_str} | "
                f"Telem dist: {dist_text}"
            )
        )

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