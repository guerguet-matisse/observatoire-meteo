"""Offline unit tests for the weather feature helpers and SQLite history query."""
import os
import tempfile
import unittest
from unittest.mock import patch

import database
import weather_features
import radar_service


class WeatherFeatureTests(unittest.TestCase):
    def test_weather_code_labels(self):
        self.assertEqual(weather_features.weather_code_label(0), "Ciel dégagé")
        self.assertEqual(weather_features.weather_code_label(95), "Orage")
        self.assertEqual(weather_features.weather_code_label(None), "Conditions inconnues")

    def test_air_quality_thresholds(self):
        self.assertEqual(weather_features.air_quality_label(12)[0], "Très bonne")
        self.assertEqual(weather_features.air_quality_label(55)[0], "Moyenne")
        self.assertEqual(weather_features.air_quality_label(110)[0], "Très mauvaise")
        self.assertEqual(weather_features.air_quality_label(None)[0], "Indisponible")

    def test_alert_builder_detects_rain_and_wind(self):
        forecast = {
            "current": {"wind_gusts_10m": 92, "temperature_2m": 12},
            "hourly": {"time": ["2026-11-05T19:00"], "precipitation_probability": [90]},
            "daily": {"time": ["2026-11-06"], "wind_speed_10m_max": [82],
                      "precipitation_probability_max": [95], "uv_index_max": [3],
                      "temperature_2m_min": [6], "temperature_2m_max": [18]},
        }
        alerts = weather_features.build_alerts(forecast)
        codes = {item["code"] for item in alerts}
        self.assertIn("gust", codes)
        self.assertIn("rain-hour", codes)
        self.assertIn("wind-day", codes)
        self.assertIn("rain-day", codes)

    def test_alert_builder_detects_air_quality(self):
        alerts = weather_features.build_alerts({}, {"current": {"european_aqi": 125}})
        self.assertEqual(alerts[0]["code"], "air-quality")

    def test_radar_tile_coordinates_are_bounded(self):
        x, y = radar_service.latlon_to_tile(49.38, 3.32, 7)
        self.assertGreaterEqual(x, 0)
        self.assertLess(x, 128)
        self.assertGreaterEqual(y, 0)
        self.assertLess(y, 128)

    def test_history_query_uses_existing_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "test_meteo.db")
            with patch.object(database, "DB_PATH", path):
                database.init_db()
                with database.get_connection() as conn:
                    city_id = database.get_or_create_ville(conn, "Soissons", 49.38, 3.32)
                    database.insert_releve(conn, city_id, 12.5, 18.0, "2026-11-05T12:00")
                    rows = database.historique_ville(conn, "Soissons", 365, 20)
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["ville"], "Soissons")
                    self.assertAlmostEqual(rows[0]["temperature"], 12.5)
                    self.assertTrue(database.register_alert_once(
                        "Soissons|rain-day|2026-11-06", "Soissons", "rain-day",
                        "Pluie", "Pluie probable", "watch", "2026-11-05T18:00"))
                    self.assertFalse(database.register_alert_once(
                        "Soissons|rain-day|2026-11-06", "Soissons", "rain-day",
                        "Pluie", "Pluie probable", "watch", "2026-11-05T18:01"))
                    self.assertEqual(len(database.recent_alerts()), 1)
                    database.set_setting("windows_alerts", "1")
                    self.assertEqual(database.get_setting("windows_alerts"), "1")


if __name__ == "__main__":
    unittest.main()
