"""Jour 4 : Dashboard Streamlit + Plotly connecté à l'API FastAPI.

Lancer en local :  streamlit run dashboard/app.py     (API sur http://localhost:8000)
"""
import os
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
INTERVALLES = {"15 s": 15, "30 s": 30, "1 min": 60, "5 min": 300}

st.set_page_config(page_title="Observatoire Météo", page_icon="🌦️", layout="wide")
st.markdown(
    """<style>
    .block-container {padding-top: 2rem;}
    [data-testid="stMetricValue"] {font-size: 2.2rem; font-weight: 700;}
    </style>""",
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------ accès API
class ApiError(Exception):
    pass


def _request(method: str, path: str, timeout: int = 10, **kw):
    try:
        r = requests.request(method, f"{API_URL}{path}", timeout=timeout, **kw)
    except requests.RequestException as e:
        raise ApiError(f"impossible de joindre l'API ({e.__class__.__name__})") from e
    if r.status_code == 404:
        return None
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        raise ApiError(f"erreur {r.status_code} : {detail}")
    return r.json()


@st.cache_data(ttl=10, show_spinner=False)
def load_villes():
    return _request("GET", "/villes") or []


@st.cache_data(ttl=10, show_spinner=False)
def load_releves(ville: str, debut: str | None = None, fin: str | None = None, limite: int = 500):
    params = {"limite": limite}
    if debut:
        params["debut"] = debut
    if fin:
        params["fin"] = fin
    return _request("GET", f"/meteo/{ville}", params=params) or []


def to_df(data) -> pd.DataFrame:
    df = pd.DataFrame(data)
    df["date_heure"] = pd.to_datetime(df["date_heure"])
    return df.sort_values("date_heure")


def actualiser(nom: str) -> bool:
    """Demande à l'API de collecter un nouveau relevé."""
    with st.spinner(f"Collecte de {nom}…"):
        try:
            res = _request("POST", f"/meteo/{nom}/actualiser", timeout=30)
        except ApiError as e:
            st.session_state["flash"] = f"❌ {e}"
            return False
    st.cache_data.clear()
    nouveau = bool(res and res.get("nouveau_releve"))
    st.session_state["flash"] = "✅ Nouveau relevé enregistré" if nouveau else "ℹ️ Relevé déjà à jour pour cette heure"
    return True


# ------------------------------------------------------------------ chargement initial
if msg := st.session_state.pop("flash", None):
    st.toast(msg)

try:
    villes = load_villes()
except ApiError as e:
    st.title("🌦️ Observatoire Météo")
    st.error(f"🔌 **API indisponible** — {e}\n\nURL utilisée : `{API_URL}`")
    if st.button("Réessayer"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

noms = [v["nom"] for v in villes]

# ------------------------------------------------------------------ barre latérale
with st.sidebar:
    st.title("🌦️ Observatoire")
    st.caption("Météo en temps réel · Open-Meteo")

    with st.form("ajout", clear_on_submit=True):
        nouvelle = st.text_input("Ajouter une ville", placeholder="ex. Soissons")
        if st.form_submit_button("＋ Ajouter", use_container_width=True) and nouvelle.strip():
            if actualiser(nouvelle.strip()):
                st.rerun()

    if noms:
        st.divider()
        ville = st.selectbox("Ville principale", noms)
        comparer = st.multiselect("Comparer avec", [n for n in noms if n != ville])
        rng = st.date_input("Période", value=(date.today() - timedelta(days=7), date.today()))
        st.divider()
        auto = st.toggle("Rafraîchissement automatique", value=True)
        label = st.selectbox("Intervalle", list(INTERVALLES), index=1, disabled=not auto)
        if st.button("⟳ Collecter un relevé maintenant", use_container_width=True):
            if actualiser(ville):
                st.rerun()
    st.caption(f"API : `{API_URL}`")

if not noms:
    st.title("🌦️ Observatoire Météo")
    st.info("Aucune ville pour l'instant. Ajoute-en une dans la barre latérale.")
    st.stop()

if not isinstance(rng, tuple) or len(rng) != 2:
    st.info("Sélectionne une date de début **et** une date de fin.")
    st.stop()
debut, fin = rng


# ------------------------------------------------------------------ contenu (rafraîchi automatiquement)
def render(ville: str, comparer: list[str], debut: date, fin: date):
    st.title(f"🌦️ {ville}")
    try:
        with st.spinner("Chargement des données…"):
            frames = []
            for nom in [ville, *comparer]:
                data = load_releves(nom, debut.isoformat(), fin.isoformat())
                if data:
                    frames.append(to_df(data))
            last_by_city = {v["nom"]: (load_releves(v["nom"], limite=1) or [None])[0] for v in villes}
    except ApiError as e:
        st.error(f"🔌 **API indisponible** — {e}")
        return

    if not frames or frames[0]["ville"].iloc[0].lower() != ville.lower():
        st.warning(f"Aucun relevé pour {ville} entre le {debut:%d/%m/%Y} et le {fin:%d/%m/%Y}. "
                   "Élargis la période ou collecte un relevé.")
        return

    df = frames[0]
    all_df = pd.concat(frames)

    # --- KPIs
    last, prev = df.iloc[-1], (df.iloc[-2] if len(df) > 1 else None)
    jour = df[df["date_heure"].dt.date == last["date_heure"].date()]
    cols = st.columns(4)
    kpis = [
        ("Température actuelle", f"{last['temperature']:.1f} °C",
         None if prev is None else f"{last['temperature'] - prev['temperature']:+.1f} °C", "normal"),
        ("Max du jour", f"{jour['temperature'].max():.1f} °C", None, "normal"),
        ("Min du jour", f"{jour['temperature'].min():.1f} °C", None, "normal"),
        ("Vent moyen (période)", f"{df['vitesse_vent'].mean():.1f} km/h",
         f"dernier : {last['vitesse_vent']:.0f} km/h", "off"),
    ]
    for col, (titre, valeur, delta, dcolor) in zip(cols, kpis):
        with col, st.container(border=True):
            st.metric(titre, valeur, delta, delta_color=dcolor)

    tab_graph, tab_carte, tab_data = st.tabs(["📈 Évolution", "🗺️ Carte", "🗃️ Données"])

    with tab_graph:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Température (°C)")
            fig = px.line(all_df, x="date_heure", y="temperature", color="ville", markers=True,
                          labels={"date_heure": "", "temperature": "°C", "ville": ""})
            fig.update_traces(line_shape="spline")
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=380, hovermode="x unified",
                              legend=dict(orientation="h", y=1.12))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("Vitesse du vent (km/h)")
            fig = px.line(all_df, x="date_heure", y="vitesse_vent", color="ville", markers=True,
                          labels={"date_heure": "", "vitesse_vent": "km/h", "ville": ""})
            fig.update_traces(line_shape="spline")
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=380, hovermode="x unified",
                              legend=dict(orientation="h", y=1.12))
            st.plotly_chart(fig, use_container_width=True)

    with tab_carte:
        rows = [{**v, "temperature": (last_by_city[v["nom"]] or {}).get("temperature"),
                 "taille": 22 if v["nom"] == ville else 14} for v in villes]
        dfm = pd.DataFrame(rows)
        fig = px.scatter_map(
            dfm, lat="latitude", lon="longitude", hover_name="nom", color="temperature", size="taille",
            size_max=22, zoom=4, color_continuous_scale="RdYlBu_r", map_style="open-street-map",
            hover_data={"temperature": ":.1f", "taille": False, "latitude": ":.2f", "longitude": ":.2f"},
            labels={"temperature": "°C"},
        )
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=520)
        st.plotly_chart(fig, use_container_width=True)

    with tab_data:
        table = all_df.sort_values("date_heure", ascending=False)[
            ["ville", "date_heure", "temperature", "vitesse_vent"]]
        st.dataframe(table, hide_index=True, use_container_width=True)
        st.download_button("⬇️ Télécharger en CSV", table.to_csv(index=False).encode("utf-8"),
                           file_name=f"meteo_{ville}.csv", mime="text/csv")

    st.caption(f"Dernière actualisation de l'affichage : {datetime.now():%H:%M:%S}")


st.fragment(run_every=INTERVALLES[label] if auto else None)(render)(ville, comparer, debut, fin)
