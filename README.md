# 🌦️ L'Observatoire Météo

<p align="center">
  <strong>Une station météo personnelle pour suivre, comparer et comprendre les conditions météorologiques.</strong><br>
  Application Python · CustomTkinter · FastAPI · SQLite · Open-Meteo
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Interface-CustomTkinter-2D6A4F" alt="CustomTkinter">
  <img src="https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
</p>

---

## 📌 Présentation

**L'Observatoire Météo** est une application Python qui collecte les données météorologiques, les valide, les stocke localement et les rend accessibles depuis une interface graphique ou une API REST.

Le projet s'appuie sur **Open-Meteo**, **Pydantic**, **SQLite**, **CustomTkinter** et **FastAPI**. Il propose un tableau de bord météo, une carte interactive, des prévisions, un radar de précipitations, un centre de vigilance et des outils de comparaison.

## ✨ Fonctionnalités

### 🖥️ Tableau de bord et carte
- Interface de bureau sombre avec CustomTkinter.
- Ajout et suivi de plusieurs villes.
- Conditions actuelles : température et vent.
- Actualisation manuelle et collecte périodique.
- Historique météo et graphiques d'évolution.
- Carte interactive OpenStreetMap avec marqueurs des villes.
- Coloration de la carte selon la température ou le vent.

### 🌧️ Radar des précipitations
- Images radar récentes autour de la ville sélectionnée.
- Animation, lecture, pause et navigation entre les images.
- Superposition sur un fond OpenStreetMap.

> Le radar affiche les images passées fournies par RainViewer. Il ne constitue pas une prévision radar future.

### 📅 Prévisions sur 7 jours
- Prévisions horaires sur les prochaines 24 heures.
- Prévisions quotidiennes sur 7 jours.
- Températures minimales et maximales.
- Probabilité et cumul de précipitations.
- Vent maximal et indice UV.
- Heures de lever et de coucher du soleil.

### 🌫️ Qualité de l'air
- Indice européen de qualité de l'air (European AQI).
- Particules fines PM2.5 et PM10.
- Dioxyde d'azote (NO₂) et ozone (O₃).

### ⚠️ Centre de vigilance
Détection indicative de situations à surveiller :
- Pluie probable et fortes précipitations.
- Vent fort et rafales.
- Risque de gel et fortes chaleurs.
- Indice UV élevé.
- Qualité de l'air dégradée.

Les notifications Windows peuvent être activées ou désactivées. Les alertes sont historisées dans SQLite afin de limiter les notifications répétées.

> **Important :** les alertes sont calculées à partir des données disponibles et ne remplacent pas les vigilances officielles de Météo-France. Consultez les sources officielles pour toute décision de sécurité.

### 🌍 Comparateur de villes
Compare les villes enregistrées selon :
- la température actuelle ;
- les températures minimales et maximales prévues sur 7 jours ;
- la probabilité maximale de pluie ;
- le vent maximal prévu.

### 📊 Historique et rapports
- Historique filtrable sur 24 h, 7 jours, 30 jours ou 1 an.
- Export des relevés au format CSV.
- Génération de bulletins météorologiques PDF.
- Stockage local des villes, relevés, paramètres et alertes.

## 🧱 Architecture

```text
       Open-Meteo / RainViewer / OpenStreetMap
                       │
                       ▼
              client.py / services
         Requêtes HTTP et récupération des données
                       │
                       ▼
                 Pydantic
              Validation des données
                       │
                       ▼
                 pipeline.py
                Collecte météo
                       │
                       ▼
                 database.py
                   SQLite
                       │
              ┌────────┴────────┐
              ▼                 ▼
            gui.py            main.py
       CustomTkinter          FastAPI
       Application           API REST
       de bureau          + Prometheus
```

Les prévisions et la qualité de l'air sont récupérées par un module dédié et mises en cache en mémoire pendant 10 minutes. Les images radar sont traitées par un service distinct.

## 🛠️ Technologies

| Technologie | Rôle |
|---|---|
| Python | Langage principal |
| CustomTkinter / Tkinter | Interface de bureau |
| TkinterMapView | Carte interactive |
| Open-Meteo | Météo, géocodage et qualité de l'air |
| RainViewer | Images radar de précipitations |
| OpenStreetMap | Fond cartographique |
| Requests / Requests-Cache | Requêtes HTTP et cache |
| Pydantic | Validation des données |
| SQLite | Stockage local |
| FastAPI / Uvicorn | API REST |
| Prometheus | Métriques et observabilité |
| ReportLab | Génération PDF |
| Winotify | Notifications Windows |
| Pillow | Traitement des images |

## 🚀 Installation sous Windows

### 1. Récupérer le projet

```powershell
git clone https://github.com/guerguet-matisse/observatoire-meteo.git
cd observatoire-meteo
```

Pour utiliser la branche de développement :

```powershell
git checkout feature/interactive-weather-map
git pull --ff-only origin feature/interactive-weather-map
```

### 2. Créer l'environnement virtuel

Python 3.12 est recommandé.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloque l'activation :

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. Installer les dépendances et démarrer

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python gui.py
```

La base `meteo.db` est créée automatiquement au premier lancement, à côté du programme.

## 🔌 API FastAPI

L'API utilise son propre fichier de dépendances :

```powershell
python -m pip install -r requirements-api.txt
uvicorn main:app --reload
```

| URL | Description |
|---|---|
| http://127.0.0.1:8000/docs | Documentation interactive Swagger |
| http://127.0.0.1:8000/redoc | Documentation ReDoc |
| http://127.0.0.1:8000/health | État de l'API |
| http://127.0.0.1:8000/metrics | Métriques Prometheus |

### Endpoints disponibles

| Méthode | Endpoint | Description |
|---|---|---|
| GET | `/health` | Vérifier que l'API fonctionne |
| GET | `/villes` | Lister les villes suivies |
| GET | `/meteo/{ville}` | Consulter les relevés |
| GET | `/meteo/{ville}/stats` | Statistiques historiques |
| POST | `/meteo/{ville}/actualiser` | Déclencher une collecte |
| GET | `/previsions/{ville}` | Prévisions météo |
| GET | `/qualite-air/{ville}` | Qualité de l'air |
| GET | `/alertes/{ville}` | Alertes indicatives |
| GET | `/radar/frames` | Images radar disponibles |

Exemple : http://127.0.0.1:8000/previsions/Paris

### Activer la collecte automatique de l'API

La collecte en arrière-plan est désactivée par défaut. Pour collecter trois villes toutes les 15 minutes :

```powershell
$env:COLLECT_INTERVAL_MIN = "15"
$env:COLLECT_CITIES = "Saint-Quentin,Paris,Lille"
uvicorn main:app --reload
```

Une valeur de `0` désactive cette collecte.

## 🐳 Docker

Le dépôt contient une configuration Docker Compose pour l'API, le dashboard, Prometheus et Grafana.

```bash
docker compose up --build
```

Arrêt des services :

```bash
docker compose down
```

> Attention : `docker compose down -v` supprime également les volumes persistants et les données qu'ils contiennent.

## 📁 Structure du projet

```text
observatoire-meteo/
├── .github/workflows/       # Vérifications automatisées
├── tests/                   # Tests unitaires
├── client.py                # Client HTTP et géocodage
├── database.py              # Base SQLite et requêtes
├── gui.py                   # Application CustomTkinter
├── main.py                  # API FastAPI
├── metrics.py               # Métriques Prometheus
├── models.py                # Modèles Pydantic
├── pipeline.py              # Collecte et stockage
├── radar_service.py         # Service radar RainViewer
├── reporting.py              # Génération des PDF
├── weather_features.py      # Prévisions, air et alertes
├── requirements.txt         # Dépendances interface
├── requirements-api.txt     # Dépendances API
├── docker-compose.yml
├── Dockerfile.api
└── meteo.db                 # Créée au lancement
```

## 🧪 Tests

Exécuter les tests localement :

```powershell
python -m unittest discover -s tests -v
python -m compileall -q .
```

GitHub Actions exécute les tests et vérifie la compilation Python lors des pushes sur `main` et `feature/interactive-weather-map`, ainsi que lors des pull requests vers `main`.

## 🔐 Sources et utilisation des données

- [Open-Meteo](https://open-meteo.com/) : météo, géocodage et qualité de l'air.
- [RainViewer](https://www.rainviewer.com/) : images radar de précipitations.
- [OpenStreetMap](https://www.openstreetmap.org/) : fond cartographique.

Les données dépendent de services externes et peuvent être temporairement indisponibles. Les tuiles cartographiques sont mises en cache localement pour limiter les requêtes répétées. Respecte les conditions d'utilisation et les politiques de chaque fournisseur.

## 🗺️ Pistes d'évolution

- Développer les analyses climatiques et les statistiques à long terme.
- Personnaliser les seuils et les règles de notification.
- Ajouter de nouvelles sources météorologiques.
- Enrichir les outils de comparaison et de visualisation.
- Renforcer les tests et la robustesse générale.

## 👤 Auteur

**Matisse Guerguet** · [GitHub](https://github.com/guerguet-matisse)

Dépôt : [guerguet-matisse/observatoire-meteo](https://github.com/guerguet-matisse/observatoire-meteo)

---

<p align="center"><sub>🌦️ Observer les conditions, comprendre leur évolution.</sub></p>
