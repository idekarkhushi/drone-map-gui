class MissionHandler:
    def __init__(self, mavlink):
        self.mav = mavlink

    def send_waypoint(self, lat, lon, alt):
        self.mav.master.mav.mission_item_send(
            self.mav.master.target_system,
            self.mav.master.target_component,
            0,
            3,  # MAV_FRAME_GLOBAL_RELATIVE_ALT
            16, # NAV_WAYPOINT
            0, 1,
            0, 0, 0, 0,
            lat, lon, alt
        )

    def takeoff(self, alt):
        self.mav.master.mav.command_long_send(
            self.mav.master.target_system,
            self.mav.master.target_component,
            22,  # MAV_CMD_NAV_TAKEOFF
            0,
            0, 0, 0, 0, 0, 0, alt
        )

    def land(self):
        self.mav.master.mav.command_long_send(
            self.mav.master.target_system,
            self.mav.master.target_component,
            21,  # MAV_CMD_NAV_LAND
            0,0,0,0,0,0,0,0
        )