"""Terminal composition for Orrery; geometry is supplied by astronomy.py.

Linecast supplies colour negotiation, braille graphing, the half-block
framebuffer and its complete real-sky renderer. No images, fonts or network.
"""

from __future__ import annotations

import math
import re
import linecast
from dataclasses import dataclass
from datetime import datetime, timezone

from linecast._graphics import Framebuffer, RESET, fg, bg, lerp
from linecast._braille import build_braille_curve
from linecast.sky import _BRAILLE
from linecast._orrery_astronomy import BODIES, orbit_points, position_at

FIELD = (5, 10, 15)
IVORY = (237, 232, 228)
CYAN = (48, 176, 208)
COPPER = (200, 90, 46)
MUTED = lerp(FIELD, IVORY, 0.58)
DIM = lerp(FIELD, IVORY, 0.36)
RULE = lerp(FIELD, IVORY, 0.12)
BODY_COLORS = {
    "mercury": (171, 164, 155),
    "venus": (218, 190, 136),
    "earth": (102, 183, 212),
    "mars": (210, 112, 79),
    "jupiter": (195, 161, 130),
    "saturn": (217, 195, 149),
    "uranus": (144, 208, 210),
    "neptune": (104, 136, 213),
    "pluto": (169, 147, 135),
}
BODY_BY_ID = {b["id"]: b for b in BODIES}
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


_ENGLISH = {
    "help_footer": "ProDyn.ai",
    "unset_observer": "OBSERVER UNSET",
}


def translate(key, lang="en", fallback=None):
    """Use an explicit English fallback until a complete Orrery table exists."""
    return _ENGLISH.get(key, fallback if fallback is not None else key)


SKY_MODERN_START = datetime(1900, 1, 1, tzinfo=timezone.utc)
SKY_MODERN_END = datetime(2100, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Palette:
    field: tuple[int, int, int]
    ivory: tuple[int, int, int]
    cyan: tuple[int, int, int]
    copper: tuple[int, int, int]
    muted: tuple[int, int, int]
    dim: tuple[int, int, int]
    rule: tuple[int, int, int]
    brand: tuple[int, int, int]
    body_colors: dict


ORRERY_PALETTE = Palette(FIELD, IVORY, CYAN, COPPER, MUTED, DIM, RULE, (94, 145, 190), BODY_COLORS)


def palette_for(theme):
    """Return a per-render palette; never mutate module or terminal globals."""
    if theme == "orrery":
        return ORRERY_PALETTE
    from linecast import _theme

    _theme.ensure_theme_loaded()
    field, ivory = _theme.theme_bg, _theme.theme_fg
    cyan = _theme.ensure_contrast(_theme.themed((48, 176, 208)), field, 3.0)
    copper = _theme.ensure_contrast(_theme.themed((200, 90, 46)), field, 2.5)
    muted = _theme.ensure_contrast(_theme.neutral_tone(0.58), field, 2.5)
    dim = _theme.ensure_contrast(_theme.neutral_tone(0.38), field, 1.8)
    rule = _theme.neutral_tone(0.16)
    brand = _theme.ensure_contrast(_theme.themed((78, 135, 194)), field, 2.5)
    bodies = {key: _theme.themed(color) for key, color in BODY_COLORS.items()}
    return Palette(field, ivory, cyan, copper, muted, dim, rule, brand, bodies)


def plain(text):
    return ANSI.sub("", text)


class Canvas:
    """Fixed-cell, clipped canvas; colour changes are emitted only as needed."""

    def __init__(self, width, height, palette=None):
        self.width, self.height = width, height
        self.palette = palette or ORRERY_PALETTE
        self.cells = [
            [(" ", self.palette.ivory, self.palette.field) for _ in range(width)]
            for _ in range(height)
        ]

    def put(self, x, y, char, ink=None, paper=None):
        ink = self.palette.ivory if ink is None else ink
        paper = self.palette.field if paper is None else paper
        x, y = int(x), int(y)
        if 0 <= x < self.width and 0 <= y < self.height:
            self.cells[y][x] = (char, ink, paper)

    def text(self, x, y, text, ink=None, paper=None):
        for i, char in enumerate(text):
            self.put(x + i, y, char, ink, paper)

    def fill(self, x, y, w, h, ink=None):
        ink = self.palette.field if ink is None else ink
        for row in range(max(0, y), min(self.height, y + h)):
            for col in range(max(0, x), min(self.width, x + w)):
                self.put(col, row, " ", self.palette.ivory, ink)

    def framebuffer(self, x, y, fb):
        for row in range(fb.graph_h):
            for col in range(fb.graph_w):
                top, bot = fb.fb[row * 2][col], fb.fb[row * 2 + 1][col]
                self.put(x + col, y + row, " " if top == bot else "▄", bot, top)

    def lines(self):
        out = []
        for row in self.cells:
            parts = []
            last_ink = last_paper = None
            for char, ink, paper in row:
                if paper != last_paper:
                    parts.append(bg(*paper))
                    last_paper = paper
                if ink != last_ink:
                    parts.append(fg(*ink))
                    last_ink = ink
                parts.append(char)
            out.append("".join(parts) + RESET)
        return out


def display_radius(body, compressed=True, inner=False):
    """Per-orbit display radius; spaced mode preserves each ellipse's shape.

    Equalised orbital lanes are intentionally NOT a physical distance scale.
    A single scale factor per ellipse keeps the real eccentricity and focus.
    """
    if not compressed:
        return body["aAU"]
    index = next(i for i, b in enumerate(BODIES) if b["id"] == body["id"])
    radii = (0.18, 0.27, 0.36, 0.45, 0.56, 0.68, 0.80, 0.92, 1.06)
    return radii[index] / (radii[3] if inner else 1)


def project_orbit(point, body, state, width, height):
    """Project AU geometry into character coordinates and return view depth."""
    extent = (
        (1.25 if state.inner else 1.40) if state.compressed else (1.85 if state.inner else 52.0)
    )
    factor = (
        display_radius(body, state.compressed, state.inner) / body["aAU"]
        if state.compressed
        else 1.0
    )
    x, y, z = (point[axis] * factor for axis in ("x", "y", "z"))
    angle = math.radians(state.rotation)
    x, y = x * math.cos(angle) - y * math.sin(angle), x * math.sin(angle) + y * math.cos(angle)
    inclination = math.radians((70 if height < 18 else 57) if state.tilted else 0)
    vertical = y * math.cos(inclination) + z * math.sin(inclination)
    depth = y * math.sin(inclination) - z * math.cos(inclination)
    # A terminal cell is approximately twice as tall as wide. The orbit is
    # fitted in that physical aspect, not stretched to fill a rectangle.
    scale = (
        min(
            (width - 9) / (2 * extent),
            (height - (1 if height < 18 else 3)) / (extent * (math.cos(inclination) + 0.1)),
        )
        * state.zoom
    )
    return width * 0.5 + x * scale, height * 0.49 - vertical * scale * 0.5, depth


def draw_curve(canvas, points, x0, y0, w, h, color, selected=False, palette=None):
    """Rasterise projected 3-D orbit segments with Linecast's 2×4 braille bits."""
    palette = palette or ORRERY_PALETTE
    FIELD = palette.field
    dots = {}
    for a, b in zip(points, points[1:]):
        ax, ay, az = a
        bx, by, bz = b
        steps = max(1, int(max(abs(bx - ax) * 2, abs(by - ay) * 4)) + 1)
        # Skip wholly off-screen segments; zoomed traces can be very long.
        if max(ax, bx) < 0 or min(ax, bx) >= w or max(ay, by) < 0 or min(ay, by) >= h:
            continue
        for i in range(steps + 1):
            t = i / steps
            px, py = (
                int(math.floor((ax + (bx - ax) * t) * 2)),
                int(math.floor((ay + (by - ay) * t) * 4)),
            )
            col, row = px // 2, py // 4
            if not (0 <= col < w and 0 <= row < h):
                continue
            bits, depth = dots.get((col, row), (0, -math.inf))
            dots[col, row] = (bits | _BRAILLE[px % 2][py % 4], max(depth, az + (bz - az) * t))
    for (col, row), (bits, depth) in dots.items():
        near = 0.5 + 0.5 * math.tanh(depth * 2)
        ink = lerp(FIELD, color, (0.46 + 0.36 * near) if selected else (0.19 + 0.22 * near))
        old, _, _ = canvas.cells[y0 + row][x0 + col]
        if 0x2800 <= ord(old) <= 0x28FF:
            bits |= ord(old) - 0x2800
        canvas.put(x0 + col, y0 + row, chr(0x2800 + bits), ink)


def portrait(body_id, width=24, height=9, palette=None):
    """A deliberately illustrative disc, lit from upper left; not a map.

    Uses Linecast's framebuffer and sub-pixel blending, at equal display size.
    No rendered features are claimed as observed or geographically accurate.
    """
    palette = palette or ORRERY_PALETTE
    FIELD, IVORY, BODY_COLORS = palette.field, palette.ivory, palette.body_colors
    fb = Framebuffer(width, height, bg_color=FIELD)
    base = BODY_COLORS[body_id]
    radius = min(width * 0.39, height * 0.87)
    cx, cy = width * 0.48, height * 0.95
    if body_id == "saturn":
        radius *= 0.73

    # Rings: back half, sphere, then front half.
    def rings(front):
        if body_id != "saturn":
            return
        for y in range(height * 2):
            for x in range(width):
                dx, dy = x - cx, y - cy
                rx = dx * 0.96 + dy * 0.28
                ry = -dx * 0.28 + dy * 0.96
                r = math.hypot(rx, ry * 3.4) / radius
                if 1.35 < r < 2.12 and (ry > 0) == front:
                    if math.hypot(dx, dy) < radius and not front:
                        continue
                    ring = lerp(base, FIELD, 0.72 if 1.77 < r < 1.87 else 0.36)
                    fb.set_pixel(x, y, ring)

    rings(False)
    for y in range(height * 2):
        for x in range(width):
            nx, ny = (x - cx) / radius, (y - cy) / radius
            rr = nx * nx + ny * ny
            if rr > 1:
                continue
            nz = math.sqrt(1 - rr)
            latitude = math.asin(max(-1, min(1, ny)))
            longitude = math.atan2(nx, nz)
            surface = base
            if body_id in ("jupiter", "saturn"):
                band = math.sin(latitude * 24 + 0.3 * math.sin(longitude * 6))
                surface = lerp(base, (118, 80, 60), 0.28 * (0.5 + band * 0.5))
                if (
                    body_id == "jupiter"
                    and ((nx - 0.30) / 0.28) ** 2 + ((ny - 0.30) / 0.13) ** 2 < 1
                ):
                    surface = (172, 102, 76)
            elif body_id == "earth":
                coast = math.sin(longitude * 4 + latitude * 3) + 0.6 * math.cos(
                    latitude * 8 - longitude * 3
                )
                surface = (68, 124, 115) if coast > 0.57 else (57, 126, 173)
                cloud = math.sin(latitude * 15 + longitude * 5) + math.cos(
                    longitude * 12 - latitude * 7
                )
                if cloud > 1.30 or abs(latitude) > 1.14:
                    surface = lerp(surface, IVORY, 0.73)
            elif body_id in ("mercury", "mars"):
                texture = math.sin(longitude * 19 + latitude * 7) * math.cos(latitude * 23)
                surface = lerp(base, (76, 53, 47), (texture + 1) * 0.12)
            light = max(0, -nx * 0.48 - ny * 0.38 + nz * 0.68)
            shade = 0.08 + 0.92 * light
            surface = lerp(FIELD, surface, min(1, shade))
            edge = min(1, (1 - math.sqrt(rr)) * radius + 0.15)
            fb.set_pixel(x, y, surface, edge)
    rings(True)
    return fb


def draw_orbits(canvas, state, x0, y0, w, h, palette=None):
    palette = palette or ORRERY_PALETTE
    CYAN, MUTED, DIM, RULE, COPPER = (
        palette.cyan,
        palette.muted,
        palette.dim,
        palette.rule,
        palette.copper,
    )
    BODY_COLORS = palette.body_colors
    hits = []
    geometry = {}
    ordered = sorted(state.bodies, key=lambda b: b["id"] == state.selected)
    for body in ordered:
        pts = orbit_points(body["id"], state.moment, count=240)
        geometry[body["id"]] = pts
        projected = [project_orbit(p, body, state, w, h) for p in pts]
        draw_curve(
            canvas,
            projected,
            x0,
            y0,
            w,
            h,
            CYAN if body["id"] == state.selected else BODY_COLORS[body["id"]],
            body["id"] == state.selected,
            palette,
        )
    sx, sy = x0 + int(w * 0.5), y0 + int(h * 0.49)
    canvas.put(sx, sy, "☉", COPPER)
    taken = {(sx, sy)}
    projected_bodies = []
    # Selected labels have first claim; all actual markers are reserved first.
    for body in sorted(state.bodies, key=lambda b: b["id"] != state.selected):
        p = position_at(body["id"], state.moment)
        x, y, z = project_orbit(p, body, state, w, h)
        x, y = x0 + round(x), y0 + round(y)
        if x0 <= x < x0 + w and y0 <= y < y0 + h:
            projected_bodies.append((body, x, y, z))
            taken.update((xx, yy) for xx in range(x - 1, x + 2) for yy in range(y, y + 1))
    for body, x, y, _depth in projected_bodies:
        selected = body["id"] == state.selected
        color = CYAN if selected else BODY_COLORS[body["id"]]
        canvas.put(x, y, "●" if selected else "•", color)
        hits.append((body["id"], x, y, 2))
        name = body["name"] if h >= 18 or selected else body["name"][:3]
        if selected:
            name = name.upper()
        candidates = (
            (x + 2, y),
            (x - len(name) - 2, y),
            (x + 1, y - 1),
            (x + 1, y + 1),
            (x - len(name), y - 2),
        )
        for lx, ly in candidates:
            cells = {(i, ly) for i in range(lx - 1, lx + len(name) + 1)}
            if lx < x0 + 1 or lx + len(name) >= x0 + w or ly < y0 or ly >= y0 + h or cells & taken:
                continue
            canvas.text(lx - 1, ly, " " + name + " ", color if selected else MUTED)
            taken.update(cells)
            hits.append((body["id"], lx + len(name) // 2, ly, max(2, len(name) // 2)))
            break
    # Quiet viewport registration marks, not a decorative grid.
    for x in (x0 + 1, x0 + w - 2):
        canvas.put(x, y0 + h // 2, "─", RULE)
    canvas.text(x0 + 2, y0, "HELIOCENTRIC", DIM)
    scale = "SPACED / NOT TO SCALE" if state.compressed else "TRUE AU / DISTANCES"
    canvas.text(x0 + 2, y0 + h - 1, scale, DIM)
    return hits, geometry


def sidebar(canvas, state, x, y, width, height, geometry, palette=None):
    palette = palette or ORRERY_PALETTE
    FIELD, IVORY, CYAN, DIM = palette.field, palette.ivory, palette.cyan, palette.dim
    body = BODY_BY_ID[state.selected]
    p = position_at(state.selected, state.moment)
    canvas.text(x, y, f"{BODIES.index(body) + 1:02d} / SELECTED BODY", CYAN)
    canvas.text(x, y + 2, body["name"].upper(), IVORY)
    disc_h = 8 if height >= 25 else 5
    disc_w = min(width - 1, 24)
    canvas.framebuffer(x, y + 4, portrait(state.selected, disc_w, disc_h, palette))
    yy = y + 4 + disc_h
    canvas.text(x, yy, "ILLUSTRATIVE · NOT TO SCALE", DIM)
    yy += 2
    values = [
        ("SOLAR DISTANCE", f"{p['radiusAU']:.3f} AU"),
        ("ORBITAL PERIOD", f"{body['periodDays']:,.2f} d"),
        ("MEAN RADIUS", f"{body['radiusKm']:,.0f} km"),
        ("ECCENTRICITY", f"{body['eccentricity']:.4f}"),
    ]
    for label, value in values:
        canvas.text(x, yy, label, DIM)
        canvas.text(x, yy + 1, value, IVORY)
        yy += 2
    if yy + 4 < y + height:
        canvas.text(x, yy, "RADIAL PROFILE / ONE ORBIT", DIM)
        pts = geometry.get(state.selected) or orbit_points(state.selected, state.moment, count=120)
        radii = [math.sqrt(p["x"] ** 2 + p["y"] ** 2 + p["z"] ** 2) for p in pts]
        curve = build_braille_curve(radii, width - 2, n_rows=2, pad_frac=0.05)
        for row, cells in enumerate(curve):
            canvas.text(x, yy + 1 + row, "".join(ch for ch, _ in cells), lerp(FIELD, CYAN, 0.7))


def inventory(canvas, state, row, palette=None):
    palette = palette or ORRERY_PALETTE
    CYAN, MUTED, DIM = palette.cyan, palette.muted, palette.dim
    hits = []
    short = canvas.width < 105
    items = [f"{i + 1} {b['name'][:3] if short else b['name']}" for i, b in enumerate(BODIES)]
    used = sum(len(item) for item in items)
    gap = max(1, min(3, (canvas.width - 4 - used) // (len(items) - 1)))
    x = max(2, (canvas.width - used - gap * (len(items) - 1)) // 2)
    for body, item in zip(BODIES, items):
        active = body["id"] == state.selected
        canvas.text(x, row, item, CYAN if active else (MUTED if body in state.bodies else DIM))
        if active:
            canvas.text(x, row - 1, "─" * len(item), CYAN)
        hits.append((body["id"], x + len(item) // 2, row, len(item) // 2 + 1))
        x += len(item) + gap
    return hits


def sky_lines(state, width, height, camera, runtime=None):
    """Embed the actual Linecast sky using only its explicit render API."""
    from linecast import sky

    view = camera.view()
    if runtime is None:
        from linecast._runtime import RuntimeConfig

        runtime = RuntimeConfig(live=False, icons="plain", lang="en", oneline=False)
    result = sky.render(
        state.moment,
        *state.location,
        runtime,
        view,
        fullscreen=False,
        today=state.moment.date(),
        location_label="",
        size=(width, height + 3),
        show_banner=False,
    )
    return result.split("\x00", 1)[0].splitlines()[:height]


def modal(canvas, title, lines, palette=None):
    palette = palette or ORRERY_PALETTE
    FIELD, IVORY, CYAN, MUTED, RULE = (
        palette.field,
        palette.ivory,
        palette.cyan,
        palette.muted,
        palette.rule,
    )
    w = min(canvas.width - 6, max(len(title) + 4, max(map(len, lines), default=0) + 4))
    h = min(canvas.height - 4, len(lines) + 4)
    x, y = (canvas.width - w) // 2, (canvas.height - h) // 2
    canvas.fill(x - 1, y - 1, w + 2, h + 2, FIELD)
    canvas.text(x, y, "─" * w, CYAN)
    canvas.text(x + 2, y, " " + title + " ", CYAN)
    for i, line in enumerate(lines[: h - 3]):
        canvas.text(x + 2, y + 2 + i, line[: w - 4], IVORY if i == 0 else MUTED)
    canvas.text(x, y + h - 1, "─" * w, RULE)
    brand = " ProDyn.ai "
    if w >= len(brand) + 4:
        bx = x + (w - len(brand)) // 2
        canvas.text(bx, y + h - 1, brand, palette.brand)


HELP = [
    "One UTC clock. Two ways to see the solar system.",
    "",
    "Space / p     play or pause in place",
    ", / .         slower / faster     r  reverse",
    "[ / ]         step one day        n  reset to now",
    "Arrows        day step; sky mode: 15 minutes",
    "Tab / 1–9     select body         click  select",
    "+ / - / wheel zoom                0  reset camera",
    "a / d / drag  rotate; sky: look around (WASD)",
    "u             spaced / true AU    i  inner / all",
    "t             tilted / top-down   v  orbit / sky",
    "l             enter LAT,LON       c  sky figures",
    "b             loop date range (off by default)",
    "g             confirm public-IP approximate lookup",
    "m             face the Moon       q  quit",
    "",
    "Orbits: approximate Keplerian elements, not navigation.",
    "Spaced lanes & body discs are not physical size scales.",
    "Sky: Linecast ephemeris + real local star catalogues.",
    "Earth orbit represents the Earth–Moon barycentre.",
    "No lookup unless g is explicitly confirmed. Press any key to return.",
]


def render_frame(
    state,
    width,
    height,
    camera=None,
    *,
    help_open=False,
    location_confirm=False,
    location_text=None,
    location_error="",
    runtime=None,
):
    width, height = max(1, width), max(1, height)
    palette = palette_for(state.theme)
    IVORY, CYAN = palette.ivory, palette.cyan
    MUTED, DIM, RULE = palette.muted, palette.dim, palette.rule
    canvas = Canvas(width, height, palette)
    if width < 60 or height < 20:
        canvas.text(2, 1, "ORRERY", IVORY)
        canvas.text(2, 3, "Please resize to at least 60 × 20.", MUTED)
        canvas.text(2, 5, "Recommended: 80 × 24 or 120 × 40.", DIM)
        canvas.text(2, 7, "q quit · ? help", CYAN)
        canvas.text(2, 9, "LOOP ON" if state.loop else "LOOP OFF", MUTED)
        return "\n".join(canvas.lines()), []
    wide = width >= 106 and height >= 30
    canvas.text(2, 1, "O R R E R Y", IVORY)
    canvas.text(17, 1, "ORBITAL INSTRUMENT" if state.view == "orbit" else "OBSERVATION", DIM)
    clock = state.moment.date().isoformat() + state.moment.strftime("  %H:%M UTC")
    canvas.text(width - len(clock) - 2, 1, clock, MUTED)
    canvas.text(2, 2, "─" * (width - 4), RULE)
    status = (
        "PLAY" if state.playing else "HOLD"
    ) + f"  {'+' if state.direction > 0 else '−'}{state.speed:g} d/s"
    status += "  LOOP" if state.loop else "  BOUNDED"
    canvas.text(2, 3, status, CYAN if state.playing else MUTED)
    if state.view == "orbit":
        modes = (
            f"{'INNER' if state.inner else 'SOLAR SYSTEM'}  /  "
            f"{'TILTED' if state.tilted else 'TOP-DOWN'}  /  {state.zoom:.2f}×"
        )
    else:
        if state.location is None:
            modes = "OBSERVER UNSET"
        else:
            source = "INFERRED / APPROX" if state.location_inferred else "MANUAL SITE"
            modes = f"{state.location[0]:+.3f}°, {state.location[1]:+.3f}°  /  {source}"
    canvas.text(width - len(modes) - 2, 3, modes, DIM)
    sky_slice = None
    hits = []
    if state.view == "orbit":
        bottom = height - 7
        plot_w = width - 34 if wide else width - 2
        plot_y = 5 if wide else 4
        hits, geometry = draw_orbits(canvas, state, 1, plot_y, plot_w, bottom - plot_y, palette)
        if wide:
            for y in range(5, height - 6):
                canvas.put(width - 31, y, "│", RULE)
            sidebar(canvas, state, width - 28, 5, 26, height - 11, geometry, palette)
        else:
            b = BODY_BY_ID[state.selected]
            pos = position_at(state.selected, state.moment)
            canvas.text(
                3,
                height - 7,
                f"{b['name'].upper()}  {pos['radiusAU']:.3f} AU from Sun  / "
                f" {b['periodDays']:,.1f} d orbit",
                MUTED,
            )
        hits += inventory(canvas, state, height - 5, palette)
    else:
        image_h = height - 10
        if state.location is None:
            y = max(6, height // 2 - 3)
            canvas.text(5, y, "THE SKY NEEDS A PLACE TO STAND.", IVORY)
            canvas.text(5, y + 2, "Press l to enter latitude,longitude.", CYAN)
            canvas.text(5, y + 3, "No IP lookup unless you confirm it.", MUTED)
            canvas.text(5, y + 4, "Press g for an optional approximate IP lookup.", MUTED)
            canvas.text(5, y + 5, "Example format: 34.05,-118.25  (not your location)", DIM)
        elif camera is not None and not (SKY_MODERN_START <= state.moment <= SKY_MODERN_END):
            canvas.text(5, max(6, height // 2 - 1), "SKY DATE OUTSIDE MODERN INTERVAL.", IVORY)
            canvas.text(
                5,
                max(6, height // 2 + 1),
                "Educational display only; no sky frame rendered.",
                MUTED,
            )
        elif camera is not None:
            sky_slice = (5, sky_lines(state, width, image_h, camera, runtime))
            canvas.text(
                2,
                height - 5,
                f"LINECAST SKY  /  AZ {camera.az:05.1f}°  ALT {camera.alt:04.1f}°  "
                f"FOV {camera.fov:.0f}°",
                DIM,
            )
    note = state.note
    if not note:
        note = (
            f"Keplerian model · sizes illustrative · Linecast {linecast.__version__}"
            if state.view == "orbit"
            else "Real sky / local catalogues · stars emerge after twilight · same UTC"
        )
    brand = "ORRERY.ProDyn.ai"
    brand_x = width - len(brand) - 2
    canvas.text(2, height - 4, note[: max(0, brand_x - 4)], DIM)
    if brand_x >= 2:
        canvas.text(brand_x, height - 4, "ORRERY", IVORY)
        canvas.text(brand_x + len("ORRERY"), height - 4, ".ProDyn.ai", palette.brand)
    canvas.text(2, height - 3, "─" * (width - 4), RULE)
    if state.view == "orbit":
        controls = "Space play   Tab select   b loop   v sky   ? help   q quit"
    else:
        controls = (
            "Space play   WASD look   +/- zoom   l site   g infer   v orbit   ? help   q quit"
        )
    canvas.text(2, height - 2, controls[: width - 4], MUTED)
    # Flat modal composition also works in --print, with exact dimensions.
    if help_open:
        if height < 28:
            lines = [HELP[i] for i in (0, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 17, 20)]
        else:
            lines = HELP
        modal(canvas, "CONTROLS / FIELD NOTES", lines, palette)
        sky_slice = None
    if location_confirm:
        modal(
            canvas,
            "INFER OBSERVING SITE?",
            [
                "This will query a public-IP approximate lookup.",
                "No location is saved or cached.",
                "The result is labeled inferred / approximate.",
                "",
                "Enter or y: continue   Esc: cancel",
            ],
            palette,
        )
        sky_slice = None
    if location_text is not None:
        modal(
            canvas,
            "OBSERVER / DECIMAL COORDINATES",
            [
                "Latitude −90..90; longitude −180..180 (east +).",
                "",
                location_text + "▏",
                "",
                (location_error or "Stored in this session only. No network request.")[
                    : width - 12
                ],
                "Enter save  ·  Esc cancel  ·  Ctrl-U clear",
            ],
            palette,
        )
        sky_slice = None
    lines = canvas.lines()
    if sky_slice is not None:
        start, native = sky_slice
        lines[start : start + len(native)] = native
    return "\n".join(lines), hits
