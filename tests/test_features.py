"""Offline unit tests for the weather feature helpers and SQLite history query."""
import os
import tempfile
import unittest
from unittest.mock import patch

import database
import weather_features


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


if __name__ == "__main__":
    unittest.main()
