"""RainViewer precipitation radar with a cached OpenStreetMap basemap."""
from __future__ import annotations

from io import BytesIO
import math
import requests
import requests_cache
from PIL import Image

MANIFEST_URL = "https://api.rainviewer.com/public/weather-maps.json"
OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
RADAR_CACHE_SECONDS = 180
RADAR_ZOOM = 7
MAX_FRAMES = 12

_radar_session = requests_cache.CachedSession(
    cache_name="observatoire_radar_api", backend="sqlite",
    expire_after=RADAR_CACHE_SECONDS, cache_control=True,
)
_radar_session.headers.update({"User-Agent": "ObservatoireMeteo/3.0 (desktop weather application)"})
_osm_session = requests_cache.CachedSession(
    cache_name="observatoire_radar_osm", backend="sqlite",
    expire_after=7 * 24 * 60 * 60, cache_control=True,
)
_osm_session.headers.update({"User-Agent": "ObservatoireMeteo/3.0 (desktop application; OSM tile cache)"})

class RadarServiceError(RuntimeError):
    """Erreur de récupération du radar météo."""


def latlon_to_tile(latitude: float, longitude: float, zoom: int = RADAR_ZOOM) -> tuple[float, float]:
    latitude = max(-85.05112878, min(85.05112878, float(latitude)))
    longitude = max(-180.0, min(180.0, float(longitude)))
    scale = 2 ** int(zoom)
    x = (longitude + 180.0) / 360.0 * scale
    lat_rad = math.radians(latitude)
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * scale
    return x, y


def get_radar_manifest() -> dict:
    try:
        response = _radar_session.get(MANIFEST_URL, timeout=12)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RadarServiceError("Le radar RainViewer est momentanément indisponible.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("radar"), dict):
        raise RadarServiceError("Réponse du radar RainViewer invalide.")
    return payload


def _base_map(latitude: float, longitude: float, zoom: int = RADAR_ZOOM) -> Image.Image:
    tile_x, tile_y = latlon_to_tile(latitude, longitude, zoom)
    center_x, center_y = int(tile_x), int(tile_y)
    scale = 2 ** zoom
    mosaic = Image.new("RGB", (768, 768), "#172039")
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            x = (center_x + dx) % scale
            y = max(0, min(scale - 1, center_y + dy))
            try:
                response = _osm_session.get(OSM_TILE_URL.format(z=zoom, x=x, y=y), timeout=12)
                response.raise_for_status()
                tile = Image.open(BytesIO(response.content)).convert("RGB").resize((256, 256))
                mosaic.paste(tile, ((dx + 1) * 256, (dy + 1) * 256))
            except (requests.RequestException, OSError, ValueError) as exc:
                raise RadarServiceError("Impossible de charger le fond OpenStreetMap du radar.") from exc
    center_px = 256 + (tile_x - center_x) * 256
    center_py = 256 + (tile_y - center_y) * 256
    left, top = round(center_px - 256), round(center_py - 256)
    return mosaic.crop((left, top, left + 512, top + 512))


def get_radar_animation(latitude: float, longitude: float, limit: int = MAX_FRAMES) -> list[dict]:
    manifest = get_radar_manifest()
    frames = manifest.get("radar", {}).get("past", [])
    if not frames:
        raise RadarServiceError("Aucune image radar récente n'est disponible.")
    frames = frames[-max(2, min(int(limit), MAX_FRAMES)):]
    base = _base_map(latitude, longitude)
    result = []
    for frame in frames:
        path = str(frame.get("path", "")).rstrip("/")
        if not path:
            continue
        url = f"{manifest['host'].rstrip('/')}{path}/512/{RADAR_ZOOM}/{float(latitude):.5f}/{float(longitude):.5f}/2/1_1.png"
        try:
            response = _radar_session.get(url, timeout=15)
            response.raise_for_status()
            overlay = Image.open(BytesIO(response.content)).convert("RGBA")
            if overlay.size != (512, 512):
                overlay = overlay.resize((512, 512))
            composed = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
            result.append({"time": int(frame["time"]), "image": composed})
        except (requests.RequestException, OSError, ValueError, KeyError):
            continue
    if not result:
        raise RadarServiceError("Les images radar n'ont pas pu être téléchargées.")
    return result
