"""Modèles Pydantic : validation des données entrantes (Jour 1) et sortantes (Jour 3)."""
from pydantic import BaseModel, Field


# ---------- Jour 1 : données reçues d'Open-Meteo ----------
class CurrentWeather(BaseModel):
    time: str                      # ex. "2026-11-02T10:00"
    temperature_2m: float          # °C
    wind_speed_10m: float          # km/h


class WeatherResponseModel(BaseModel):
    latitude: float
    longitude: float
    current: CurrentWeather


class GeocodingResult(BaseModel):
    name: str
    latitude: float
    longitude: float


# ---------- Jour 3 : données renvoyées par notre API ----------
class VilleOut(BaseModel):
    id: int
    nom: str
    latitude: float
    longitude: float


class ReleveOut(BaseModel):
    id: int
    ville: str
    temperature: float = Field(description="Température en °C")
    vitesse_vent: float = Field(description="Vitesse du vent en km/h")
    date_heure: str


class StatsOut(BaseModel):
    ville: str
    nb_releves: int
    temperature_moyenne: float
    temperature_min: float
    temperature_max: float
    vent_moyen: float
