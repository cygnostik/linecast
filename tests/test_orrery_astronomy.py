"""Native Orrery astronomy contract and independently bundled fixtures."""

from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path

import pytest

from linecast import _orrery_astronomy as astronomy

UTC = timezone.utc
J2000 = datetime(2000, 1, 1, 12, tzinfo=UTC)
REFERENCE = json.loads((Path(__file__).parent / "fixtures" / "science_reference.json").read_text())
LONG_RANGE = json.loads(
    (Path(__file__).parent / "fixtures" / "long_range_horizons.json").read_text()
)["samples"]


def parse_date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_positions_and_descriptors_match_bundled_reference():
    assert len(REFERENCE["positions"]) == 72
    assert len(astronomy.BODIES) == 9
    assert astronomy.BODIES == REFERENCE["bodies"]
    for expected in REFERENCE["positions"]:
        actual = astronomy.position_at(expected["id"], parse_date(expected["date"]))
        assert set(actual) == {"x", "y", "z", "radiusAU", "longitudeDeg"}
        for field in actual:
            assert actual[field] == pytest.approx(expected[field], abs=2e-11)


def test_orbits_match_reference_and_close():
    for expected in REFERENCE["orbits"]:
        actual = astronomy.orbit_points(
            expected["id"], parse_date(expected["date"]), expected["count"]
        )
        assert len(actual) == expected["count"] + 1
        for point, wanted in zip(actual, expected["points"]):
            for axis in "xyz":
                assert point[axis] == pytest.approx(wanted[axis], abs=2e-12)
    for body in astronomy.BODIES:
        points = astronomy.orbit_points(body["id"], J2000)
        assert len(points) == 241
        assert points[0] == points[-1]
        assert points[0] is not points[-1]


def test_long_range_samples_and_inclusive_endpoints():
    for expected in LONG_RANGE:
        actual = astronomy.position_at(expected["id"], parse_date(expected["date"]))
        for axis in "xyz":
            assert actual[axis] == pytest.approx(expected[axis], abs=expected["toleranceAU"])
    for endpoint in (astronomy.MIN_DATE, astronomy.MAX_DATE):
        for body in astronomy.BODIES:
            astronomy.position_at(body["id"], endpoint)
            astronomy.orbit_points(body["id"], endpoint, 3)
    with pytest.raises(ValueError):
        astronomy.validate_date(astronomy.MAX_DATE + timedelta(microseconds=1))


def test_validation_is_strict_and_offsets_normalize():
    assert astronomy.validate_date(J2000.astimezone(timezone(timedelta(hours=5.5)))) == J2000
    for value in (None, "2000-01-01", J2000.date(), True, [], {}):
        with pytest.raises(TypeError):
            astronomy.validate_date(value)
    with pytest.raises(ValueError):
        astronomy.validate_date(datetime(2000, 1, 1))
    for count in (0, 2, 10001, 3.0, True, None, "12"):
        with pytest.raises(ValueError):
            astronomy.orbit_points("earth", J2000, count)
    for body in ("Earth", "sun", "moon", None, []):
        with pytest.raises(ValueError):
            astronomy.position_at(body, J2000)


def test_positions_are_finite_physical_and_do_not_use_period_descriptor():
    for body in astronomy.BODIES:
        result = astronomy.position_at(body["id"], J2000)
        assert result["radiusAU"] == pytest.approx(
            math.hypot(result["x"], result["y"], result["z"])
        )
        assert 0 <= result["longitudeDeg"] < 360
    earth = next(body for body in astronomy.BODIES if body["id"] == "earth")
    old = earth["periodDays"]
    before = astronomy.position_at("earth", J2000 + timedelta(days=100))
    try:
        earth["periodDays"] = 1
        assert astronomy.position_at("earth", J2000 + timedelta(days=100)) == before
    finally:
        earth["periodDays"] = old
