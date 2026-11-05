"""API FastAPI : endpoints météo (Jour 3) + métriques Prometheus (Jour 5).

Swagger : http://127.0.0.1:8000/docs     Métriques : http://127.0.0.1:8000/metrics
"""
import asyncio
import logging
import os
import sqlite3
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator

import client
import database
import pipeline
from models import ReleveOut, StatsOut, VilleOut

log = logging.getLogger("observatoire")

# Collecte automatique en arrière-plan (désactivée si COLLECT_INTERVAL_MIN=0)
COLLECT_INTERVAL_MIN = float(os.environ.get("COLLECT_INTERVAL_MIN", "0"))
COLLECT_CITIES = [c.strip() for c in os.environ.get("COLLECT_CITIES", "").split(",") if c.strip()]


async def collecteur():
    while True:
        for nom in COLLECT_CITIES:
            try:
                await asyncio.to_thread(pipeline.collecter_ville, nom)
            except client.ApiError as e:
                log.warning("Collecte de %s en échec : %s", nom, e)
            except Exception:                                   # noqa: BLE001
                log.exception("Erreur inattendue pendant la collecte de %s", nom)
        await asyncio.sleep(COLLECT_INTERVAL_MIN * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    task = None
    if COLLECT_INTERVAL_MIN > 0 and COLLECT_CITIES:
        task = asyncio.create_task(collecteur())
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="L'Observatoire Météo",
    description="Collecte la météo via Open-Meteo, la stocke dans SQLite et l'expose via une API documentée et observable.",
    version="2.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------- observabilité
Instrumentator(excluded_handlers=["/metrics", "/health"]).instrument(app).expose(
    app, endpoint="/metrics", include_in_schema=False
)


def _scalar(sql: str) -> float:
    try:
        conn = database.get_connection()
        try:
            return conn.execute(sql).fetchone()[0] or 0
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


Gauge("meteo_releves_count", "Nombre de relevés stockés dans SQLite").set_function(
    lambda: _scalar("SELECT COUNT(*) FROM releves"))
Gauge("meteo_villes_count", "Nombre de villes suivies").set_function(
    lambda: _scalar("SELECT COUNT(*) FROM villes"))
Gauge("meteo_db_size_bytes", "Taille du fichier SQLite").set_function(
    lambda: os.path.getsize(database.DB_PATH) if os.path.exists(database.DB_PATH) else 0)


# ---------------------------------------------------------------- routes
def get_db():
    conn = database.get_connection()
    try:
        yield conn
    finally:
        conn.close()


@app.get("/health", tags=["Système"])
def health():
    """Sonde de santé (utilisée par Docker)."""
    return {"status": "ok"}


@app.get("/villes", response_model=list[VilleOut], tags=["Villes"])
def lister_villes(conn=Depends(get_db)):
    """Liste des villes suivies (avec coordonnées)."""
    return [dict(r) for r in database.lister_villes(conn)]


@app.get("/meteo/{ville}", response_model=list[ReleveOut], tags=["Météo"])
def meteo_ville(
    ville: str,
    limite: int = Query(50, ge=1, le=500),
    debut: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Date de début (YYYY-MM-DD)"),
    fin: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Date de fin (YYYY-MM-DD)"),
    conn=Depends(get_db),
):
    """Derniers relevés d'une ville, filtrables par période (404 si aucune donnée)."""
    rows = database.releves_ville(conn, ville, limite, debut, fin)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Aucun relevé pour « {ville} »")
    return [dict(r) for r in rows]


@app.get("/meteo/{ville}/stats", response_model=StatsOut, tags=["Météo"])
def stats(ville: str, conn=Depends(get_db)):
    """Statistiques simples (moyenne, min, max) pour une ville."""
    s = database.stats_ville(conn, ville)
    if s is None:
        raise HTTPException(status_code=404, detail=f"Aucun relevé pour « {ville} »")
    return dict(s)


@app.post("/meteo/{ville}/actualiser", status_code=201, tags=["Météo"])
def actualiser(ville: str):
    """Interroge Open-Meteo et enregistre un nouveau relevé."""
    try:
        nom, nouveau = pipeline.collecter_ville(ville)
    except client.ApiError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"ville": nom, "nouveau_releve": nouveau}
