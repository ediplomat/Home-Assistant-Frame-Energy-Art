"""Checks for the built-in update schedule (no Home Assistant needed)."""
import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("frame_schedule", ROOT / "custom_components/frame_energy/schedule.py")
schedule = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schedule)

NOW = datetime(2026, 10, 17, 19, 0, 30, tzinfo=timezone.utc)


class ScheduleTests(unittest.TestCase):
    def test_interval_values(self):
        self.assertEqual(schedule.interval_minutes("15"), 15)
        self.assertEqual(schedule.interval_minutes(5), 5)
        self.assertIsNone(schedule.interval_minutes("manual"))
        self.assertIsNone(schedule.interval_minutes(None))
        self.assertIsNone(schedule.interval_minutes("0"))

    def test_runs_line_up_with_the_clock(self):
        self.assertEqual(schedule.schedule_minutes(15), [0, 15, 30, 45])
        self.assertEqual(schedule.schedule_minutes(60), [0])
        self.assertEqual(schedule.schedule_minutes(5), list(range(0, 60, 5)))

    def test_first_update_runs(self):
        self.assertFalse(schedule.should_skip(False, None, NOW, 15))

    def test_skips_while_another_update_runs(self):
        self.assertTrue(schedule.should_skip(True, None, NOW, 15))

    def test_skips_when_an_automation_just_made_a_picture(self):
        # The user's automation ran at 19:00:00; the schedule runs at 19:00:30.
        self.assertTrue(schedule.should_skip(False, NOW - timedelta(seconds=30), NOW, 15))

    def test_runs_when_the_last_picture_is_old_enough(self):
        self.assertFalse(schedule.should_skip(False, NOW - timedelta(minutes=15), NOW, 15))
        self.assertFalse(schedule.should_skip(False, NOW - timedelta(minutes=8), NOW, 15))


if __name__ == "__main__":
    unittest.main()
