"""Dependency-free port of Orrery's JPL approximate Keplerian model.

Sources: https://ssd.jpl.nasa.gov/planets/approx_pos.html (Tables 1, 2a,
and 2b), and https://ssd.jpl.nasa.gov/ftp/eph/planets/ioms/ExplSupplChap8.pdf
(original Tables 8.10.2--8.10.4, including Pluto). The original Table 1
coefficients and behavior are retained for 1800--2050. Outside that interval
the official long-range Table 2a coefficients are used, with its mandatory
Table 2b mean-anomaly corrections for Jupiter through Pluto.

Positions are heliocentric J2000 mean ecliptic/equinox coordinates in AU;
x points toward the equinox and z toward ecliptic north. Earth denotes the
Earth–Moon barycenter, NOT the geocenter. UTC is used as approximate TDB:
no leap-second, light-time, or apparent-position corrections are made.
This is educational geometry, not a precision ephemeris or navigation tool;
Pluto retains the lower-accuracy original fit, not modern Horizons values.

Aware datetimes are normalized to UTC. The inclusive supported range is UTC
midnight 0001-01-01 through 3000-01-01. This is the AD subset representable
by Python's datetime; the source Table 2 fit itself is stated for 3000 BC--
3000 AD. The long-range model is not a claim of BC support. Table 1 remains
the exact model for 1800-01-01 through 2050-01-01 inclusive, so switching at
the endpoints is intentionally discontinuous. Orbit paths are instantaneous
fitted ellipses sampled in eccentric anomaly, not integrated trajectories.
Physical descriptors are fixed references; the position solver uses secular
rates, not periodDays or display scaling.

Radii (volume-equivalent mean km) and sidereal periods (Julian years times
365.25) come from https://ssd.jpl.nasa.gov/planets/phys_par.html. Mercury's
2.11 arcminute and Venus's 177.3 degree tilts come from JPL Horizons physical
headers (targets 199 and 299); remaining tilts follow NASA planet fact pages.
Pluto's coarse retrograde tilt is 180 - 57 degrees, not a fitted spin pole.
"""

from datetime import datetime, timezone
import math


MIN_DATE = datetime(1, 1, 1, tzinfo=timezone.utc)
MAX_DATE = datetime(3000, 1, 1, tzinfo=timezone.utc)
_TABLE1_MIN = datetime(1800, 1, 1, tzinfo=timezone.utc)
_TABLE1_MAX = datetime(2050, 1, 1, tzinfo=timezone.utc)
_J2000 = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
_CENTURY_SECONDS = 36525 * 86400
_DEG = math.pi / 180

# Columns: a (AU), e (dimensionless), I, L, perihelion longitude, node
# (angles in degrees), followed by their rates per Julian century.
_ELEMENTS = {
    "mercury": (
        (0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593),
        (0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081),
    ),
    "venus": (
        (0.72333566, 0.00677672, 3.39467605, 181.97909950, 131.60246718, 76.67984255),
        (0.00000390, -0.00004107, -0.00078890, 58517.81538729, 0.00268329, -0.27769418),
    ),
    "earth": (
        (1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0),
        (0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0),
    ),
    "mars": (
        (1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891),
        (0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343),
    ),
    "jupiter": (
        (5.20288700, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909),
        (-0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106),
    ),
    "saturn": (
        (9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448),
        (-0.00125060, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794),
    ),
    "uranus": (
        (19.18916464, 0.04725744, 0.77263783, 313.23810451, 170.95427630, 74.01692503),
        (-0.00196176, -0.00004397, -0.00242939, 428.48202785, 0.40805281, 0.04240589),
    ),
    "neptune": (
        (30.06992276, 0.00859048, 1.77004347, -55.12002969, 44.96476227, 131.78422574),
        (0.00026291, 0.00005105, 0.00035372, 218.45945325, -0.32241464, -0.00508664),
    ),
    "pluto": (
        (39.48211675, 0.24882730, 17.14001206, 238.92903833, 224.06891629, 110.30393684),
        (-0.00031596, 0.00005170, 0.00004818, 145.20780515, -0.04062942, -0.01183482),
    ),
}

# Table 2a / original Table 8.10.3: 3000 BC--3000 AD. Each tuple is
# (value at J2000, secular rate per Julian century).
_LONG_RANGE_ELEMENTS = {
    "mercury": (
        (0.38709843, 0.20563661, 7.00559432, 252.25166724, 77.45771895, 48.33961819),
        (0.00000000, 0.00002123, -0.00590158, 149472.67486623, 0.15940013, -0.12214182),
    ),
    "venus": (
        (0.72332102, 0.00676399, 3.39777545, 181.97970850, 131.76755713, 76.67261496),
        (-0.00000026, -0.00005107, 0.00043494, 58517.81560260, 0.05679648, -0.27274174),
    ),
    "earth": (
        (1.00000018, 0.01673163, -0.00054346, 100.46691572, 102.93005885, -5.11260389),
        (-0.00000003, -0.00003661, -0.01337178, 35999.37306329, 0.31795260, -0.24123856),
    ),
    "mars": (
        (1.52371243, 0.09336511, 1.85181869, -4.56813164, -23.91744784, 49.71320984),
        (0.00000097, 0.00009149, -0.00724757, 19140.29934243, 0.45223625, -0.26852431),
    ),
    "jupiter": (
        (5.20248019, 0.04853590, 1.29861416, 34.33479152, 14.27495244, 100.29282654),
        (-0.00002864, 0.00018026, -0.00322699, 3034.90371757, 0.18199196, 0.13024619),
    ),
    "saturn": (
        (9.54149883, 0.05550825, 2.49424102, 50.07571329, 92.86136063, 113.63998702),
        (-0.00003065, -0.00032044, 0.00451969, 1222.11494724, 0.54179478, -0.25015002),
    ),
    "uranus": (
        (19.18797948, 0.04685740, 0.77298127, 314.20276625, 172.43404441, 73.96250215),
        (-0.00020455, -0.00001550, -0.00180155, 428.49512595, 0.09266985, 0.05739699),
    ),
    "neptune": (
        (30.06952752, 0.00895439, 1.77005520, 304.22289287, 46.68158724, 131.78635853),
        (0.00006447, 0.00000818, 0.00022400, 218.46515314, 0.01009938, -0.00606302),
    ),
    # Pluto is retained from the official original PDF, which the current
    # HTML page omits because Pluto was removed from its planet list.
    "pluto": (
        (39.48686035, 0.24885238, 17.14104260, 238.96535011, 224.09702598, 110.30167986),
        (0.00449751, 0.00006016, 0.00000501, 145.18042903, -0.00968827, -0.00809981),
    ),
}

# Table 2b / original Table 8.10.4. Units are degrees, degrees, degrees,
# degrees per century; the correction is added to M in degrees.
_LONG_RANGE_ANOMALY = {
    "jupiter": (-0.00012452, 0.06064060, -0.35635438, 38.35125000),
    "saturn": (0.00025899, -0.13434469, 0.87320147, 38.35125000),
    "uranus": (0.00058331, -0.97731848, 0.17689245, 7.67025000),
    "neptune": (-0.00041348, 0.68346318, -0.10162547, 7.67025000),
    "pluto": (-0.01262724, 0.0, 0.0, 0.0),
}
_PROPERTIES = (
    ("mercury", 2439.4, 0.2408467, 2.11 / 60),
    ("venus", 6051.8, 0.61519726, 177.3),
    ("earth", 6371.0084, 1.0000174, 23.4),
    ("mars", 3389.50, 1.8808476, 25),
    ("jupiter", 69911, 11.862615, 3),
    ("saturn", 58232, 29.447498, 26.73),
    ("uranus", 25362, 84.016846, 97.77),
    ("neptune", 24622, 164.79132, 28),
    ("pluto", 1188.3, 247.92065, 123),
)
BODIES = [
    {
        "id": body_id,
        "name": body_id.capitalize(),
        "aAU": _ELEMENTS[body_id][0][0],
        "eccentricity": _ELEMENTS[body_id][0][1],
        "inclinationDeg": _ELEMENTS[body_id][0][2],
        "radiusKm": radius,
        "periodDays": years * 365.25,
        "tiltDeg": tilt,
    }
    for body_id, radius, years, tilt in _PROPERTIES
]


def utc_now():
    """Return the current aware UTC datetime (without clamping the clock)."""
    return datetime.now(timezone.utc)


def validate_date(dt):
    """Normalize an aware datetime to UTC; reject invalid types/range.

    TypeError indicates a non-datetime; ValueError indicates a naive datetime
    or an instant outside the inclusive fitted-model interval.
    """
    if not isinstance(dt, datetime):
        raise TypeError("Expected a timezone-aware datetime")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("Expected a timezone-aware datetime")
    try:
        result = dt.astimezone(timezone.utc)
    except OverflowError as exc:
        raise ValueError("Date outside the fitted-model interval") from exc
    if not MIN_DATE <= result <= MAX_DATE:
        raise ValueError("Date outside 0001-01-01 through 3000-01-01 UTC midnight")
    return result


def _uses_table1(dt):
    return _TABLE1_MIN <= dt <= _TABLE1_MAX


def _elements_at(body_id, dt):
    if not isinstance(body_id, str) or body_id not in _ELEMENTS:
        raise ValueError("Unknown body ID")
    date = validate_date(dt)
    t = (date - _J2000).total_seconds() / _CENTURY_SECONDS
    base, rate = _ELEMENTS[body_id] if _uses_table1(date) else _LONG_RANGE_ELEMENTS[body_id]
    return tuple(value + change * t for value, change in zip(base, rate))


def _wrap_degrees(value):
    # fmod preserves the source's signed remainder before its positive wrap.
    return math.fmod(math.fmod(value, 360) + 360, 360)


def _eccentric_anomaly(mean, eccentricity):
    eccentric = mean + eccentricity * math.sin(mean)
    for _ in range(20):
        correction = (eccentric - eccentricity * math.sin(eccentric) - mean) / (
            1 - eccentricity * math.cos(eccentric)
        )
        eccentric -= correction
        if abs(correction) < 1e-13:
            return eccentric
    raise RuntimeError("Kepler solver did not converge")


def _point_on_ellipse(elements, eccentric):
    a, e, inclination, _, perihelion, node = elements
    omega = (perihelion - node) * _DEG
    i = inclination * _DEG
    ascending = node * _DEG
    cw, sw = math.cos(omega), math.sin(omega)
    co, so = math.cos(ascending), math.sin(ascending)
    ci, si = math.cos(i), math.sin(i)
    xp = a * (math.cos(eccentric) - e)
    yp = a * math.sqrt(1 - e * e) * math.sin(eccentric)
    return {
        "x": (cw * co - sw * so * ci) * xp + (-sw * co - cw * so * ci) * yp,
        "y": (cw * so + sw * co * ci) * xp + (-sw * so + cw * co * ci) * yp,
        "z": sw * si * xp + cw * si * yp,
    }


def position_at(body_id, dt):
    """Return x/y/z/radiusAU (AU) and longitudeDeg [0, 360); Earth is EMB."""
    date = validate_date(dt)
    elements = _elements_at(body_id, dt)
    mean_degrees = elements[3] - elements[4]
    if not _uses_table1(date):
        b, c, s, f = _LONG_RANGE_ANOMALY.get(body_id, (0, 0, 0, 0))
        t = (date - _J2000).total_seconds() / _CENTURY_SECONDS
        mean_degrees += b * t * t + c * math.cos(f * t * _DEG) + s * math.sin(f * t * _DEG)
    mean = (_wrap_degrees(mean_degrees + 180) - 180) * _DEG
    point = _point_on_ellipse(elements, _eccentric_anomaly(mean, elements[1]))
    return {
        **point,
        "radiusAU": math.hypot(point["x"], point["y"], point["z"]),
        "longitudeDeg": _wrap_degrees(math.atan2(point["y"], point["x"]) / _DEG),
    }


def orbit_points(body_id, dt, count=240):
    """Return count+1 x/y/z points, closing with a copy of the first point.

    count must be an integer from 3 through 10,000 (not bool). Samples are
    uniform in eccentric anomaly, not time; coordinates remain physical AU.
    """
    if isinstance(count, bool) or not isinstance(count, int) or not 3 <= count <= 10000:
        raise ValueError("Orbit segment count must be an integer from 3 through 10000")
    elements = _elements_at(body_id, dt)
    points = [_point_on_ellipse(elements, 2 * math.pi * index / count) for index in range(count)]
    points.append(points[0].copy())
    return points
