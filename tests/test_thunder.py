import json
import math
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from auto_update.utils.util_thunder import (
    CHINA_TZ, build_thunder_alert, fetch_thunder_alert, parse_radar_page,
    parse_time, projected_distance_km, settings_from_config,
)


class ThunderTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 20, 12, 5, tzinfo=CHINA_TZ)

    def warning(self, **overrides):
        return {
            "INDENTIFIER": "test-zhongshan", "AREA_CODE": "442000",
            "DISTRICTS_NAME": "中山市", "CATEGORY_CNNAME": "雷雨大风",
            "SEVERITY": "3", "ALERT_TYPE": "2", "PUBLISHDATE": "2026-05-20 12:00:00.0",
            "TITLE": "测试雷雨大风黄色预警", "CONTENT": "测试正文，不是真实预警",
            **overrides,
        }

    def build(self, rows, now=None, settings=None):
        return build_thunder_alert({"DATA": rows}, settings or {}, now or self.now)

    def test_published_anchor_and_fixed_50_projection(self):
        first = self.build([self.warning()])
        later = self.build([self.warning()], self.now + timedelta(minutes=10))
        candidate = first["candidates"][0]
        self.assertTrue(first["enabled"])
        self.assertEqual(candidate["distance_km"], 68.3)
        self.assertEqual(candidate["travel_minutes"], 82)
        self.assertEqual(candidate["estimated_arrival"], "2026-05-20T13:22:00+08:00")
        self.assertEqual(candidate["estimated_arrival"], later["candidates"][0]["estimated_arrival"])
        self.assertEqual(first["event_id"], later["event_id"])

    def test_districts_use_same_city_centre(self):
        candidates = self.build([self.warning(AREA_CODE=code, INDENTIFIER=code)
                                 for code in ("440100", "440113")])["candidates"]
        self.assertEqual(candidates[0]["source_longitude"], 113.2644)
        self.assertEqual(candidates[0]["distance_km"], candidates[1]["distance_km"])

    def test_distance_uses_target_latitude_not_diagonal(self):
        expected = 6371.0088 * math.cos(math.radians(22.5431)) * math.radians(114.0579 - 113.5)
        self.assertAlmostEqual(projected_distance_km(113.5, 22.5431, 114.0579), expected)

    def test_closer_cities_get_higher_distance_confidence(self):
        rows = [self.warning(AREA_CODE=code, INDENTIFIER=code) for code in ("441700", "442000", "441900")]
        candidates = self.build(rows)["candidates"]
        self.assertEqual([c["city"] for c in candidates], ["东莞", "中山", "阳江"])
        self.assertEqual([c["confidence"] for c in candidates], ["较高", "中等", "较低"])

    def test_later_yangjiang_does_not_replace_earlier_zhuhai(self):
        zhuhai = self.warning(AREA_CODE="440400", CATEGORY_CNNAME="雷电", INDENTIFIER="zhuhai",
                             PUBLISHDATE="2026-05-20 11:50:00")
        first = self.build([zhuhai])
        later = self.build([zhuhai, self.warning(AREA_CODE="441700", CATEGORY_CNNAME="雷电",
                                                INDENTIFIER="yangjiang", PUBLISHDATE="2026-05-20 12:04:00")])
        primary = later["candidates"][0]
        self.assertEqual(primary["id"], "zhuhai")
        self.assertEqual(primary["estimated_arrival"], "2026-05-20T12:49:00+08:00")
        self.assertEqual(first["event_id"], later["event_id"])

    def test_latest_active_warning_in_closest_city_across_types_districts(self):
        candidates = self.build([
            self.warning(AREA_CODE="440400", CATEGORY_CNNAME="雷电", INDENTIFIER="old"),
            self.warning(AREA_CODE="440402", CATEGORY_CNNAME="暴雨", INDENTIFIER="new",
                         PUBLISHDATE="2026-05-20 12:04:00"),
        ])["candidates"]
        self.assertEqual(candidates[0]["id"], "new")
        self.assertEqual(candidates[0]["estimated_arrival"], "2026-05-20T13:03:00+08:00")

    def test_newer_cancellation_supersedes_in_any_order(self):
        cancellation = self.warning(SEVERITY="6", PUBLISHDATE="2026-05-20 12:03:00", INDENTIFIER="cancel")
        for rows in ([self.warning(), cancellation], [cancellation, self.warning()]):
            result = self.build(rows)
            self.assertFalse(result["enabled"])
            self.assertEqual(result["audit"]["cancelled"], 1)

    def test_cancelled_nearest_city_falls_back_to_farther_active_city(self):
        result = self.build([self.warning(AREA_CODE="440400", SEVERITY="6"), self.warning()])
        self.assertEqual(result["candidates"][0]["city"], "中山")

    def test_invalid_future_stale_and_unrelated_records(self):
        rows = [self.warning(PUBLISHDATE="broken"),
                self.warning(AREA_CODE="441700", PUBLISHDATE="2026-05-20 03:00:00"),
                self.warning(AREA_CODE="440700", PUBLISHDATE="2026-05-20 13:00:00"),
                self.warning(CATEGORY_CNNAME="森林火险"), self.warning(AREA_CODE="441300")]
        result = self.build(rows)
        self.assertFalse(result["enabled"])
        for field in ("invalid_time", "stale", "future"):
            self.assertEqual(result["audit"][field], 1)
        self.assertEqual(result["audit"]["outside_region_or_type"], 2)

    def test_elapsed_time_not_extended_by_refresh(self):
        result = self.build([self.warning(AREA_CODE="441900", PUBLISHDATE="2026-05-20 10:00:00")])
        self.assertFalse(result["enabled"])
        self.assertEqual(result["audit"]["elapsed_window"], 1)

    def test_far_city_survives_three_hours_without_eta_reset(self):
        row = self.warning(AREA_CODE="441700", PUBLISHDATE="2026-05-20 08:00:00")
        result = self.build([row])
        self.assertTrue(result["enabled"])
        self.assertEqual(result["candidates"][0]["estimated_arrival"], "2026-05-20T12:16:00+08:00")
        self.assertEqual(result["candidates"][0]["expires_at"], "2026-05-20T12:46:00+08:00")

    def test_china_season_boundaries_even_on_utc_runner(self):
        for now, expected in (
            (datetime(2026, 2, 28, 15, 59, tzinfo=timezone.utc), "outside_season"),
            (datetime(2026, 2, 28, 16, 0, tzinfo=timezone.utc), "no_recent_candidate"),
            (datetime(2026, 5, 31, 15, 59, tzinfo=timezone.utc), "no_recent_candidate"),
            (datetime(2026, 5, 31, 16, 0, tzinfo=timezone.utc), "outside_season"),
        ):
            self.assertEqual(self.build([], now)["status"], expected)

    def test_collect_all_year_and_manual_modes(self):
        october = datetime(2026, 10, 12, 12, 5, tzinfo=CHINA_TZ)
        row = self.warning(PUBLISHDATE="2026-10-12 12:00:00")
        self.assertFalse(self.build([row], october)["enabled"])
        self.assertEqual(len(self.build([row], october)["candidates"]), 1)
        self.assertTrue(self.build([row], october, {"default_mode": "on"})["enabled"])
        self.assertFalse(self.build([self.warning()], settings={"default_mode": "off"})["enabled"])
        with patch("auto_update.utils.util_thunder._read_url", return_value=json.dumps({"DATA": []})) as fetch:
            fetch_thunder_alert({}, Mock(), october)
            fetch.assert_called_once()

    def test_schema_source_and_invalid_settings_fail_closed(self):
        with self.assertRaises(ValueError):
            self.build([None])
        with patch("auto_update.utils.util_thunder._read_url", side_effect=OSError("offline")):
            self.assertEqual(fetch_thunder_alert({}, Mock(), self.now)["status"], "source_error")
        for settings in ({"speed_kmh": 60}, {"default_mode": "bad"}, {"data_ttl_minutes": -1}):
            with self.assertRaises(ValueError):
                settings_from_config(settings)
            self.assertFalse(fetch_thunder_alert(settings, Mock(), self.now)["enabled"])

    def test_radar_utc_time_freshness_and_domain(self):
        html = '<img id=imgpath src="https://image.nmc.cn/product/2026/05/20/RDCP/SEVP_AOC_RDCP_SLDAS3_ECREF_ASCN_L88_PI_20260520040000000.PNG?v=1">'
        self.assertEqual(parse_radar_page(html, self.now)["observed_at"], "2026-05-20T12:00:00+08:00")
        with self.assertRaises(ValueError):
            parse_radar_page(html, self.now + timedelta(hours=1))
        with self.assertRaises(ValueError):
            parse_radar_page(html.replace("image.nmc.cn", "invalid.example"), self.now)

    def test_validity_does_not_exceed_primary_expiry(self):
        result = self.build([self.warning()], self.now + timedelta(minutes=60))
        self.assertLessEqual(parse_time(result["valid_until"]), parse_time(result["candidates"][0]["expires_at"]))

    def test_zero_countdown_keeps_30_minute_grace(self):
        before = self.build([self.warning()], datetime(2026, 5, 20, 13, 21, 59, tzinfo=CHINA_TZ))
        at_zero = self.build([self.warning()], datetime(2026, 5, 20, 13, 22, tzinfo=CHINA_TZ))
        self.assertTrue(before["enabled"])
        self.assertEqual(before["candidates"][0]["expires_at"], "2026-05-20T13:52:00+08:00")
        self.assertTrue(at_zero["enabled"])
        at_expiry = self.build([self.warning()], datetime(2026, 5, 20, 13, 52, tzinfo=CHINA_TZ))
        self.assertFalse(at_expiry["enabled"])


if __name__ == "__main__":
    unittest.main()
