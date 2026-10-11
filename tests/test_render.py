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

if __name__ == "__main__":
    unittest.main()
