"""Renderer checks independent of a running Home Assistant instance."""
import importlib.util
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("art_renderer", ROOT / "custom_components/frame_energy/render.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)

class RendererTests(unittest.TestCase):
    def test_power_units_and_invalid_values(self):
        for value, unit, expected in [(1500, "W", 1.5), (1.5, "kW", 1.5), (1, "MW", None), ("NaN", "W", None)]:
            state = {"solar": {"state": str(value), "attributes": {"unit_of_measurement": unit}}}
            self.assertEqual(renderer.numeric(state, "solar", True), expected)
        self.assertIsNone(renderer.numeric({"battery": {"state": "101"}}, "battery"))
        self.assertIsNone(renderer.numeric({}, "solar", True))

    def test_render_with_missing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "art.jpg"
            renderer.render(ROOT / "assets/tuscan_background.jpg", output, {}, [], datetime(2026, 1, 1, tzinfo=timezone.utc))
            with Image.open(output) as result:
                self.assertEqual(result.size, (1920, 1080))
                self.assertEqual(result.format, "JPEG")
            self.assertEqual(list(Path(tmp).glob(".frame_energy_*")), [])

    def test_column_width_stays_inside_frame(self):
        self.assertEqual(renderer.column_width(710), 245)
        self.assertLessEqual(1800 + renderer.column_width(1800) / 2, renderer.RIGHT_EDGE)

    def test_custom_labels_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "art.jpg"
            renderer.render(ROOT / "assets/tuscan_background.jpg", output, {}, [], datetime(2026, 1, 1, tzinfo=timezone.utc),
                            {"vehicle1_name": "Volkswagen ID.Buzz Long Range", "vehicle1_letter": "V", "location_name": ""})
            self.assertTrue(output.is_file())

    def test_two_cars_keep_original_layout(self):
        self.assertEqual(renderer.column_positions(5), [710, 990, 1270, 1540, 1800])

    def test_fewer_columns_are_centred_and_inside_frame(self):
        for count in (3, 4):
            xs = renderer.column_positions(count)
            self.assertAlmostEqual((xs[0] + xs[-1]) / 2, renderer.COLUMN_CENTRE, delta=1)
            self.assertLessEqual(xs[-1] + renderer.column_width(xs[-1]) / 2, renderer.RIGHT_EDGE)

    def test_one_car_and_no_car_render(self):
        snapshot = {"tesla": {"state": "64"}, "hyundai": {"state": "81"}}
        with tempfile.TemporaryDirectory() as tmp:
            for cars in (["tesla"], ["hyundai"], []):
                output = Path(tmp) / f"art_{len(cars)}.jpg"
                renderer.render(ROOT / "assets/tuscan_background.jpg", output, snapshot, [],
                                datetime(2026, 1, 1, tzinfo=timezone.utc), cars=cars)
                self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
