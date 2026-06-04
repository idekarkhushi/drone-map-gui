from __future__ import annotations
import threading
import time
from typing import Callable, Optional
from pymavlink import mavutil

# ─── tunables ─────────────────────────────────────────────────────────────────

LAUNCH_ALTITUDE_DEFAULT = 15.0        # metres AGL
ARM_TIMEOUT             = 10.0        # seconds to wait for arming confirmation
TAKEOFF_CONFIRM_TIMEOUT = 8.0         # seconds to wait for altitude climb start
PREFLIGHT_BATTERY_MIN   = 20          # % – refuse launch below this
PREFLIGHT_GPS_MIN       = 6           # satellites required

class AbortMode:
    RTL   = "RTL"    # Return To Launch  (preferred)
    LAND  = "LAND"   # Land in place
    BRAKE = "BRAKE"  # Brake / loiter (multirotor)

# ═══════════════════════════════════════════════════════════════════════════════
#  ACTION HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

class ActionHandler:
    # ── callbacks (assign before calling launch / abort) ──────────────────────
    on_launch_status: Optional[Callable[[str, bool], None]] = None
    on_abort_status: Optional[Callable[[str, bool], None]] = None
    on_state_change: Optional[Callable[[str], None]] = None
    
    # ── init ──────────────────────────────────────────────────────────────────

    def __init__(self) -> None:
        self.master: Optional[mavutil.mavudp] = None
        self._lock = threading.Lock()

        # public readable state
        self.state: str = "IDLE"
        self.abort_mode: str = AbortMode.RTL

        # internal
        self._launch_thread: Optional[threading.Thread] = None
        self._abort_thread:  Optional[threading.Thread] = None

    # ── connection ────────────────────────────────────────────────────────────

    def attach_connection(self, master) -> None:
        """Share the pymavlink master already opened by ConnectPanel / GCSApp."""
        self.master = master

    def connect(
        self,
        connection_string: str = "udp:127.0.0.1:14550",
        baudrate: int = 57600,
        timeout: int = 5,
    ) -> bool:
        """Open a dedicated connection (useful for standalone testing)."""
        try:
            self.master = mavutil.mavlink_connection(connection_string, baud=baudrate)
            self.master.wait_heartbeat(timeout=timeout)
            print(f"[Actions] Connected → {connection_string}")
            return True
        except Exception as exc:
            print(f"[Actions] Connection failed: {exc}")
            self.master = None
            return False

    # ── public API ────────────────────────────────────────────────────────────

    def launch(self, target_altitude: float = LAUNCH_ALTITUDE_DEFAULT) -> None:
        """
        Non-blocking.  Spawns the launch sequence in a daemon thread.
        No-op if already in a non-idle state.
        """
        with self._lock:
            if self.state not in ("IDLE", "ERROR", "ABORTED"):
                self._emit_launch(f"Cannot launch — current state: {self.state}", False)
                return
            self._set_state("PRE_FLIGHT")

        self._launch_thread = threading.Thread(
            target=self._launch_sequence,
            args=(target_altitude,),
            daemon=True,
        )
        self._launch_thread.start()

    def abort(self) -> None:
        with self._lock:
            if self.state in ("IDLE", "ABORTED", "ABORTING"):
                self._emit_abort(f"Nothing to abort — state: {self.state}", False)
                return
            self._set_state("ABORTING")

        self._abort_thread = threading.Thread(
            target=self._abort_sequence,
            daemon=True,
        )
        self._abort_thread.start()

    def reset(self) -> None:
        """Return handler to IDLE so a fresh launch can be attempted."""
        with self._lock:
            self._set_state("IDLE")

    # ── launch sequence ───────────────────────────────────────────────────────

    def _launch_sequence(self, target_altitude: float) -> None:
        try:
            # ── 1. Pre-flight checks ──────────────────────────────────────────
            self._emit_launch("Running pre-flight checks…", True)
            ok, reason = self._preflight_checks()
            if not ok:
                self._emit_launch(f"Pre-flight FAIL: {reason}", False)
                self._set_state("ERROR")
                return

            if self._is_aborting():
                return

            self._emit_launch("Pre-flight checks passed ✓", True)

            # ── 2. Set AUTO mode ──────────────────────────────────────────────
            self._emit_launch("Setting flight mode → AUTO…", True)
            if not self._set_mode("AUTO"):
                self._emit_launch("Failed to set AUTO mode", False)
                self._set_state("ERROR")
                return

            if self._is_aborting():
                return

            # ── 3. Arm ────────────────────────────────────────────────────────
            self._set_state("ARMING")
            self._emit_launch("Arming motors…", True)
            if not self._arm_vehicle():
                self._emit_launch("Arming failed — check pre-arm messages", False)
                self._set_state("ERROR")
                return

            if self._is_aborting():
                self._disarm_vehicle()
                return

            # ── 4. Takeoff ────────────────────────────────────────────────────
            self._set_state("TAKING_OFF")
            self._emit_launch(f"Sending TAKEOFF → {target_altitude:.1f} m…", True)
            if not self._send_takeoff(target_altitude):
                self._emit_launch("Takeoff command rejected", False)
                self._disarm_vehicle()
                self._set_state("ERROR")
                return

            if self._is_aborting():
                return

            # ── 5. Confirm climb ──────────────────────────────────────────────
            self._emit_launch("Confirming climb…", True)
            climbing = self._wait_for_climb()
            if not climbing:
                self._emit_launch("No altitude gain detected — check vehicle", False)
                self._set_state("ERROR")
                return

            self._set_state("AIRBORNE")
            self._emit_launch(
                f"AIRBORNE ✓  Target: {target_altitude:.1f} m", True
            )

        except Exception as exc:
            self._emit_launch(f"Launch exception: {exc}", False)
            self._set_state("ERROR")

    # ── abort sequence ────────────────────────────────────────────────────────

    def _abort_sequence(self) -> None:
        try:
            self._emit_abort("ABORT initiated…", True)

            if self.abort_mode == AbortMode.RTL:
                self._emit_abort("Setting mode → RTL…", True)
                ok = self._set_mode("RTL")
            elif self.abort_mode == AbortMode.LAND:
                self._emit_abort("Setting mode → LAND…", True)
                ok = self._set_mode("LAND")
            elif self.abort_mode == AbortMode.BRAKE:
                self._emit_abort("Setting mode → BRAKE…", True)
                ok = self._set_mode("BRAKE")
            else:
                ok = False

            if not ok:
                # Last resort: disarm
                self._emit_abort("Mode change failed — DISARMING immediately", False)
                self._disarm_vehicle()
                self._set_state("ABORTED")
                self._emit_abort("Vehicle disarmed. ABORT complete.", False)
                return

            self._set_state("LANDING")
            self._emit_abort(f"ABORT complete — mode: {self.abort_mode}", True)

        except Exception as exc:
            self._emit_abort(f"Abort exception: {exc}", False)
            self._set_state("ERROR")

    # ── pre-flight checks ─────────────────────────────────────────────────────

    def _preflight_checks(self) -> tuple[bool, str]:
        if self.master is None:
            return False, "No MAVLink connection"

        msgs = getattr(self.master, "messages", {})

        # --- Heartbeat present ---
        hb = msgs.get("HEARTBEAT")
        if hb is None:
            # Try blocking read for up to 3 s
            hb = self.master.recv_match(type="HEARTBEAT", blocking=True, timeout=3)
        if hb is None:
            return False, "No heartbeat from vehicle"

        # --- Battery ---
        sys_st = msgs.get("SYS_STATUS")
        if sys_st is not None:
            pct = sys_st.battery_remaining
            if 0 <= pct < PREFLIGHT_BATTERY_MIN:
                return False, f"Battery too low ({pct}% < {PREFLIGHT_BATTERY_MIN}%)"

        # --- GPS ---
        gps = msgs.get("GPS_RAW_INT")
        if gps is not None:
            if gps.fix_type < 3:
                return False, f"GPS fix insufficient (fix_type={gps.fix_type})"
            if gps.satellites_visible < PREFLIGHT_GPS_MIN:
                return False, (
                    f"Too few satellites ({gps.satellites_visible} "
                    f"< {PREFLIGHT_GPS_MIN})"
                )

        # --- EKF ---
        ekf = msgs.get("EKF_STATUS_REPORT")
        if ekf is not None:
            BAD = (
                mavutil.mavlink.EKF_UNINITIALIZED |
                mavutil.mavlink.EKF_CONST_POS_MODE
            )
            if ekf.flags & BAD:
                return False, f"EKF not healthy (flags=0x{ekf.flags:04x})"

        return True, ""

    # ── MAVLink helpers ───────────────────────────────────────────────────────

    def _set_mode(self, mode_name: str) -> bool:
        """Set an ArduPilot flight mode by name. Returns True on ACK."""
        if self.master is None:
            return False

        try:
            mode_id = self.master.mode_mapping().get(mode_name)
            if mode_id is None:
                print(f"[Actions] Unknown mode: {mode_name}")
                return False

            self.master.mav.set_mode_send(
                self.master.target_system,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                mode_id,
            )

            # Wait for HEARTBEAT confirming the new mode
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                msg = self.master.recv_match(
                    type="HEARTBEAT", blocking=True, timeout=1.0
                )
                if msg and msg.custom_mode == mode_id:
                    return True
            return False

        except Exception as exc:
            print(f"[Actions] _set_mode error: {exc}")
            return False

    def _arm_vehicle(self) -> bool:
        """Send ARM command and wait for confirmation."""
        if self.master is None:
            return False
        try:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0,     # confirmation
                1,     # param1: 1=arm
                0, 0, 0, 0, 0, 0,
            )

            deadline = time.monotonic() + ARM_TIMEOUT
            while time.monotonic() < deadline:
                if self._is_aborting():
                    return False
                msg = self.master.recv_match(
                    type=["COMMAND_ACK", "HEARTBEAT"],
                    blocking=True,
                    timeout=1.0,
                )
                if msg is None:
                    continue

                if msg.get_type() == "COMMAND_ACK":
                    if (msg.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM
                            and msg.result == mavutil.mavlink.MAV_RESULT_ACCEPTED):
                        return True
                    elif msg.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
                        print(f"[Actions] ARM rejected: result={msg.result}")
                        return False

                elif msg.get_type() == "HEARTBEAT":
                    # ArduPilot sets MAV_MODE_FLAG_SAFETY_ARMED when armed
                    armed = bool(
                        msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                    )
                    if armed:
                        return True

            return False

        except Exception as exc:
            print(f"[Actions] _arm_vehicle error: {exc}")
            return False

    def _disarm_vehicle(self) -> bool:
        """Force-disarm (used in abort / error recovery)."""
        if self.master is None:
            return False
        try:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0,
                0,       # param1: 0=disarm
                21196,   # param2: magic number for force-disarm
                0, 0, 0, 0, 0,
            )
            time.sleep(0.5)
            return True
        except Exception as exc:
            print(f"[Actions] _disarm_vehicle error: {exc}")
            return False

    def _send_takeoff(self, altitude: float) -> bool:
        """Send MAV_CMD_NAV_TAKEOFF and wait for ACK."""
        if self.master is None:
            return False
        try:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                0,
                0, 0, 0, 0,   # params 1-4 unused
                0.0, 0.0,     # lat, lon (0 = use current)
                altitude,     # altitude AGL in metres
            )

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                msg = self.master.recv_match(
                    type="COMMAND_ACK", blocking=True, timeout=1.0
                )
                if msg and msg.command == mavutil.mavlink.MAV_CMD_NAV_TAKEOFF:
                    return msg.result == mavutil.mavlink.MAV_RESULT_ACCEPTED
            return False

        except Exception as exc:
            print(f"[Actions] _send_takeoff error: {exc}")
            return False

    def _wait_for_climb(self) -> bool:
        """Return True if the vehicle starts climbing within TAKEOFF_CONFIRM_TIMEOUT."""
        if self.master is None:
            return False
        deadline = time.monotonic() + TAKEOFF_CONFIRM_TIMEOUT
        while time.monotonic() < deadline:
            if self._is_aborting():
                return False
            msg = self.master.recv_match(
                type="VFR_HUD", blocking=True, timeout=1.0
            )
            if msg and msg.climb > 0.3:    # climbing faster than 0.3 m/s
                return True
        return False

    # ── internal state helpers ────────────────────────────────────────────────

    def _set_state(self, new_state: str) -> None:
        self.state = new_state
        print(f"[Actions] State → {new_state}")
        if self.on_state_change:
            self.on_state_change(new_state)

    def _is_aborting(self) -> bool:
        return self.state in ("ABORTING", "ABORTED")

    def _emit_launch(self, message: str, ok: bool) -> None:
        print(f"[Actions][LAUNCH] {message}")
        if self.on_launch_status:
            self.on_launch_status(message, ok)

    def _emit_abort(self, message: str, ok: bool) -> None:
        print(f"[Actions][ABORT] {message}")
        if self.on_abort_status:
            self.on_abort_status(message, ok)