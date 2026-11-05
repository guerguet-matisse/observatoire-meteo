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


def build_alerts(forecast: dict, air: dict | None = None) -> list[dict]:
    """Construit des alertes indicatives à partir des prévisions, pas des vigilances officielles."""
    alerts: list[dict] = []
    current = forecast.get("current", {}) if isinstance(forecast, dict) else {}
    hourly = forecast.get("hourly", {}) if isinstance(forecast, dict) else {}
    daily = forecast.get("daily", {}) if isinstance(forecast, dict) else {}

    def number(value):
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def add(code, validity, severity, title, message):
        alerts.append({"code": code, "validity": str(validity), "severity": severity,
                       "title": title, "message": message})

    gust = number(current.get("wind_gusts_10m"))
    wind = number(current.get("wind_speed_10m"))
    temp = number(current.get("temperature_2m"))
    if gust is not None and gust >= 85:
        add("gust", "now", "danger" if gust >= 100 else "warning",
            "Rafales violentes", f"Rafales actuellement estimées à {gust:.0f} km/h.")
    elif wind is not None and wind >= 65:
        add("wind-now", "now", "warning", "Vent fort",
            f"Vent actuellement estimé à {wind:.0f} km/h.")
    if temp is not None and temp <= 0:
        add("frost-now", "now", "watch", "Risque de gel",
            f"Température actuelle : {temp:.1f} °C.")
    elif temp is not None and temp >= 35:
        add("heat-now", "now", "warning", "Forte chaleur",
            f"Température actuelle : {temp:.1f} °C.")

    hours = hourly.get("time", [])
    rain_probs = hourly.get("precipitation_probability", [])
    for index, probability in enumerate(rain_probs[:3]):
        value = number(probability)
        if value is not None and value >= 80:
            hour = hours[index] if index < len(hours) else f"heure-{index}"
            add("rain-hour", hour, "warning", "Pluie probable prochainement",
                f"Probabilité de précipitations : {value:.0f} % vers {str(hour).replace('T', ' ')}.")
            break

    days = daily.get("time", [])
    for index, day in enumerate(days):
        def day_value(key):
            values = daily.get(key, [])
            return number(values[index]) if index < len(values) else None
        max_wind = day_value("wind_speed_10m_max")
        rain = day_value("precipitation_probability_max")
        uv = day_value("uv_index_max")
        minimum = day_value("temperature_2m_min")
        maximum = day_value("temperature_2m_max")
        if max_wind is not None and max_wind >= 80:
            add("wind-day", day, "danger" if max_wind >= 100 else "warning",
                "Vent fort prévu", f"Vent maximal prévu : {max_wind:.0f} km/h le {day}.")
        if rain is not None and rain >= 90:
            add("rain-day", day, "watch", "Fort risque de pluie",
                f"Probabilité maximale de pluie : {rain:.0f} % le {day}.")
        if uv is not None and uv >= 8:
            add("uv", day, "watch", "Indice UV élevé",
                f"Indice UV maximal prévu : {uv:.0f} le {day}.")
        if minimum is not None and minimum <= -2:
            add("frost-day", day, "watch", "Gel possible",
                f"Température minimale prévue : {minimum:.1f} °C le {day}.")
        if maximum is not None and maximum >= 35:
            add("heat-day", day, "warning", "Forte chaleur prévue",
                f"Température maximale prévue : {maximum:.1f} °C le {day}.")

    air_current = air.get("current", {}) if isinstance(air, dict) else {}
    aqi = number(air_current.get("european_aqi"))
    if aqi is not None and aqi > 100:
        add("air-quality", "today", "warning", "Qualité de l'air très dégradée",
            f"Indice européen de qualité de l'air : {aqi:.0f}.")
    order = {"danger": 0, "warning": 1, "watch": 2}
    return sorted(alerts, key=lambda item: order.get(item["severity"], 3))
