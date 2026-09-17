# Native Orrery verification

The branch builds against Linecast 2.6.1. It is a proposed native addition, not an upstream release.

## Checked locally

- The full offline upstream suite passed after native integration and quit-path repair: **4,097 tests**, **307 subtests**, with 2 skipped and 72 integration tests deselected. Subsequent version-command/footer regressions are additional focused tests.
- **2,045 adversarial assertions** passed across layout boundaries, all nine bodies, polar sites, deterministic control sequences, and clock overflow.
- **15 controlling-PTY scenarios** passed: resize/quit, modal Ctrl-C, SIGINT, SIGTERM, and help/site/loop controls, each repeated three times. Every run restored terminal attributes and the alternate screen without a traceback or forced timeout.
- The real printable `q` path has a dedicated POSIX regression test. This caught a defect that static/unit checks alone missed; the live-loop intercept contract now permits a clean quit request.
- Ruff and whitespace checks passed.
- A wheel was built and installed into a separate environment. The command produced nine-body JSON from outside the checkout, with no inferred observer. The complete Orrery MIT notice was verified under the wheel's distribution licence directory.
- Visuals in this folder are actual native static frames, using a fixed UTC date and explicit example coordinates. The dot-cell rasterizer preserves the emitted Unicode Braille pattern.

## Reproduce

```sh
uv run --with pytest pytest tests -q -p no:cacheprovider
uv run --with ruff ruff check src tests scripts
uv build --wheel
uv run linecast orrery --version
uv run linecast orrery --json --date 2000-01-01T12:00:00Z
```

Cross-platform CI is linked from the fork's validation pull request. Linux controlling-terminal checks do not constitute full interactive Windows desktop certification. Orrery-specific labels currently fall back to English. [Model/source limitations](orrery-astronomy.md) remain explicit.
