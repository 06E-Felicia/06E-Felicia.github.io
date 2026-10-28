"""Admin workflow modes persist centrally; all I/O is isolated in mocks."""
import contextlib
import io
import os
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from auto_update import updater
from auto_update.utils.util_thunder import CHINA_TZ, apply_monitor_mode, build_thunder_alert


class BackendModeTests(unittest.TestCase):
    def test_choices_and_keep_do_not_mutate_original(self):
        original = {"default_mode": "off", "arrival_grace_minutes": 30}
        for requested, expected in (
            ("keep", "off"), ("保持当前设置", "off"),
            ("自动（3–5 月）", "auto"), ("开启", "on"), ("关闭", "off"),
            ("auto", "auto"), ("on", "on"), ("off", "off"),
        ):
            settings = apply_monitor_mode(original, requested)
            self.assertEqual(settings["default_mode"], expected)
            self.assertEqual(settings["speed_kmh"], 50)
            self.assertEqual(settings["arrival_grace_minutes"], 30)
            self.assertEqual(settings["max_warning_age_hours"], 6)
            self.assertEqual(original["default_mode"], "off")
        self.assertEqual(apply_monitor_mode({}, "keep")["default_mode"], "auto")
        with self.assertRaises(ValueError):
            apply_monitor_mode(original, "invalid-input")

    def test_admin_choice_survives_later_scheduled_runs(self):
        data = {"THUNDER_MONITOR_CONFIG": {"default_mode": "auto"},
                "ALERT_CONFIG": {"enabled": True, "title": "isolated official warning"}}
        service = Mock()
        service.get_value.side_effect = lambda key, default: data.get(key, default)
        service.set_values.side_effect = data.update
        now = datetime(2026, 10, 13, 12, 5, tzinfo=CHINA_TZ)
        feed = {"DATA": [{"AREA_CODE": "440400", "CATEGORY_CNNAME": "雷电",
                          "ALERT_TYPE": "2", "SEVERITY": "3", "INDENTIFIER": "isolated",
                          "PUBLISHDATE": "2026-10-13 12:00:00", "CONTENT": "test only"}]}
        with patch.object(updater, "LoggingService", return_value=Mock()), \
                patch.object(updater, "ConfigurationService", return_value=service), \
                patch.object(updater, "fetch_shenzhen_weather", side_effect=OSError("isolated source outage")), \
                patch.object(updater, "fetch_thunder_alert", side_effect=lambda settings, logger:
                             build_thunder_alert(feed, settings, now)), \
                contextlib.redirect_stdout(io.StringIO()):
            for requested, expected, enabled in (
                ("关闭", "off", False), (None, "off", False),
                ("开启", "on", True), (None, "on", True),
                ("自动（3–5 月）", "auto", False), (None, "auto", False),
            ):
                with patch.dict(os.environ, {}, clear=True):
                    if requested is not None:
                        os.environ["THUNDER_MONITOR_MODE"] = requested
                    updater.main()
                self.assertEqual(data["THUNDER_MONITOR_CONFIG"]["default_mode"], expected)
                self.assertEqual(data["THUNDER_ALERT_CONFIG"]["settings"]["default_mode"], expected)
                self.assertEqual(data["THUNDER_ALERT_CONFIG"]["enabled"], enabled)
                self.assertEqual(data["ALERT_CONFIG"]["enabled"], True)
                if not enabled:
                    self.assertEqual(data["THUNDER_ALERT_CONFIG"]["candidates"], [])

    def test_invalid_choice_never_writes(self):
        service = Mock()
        service.get_value.return_value = {"default_mode": "auto"}
        with patch.object(updater, "LoggingService", return_value=Mock()), \
                patch.object(updater, "ConfigurationService", return_value=service), \
                patch.dict(os.environ, {"THUNDER_MONITOR_MODE": "unknown"}):
            with self.assertRaises(ValueError):
                updater.main()
        service.set_values.assert_not_called()


if __name__ == "__main__":
    unittest.main()
