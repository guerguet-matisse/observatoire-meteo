"""Jour 1 : client HTTP robuste (session, timeout, gestion d'erreurs) + validation Pydantic.
Jour 5 : chaque appel est mesuré (latence + erreurs) pour Prometheus."""
import time

import requests
from pydantic import ValidationError

from metrics import OPENMETEO_ERRORS, OPENMETEO_LATENCY
from models import GeocodingResult, WeatherResponseModel

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
TIMEOUT = 10  # secondes

session = requests.Session()
session.headers.update({"User-Agent": "observatoire-meteo/1.0"})


class ApiError(Exception):
    """Erreur lors de l'appel à l'API externe ou données invalides."""


def _get_json(url: str, params: dict, endpoint: str) -> dict:
    t0 = time.perf_counter()
    try:
        r = session.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()          # lève HTTPError pour 4xx / 5xx
        return r.json()
    except requests.Timeout as e:
        OPENMETEO_ERRORS.labels(endpoint).inc()
        raise ApiError("Délai dépassé en appelant l'API") from e
    except requests.HTTPError as e:
        OPENMETEO_ERRORS.labels(endpoint).inc()
        raise ApiError(f"Erreur HTTP {e.response.status_code}") from e
    except requests.RequestException as e:
        OPENMETEO_ERRORS.labels(endpoint).inc()
        raise ApiError(f"Erreur réseau : {e}") from e
    except ValueError as e:
        OPENMETEO_ERRORS.labels(endpoint).inc()
        raise ApiError("Réponse non JSON") from e
    finally:
        OPENMETEO_LATENCY.labels(endpoint).observe(time.perf_counter() - t0)


def geocoder(nom: str) -> GeocodingResult:
    """Trouve les coordonnées d'une ville."""
    data = _get_json(GEOCODING_URL, {"name": nom, "count": 1, "language": "fr"}, "geocoding")
    resultats = data.get("results")
    if not resultats:
        raise ApiError(f"Ville introuvable : {nom}")
    try:
        return GeocodingResult(**resultats[0])
    except ValidationError as e:
        OPENMETEO_ERRORS.labels("geocoding").inc()
        raise ApiError(f"Données de géocodage invalides : {e}") from e


def get_weather(latitude: float, longitude: float) -> WeatherResponseModel:
    """Récupère la météo actuelle (heure locale de la ville) et la valide avec Pydantic."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,wind_speed_10m",
        "timezone": "auto",
    }
    data = _get_json(FORECAST_URL, params, "forecast")
    try:
        return WeatherResponseModel(**data)
    except ValidationError as e:
        OPENMETEO_ERRORS.labels("forecast").inc()
        raise ApiError(f"Données météo invalides : {e}") from e


if __name__ == "__main__":
    ville = geocoder("Saint-Quentin")
    meteo = get_weather(ville.latitude, ville.longitude)
    print(meteo.model_dump_json(indent=2))
