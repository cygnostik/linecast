"""Native Orrery application, rendering, and CLI contracts."""

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from linecast import _orrery_render as render
from linecast.orrery import (
    BODIES,
    MAX_DATE,
    MIN_DATE,
    OrreryApp,
    State,
    build_parser,
    main,
    parse_date,
    parse_location,
    payload,
)

INSTANT = parse_date("2026-09-16T06:00:00Z")


def frame_lines(text):
    return text.splitlines()


def test_native_public_api_and_iso_dates():
    assert parse_date("2026-09-16") == datetime(2026, 9, 16, tzinfo=timezone.utc)
    assert parse_date("2026-09-16T02:00:00+02:00") == datetime(2026, 9, 16, tzinfo=timezone.utc)
    assert parse_date("0001-01-01") == MIN_DATE
    assert parse_date("3000-01-01") == MAX_DATE
    assert parse_location("-34.05, -118.25") == (-34.05, -118.25)
    for value in ("nan,0", "0,inf", "91,0", "0,181", "London", "0,0,0"):
        with pytest.raises(ValueError):
            parse_location(value)


def test_static_frames_are_reproducible_and_year_one_is_zero_padded():
    for width, height in ((80, 24), (120, 40), (60, 20), (40, 16)):
        app = OrreryApp(State(moment=INSTANT, playing=False), width, height)
        first = app.render_static()
        assert len(frame_lines(first)) == height
        assert first == app.render_static()
        if width >= 60:
            assert any("UTC" in line for line in frame_lines(first))
    ancient = OrreryApp(State(moment=MIN_DATE, playing=False), 80, 24).render_static()
    assert "0001-01-01" in ancient


def test_controls_cover_selection_loop_view_and_limits():
    app = OrreryApp(State(moment=INSTANT, playing=False), 80, 24)
    app.intercept("char:b")
    assert app.state.loop
    app.intercept("key:tab")
    assert app.state.selected == "mars"
    app.intercept("char:9")
    assert app.state.selected == "pluto"
    app.intercept("char:v")
    assert app.state.view == "sky"
    app.intercept("char:v")
    assert app.state.view == "orbit"
    app.state.moment = MAX_DATE
    app.state.playing = True
    app.advance(60)
    assert app.state.moment != MAX_DATE
    app.intercept("char:b")
    app.state.moment = MAX_DATE
    app.state.playing = True
    app.advance(60)
    assert app.state.moment == MAX_DATE
    assert not app.state.playing


def test_loop_wraps_both_directions_and_nonfinite_is_safe():
    app = OrreryApp(State(moment=MAX_DATE, playing=False, loop=True), 80, 24)
    app.shift_days(2, pause=False)
    assert app.state.moment == MIN_DATE.replace(day=3)
    app.state.moment = MIN_DATE
    app.shift_days(-2, pause=False)
    assert app.state.moment == MAX_DATE - timedelta(days=2)
    app.state.moment = INSTANT
    app.state.playing = True
    app.advance(float("nan"))
    assert app.state.moment == INSTANT
    app.advance(float("inf"))
    assert app.state.moment == MAX_DATE


def test_location_is_explicit_and_confirmation_n_cancels_without_lookup(tmp_path):
    app = OrreryApp(State(moment=INSTANT, playing=False, view="sky"), 80, 24)
    app.intercept("char:g")
    assert app.location_confirm
    with patch.object(app, "infer_location", side_effect=AssertionError("lookup")):
        app.intercept("char:n")
    assert not app.location_confirm
    assert app.state.location is None

    app.intercept("char:l")
    for char in "34.05,-118.25":
        app.intercept("char:" + char)
    app.intercept("key:enter")
    assert app.state.location == (34.05, -118.25)
    assert "No IP lookup" not in app.render_static()


def test_confirmed_inference_is_opt_in_and_not_persisted():
    app = OrreryApp(State(moment=INSTANT, playing=False, view="sky"), 80, 24)
    config_dir = Path(os.environ["LINECAST_CONFIG_DIR"])
    before = sorted(config_dir.rglob("*"))
    app.intercept("char:g")
    with patch(
        "linecast._http.fetch_json",
        return_value={"loc": "51.48,0", "country": "GB"},
    ) as fetch:
        app.intercept("char:y")
    assert fetch.called
    assert app.state.location == (51.48, 0.0)
    assert app.state.location_inferred
    assert sorted(config_dir.rglob("*")) == before


def test_sky_embedding_uses_explicit_dimensions_without_global_patching():
    from linecast import sky

    app = OrreryApp(
        State(moment=INSTANT, playing=False, location=(34.05, -118.25), view="sky"), 80, 24
    )
    original_size = sky.get_terminal_size
    original_banner = sky.install_banner
    with patch.object(sky, "render", wraps=sky.render) as mocked:
        text = app.render_static()
    assert mocked.call_args.kwargs["size"] == (80, 17)
    assert mocked.call_args.kwargs["show_banner"] is False
    assert sky.get_terminal_size is original_size
    assert sky.install_banner is original_banner
    assert len(frame_lines(text)) == 24


def test_unset_observer_never_constructs_a_fake_site_and_payload_is_clear():
    app = OrreryApp(State(moment=INSTANT, playing=False, view="sky"), 80, 24)
    with patch("linecast.sky.Scene", side_effect=AssertionError("fake observer")):
        text = app.render_static()
    assert "OBSERVER UNSET" in text
    assert "No IP lookup" in text
    assert payload(app.state)["observer"] is None


def test_native_and_orrery_palettes_are_per_render_and_footer_is_properdyn():
    original = render.ORRERY_PALETTE
    assert render.palette_for("native") is not render.palette_for("orrery")
    text = OrreryApp(State(moment=INSTANT, playing=False), 80, 24).render_static()
    assert render.ORRERY_PALETTE == original
    assert "ProDyn.ai" in text
    assert "ORRERY.ProDyn.ai" in text


def test_json_and_print_are_static_offline_and_do_not_write_config():
    config_dir = Path(os.environ["LINECAST_CONFIG_DIR"])
    before = sorted(config_dir.rglob("*"))
    output = StringIO()
    with redirect_stdout(output):
        assert main(["--json", "--date", "2026-09-16", "--view", "sky", "--location", "0,0"]) == 0
    data = json.loads(output.getvalue())
    assert len(data["bodies"]) == len(BODIES)
    assert data["observer"] == {"latitude": 0.0, "longitude": 0.0}
    assert data["utc"] == "2026-09-16T00:00:00+00:00"
    output = StringIO()
    with redirect_stdout(output):
        assert main(["--print", "--date", "2026-09-16", "--width", "80", "--height", "24"]) == 0
    assert "O R R E R Y" in output.getvalue()
    assert sorted(config_dir.rglob("*")) == before


def test_parser_and_translation_fallback_are_explicit():
    args = build_parser().parse_args(["--theme", "orrery", "--loop", "--lang", "fr"])
    assert args.theme == "orrery"
    assert args.loop
    assert args.lang == "fr"
    assert render.translate("unknown-key", "fr", "Fallback label") == "Fallback label"


def test_q_and_ctrl_c_are_native_live_actions_without_override():
    app = OrreryApp(State(moment=INSTANT, playing=False), 80, 24)
    assert not app.intercept("quit")
    assert not hasattr(app, "read_key_extended")
    assert type(app).run is __import__("linecast._live", fromlist=["LiveApp"]).LiveApp.run


def test_dispatch_and_all_completion_scripts_include_orrery_options():
    from linecast import __main__ as cli
    from linecast._completion import render_completion

    assert cli.COMMANDS["orrery"] == "linecast.orrery"
    assert "linecast orrery" in cli.HELP
    for shell in ("bash", "zsh", "fish", "nu"):
        script = render_completion(shell)
        assert "orrery" in script
        assert "--infer-location" in script or "-l infer-location" in script
        assert "--theme" in script or "-l theme" in script
