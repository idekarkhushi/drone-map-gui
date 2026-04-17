from ui.app import MapApp
from ui.geofence_window import GeoFenceWindow
from core.mavlink_handler import MAVLinkHandler
from core.mission_handler import MissionHandler

if __name__ == "__main__":
    app = MapApp()
    app.mainloop()