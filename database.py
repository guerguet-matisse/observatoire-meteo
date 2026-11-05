"""Jour 2 : base SQLite (création des tables, insertions, lectures)."""
import os
import sqlite3
import sys
from datetime import datetime, timedelta

# La base est stockée à côté du .exe (ou du script), quel que soit le dossier de lancement.
BASE_DIR = (
    os.path.dirname(sys.executable)
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)
DB_PATH = os.environ.get("METEO_DB_PATH") or os.path.join(BASE_DIR, "meteo.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS villes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nom       TEXT NOT NULL UNIQUE,
    latitude  REAL NOT NULL,
    longitude REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS releves (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ville_id     INTEGER NOT NULL REFERENCES villes(id),
    temperature  REAL NOT NULL,
    vitesse_vent REAL NOT NULL,
    date_heure   TEXT NOT NULL,
    UNIQUE (ville_id, date_heure)
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)


def get_or_create_ville(conn, nom: str, latitude: float, longitude: float) -> int:
    row = conn.execute("SELECT id FROM villes WHERE nom = ?", (nom,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO villes (nom, latitude, longitude) VALUES (?, ?, ?)",
        (nom, latitude, longitude),
    )
    return cur.lastrowid


def insert_releve(conn, ville_id: int, temperature: float, vitesse_vent: float, date_heure: str) -> bool:
    """Insère un relevé. Renvoie False s'il existait déjà (même ville + même heure)."""
    cur = conn.execute(
        """INSERT OR IGNORE INTO releves (ville_id, temperature, vitesse_vent, date_heure)
           VALUES (?, ?, ?, ?)""",
        (ville_id, temperature, vitesse_vent, date_heure),
    )
    return cur.rowcount == 1


# ---------- Lectures ----------
def lister_villes(conn):
    return conn.execute("SELECT id, nom, latitude, longitude FROM villes ORDER BY nom").fetchall()


def releves_ville(conn, nom: str, limite: int = 50, debut: str | None = None, fin: str | None = None):
    """Derniers relevés d'une ville (du plus récent au plus ancien), filtrables par date (YYYY-MM-DD)."""
    sql = """SELECT r.id, v.nom AS ville, r.temperature, r.vitesse_vent, r.date_heure
             FROM releves r JOIN villes v ON v.id = r.ville_id
             WHERE v.nom = ? COLLATE NOCASE"""
    params: list = [nom]
    if debut:
        sql += " AND r.date_heure >= ?"
        params.append(debut)
    if fin:
        sql += " AND r.date_heure <= ?"
        params.append(fin + "T23:59:59")
    sql += " ORDER BY r.date_heure DESC LIMIT ?"
    params.append(limite)
    return conn.execute(sql, params).fetchall()


def stats_ville(conn, nom: str):
    return conn.execute(
        """SELECT v.nom AS ville,
                  COUNT(r.id)          AS nb_releves,
                  AVG(r.temperature)   AS temperature_moyenne,
                  MIN(r.temperature)   AS temperature_min,
                  MAX(r.temperature)   AS temperature_max,
                  AVG(r.vitesse_vent)  AS vent_moyen
           FROM villes v JOIN releves r ON r.ville_id = v.id
           WHERE v.nom = ? COLLATE NOCASE
           GROUP BY v.id""",
        (nom,),
    ).fetchone()


def historique_ville(conn, nom: str, jours: int = 7, limite: int = 5000):
    """Retourne les relevés récents d'une ville, du plus récent au plus ancien."""
    jours = max(1, min(int(jours), 365))
    limite = max(1, min(int(limite), 10000))
    debut = (datetime.now() - timedelta(days=jours)).isoformat(timespec="minutes")
    return conn.execute(
        """SELECT r.id, v.nom AS ville, r.temperature, r.vitesse_vent, r.date_heure
           FROM releves r JOIN villes v ON v.id = r.ville_id
           WHERE v.nom = ? COLLATE NOCASE AND r.date_heure >= ?
           ORDER BY r.date_heure DESC LIMIT ?""",
        (nom, debut, limite),
    ).fetchall()
