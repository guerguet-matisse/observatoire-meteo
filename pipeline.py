"""Jour 2 : pipeline complet API -> validation Pydantic -> SQLite, puis statistiques."""
import sys

import client
import database
import metrics


def collecter_ville(nom_ville: str) -> tuple[str, bool]:
    """Interroge l'API, valide, insère. Renvoie (nom officiel de la ville, nouveau relevé ajouté ?)."""
    ville = client.geocoder(nom_ville)
    meteo = client.get_weather(ville.latitude, ville.longitude)

    with database.get_connection() as conn:   # commit automatique si pas d'erreur
        ville_id = database.get_or_create_ville(conn, ville.name, ville.latitude, ville.longitude)
        nouveau = database.insert_releve(
            conn,
            ville_id,
            meteo.current.temperature_2m,
            meteo.current.wind_speed_10m,
            meteo.current.time,
        )
    if nouveau:
        metrics.RELEVES_INSERTED.inc()
    return ville.name, nouveau


def collecter(nom_ville: str) -> bool:
    """Version simple : renvoie True si un nouveau relevé a été ajouté."""
    return collecter_ville(nom_ville)[1]


def afficher_stats(nom_ville: str) -> None:
    with database.get_connection() as conn:
        s = database.stats_ville(conn, nom_ville)
    if s is None:
        print(f"Aucune donnée pour {nom_ville}")
        return
    print(
        f"{s['ville']} : {s['nb_releves']} relevé(s) | "
        f"T moy {s['temperature_moyenne']:.1f} °C "
        f"(min {s['temperature_min']:.1f} / max {s['temperature_max']:.1f}) | "
        f"vent moy {s['vent_moyen']:.1f} km/h"
    )


if __name__ == "__main__":
    database.init_db()
    villes = sys.argv[1:] or ["Saint-Quentin", "Paris", "Lille"]
    for nom in villes:
        try:
            nouveau = collecter(nom)
            print(f"{nom} : {'nouveau relevé enregistré' if nouveau else 'relevé déjà présent'}")
            afficher_stats(nom)
        except client.ApiError as e:
            print(f"{nom} : échec ({e})")
