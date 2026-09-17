# Third-party notices

## Native Orrery

The native command adapts [Orrery for Linecast 0.2.0](https://github.com/cygnostik/orrery-linecast/tree/abc204b1dc19053ec38e717c05b100c044d4cf11), whose orbital module derives from the original [Orrery](https://github.com/cygnostik/orrery). Identified public reference: [science.js at c7388feb1db609caa1d4843cde0fc615c57dafdd](https://github.com/cygnostik/orrery/blob/c7388feb1db609caa1d4843cde0fc615c57dafdd/src/science.js). The initial cross-language fixture's exact export revision was not recorded; it is a regression reference, not an independent ephemeris.

The following notice is retained from the MIT-licensed Orrery source. Linecast's own copyright and licence remain in `LICENSE`.

```text
MIT License

Copyright (c) 2026 Chris M. / Promethean Dynamic

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Scientific sources

Orbital elements follow [JPL's approximate planetary positions](https://ssd.jpl.nasa.gov/planets/approx_pos.html), Tables 1, 2a, 2b, and the [original explanatory chapter](https://ssd.jpl.nasa.gov/ftp/eph/planets/ioms/ExplSupplChap8.pdf), which includes Pluto. Independent sample vectors come from [JPL Horizons](https://ssd-api.jpl.nasa.gov/doc/horizons.html). Physical quantities follow the original Orrery reference and [JPL planetary physical parameters](https://ssd.jpl.nasa.gov/planets/phys_par.html).

The adjacent observing view reuses Linecast's existing sky renderer and catalogues, which retain their own attributions. The orbital and observing models are separate educational approximations. See [astronomy notes](docs/orrery-astronomy.md) for dates, frames, uncertainty, and limitations.
