"""Publication regressions: real pacing, explicit consent, faithful small details."""

from datetime import datetime, timezone
import re
import unittest
from unittest.mock import patch

from linecast.orrery import OrreryApp, State
from linecast import _orrery_render as render


class PublicationTests(unittest.TestCase):
    def test_help_rule_has_only_the_requested_short_credit(self):
        canvas = render.Canvas(100, 32)
        render.modal(canvas, "CONTROLS / FIELD NOTES", render.HELP)
        text = re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(canvas.lines()))
        self.assertIn("ProDyn.ai", text)
        self.assertNotIn("ORRERY.ProDyn.ai", text)

    def test_unset_site_offers_both_manual_and_opt_in_inference(self):
        app = OrreryApp(State(view="sky", playing=False), 120, 40)
        self.assertIn("Press g for an optional approximate IP lookup.", app.render_static())

    def test_early_year_is_zero_padded(self):
        app = OrreryApp(State(moment=datetime(1, 1, 1, tzinfo=timezone.utc)), 120, 40)
        self.assertIn("0001-01-01", app.render_static())

    def test_no_declines_location_confirmation_without_lookup(self):
        app = OrreryApp(State(), 120, 40)
        app.on_action("g")
        with patch.object(app, "infer_location") as infer:
            app.intercept("char:n")
        self.assertFalse(app.location_confirm)
        infer.assert_not_called()

    def test_sky_frame_pacing_reuses_frame_until_due(self):
        app = OrreryApp(State(view="sky", playing=False), 120, 40)
        app.interval = 0.10
        with (
            patch.object(app, "render_static", return_value="frame") as paint,
            patch("linecast.orrery.time.monotonic", return_value=100.0) as clock,
        ):
            self.assertEqual(app.render(), "frame")
            clock.return_value = 100.02
            self.assertEqual(app.render(), "frame")
            self.assertEqual(paint.call_count, 1)
            clock.return_value = 100.12
            app.render()
            self.assertEqual(paint.call_count, 2)
            app.on_action("b")
            app.render()
            self.assertEqual(paint.call_count, 3, "input must invalidate the cached frame")


if __name__ == "__main__":
    unittest.main()
