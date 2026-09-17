# Third-party notices

## Orrery port

`linecast.orrery` is a native Python port of the public Orrery interface and
visual vocabulary from [cygnostik/orrery](https://github.com/cygnostik/orrery),
revision `c7388feb1db609caa1d4843cde0fc615c57dafdd`. The upstream project is
MIT-licensed; its license text is retained in `LICENSE` and this port remains
MIT-licensed.

## Astronomy data

The dependency-free orbital coefficients are derived from NASA/JPL Solar
System Dynamics, *Approximate Positions of the Planets* Tables 1, 2a, and 2b:
<https://ssd.jpl.nasa.gov/planets/approx_pos.html> and
<https://ssd.jpl.nasa.gov/ftp/eph/planets/ioms/ExplSupplChap8.pdf>. Physical
radii and sidereal periods are from JPL Planetary Physical Parameters:
<https://ssd.jpl.nasa.gov/planets/phys_par.html>. This is an approximate
educational model, not a navigation ephemeris.

The adjacent sky view uses Linecast's existing local catalogues and renderer;
no Orrery command performs a network request unless the user explicitly
confirms public-IP inference with `--infer-location` or `g`, and that result
is not saved.
