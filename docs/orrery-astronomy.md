# Astronomy model and supported dates

`linecast._orrery_astronomy` is an educational, dependency-free Keplerian approximation. It
returns heliocentric J2000 mean-ecliptic/equinox coordinates in AU. `x` points
toward the J2000 equinox and `z` toward ecliptic north. `earth` means the
Earth-Moon barycenter (EMB), not the geocenter. `position_at()` and
`orbit_points()` keep their existing signatures and output shapes; `BODIES`,
`MIN_DATE`, and `MAX_DATE` remain module exports.

## Supported range

The inclusive exported range is:

- `MIN_DATE = 0001-01-01T00:00:00+00:00`
- `MAX_DATE = 3000-01-01T00:00:00+00:00`

`MAX_DATE` is the start of 3000, not the end of that year. Python's standard
`datetime` has no year 0 and cannot represent BC dates, so this implementation
supports only the AD subset of JPL's long-range fit. Dates outside the two
endpoints raise `ValueError`; aware non-UTC inputs are normalized to UTC.
Naive datetimes and non-datetime values retain the existing validation errors.

The time variable is computed from the `datetime` difference to J2000.0 using
36525 86400-second days per Julian century. UTC is treated as an educational
approximation to TDB: leap seconds, UTC/TDB offsets, light-time, aberration,
and apparent-place corrections are not applied. Date arithmetic therefore uses
Python's proleptic Gregorian labels; historical users who need a different
calendar convention must convert before calling this API.

## Two official JPL fits

The implementation deliberately does not extrapolate the modern fit across the
whole extended range:

- On the inclusive interval 1800-01-01 through 2050-01-01, it uses the original
  JPL Table 1 coefficients. This preserves the original Orrery `science.js`
  behavior and its regression fixtures exactly.
- Outside that interval, it uses the official long-range Table 2a coefficients
  (the original paper's Table 8.10.3) and adds the required Table 2b mean
  anomaly terms (original Table 8.10.4) for Jupiter through Pluto. Pluto's
  long-range coefficients are taken from the original JPL explanatory
  supplement PDF, because the current HTML page omits Pluto after its removal
  from the planet list. No modern-fit Pluto coefficients are extrapolated.

The model switch is intentionally discontinuous at the boundaries: a date just
before 1800 or just after 2050 uses a different fitted solution from the exact
boundary date. This is preferable to silently extending a fit outside the
interval JPL gives for it. `orbit_points()` uses the selected fit's
instantaneous ellipse; Table 2b affects mean anomaly for `position_at()`, not
the ellipse path itself.

JPL describes the fits as lower-accuracy formulae, not integrated trajectories.
Its nominal long-range errors (3000 BC--3000 AD) are approximately:

| body | longitude | latitude | distance |
| --- | ---: | ---: | ---: |
| Mercury | 20 arcsec | 15 arcsec | 1,000 km |
| Venus | 40 arcsec | 30 arcsec | 8,000 km |
| EMB | 40 arcsec | 15 arcsec | 15,000 km |
| Mars | 100 arcsec | 40 arcsec | 30,000 km |
| Jupiter | 600 arcsec | 100 arcsec | 1,000,000 km |
| Saturn | 1,000 arcsec | 100 arcsec | 4,000,000 km |
| Uranus | 2,000 arcsec | 30 arcsec | 8,000,000 km |
| Neptune | 400 arcsec | 15 arcsec | 4,000,000 km |
| Pluto | 400 arcsec | 100 arcsec | 2,500,000 km |

The 1800--2050 nominal errors are materially smaller for most bodies. These
are accuracy expectations, not test tolerances or navigation guarantees.

## Independent verification

`tests/fixtures/long_range_horizons.json` contains four compact samples outside
Table 1: EMB and Jupiter at 1700-01-01T12:00:00Z, Neptune at
2200-01-01T12:00:00Z, and Pluto at 2900-01-01T12:00:00Z. The fixture records
its provenance and compares against JPL Horizons API geometric vectors:

- target centered on the Sun (`CENTER=500@10`)
- `REF_PLANE=ECLIPTIC`, `REF_SYSTEM=J2000`
- Gregorian calendar mode
- TDB timestamp at exactly 12:00:00
- KM-S output converted to AU using the defined astronomical unit
- no aberration or light-time correction

The tests use compact per-sample coordinate tolerances of 0.05 AU (0.10 AU for
Pluto), intentionally looser than the published long-range error table while
still detecting coefficient/model mistakes. The original Table 1 fixtures keep
their exact tight tolerances and remain the compatibility gate for the modern
interval.

Sources:

- JPL, “Approximate Positions of the Planets” (Tables 1, 2a, 2b):
  <https://ssd.jpl.nasa.gov/planets/approx_pos.html>
- JPL, *Explanatory Supplement to the Astronomical Almanac*, Chapter 8,
  original Tables 8.10.2--8.10.4 (Pluto included):
  <https://ssd.jpl.nasa.gov/ftp/eph/planets/ioms/ExplSupplChap8.pdf>
- JPL Horizons API documentation and service:
  <https://ssd-api.jpl.nasa.gov/doc/horizons.html>
  <https://ssd.jpl.nasa.gov/api/horizons.api>
