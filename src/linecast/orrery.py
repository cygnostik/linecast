#!/usr/bin/env python3
"""Orrery — a small, offline astronomical instrument powered by Linecast.

Run ``linecast orrery --help``. All displayed clocks are UTC. The orbital
model is heliocentric; the adjacent sky is Linecast's observer-centred model.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from linecast._live import LiveApp
from linecast._framebuffer import get_terminal_size
from linecast._orrery_astronomy import (
    BODIES,
    MIN_DATE,
    MAX_DATE,
    position_at,
    validate_date,
    utc_now,
)
from linecast._runtime import RuntimeConfig, VersionAction
from linecast._i18n import LANGUAGE_CODES

BODY_IDS = tuple(body["id"] for body in BODIES)
SPEEDS = (1 / 24, 1.0, 6.0, 30.0, 120.0, 365.0)  # simulated days / real second


def resolved_language(value):
    """Resolve an Orrery language with Linecast's explicit English fallback."""
    code = (value or "en").strip().lower().replace("_", "-").split("-", 1)[0]
    return code if code in LANGUAGE_CODES else "en"


def parse_date(value: str) -> datetime:
    """ISO date/time; a missing offset explicitly means UTC, not local time."""
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return validate_date(result)
    except (ValueError, OverflowError) as exc:
        message = (f"date must be ISO UTC, between {MIN_DATE.date()} and "
                   f"{MAX_DATE.date()}: {exc}")
        raise ValueError(message) from exc


def parse_location(value: str) -> tuple[float, float]:
    """Coordinates only. Never geocode, infer a site, or make a network call."""
    try:
        lat, lon = (float(part.strip()) for part in value.split(","))
    except (ValueError, TypeError) as exc:
        raise ValueError("location must be LAT,LON in decimal degrees") from exc
    valid = math.isfinite(lat) and math.isfinite(lon)
    if not (valid and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("latitude must be -90..90 and longitude -180..180 (finite numbers)")
    return lat, lon


@dataclass
class State:
    moment: datetime = field(default_factory=utc_now)
    location: tuple[float, float] | None = None
    selected: str = "earth"
    view: str = "orbit"
    playing: bool = True
    speed_index: int = 2
    direction: int = 1
    compressed: bool = True
    inner: bool = False
    tilted: bool = True
    zoom: float = 1.0
    rotation: float = -18.0
    note: str = ""
    loop: bool = False
    location_inferred: bool = False
    theme: str = "native"

    def __post_init__(self):
        self.moment = validate_date(self.moment)
        if self.theme not in ("orrery", "native"):
            raise ValueError("theme must be 'orrery' or 'native'")

    @property
    def speed(self):
        return SPEEDS[self.speed_index]

    @property
    def bodies(self):
        return BODIES[:4] if self.inner else BODIES


class OrreryApp(LiveApp):
    """One LiveApp and one clock for both orbital and native sky renderers."""

    interval = 1 / 20
    mouse = True

    def __init__(self, state=None, width=None, height=None, runtime=None):
        self.state = state or State()
        self.width, self.height = width, height
        self.runtime = runtime
        self.interval = 1 / 20 if self.state.view == "orbit" else 0.10
        self.hits = []
        self.help_open = False
        self.location_edit = False
        self.location_text = ""
        self.location_error = ""
        self.location_confirm = False
        self.camera = None
        self._last_tick = time.monotonic()
        self._drag_rotation = None

    def dimensions(self):
        cols, rows = get_terminal_size()
        return self.width or cols, self.height or rows

    def advance(self, seconds):
        if not self.state.playing or self.help_open or self.location_edit or self.location_confirm:
            return
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            return
        if math.isnan(seconds):
            self.state.note = "Ignored a non-finite clock advance."
            return
        if math.isinf(seconds):
            days = (math.inf if seconds > 0 else 0.0) * self.state.speed * self.state.direction
        else:
            days = max(0.0, seconds) * self.state.speed * self.state.direction
        self.shift_days(days, pause=False)

    def shift_days(self, days, pause=True):
        s = self.state
        try:
            days = float(days)
        except (TypeError, ValueError):
            return False
        if math.isnan(days):
            s.note = "Ignored a non-finite date advance."
            return False
        if s.loop and math.isfinite(days):
            span = (MAX_DATE - MIN_DATE).total_seconds() / 86400.0
            offset = (s.moment - MIN_DATE).total_seconds() / 86400.0
            target = offset + math.fmod(days, span)
            if 0.0 <= target <= span:
                s.moment = MIN_DATE + timedelta(days=target)
            else:
                s.moment = MIN_DATE + timedelta(days=target % span)
            if pause:
                s.playing = False
            return True
        if math.isinf(days):
            s.moment = MAX_DATE if days > 0 else MIN_DATE
            s.playing = False
            s.note = "Model date limit reached; reverse or reset with n."
            return False
        try:
            new = s.moment + timedelta(days=days)
        except OverflowError:
            s.moment = MAX_DATE if days > 0 else MIN_DATE
            s.playing = False
            s.note = "Model date limit reached; reverse or reset with n."
            return False
        if new > MAX_DATE or new < MIN_DATE:
            s.moment = max(MIN_DATE, min(MAX_DATE, new))
            s.playing = False
            s.note = "Model date limit reached; reverse or reset with n."
        else:
            s.moment = new
        if pause:
            s.playing = False
        return True

    def sky_camera(self):
        if self.camera is None and self.state.location is not None:
            from linecast._sky_live import Camera
            from linecast.sky import Scene, default_view

            cols, rows = self.dimensions()
            view = default_view(Scene(self.state.moment, *self.state.location), cols, rows - 5)
            self.camera = Camera(view.az, view.alt, view.fov, view.figures)
        return self.camera

    def render_static(self):
        from linecast._orrery_render import render_frame

        started = time.monotonic()
        cols, rows = self.dimensions()
        result, self.hits = render_frame(
            self.state,
            cols,
            rows,
            self.sky_camera() if self.state.view == "sky" else None,
            help_open=self.help_open,
            location_confirm=self.location_confirm,
            location_text=self.location_text if self.location_edit else None,
            location_error=self.location_error,
            runtime=self.runtime,
        )
        if self.state.view == "sky":
            # Sky rendering includes a catalogue projection; don't ask the
            # live loop for a blanket 20 Hz when that work exceeds the budget.
            self.interval = max(0.10, min(0.50, (time.monotonic() - started) * 1.25))
        return result

    def render(self, **_frame):
        now = time.monotonic()
        self.advance(now - self._last_tick)
        self._last_tick = now
        # LiveApp snapshots its interval on entry. Bound expensive sky paints
        # here instead of assuming later self.interval changes retune its loop.
        key = (
            self.dimensions(),
            self.state.view,
            tuple((k, v) for k, v in vars(self.state).items() if k != "moment"),
            self.help_open,
            self.location_edit,
            self.location_confirm,
            self.location_text,
            self.location_error,
        )
        if (
            self.state.view == "sky"
            and getattr(self, "_cached_key", None) == key
            and now - getattr(self, "_painted_at", float("-inf")) < self.interval
        ):
            return self._cached_frame
        self._cached_frame = self.render_static()
        self._cached_key = key
        self._painted_at = now
        return self._cached_frame

    def text_mode(self):
        return True

    def intercept(self, action):
        self._cached_key = None  # Every input gets an immediate frame.
        if self.location_edit:
            if action in ("escape", "quit"):
                self.location_edit = False
                return True
            if action == "key:enter":
                try:
                    self.state.location = parse_location(self.location_text)
                except ValueError as exc:
                    self.location_error = str(exc)
                else:
                    self.state.location_inferred = False
                    self.location_edit = False
                    self.camera = None
                    self.state.note = "Observer set locally. Coordinates are not sent anywhere."
                return True
            if action == "key:backspace":
                self.location_text = self.location_text[:-1]
            elif action == "key:kill":
                self.location_text = ""
            elif (
                action.startswith("char:") and action[5:].isascii() and len(self.location_text) < 48
            ):
                self.location_text += action[5:]
            return True
        if self.location_confirm:
            if action in ("escape", "quit", "char:n", "char:N"):
                self.location_confirm = False
                return True
            if action in ("key:enter", "char:y", "char:Y"):
                self.location_confirm = False
                self.infer_location()
                return True
            return True
        if self.help_open:
            self.help_open = False
            self._last_tick = time.monotonic()
            return True
        if action in ("char:q", "char:Q"):
            return "quit"
        if action == "quit":
            return False
        if action == "escape":
            return True
        if action in ("fwd", "back"):
            self.shift_days(
                (1 if action == "fwd" else -1) * (1 / 96 if self.state.view == "sky" else 1)
            )
            return True
        if action == "key:tab":
            self.select_next()
            return True
        if action.startswith("char:"):
            return self.on_action(action[5:])
        if action.startswith("key:"):
            return self.on_action(action[4:])
        return False

    def select_next(self):
        ids = [body["id"] for body in self.state.bodies]
        i = ids.index(self.state.selected) if self.state.selected in ids else -1
        self.select(ids[(i + 1) % len(ids)])

    def select(self, body_id):
        self.state.selected = body_id
        if body_id not in [b["id"] for b in self.state.bodies]:
            self.state.inner = False
        if self.state.view == "sky":
            self.aim_selected()

    def aim_selected(self, moon=False):
        cam = self.sky_camera()
        if cam is None:
            return
        from linecast.sky import Scene

        scene = Scene(self.state.moment, *self.state.location)
        if moon:
            alt, az, label = scene.moon_alt, scene.moon_az, "Moon"
        else:
            entry = next((p for p in scene.planets if p[0] == self.state.selected), None)
            if entry is None:
                self.state.note = (
                    "Earth is the observing platform in sky mode."
                    if self.state.selected == "earth"
                    else "Pluto is not in the Linecast sky ephemeris."
                )
                return
            alt, az, label = entry[2], entry[3], self.state.selected.title()
        if alt < 0:
            self.state.note = f"{label}: {alt:+.1f}° altitude, below the horizon at this UTC."
        else:
            self.state.note = f"{label}: {alt:+.1f}° altitude / {az:.1f}° azimuth."
        cam.fly_to(az, max(8, alt))

    def on_action(self, key):
        self._cached_key = None  # Every input gets an immediate frame.
        s = self.state
        cam = self.sky_camera() if s.view == "sky" else None
        if key in (" ", "p"):
            s.playing = not s.playing
            self._last_tick = time.monotonic()
        elif key == "n":
            s.moment = utc_now()
            s.playing = False
            s.note = "UTC reset to now."
        elif key == "r":
            s.direction *= -1
        elif key == "b":
            s.loop = not s.loop
            s.note = (
                "Looping enabled; date wraps with overshoot."
                if s.loop
                else "Looping disabled; model endpoints hold."
            )
        elif key in (".", ","):
            s.speed_index = max(0, min(len(SPEEDS) - 1, s.speed_index + (1 if key == "." else -1)))
        elif key in ("[", "]"):
            self.shift_days(1 if key == "]" else -1)
        elif key == "v":
            s.view = "sky" if s.view == "orbit" else "orbit"
            s.playing = False
            s.note = "Shared UTC clock paused on view change. Space resumes."
            self.interval = 1 / 20 if s.view == "orbit" else 0.10
        elif key == "l":
            self.location_edit = True
            self.location_text = (
                "" if s.location is None else f"{s.location[0]:g},{s.location[1]:g}"
            )
            self.location_error = ""
        elif key == "g":
            self.location_confirm = True
        elif key in ("?", "h"):
            self.help_open = True
        elif key in "123456789" and len(key) == 1:
            self.select(BODY_IDS[int(key) - 1])
        elif key in ("+", "=", "-"):
            self.on_wheel(1 if key != "-" else -1, 0, 0)
        elif key in ("a", "d", "w", "s"):
            if cam is not None:
                cam.pan({"a": -1, "d": 1}.get(key, 0), {"w": 1, "s": -1}.get(key, 0))
            elif key in ("a", "d"):
                s.rotation = (s.rotation + (8 if key == "d" else -8)) % 360
        elif key == "c" and cam is not None:
            cam.figures = (cam.figures + 2) % 3
        elif key == "m" and cam is not None:
            self.aim_selected(moon=True)
        elif key == "u":
            s.compressed = not s.compressed
        elif key == "i":
            s.inner = not s.inner
            s.zoom = 1
            if s.inner and s.selected not in BODY_IDS[:4]:
                s.selected = "earth"
        elif key == "t":
            s.tilted = not s.tilted
        elif key == "0":
            s.zoom, s.rotation, s.tilted = 1.0, -18.0, True
            self.camera = None
        else:
            return False
        return True

    def infer_location(self):
        """Opt-in public-IP lookup, without Linecast's cache/config writes."""
        try:
            from linecast._http import fetch_json
            from linecast._location import PROVIDERS
        except ImportError as exc:  # pragma: no cover - installed dependency
            self.location_error = f"Approximate lookup unavailable: {exc}"
            self.state.note = self.location_error
            return False
        deadline = time.monotonic() + 5.0
        last_error = "no provider succeeded"
        for name, url, parse in PROVIDERS:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                data = fetch_json(
                    url,
                    headers={"Accept": "application/json"},
                    timeout=min(2.0, max(0.1, remaining)),
                )
                lat, lon, _country = parse(data)
                location = parse_location(f"{lat},{lon}")
            except Exception as exc:
                last_error = f"{name}: {type(exc).__name__}"
                continue
            self.state.location = location
            self.state.location_inferred = True
            self.camera = None
            self.state.note = (
                "Inferred/approximate public-IP location set for this session; "
                "not saved. Manual LAT,LON remains available."
            )
            return True
        self.state.note = (
            f"Approximate public-IP lookup failed ({last_error}); sky remains usable offline."
        )
        self.location_error = self.state.note
        return False

    def on_wheel(self, direction, col, row):
        self._cached_key = None  # Every input gets an immediate frame.
        if self.help_open or self.location_edit:
            return False
        cam = self.sky_camera() if self.state.view == "sky" else None
        if cam is not None:
            cam.zoom(1 / 1.25 if direction > 0 else 1.25)
        else:
            self.state.zoom = min(
                8, max(0.3, self.state.zoom * (1.16 if direction > 0 else 1 / 1.16))
            )
        return True

    def on_drag(self, dcol, drow, done):
        self._cached_key = None  # Every input gets an immediate frame.
        if self.help_open or self.location_edit:
            return False
        cam = self.sky_camera() if self.state.view == "sky" else None
        if cam is not None:
            cols, _ = self.dimensions()
            from linecast.sky import focal_length

            cam.focal = focal_length(cols, cam.fov)
            return cam.release() if done else cam.drag(dcol, drow)
        if self._drag_rotation is None:
            self._drag_rotation = self.state.rotation
        self.state.rotation = (self._drag_rotation + dcol * 1.2) % 360
        if done:
            self._drag_rotation = None
        return bool(dcol or drow)

    def on_click(self, col, row):
        self._cached_key = None  # Every input gets an immediate frame.
        if self.help_open or self.location_edit:
            return False
        x, y = col - 1, row - 1
        candidates = [
            (abs(x - hx) + 2 * abs(y - hy), body_id)
            for body_id, hx, hy, radius in self.hits
            if abs(x - hx) <= radius and abs(y - hy) <= 1
        ]
        if candidates:
            self.select(min(candidates)[1])
            return True
        return False


def build_parser():
    parser = argparse.ArgumentParser(
        prog="linecast orrery",
        description="Orrery — offline solar-system instrument, powered by Linecast.",
        epilog=("UTC everywhere. ISO dates without an offset mean UTC. Location lookup is "
                "never used unless --infer-location or g is explicitly confirmed."),
    )
    parser.add_argument("--version", action=VersionAction)
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--print",
        dest="print_frame",
        action="store_true",
        help="print one frame (use --date for reproducibility)",
    )
    output.add_argument(
        "--json", action="store_true", help="emit physical coordinates and state as JSON"
    )
    parser.add_argument(
        "--date", metavar="ISO", help="initial UTC instant; YYYY-MM-DD or ISO timestamp"
    )
    parser.add_argument(
        "--location",
        metavar="LAT,LON",
        help=("explicit decimal coordinates, east longitude positive; use "
              "--location=-34,-70 for negative latitude"),
    )
    parser.add_argument("--width", type=int, help="frame width, 40..300 columns")
    parser.add_argument("--height", type=int, help="frame height, 16..100 rows")
    parser.add_argument("--view", choices=("orbit", "sky"), default="orbit")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="wrap the finite model date range (default: hold at endpoints)",
    )
    parser.add_argument(
        "--infer-location",
        action="store_true",
        help="opt in to a public-IP approximate observing site; not saved",
    )
    parser.add_argument(
        "--theme",
        choices=("orrery", "native"),
        default="native",
        help="colour palette (default: native; orrery preserves the Orrery palette)",
    )
    parser.add_argument(
        "--lang",
        default="en",
        help="Linecast language code; Orrery labels use explicit English fallback",
    )
    return parser


def payload(state):
    observer = (
        None
        if state.location is None
        else {"latitude": state.location[0], "longitude": state.location[1]}
    )
    if observer is not None and state.location_inferred:
        observer.update(source="inferred/approximate public-IP", saved=False)
    result = {
        "application": "Orrery",
        "utc": state.moment.isoformat(),
        "view": state.view,
        "loop": state.loop,
        "theme": state.theme,
        "observer": observer,
        "selected": state.selected,
        "model": "approximate heliocentric Keplerian elements; not for navigation",
        "referenceFrame": "J2000 mean ecliptic/equinox; AU; UTC approximates TDB",
        "earthPosition": "Earth–Moon barycenter, not the geocenter",
        "display": {"scale": "spaced" if state.compressed else "AU", "body_sizes_to_scale": False},
        "bodies": [dict(body, position=position_at(body["id"], state.moment)) for body in BODIES],
    }
    if state.view == "sky" and state.location is not None:
        from linecast.sky import Scene

        scene = Scene(state.moment, *state.location)
        result["sky"] = {
            "model": "Linecast observer-centred ephemeris",
            "sun": {"altitudeDeg": scene.sun_alt, "azimuthDeg": scene.sun_az},
            "moon": {
                "altitudeDeg": scene.moon_alt,
                "azimuthDeg": scene.moon_az,
                "illuminatedFraction": scene.moon_illum,
            },
            "planets": [
                {"id": p[0], "altitudeDeg": p[2], "azimuthDeg": p[3], "magnitude": p[4]}
                for p in scene.planets
            ],
        }
    return result


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    for value, lo, hi, label in ((args.width, 40, 300, "width"), (args.height, 16, 100, "height")):
        if value is not None and not lo <= value <= hi:
            parser.error(f"{label} must be {lo}..{hi}")
    try:
        moment = parse_date(args.date) if args.date else utc_now()
        location = parse_location(args.location) if args.location else None
    except ValueError as exc:
        parser.error(str(exc))
    runtime = RuntimeConfig(
        live=not (args.print_frame or args.json),
        icons="plain",
        lang=resolved_language(args.lang),
        oneline=False,
        json_mode=args.json,
    )
    state = State(
        moment=moment,
        location=location,
        view=args.view,
        loop=args.loop,
        theme=args.theme,
        playing=not (args.print_frame or args.json or args.view == "sky"),
    )
    if args.infer_location and location is None:
        OrreryApp(state, runtime=runtime).infer_location()
    if args.json:
        print(json.dumps(payload(state), ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    instrument = OrreryApp(state, args.width, args.height, runtime)
    if args.print_frame or not (sys.stdin.isatty() and sys.stdout.isatty()):
        state.playing = False
        from linecast._live import print_frame

        print_frame(instrument.render_static())
    else:
        instrument.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
