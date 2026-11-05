# L'Observatoire Météo

Open-Meteo → requests + Pydantic → SQLite → FastAPI (Swagger) → Dashboard Streamlit → Prometheus + Grafana.

## Tout lancer avec Docker (recommandé)
```bash
docker compose up --build
```
| Service | URL | Rôle |
|---|---|---|
| API FastAPI + Swagger | http://localhost:8000/docs | endpoints météo |
| Métriques Prometheus | http://localhost:8000/metrics | exposées par l'API |
| Dashboard Streamlit | http://localhost:8501 | interface utilisateur |
| Prometheus | http://localhost:9090 | collecte des métriques |
| Grafana | http://localhost:3000 (admin / admin) | dashboard « Observatoire Météo » déjà provisionné |

L'API collecte automatiquement Saint-Quentin, Paris et Lille toutes les 15 minutes
(variables `COLLECT_CITIES` / `COLLECT_INTERVAL_MIN` dans `docker-compose.yml`).
Arrêt : `docker compose down` (ajoute `-v` pour effacer les données).

## Sans Docker
```bash
pip install -r requirements.txt
uvicorn main:app --reload                 # API  -> http://127.0.0.1:8000/docs
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py            # Dashboard -> http://localhost:8501
python gui.py                             # Interface CustomTkinter
python pipeline.py Paris Lille            # collecte en ligne de commande
```
`build_exe.bat` (Windows) crée `ObservatoireMeteo.exe` à partir de `gui.py`.

## Structure
`models.py` Pydantic · `client.py` requests · `database.py` sqlite3 · `pipeline.py` · `metrics.py` métriques ·
`main.py` FastAPI · `dashboard/app.py` Streamlit · `prometheus/` · `grafana/` · `docker-compose.yml`


## Fonctionnalités avancées
- Prévisions horaires sur 24 h et quotidiennes sur 7 jours.
- Qualité de l'air : indice européen, PM2.5, PM10, NO₂ et ozone.
- Alertes indicatives pour pluie, vent, UV, gel, chaleur et qualité de l'air.
- Historique filtrable sur 24 h, 7 jours, 30 jours ou un an.
- Export CSV des relevés et génération de bulletins PDF.
- Endpoints FastAPI : `/previsions/{ville}` et `/qualite-air/{ville}`.
- Cache mémoire de 10 minutes pour les prévisions et la qualité de l'air.

Les seuils d'alerte sont informatifs et ne remplacent pas les vigilances officielles de Météo-France.
Les prévisions et données de qualité de l'air sont fournies par Open-Meteo.
