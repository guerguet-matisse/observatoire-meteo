"""Prévisions sur 7 jours et qualité de l'air via Open-Meteo, avec cache mémoire."""
from __future__ import annotations
import threading
import time
import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "ObservatoireMeteo/2.1 (desktop weather application)"})
_CACHE = {}
_LOCK = threading.Lock()
CACHE_SECONDS = 600

class WeatherServiceError(RuntimeError):
    """Erreur de service météo externe."""

def _get(url: str, params: dict, key: tuple) -> dict:
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and now - cached[0] < CACHE_SECONDS:
            return cached[1]
    try:
        response = _SESSION.get(url, params=params, timeout=12)
        response.raise_for_status()
        payload = response.json()
    except requests.Timeout as exc:
        raise WeatherServiceError("Le service Open-Meteo met trop de temps à répondre.") from exc
    except requests.RequestException as exc:
        raise WeatherServiceError("Impossible de joindre le service Open-Meteo.") from exc
    except ValueError as exc:
        raise WeatherServiceError("Réponse Open-Meteo illisible.") from exc
    if not isinstance(payload, dict):
        raise WeatherServiceError("Format de réponse météo inattendu.")
    with _LOCK:
        _CACHE[key] = (now, payload)
    return payload

def get_forecast(latitude: float, longitude: float) -> dict:
    params = {
        "latitude": latitude, "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,cloud_cover,pressure_msl,wind_speed_10m,wind_direction_10m,wind_gusts_10m",
        "hourly": "temperature_2m,precipitation_probability,precipitation,wind_speed_10m,uv_index",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max,uv_index_max,sunrise,sunset",
        "forecast_days": 7, "timezone": "auto",
    }
    payload = _get(FORECAST_URL, params, ("forecast", round(latitude, 3), round(longitude, 3)))
    if not isinstance(payload.get("current"), dict) or not isinstance(payload.get("daily"), dict):
        raise WeatherServiceError("Prévisions reçues incomplètes.")
    return payload

def get_air_quality(latitude: float, longitude: float) -> dict:
    params = {
        "latitude": latitude, "longitude": longitude,
        "current": "european_aqi,pm2_5,pm10,nitrogen_dioxide,ozone",
        "hourly": "european_aqi,pm2_5,pm10", "forecast_days": 1, "timezone": "auto",
    }
    payload = _get(AIR_URL, params, ("air", round(latitude, 3), round(longitude, 3)))
    if not isinstance(payload.get("current"), dict):
        raise WeatherServiceError("Données de qualité de l'air indisponibles.")
    return payload

def weather_code_label(code: int | None) -> str:
    if code is None: return "Conditions inconnues"
    labels = {0:"Ciel dégagé",1:"Principalement dégagé",2:"Partiellement nuageux",3:"Couvert",
        45:"Brouillard",48:"Brouillard givrant",51:"Bruine faible",53:"Bruine modérée",55:"Bruine dense",
        56:"Bruine verglaçante faible",57:"Bruine verglaçante dense",61:"Pluie faible",63:"Pluie modérée",
        65:"Pluie forte",66:"Pluie verglaçante faible",67:"Pluie verglaçante forte",71:"Neige faible",
        73:"Neige modérée",75:"Neige forte",77:"Grains de neige",80:"Averses faibles",81:"Averses modérées",
        82:"Averses violentes",85:"Averses de neige faibles",86:"Averses de neige fortes",95:"Orage",
        96:"Orage et grêle faible",99:"Orage et grêle forte"}
    return labels.get(int(code), "Conditions variables")

def air_quality_label(aqi: float | None) -> tuple[str, str]:
    if aqi is None: return "Indisponible", "#7f89bd"
    if aqi <= 20: return "Très bonne", "#4cd7a8"
    if aqi <= 40: return "Bonne", "#7fce83"
    if aqi <= 60: return "Moyenne", "#ffd166"
    if aqi <= 80: return "Dégradée", "#ffad66"
    if aqi <= 100: return "Mauvaise", "#ff8a4c"
    return "Très mauvaise", "#ff6b81"
