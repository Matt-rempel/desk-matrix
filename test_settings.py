from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from settings import CALGARY_TIME, Settings, effective_brightness, load_settings, save_settings, validate_settings


class SettingsTests(unittest.TestCase):
    def test_new_fields_defaults_and_round_trip(self):
        value = Settings()
        self.assertEqual((value.temp_unit, value.distance_unit, value.brightness_follow_lineup,
                          value.brightness_max, value.night_palette, value.calendar_ics_url),
                         ("C", "nm", True, 100, False, ""))
        value = validate_settings({"temp_unit": "F", "distance_unit": "km", "brightness_max": 40,
                                   "brightness_follow_lineup": False, "night_palette": True,
                                   "calendar_ics_url": " https://cal.example.com/basic.ics "})
        self.assertEqual(value.calendar_ics_url, "https://cal.example.com/basic.ics")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_settings(value, path)
            self.assertEqual(load_settings(path), value)
            # Files written before these fields existed still load.
            path.write_text('{"brightness": 55, "mode": "clock", "clock_screen_id": "clock-simple"}')
            self.assertEqual(load_settings(path).temp_unit, "C")

    def test_new_fields_are_validated(self):
        bad = [{"temp_unit": "K"}, {"distance_unit": "mi"}, {"brightness_max": 0},
               {"brightness_max": 101}, {"brightness_max": 50.5}, {"brightness_follow_lineup": 1},
               {"night_palette": "on"}, {"calendar_ics_url": "webcal://x/y.ics"},
               {"calendar_ics_url": "https://" + "a" * 510}, {"calendar_ics_url": "https://x/a b"},
               {"calendar_ics_url": "https://x:99999/"}, {"calendar_ics_url": None}]
        for data in bad:
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_settings(data)

    def test_effective_brightness(self):
        noon = datetime(2026, 10, 8, 12, 0, tzinfo=CALGARY_TIME)
        night = datetime(2026, 10, 8, 23, 0, tzinfo=CALGARY_TIME)
        value = validate_settings({"brightness": 85, "night_enabled": True, "night_brightness": 30})
        self.assertEqual(effective_brightness(value, noon), 85)
        self.assertEqual(effective_brightness(value, night), 30)
        self.assertEqual(effective_brightness(value, night, moment_brightness=60), 60)
        self.assertEqual(effective_brightness(value, noon, moment_brightness=None), 85)
        ignore = validate_settings({"brightness": 85, "brightness_follow_lineup": False})
        self.assertEqual(effective_brightness(ignore, noon, moment_brightness=10), 85)
        capped = validate_settings({"brightness": 85, "brightness_max": 50})
        self.assertEqual(effective_brightness(capped, noon), 50)
        self.assertEqual(effective_brightness(capped, noon, moment_brightness=90), 50)
        self.assertEqual(effective_brightness(capped, noon, moment_brightness=20), 20)


if __name__ == "__main__":
    unittest.main()
