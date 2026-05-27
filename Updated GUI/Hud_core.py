from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from typing import Optional

# ── Colour constants ──────────────────────────────────────────────────────────
HUD_COLOR   = "#00d4ff"
SKY_TOP     = "#0d2b52"
SKY_BOT     = "#1f4f88"
GND_TOP     = "#586d0b"
GND_BOT     = "#2e3906"
SEMI_BLACK  = "#09131d"
OUTLINE_COL = "#1f3d55"

GPS_LABELS = {
    0: "No GPS",
    1: "No Fix",
    2: "2D Fix",
    3: "3D Fix",
    4: "DGPS",
    5: "RTK Float",
    6: "RTK Fixed",
}
GPS_COLORS = {0: "#c41212", 1: "#c41212", 2: HUD_COLOR, 3: "#00ff88",
              4: "#00ff88", 5: "#00ff88", 6: "#00ff88"}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ─────────────────────────────────────────────────────────────────────────────
# HUDState  – all telemetry + display-toggle fields in one place
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class HUDState:
    # ── primary attitude ──────────────────────────────────────────────────────
    roll:    float = 0.0
    pitch:   float = 0.0
    heading: float = 0.0

    # ── nav targets ───────────────────────────────────────────────────────────
    navroll:       float = 0.0
    navpitch:      float = 0.0
    targetheading: float = 0.0
    groundcourse:  float = 0.0

    # ── speed / altitude ──────────────────────────────────────────────────────
    airspeed:     float = 0.0
    groundspeed:  float = 0.0
    targetspeed:  float = 0.0
    lowairspeed:  bool  = False
    lowgroundspeed: bool = False
    alt:          float = 0.0
    targetalt:    float = 0.0
    groundalt:    float = 0.0
    verticalspeed: float = 0.0

    # ── battery ───────────────────────────────────────────────────────────────
    batterylevel:       float = 0.0
    batterylevel2:      float = 0.0
    batteryremaining:   float = 0.0
    batteryremaining2:  float = 0.0
    current:            float = 0.0
    current2:           float = 0.0
    batterycellcount:   int   = 0
    lowvoltagealert:    bool  = False
    criticalvoltagealert: bool = False

    # ── GPS ───────────────────────────────────────────────────────────────────
    gpsfix:  float = 0.0
    gpshdop: float = 0.0
    gpsfix2: float = 0.0
    gpshdop2: float = 0.0

    # ── nav / mission ─────────────────────────────────────────────────────────
    xtrack_error: float = 0.0
    turnrate:     float = 0.0
    disttowp:     float = 0.0
    wpno:         int   = 0
    mode:         str   = "Manual"
    linkqualitygcs: float = 0.0

    # ── EKF / vibe / prearm ───────────────────────────────────────────────────
    vibex: float = 0.0
    vibey: float = 0.0
    vibez: float = 0.0
    ekfstatus:    float = 0.0
    prearmstatus: bool  = False

    # ── AOA / SSA ─────────────────────────────────────────────────────────────
    AOA:      float = 0.0
    SSA:      float = 0.0
    critAOA:  float = 25.0
    critSSA:  float = 30.0
    redSSAp:    float = 90.0
    yellowSSAp: float = 60.0
    greenSSAp:  float = 10.0

    # ── vehicle status ────────────────────────────────────────────────────────
    status:       bool  = False   # True = armed
    safetyactive: bool  = False
    failsafe:     bool  = False
    connected:    bool  = True
    load:         float = 0.0
    message:      str   = ""
    message_color: str  = "white"

    # ── units ─────────────────────────────────────────────────────────────────
    distunit:  str = "m"
    speedunit: str = "m/s"
    altunit:   str = "m"

    # ── display toggles ───────────────────────────────────────────────────────
    displayheading:   bool = True
    displayspeed:     bool = True
    displayalt:       bool = True
    displayconninfo:  bool = True
    displayxtrack:    bool = True
    displayrollpitch: bool = True
    displaygps:       bool = True
    bgon:             bool = True
    batteryon:        bool = True
    batteryon2:       bool = True
    displayekf:       bool = True
    displayvibe:      bool = True
    displayprearm:    bool = True
    displayAOASSA:    bool = False
    displayCellVoltage: bool = False

    # ── internal timestamps (set by renderer) ─────────────────────────────────
    _mode_changed_time: float = field(default=0.0, repr=False)
    _armed_time:        float = field(default=0.0, repr=False)
    _last_status:       bool  = field(default=False, repr=False)

    def set_mode(self, mode: str):
        if mode != self.mode:
            self.mode = mode
            self._mode_changed_time = time.time()


# ─────────────────────────────────────────────────────────────────────────────
# HUDRenderer  – stateless painter; call render(canvas, state, W, H)
# ─────────────────────────────────────────────────────────────────────────────
class HUDRenderer:
    """
    Call ``HUDRenderer.render(canvas, state, W, H)`` to repaint.
    All draw helpers are static / class methods so no instance is needed,
    but you may instantiate it for convenience.
    """

    # ── entry point ───────────────────────────────────────────────────────────
    @classmethod
    def render(cls, canvas, state: HUDState, W: int, H: int):
        """Clear *canvas* and repaint the full HUD from *state*."""
        canvas.delete("all")

        if W < 60 or H < 40:
            return

        roll  = state.roll  if not math.isnan(state.roll)  else 0.0
        pitch = state.pitch if not math.isnan(state.pitch) else 0.0
        hdg   = state.heading if not math.isnan(state.heading) else 0.0
        is_nan = (math.isnan(state.roll) or math.isnan(state.pitch)
                  or math.isnan(state.heading))

        halfW = W // 2
        halfH = H // 2
        fs    = max(7, H // 30)                 # base font size
        tape_w   = max(28, int(W * 0.13))       # speed / alt tape width
        heading_h = max(18, int(H * 0.12))      # heading band height

        every5 = -(H / 65.0)
        pitchoff = -pitch * every5

        hud_col = HUD_COLOR if state.connected else "#888888"

        # ── layers (paint order) ─────────────────────────────────────────────
        if state.bgon:
            cls._horizon(canvas, W, H, halfW, halfH, roll, pitchoff)

        if state.displayrollpitch:
            cls._pitch_ladder(canvas, W, H, halfW, halfH,
                              roll, pitch, pitchoff, every5, fs, hud_col)
            cls._roll_arc(canvas, W, H, halfW, halfH, roll, fs, hud_col)
            cls._aircraft_symbol(canvas, halfW, halfH, roll, state.Russian
                                 if hasattr(state, "Russian") else False)

        if state.displayAOASSA:
            cls._fpv(canvas, halfW, halfH, every5, state)

        head_h = H // 14
        if state.displayheading:
            cls._heading_tape(canvas, W, H, head_h, hdg, state, fs, hud_col)

        if state.displayxtrack:
            cls._xtrack(canvas, W, H, head_h, state, fs, hud_col)

        sb_top = halfH - halfH // 2
        sb_h   = H // 2
        if state.displayspeed:
            cls._speed_tape(canvas, 0, sb_top, tape_w, sb_h, state, fs, hud_col)
        if state.displayalt:
            cls._alt_tape(canvas, W - tape_w, sb_top, tape_w, sb_h,
                          state, fs, hud_col)
            cls._mode_wp(canvas, W - tape_w, sb_top + sb_h, state, fs, hud_col)

        if state.displayconninfo:
            cls._conn_info(canvas, W - tape_w, sb_top, state, fs, hud_col)

        if state.displayAOASSA:
            cls._aoa_tape(canvas, W, H, halfH, state)

        # ── bottom status row ────────────────────────────────────────────────
        y_gap = fs + 4
        yBot  = H - 2 * y_gap - 4
        yBot2 = H - y_gap - 4
        xPos  = fs

        if state.batteryon:
            cls._battery(canvas, xPos, yBot, yBot2, state, fs)

        if state.displaygps:
            cls._gps(canvas, W, yBot, yBot2, state, fs)

        if state.displayvibe:
            cls._vibe(canvas, W - 18 * fs, yBot2, state, fs, hud_col)

        if state.displayekf:
            cls._ekf(canvas, W - 23 * fs, yBot2, state, fs, hud_col)

        cls._centre_overlays(canvas, halfW, halfH, W, H, state, fs)

        if is_nan:
            canvas.create_text(halfW, halfH + 30, text="⚠ NaN",
                               fill="#c41212",
                               font=("Courier", fs + 4, "bold"))

    # =========================================================================
    #  HORIZON
    # =========================================================================
    @staticmethod
    def _horizon(canvas, W, H, halfW, halfH, roll, pitchoff):
        angle = math.radians(-roll)
        cos_r, sin_r = math.cos(angle), math.sin(angle)
        diag = int(math.sqrt(W * W + H * H)) + 10

        def rot(px, py):
            tx, ty = px - halfW, py - halfH
            return (tx * cos_r - ty * sin_r + halfW,
                    tx * sin_r + ty * cos_r + halfH)

        # Sky gradient (6 strips)
        for i in range(6):
            t0, t1 = i / 6, (i + 1) / 6
            y0 = halfH + pitchoff - diag * (1 - t0)
            y1_s = halfH + pitchoff - diag * (1 - t1)
            r_ = int(13  + (31  - 13)  * t0)
            g_ = int(43  + (79  - 43)  * t0)
            b_ = int(82  + (136 - 82)  * t0)
            col = f"#{r_:02x}{g_:02x}{b_:02x}"
            pts = [rot(halfW - diag, y0), rot(halfW + diag, y0),
                   rot(halfW + diag, y1_s), rot(halfW - diag, y1_s)]
            canvas.create_polygon([v for p in pts for v in p],
                                  fill=col, outline="")

        # Ground gradient (6 strips)
        for i in range(6):
            t0 = i / 6
            y0 = halfH + pitchoff + diag * i / 6
            y1_g = halfH + pitchoff + diag * (i + 1) / 6
            r_ = int(88  - (88  - 46)  * t0)
            g_ = int(109 - (109 - 57)  * t0)
            b_ = int(11  - (11  - 6)   * t0)
            col = f"#{r_:02x}{g_:02x}{b_:02x}"
            pts = [rot(halfW - diag, y0), rot(halfW + diag, y0),
                   rot(halfW + diag, y1_g), rot(halfW - diag, y1_g)]
            canvas.create_polygon([v for p in pts for v in p],
                                  fill=col, outline="")

        # Horizon line
        lx1, ly1 = rot(halfW - diag, halfH + pitchoff)
        lx2, ly2 = rot(halfW + diag, halfH + pitchoff)
        canvas.create_line(lx1, ly1, lx2, ly2, fill="#00d4ff", width=2)

    # =========================================================================
    #  PITCH LADDER
    # =========================================================================
    @staticmethod
    def _pitch_ladder(canvas, W, H, halfW, halfH,
                      roll, pitch, pitchoff, every5, fs, hud_col):
        angle = math.radians(-roll)
        cos_r, sin_r = math.cos(angle), math.sin(angle)
        llong  = W // 10
        lshort = W // 14

        def rot(px, py):
            tx, ty = px - halfW, py - halfH
            return (tx * cos_r - ty * sin_r + halfW,
                    tx * sin_r + ty * cos_r + halfH)

        for a in range(-90, 91, 5):
            if not (pitch - 29 <= a <= pitch + 20):
                continue
            y = halfH + pitchoff + a * every5
            if a % 10 == 0:
                col = "#00ff66" if a == 0 else hud_col
                lw  = llong
                x1r, y1r = rot(halfW - lw, y)
                x2r, y2r = rot(halfW + lw, y)
                canvas.create_line(x1r, y1r, x2r, y2r, fill=col, width=2)
                lx, ly = rot(halfW - lw - 28, y - 6)
                canvas.create_text(lx, ly, text=str(a),
                                   fill=hud_col,
                                   font=("Courier", max(7, fs - 1)),
                                   anchor="e")
            else:
                x1r, y1r = rot(halfW - lshort, y)
                x2r, y2r = rot(halfW + lshort, y)
                canvas.create_line(x1r, y1r, x2r, y2r, fill=hud_col, width=1)

    # =========================================================================
    #  ROLL ARC
    # =========================================================================
    @staticmethod
    def _roll_arc(canvas, W, H, halfW, halfH, roll, fs, hud_col):
        extra  = int(H / 15.0 * 4.9)
        llong  = H // 66
        radius = llong * 3 + extra

        start_angle = 90 + 30 + roll
        canvas.create_arc(halfW - radius, halfH - radius,
                          halfW + radius, halfH + radius,
                          start=start_angle - 60, extent=120,
                          style="arc", outline=hud_col, width=2)

        for a in [-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60]:
            ar = math.radians(-(90 + a - roll))
            x1 = halfW + radius * math.cos(ar)
            y1 = halfH + radius * math.sin(ar)
            x2 = halfW + (radius + llong) * math.cos(ar)
            y2 = halfH + (radius + llong) * math.sin(ar)
            canvas.create_line(x1, y1, x2, y2, fill=hud_col, width=2)
            lx = halfW + (radius + llong + 8) * math.cos(ar)
            ly = halfH + (radius + llong + 8) * math.sin(ar)
            canvas.create_text(lx, ly, text=str(abs(a)),
                               fill=hud_col,
                               font=("Courier", max(6, fs - 2)))

        # needle triangle
        nr    = radius - llong * 2
        ar0   = math.radians(-(90 - roll))
        tip_x = halfW + nr * math.cos(ar0)
        tip_y = halfH + nr * math.sin(ar0)
        b_r   = llong + 2
        ar1   = math.radians(-(90 - roll) + 15)
        ar2   = math.radians(-(90 - roll) - 15)
        b1x = halfW + (nr + b_r * 2) * math.cos(ar1)
        b1y = halfH + (nr + b_r * 2) * math.sin(ar1)
        b2x = halfW + (nr + b_r * 2) * math.cos(ar2)
        b2y = halfH + (nr + b_r * 2) * math.sin(ar2)
        w = 4 if abs(roll) > 45 else 2
        canvas.create_polygon(tip_x, tip_y, b1x, b1y, b2x, b2y,
                              outline="#c41212", fill="", width=w)

    # =========================================================================
    #  AIRCRAFT SYMBOL (wings + centre dot)
    # =========================================================================
    @staticmethod
    def _aircraft_symbol(canvas, halfW, halfH, roll, russian=False):
        angle = math.radians(-roll) if russian else 0.0
        cos_r, sin_r = math.cos(angle), math.sin(angle)
        hw = halfW // 2

        def rpt(px, py):
            return (px * cos_r - py * sin_r + halfW,
                    px * sin_r + py * cos_r + halfH)

        hh = halfW // 10
        # left wing
        ax, ay = rpt(-hw - hw // 5, 0);  bx, by = rpt(-hw, 0)
        canvas.create_line(ax, ay, bx, by, fill="#c41212", width=4)
        # right wing
        ax, ay = rpt(hw, 0);  bx, by = rpt(hw + hw // 5, 0)
        canvas.create_line(ax, ay, bx, by, fill="#c41212", width=4)
        # v-marks
        ax, ay = rpt(-1, 0);  bx, by = rpt(hw - hw // 3, hh)
        canvas.create_line(ax, ay, bx, by, fill="#c41212", width=4)
        ax, ay = rpt(1, 0);   bx, by = rpt(-hw + hw // 3, hh)
        canvas.create_line(ax, ay, bx, by, fill="#c41212", width=4)
        # centre dot
        canvas.create_oval(halfW - 4, halfH - 4, halfW + 4, halfH + 4,
                           fill="#00d4ff", outline="")

    # =========================================================================
    #  FLIGHT PATH VECTOR (AOA/SSA)
    # =========================================================================
    @staticmethod
    def _fpv(canvas, halfW, halfH, every5, state: HUDState):
        r  = halfW // 20
        cx = halfW - state.SSA * every5
        cy = halfH - state.AOA * every5
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                           outline="#c41212", width=2)
        canvas.create_line(cx - 2 * r, cy, cx - r, cy, fill="#c41212", width=2)
        canvas.create_line(cx + r, cy, cx + 2 * r, cy, fill="#c41212", width=2)
        canvas.create_line(cx, cy - 2 * r, cx, cy - r, fill="#c41212", width=2)

    # =========================================================================
    #  HEADING TAPE
    # =========================================================================
    @staticmethod
    def _heading_tape(canvas, W, H, band_h, hdg,
                      state: HUDState, fs, hud_col):
        canvas.create_rectangle(0, 0, W, band_h,
                                fill="#000000", outline=hud_col, width=1)
        canvas.create_line(5, band_h - 5, W - 5, band_h - 5,
                           fill=hud_col, width=1)

        space = (W - 10) / 120.0
        start = round(hdg - 60)

        for a in range(start, int(hdg + 61)):
            xa   = 5 + space * (a - start)
            disp = int((a + 3600)) % 360

            # target heading
            if disp == int(state.targetheading) % 360:
                canvas.create_line(xa, 0, xa, band_h,
                                   fill="#00ff00", width=5)
            # ground course
            if disp == int(state.groundcourse) % 360:
                canvas.create_line(xa, 0, xa, band_h,
                                   fill="black", width=4)

            if a % 15 == 0:
                canvas.create_line(xa, band_h - 5, xa, band_h - 12,
                                   fill=hud_col, width=2)
                labels = {0: "N", 45: "NE", 90: "E", 135: "SE",
                          180: "S", 225: "SW", 270: "W", 315: "NW"}
                lbl = labels.get(disp, str(disp))
                canvas.create_text(xa, band_h - 20, text=lbl,
                                   fill=hud_col,
                                   font=("Courier", max(7, fs - 1)))
            elif a % 5 == 0:
                canvas.create_line(xa, band_h - 5, xa, band_h - 9,
                                   fill=hud_col, width=1)

        # centre readout box
        box_w = fs * 4
        bx = W // 2 - box_w // 2
        canvas.create_rectangle(bx, 0, bx + box_w, band_h,
                                fill="white", stipple="gray50", outline="")
        canvas.create_text(W // 2, band_h // 2,
                           text=f"{int(hdg) % 360:03d}°",
                           fill="black",
                           font=("Courier", fs, "bold"))

    # =========================================================================
    #  XTRACK + TURN RATE
    # =========================================================================
    @staticmethod
    def _xtrack(canvas, W, H, head_h, state: HUDState, fs, hud_col):
        xtspace = W / 10.0 / 3.0
        bx      = W // 10
        top_y   = head_h + 5
        bot_y   = head_h + H // 10

        for off in [-2, -1, 0, 1, 2]:
            pad = 4 if off != 0 else 0
            canvas.create_line(bx + off * xtspace, top_y + pad,
                               bx + off * xtspace, bot_y - pad,
                               fill=hud_col, width=1 if off != 0 else 2)

        xe  = _clamp(state.xtrack_error, -40, 40)
        loc = xe / 20.0 * xtspace
        col = "#007f00" if abs(xe) == 40 else "#00ff00"
        canvas.create_line(bx + loc, top_y, bx + loc, bot_y,
                           fill=col, width=3)

        # turn-rate bar
        tr_y   = bot_y + 8
        tr_w   = xtspace * 5
        tr_rng = 12.0
        tr     = _clamp(state.turnrate, -tr_rng / 2, tr_rng / 2)
        trloc  = tr / tr_rng * tr_w

        for seg in [-1, 0, 1]:
            canvas.create_line(bx + seg * xtspace * 2 - xtspace / 2, tr_y,
                               bx + seg * xtspace * 2 + xtspace / 2, tr_y,
                               fill=hud_col, width=2)
        col2 = "#007f00" if abs(tr) == tr_rng / 2 else "#00ff00"
        canvas.create_line(bx + trloc - xtspace / 2, tr_y + 3,
                           bx + trloc + xtspace / 2, tr_y + 3,
                           fill=col2, width=3)
        canvas.create_line(bx + trloc, tr_y + 3, bx + trloc, tr_y + 9,
                           fill=col2, width=2)

    # =========================================================================
    #  SPEED TAPE (left)
    # =========================================================================
    @staticmethod
    def _speed_tape(canvas, sx, sy, sw, sh, state: HUDState, fs, hud_col):
        canvas.create_rectangle(sx, sy, sx + sw, sy + sh,
                                fill=SEMI_BLACK, outline=OUTLINE_COL)

        speed = state.airspeed if state.airspeed != 0 else state.groundspeed
        view  = 26.0
        space = sh / view
        start = int(speed - view / 2)

        # out-of-range target marker
        if start > state.targetspeed:
            canvas.create_line(sx, sy, sx + sw, sy,
                               fill="#00aa00", width=5)
        if speed + view / 2 < state.targetspeed:
            canvas.create_line(sx, sy + sh, sx + sw, sy + sh,
                               fill="#00aa00", width=5)

        for a in range(start, int(speed + view / 2) + 1):
            y = sy + sh - (a - start) * space
            if a == int(state.targetspeed) and state.targetspeed:
                canvas.create_line(sx, y, sx + sw, y,
                                   fill="#00ff00", width=4)
            if a % 5 == 0:
                canvas.create_line(sx + sw, y, sx + sw - 9, y,
                                   fill=hud_col, width=2)
                canvas.create_text(sx + 3, y, text=f"{a:4d}",
                                   fill=hud_col,
                                   font=("Courier", max(7, fs - 1)),
                                   anchor="w")

        # centre arrow + readout
        mid_y = sy + sh // 2
        pts = [sx, mid_y - 9,
               sx + sw - 9, mid_y - 9,
               sx + sw - 4, mid_y,
               sx + sw - 9, mid_y + 9,
               sx, mid_y + 9]
        canvas.create_polygon(pts, fill="black", outline=hud_col)
        canvas.create_text(sx + 4, mid_y,
                           text=f"{speed:.0f}{state.speedunit}",
                           fill="white",
                           font=("Courier", max(7, fs - 1), "bold"),
                           anchor="w")

        # sub-labels
        bot = sy + sh
        as_col = "#c41212" if state.lowairspeed else hud_col
        gs_col = "#c41212" if state.lowgroundspeed else hud_col
        canvas.create_text(sx + 2, bot + 4,
                           text=f"AS {state.airspeed:.1f}",
                           fill=as_col,
                           font=("Courier", max(6, fs - 2)), anchor="nw")
        canvas.create_text(sx + 2, bot + fs + 10,
                           text=f"GS {state.groundspeed:.1f}",
                           fill=gs_col,
                           font=("Courier", max(6, fs - 2)), anchor="nw")

    # =========================================================================
    #  ALTITUDE TAPE (right) + VSI wedge
    # =========================================================================
    @staticmethod
    def _alt_tape(canvas, sx, sy, sw, sh, state: HUDState, fs, hud_col):
        canvas.create_rectangle(sx, sy, sx + sw, sy + sh,
                                fill=SEMI_BLACK, outline=OUTLINE_COL)

        view  = 26.0
        space = sh / view
        start = int(state.alt - view / 2)

        # out-of-range target marker
        if start > state.targetalt:
            canvas.create_line(sx, sy, sx + sw, sy,
                               fill="#00aa00", width=5)
        if state.alt + view / 2 < state.targetalt:
            canvas.create_line(sx, sy + sh, sx + sw, sy + sh,
                               fill="#00aa00", width=5)

        for a in range(start, int(state.alt + view / 2) + 1):
            y = sy + sh - (a - start) * space
            if a == round(state.targetalt) and state.targetalt:
                canvas.create_line(sx, y, sx + sw, y,
                                   fill="#00ff00", width=4)
            if a == round(state.groundalt) and state.groundalt:
                canvas.create_rectangle(sx, y, sx + sw, sy + sh,
                                        fill="#c49564", stipple="gray25",
                                        outline="")
            if a % 5 == 0:
                canvas.create_line(sx, y, sx + 9, y,
                                   fill=hud_col, width=2)
                canvas.create_text(sx + 3, y,
                                   text=f"{a:4d}",
                                   fill=hud_col,
                                   font=("Courier", max(7, fs - 1)),
                                   anchor="nw")

        # centre arrow + readout
        mid_y = sy + sh // 2
        pts = [sx + sw, mid_y - 9,
               sx + 9, mid_y - 9,
               sx + 4, mid_y,
               sx + 9, mid_y + 9,
               sx + sw, mid_y + 9]
        canvas.create_polygon(pts, fill="black", outline=hud_col)
        canvas.create_text(sx + sw - 3, mid_y,
                           text=f"{int(state.alt)}{state.altunit}",
                           fill="white",
                           font=("Courier", max(7, fs - 1), "bold"),
                           anchor="e")

        # VSI wedge (to the left of alt tape)
        vsi_x  = sx - sw // 4
        mid_y2 = (sy + sy + sh) / 2.0
        vsi_rng = 12.0
        vs   = _clamp(state.verticalspeed, -vsi_rng / 2, vsi_rng / 2)
        scaled = vs / -vsi_rng * sh

        # outline
        canvas.create_polygon(sx, sy,
                               vsi_x, sy + sw // 4,
                               vsi_x, sy + sh - sw // 4,
                               sx, sy + sh,
                               outline=hud_col, fill="", width=2)
        # fill wedge
        peak = -min(sw // 4, abs(scaled)) if scaled >= 0 else min(sw // 4, abs(scaled))
        canvas.create_polygon(
            sx, mid_y2,
            vsi_x, mid_y2,
            vsi_x, mid_y2 + scaled + peak,
            sx, mid_y2 + scaled,
            fill="blue", outline=""
        )

    # =========================================================================
    #  MODE + WP DIST (below alt tape)
    # =========================================================================
    @staticmethod
    def _mode_wp(canvas, sx, bot_y, state: HUDState, fs, hud_col):
        now = time.time()
        mode_col = "#c41212" if (now - state._mode_changed_time) < 2.0 else hud_col
        canvas.create_text(sx - 28, bot_y + 4,
                           text=state.mode,
                           fill=mode_col,
                           font=("Courier", fs), anchor="nw")

        dist, dunit = state.disttowp, state.distunit
        if dist >= 1000:
            dunit = "km" if dunit == "m" else "mi"
            dist  = round(dist / (1000 if dunit == "km" else 5280), 1)
        else:
            dist = int(dist)

        canvas.create_text(sx - 28, bot_y + fs + 12,
                           text=f"{dist}{dunit} ▶ WP{state.wpno}",
                           fill=hud_col,
                           font=("Courier", fs), anchor="nw")

    # =========================================================================
    #  CONN INFO (link quality + clock)
    # =========================================================================
    @staticmethod
    def _conn_info(canvas, sx, sb_top, state: HUDState, fs, hud_col):
        import datetime
        lq  = state.linkqualitygcs
        y   = sb_top - fs * 3 - 18

        thresholds = [(80, 3), (50, 2), (20, 1)]
        for thresh, bar_idx in thresholds:
            if lq > thresh:
                bx = sx - bar_idx * 5 - 5
                canvas.create_line(bx, y + 10, bx, y + 18 + bar_idx * 3,
                                   fill="#00ff00", width=3)

        canvas.create_text(sx, y, text=f"{int(lq)}%",
                           fill=hud_col,
                           font=("Courier", fs), anchor="nw")
        if lq == 0:
            canvas.create_line(sx, y, sx + 48, y + 18, fill="#c41212", width=2)
            canvas.create_line(sx, y + 18, sx + 48, y, fill="#c41212", width=2)

        canvas.create_text(sx - 28, sb_top - fs - 20,
                           text=datetime.datetime.now().strftime("%H:%M:%S"),
                           fill=hud_col,
                           font=("Courier", fs), anchor="nw")

    # =========================================================================
    #  AOA TAPE
    # =========================================================================
    @staticmethod
    def _aoa_tape(canvas, W, H, halfH, state: HUDState):
        tw = W // 25
        th = H // 5
        tx = W - W // 6
        ty = halfH + halfH // 10

        red_h    = th * (state.redSSAp - state.yellowSSAp) / 100
        yellow_h = th * (state.yellowSSAp - state.greenSSAp) / 100
        green_h  = th * state.greenSSAp / 100
        blue_h   = th * (100 - state.redSSAp) / 100

        canvas.create_rectangle(tx, ty, tx + tw, ty + blue_h,
                                fill="blue", outline="")
        canvas.create_rectangle(tx, ty + blue_h, tx + tw,
                                ty + blue_h + red_h,
                                fill="#c41212", outline="")
        canvas.create_rectangle(tx, ty + blue_h + red_h,
                                tx + tw, ty + blue_h + red_h + yellow_h,
                                fill="yellow", outline="")
        canvas.create_rectangle(tx, ty + th - green_h, tx + tw, ty + th,
                                fill="#00ff00", outline="")
        canvas.create_rectangle(tx, ty, tx + tw, ty + th,
                                outline="white", fill="")

        pct   = _clamp(state.AOA / max(state.critAOA, 1), 0, 1)
        ind_y = ty + th * (1 - pct)
        asiz  = tw // 2
        canvas.create_polygon(tx + tw // 5, ind_y,
                              tx + tw // 5 - asiz, ind_y + asiz,
                              tx + tw // 5 - asiz, ind_y - asiz,
                              fill="black", outline="white")

    # =========================================================================
    #  BATTERY
    # =========================================================================
    @staticmethod
    def _battery(canvas, xPos, y0, y1, state: HUDState, fs):
        col = ("red" if state.criticalvoltagealert
               else "orange" if state.lowvoltagealert else HUD_COLOR)

        if state.displayCellVoltage and state.batterycellcount:
            cv = state.batterylevel / state.batterycellcount
            canvas.create_text(xPos, y1,
                               text=f"Cell {cv:.2f}v",
                               fill=col,
                               font=("Courier", fs), anchor="nw")
        elif state.batterylevel2 > 0 and state.batteryon2:
            canvas.create_text(xPos, y0,
                               text=(f"Bat2 {state.batterylevel2:.2f}v "
                                     f"{state.current2:.1f}A "
                                     f"{state.batteryremaining2:.0f}%"),
                               fill=col,
                               font=("Courier", fs), anchor="nw")
            canvas.create_text(xPos, y1,
                               text=(f"Bat1 {state.batterylevel:.2f}v "
                                     f"{state.current:.1f}A "
                                     f"{state.batteryremaining:.0f}%"),
                               fill=col,
                               font=("Courier", fs), anchor="nw")
        else:
            canvas.create_text(xPos, y1,
                               text=(f"Bat1 {state.batterylevel:.2f}v "
                                     f"{state.current:.1f}A "
                                     f"{state.batteryremaining:.0f}%"),
                               fill=col,
                               font=("Courier", fs), anchor="nw")

    # =========================================================================
    #  GPS
    # =========================================================================
    @staticmethod
    def _gps(canvas, W, y0, y1, state: HUDState, fs):
        rows = [y1, y0]
        for i, fix in enumerate([state.gpsfix, state.gpsfix2]):
            if i == 1 and fix == 0:
                continue
            key = int(fix)
            lbl = GPS_LABELS.get(key, str(fix))
            col = GPS_COLORS.get(key, HUD_COLOR)
            prefix = "GPS:" if i == 0 else "GPS2:"
            canvas.create_text(W - 14 * fs, rows[i],
                               text=f"{prefix}{lbl}",
                               fill=col,
                               font=("Courier", fs), anchor="nw")

    # =========================================================================
    #  VIBE
    # =========================================================================
    @staticmethod
    def _vibe(canvas, vx, vy, state: HUDState, fs, hud_col):
        vmax = max(state.vibex, state.vibey, state.vibez)
        col  = "red" if vmax > 60 else "orange" if vmax > 30 else hud_col
        lbl  = "Vibe!" if vmax > 60 else "Vibe"
        canvas.create_text(vx, vy, text=lbl, fill=col,
                           font=("Courier", fs + 1, "bold"), anchor="nw")

    # =========================================================================
    #  EKF
    # =========================================================================
    @staticmethod
    def _ekf(canvas, ex, ey, state: HUDState, fs, hud_col):
        col = ("#c41212"    if state.ekfstatus > 0.8 else
               "orange" if state.ekfstatus > 0.5 else hud_col)
        canvas.create_text(ex, ey, text="EKF", fill=col,
                           font=("Courier", fs + 1, "bold"), anchor="nw")

    # =========================================================================
    #  PRE-ARM
    # =========================================================================
    @staticmethod
    def _prearm(canvas, px, py, state: HUDState, fs):
        if state.prearmstatus:
            canvas.create_text(px, py, text="Ready to Arm",
                               fill="white",
                               font=("Courier", fs + 1), anchor="nw")
        else:
            canvas.create_text(px, py, text="Not Ready to Arm",
                               fill="#c41212",
                               font=("Courier", fs + 1), anchor="nw")

    # =========================================================================
    #  CENTRE OVERLAYS (armed / disarmed / failsafe / message)
    # =========================================================================
    @staticmethod
    def _centre_overlays(canvas, halfW, halfH, W, H,
                         state: HUDState, fs):
        now = time.time()

        # track arm transitions
        if state.status != state._last_status:
            state._armed_time = now
        state._last_status = state.status

        if not state.status:
            canvas.create_text(halfW, halfH * 2 // 3,
                               text="DISARMED", fill="#c41212",
                               font=("Courier", fs + 10, "bold"),
                               anchor="center")
            if state.displayprearm:
                prearm_text = "Ready to Arm" if state.prearmstatus else "Not Ready to Arm"
                prearm_color = "white" if state.prearmstatus else "#c41212"
                prearm_y = H - 2 * (fs + 4) - 4
                canvas.create_text(halfW, prearm_y,
                                   text=prearm_text,
                                   fill=prearm_color,
                                   font=("Courier", fs + 1, "bold"),
                                   anchor="center")
            
        elif (now - state._armed_time) < 8:
            canvas.create_text(halfW, halfH * 2 // 3,
                               text="ARMED", fill="#c41212",
                               font=("Courier", fs + 20, "bold"),
                               anchor="center")

        if state.safetyactive:
            canvas.create_text(halfW, halfH + halfH // 3,
                               text="SAFETY", fill="#c41212",
                               font=("Courier", fs + 10, "bold"),
                               anchor="center")

        if state.failsafe:
            canvas.create_text(halfW, halfH,
                               text="FAILSAFE", fill="#c41212",
                               font=("Courier", fs + 20, "bold"),
                               anchor="center")

        if state.message:
            canvas.create_text(halfW, halfH + halfH // 2,
                               text=state.message,
                               fill=state.message_color,
                               font=("Courier", fs + 4), anchor="center")

        if state.load >= 100:
            canvas.create_text(halfW + 50, H - 28,
                               text="CPU!", fill="#b80808",
                               font=("Courier", fs + 2), anchor="nw")
