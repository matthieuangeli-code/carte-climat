# -*- coding: utf-8 -*-
"""Carte climat interactive — lecture instantanée du jeu pré-calculé."""

from __future__ import annotations

import json
import math
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from branca.colormap import LinearColormap
from folium.plugins import Fullscreen
from streamlit_folium import st_folium

from city_catalog import COUNTRY_NAMES

st.set_page_config(page_title="Carte climat — France & voisins", page_icon="☀️", layout="wide")

DATA_PATH = Path("data/climate_10y.csv")
META_PATH = Path("data/climate_metadata.json")
MONTHS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
METRICS = {
    "Jours avec > 5 h de soleil": "sun_days_gt5h",
    "Température minimale moyenne": "tmin",
    "Température maximale moyenne": "tmax",
}


def metric_format(value: float, metric: str) -> str:
    return f"{value:.1f} j" if metric == "sun_days_gt5h" else f"{value:.1f} °C"


def safe_format(value, suffix="") -> str:
    return "—" if pd.isna(value) else f"{float(value):.1f}{suffix}"


def radius_for(value: float, vmin: float, vmax: float) -> float:
    if vmax <= vmin:
        return 9.0
    t = max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
    return 5.5 + 8.5 * math.sqrt(t)


def build_colormap(metric: str, vmin: float, vmax: float, caption: str) -> LinearColormap:
    colors = ["#fff7bc", "#fec44f", "#fe9929", "#d95f0e"] if metric == "sun_days_gt5h" else ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"]
    return LinearColormap(colors=colors, vmin=vmin, vmax=vmax, caption=caption)


@st.cache_data(show_spinner=False)
def load_data() -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(DATA_PATH)
    meta = json.loads(META_PATH.read_text(encoding="utf-8")) if META_PATH.exists() else {}
    return df, meta


st.sidebar.title("☀️ Carte climat")
st.sidebar.caption("Les données météo sont pré-calculées. L'application ne fait aucun téléchargement météo au démarrage.")

if not DATA_PATH.exists():
    st.error("Le fichier pré-calculé `data/climate_10y.csv` n'est pas encore disponible. Le job GitHub Actions doit finir une première fois.")
    st.code("python precompute_climate.py")
    st.stop()

climate, meta = load_data()
start_year = meta.get("start_year", "?")
end_year = meta.get("end_year", "?")

month_name = st.sidebar.selectbox("Mois", MONTHS, index=0)
month = MONTHS.index(month_name) + 1
metric_label = st.sidebar.selectbox("Indicateur", list(METRICS), index=0)
metric = METRICS[metric_label]
scope = st.sidebar.selectbox("Zone", ["France + voisins + Oslo", "France seulement", "Pays voisins seulement"])
show_labels = st.sidebar.checkbox("Afficher les noms sur la carte", value=False)

st.sidebar.divider()
st.sidebar.caption(f"Période : {start_year}–{end_year} · source Meteostat · {climate['name'].nunique()} villes pré-calculées.")
st.sidebar.caption("Changer de mois, d'indicateur ou de zone ne déclenche aucun appel réseau météo.")

rows = climate[climate["month"] == month].copy()
if scope == "France seulement":
    rows = rows[rows["country"] == "FR"]
elif scope == "Pays voisins seulement":
    rows = rows[~rows["country"].isin(["FR", "NO"])]

rows = rows[rows[metric].notna()].copy()
if rows.empty:
    st.error("Aucune donnée exploitable pour cet indicateur et ce mois.")
    st.stop()

values = rows[metric].astype(float)
vmin, vmax = float(values.min()), float(values.max())
ranked = rows.sort_values(metric, ascending=False).copy()
cmap = build_colormap(metric, vmin, vmax, f"{metric_label} — {month_name}")

st.title("Carte climat — France & pays voisins")
st.caption(f"Climat récent {start_year}–{end_year} · données pré-calculées · OpenStreetMap interactif.")

cols = st.columns(4)
best = ranked.iloc[0]
cols[0].metric("🥇 Meilleur", f"{best['name']} — {metric_format(float(best[metric]), metric)}")
for col, ref_name in zip(cols[1:], ["Biot", "Embrun", "Oslo"]):
    ref = rows[rows["name"] == ref_name]
    col.metric(ref_name, metric_format(float(ref.iloc[0][metric]), metric) if not ref.empty else "—")

map_center, zoom = ([46.4, 5.0], 5) if scope == "Pays voisins seulement" else ([46.3, 3.0], 5)
m = folium.Map(location=map_center, zoom_start=zoom, tiles=None, control_scale=True, prefer_canvas=True)
folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=True).add_to(m)
folium.TileLayer("CartoDB positron", name="Carte claire", show=False).add_to(m)
Fullscreen(position="topright", title="Plein écran", title_cancel="Quitter le plein écran").add_to(m)

for _, r in rows.iterrows():
    value = float(r[metric])
    country = COUNTRY_NAMES.get(r["country"], r["country"])
    sun_txt = safe_format(r.get("sun_days_gt5h"))
    tmin_txt = safe_format(r.get("tmin"), " °C")
    tmax_txt = safe_format(r.get("tmax"), " °C")
    coverage = r.get("sun_coverage", float("nan"))
    coverage_txt = "" if pd.isna(coverage) else f"<br><small>Couverture soleil : {float(coverage)*100:.0f}%</small>"
    popup_html = f"""
    <div style='font-family:Arial,sans-serif; min-width:230px'>
      <h4 style='margin:0 0 8px'>{r['name']} <span style='font-weight:normal'>({country})</span></h4>
      <b>{month_name} · moyenne {start_year}–{end_year}</b><br>
      ☀️ Jours &gt;5 h : <b>{sun_txt}</b><br>
      🌡️ Tmin moyenne : <b>{tmin_txt}</b><br>
      🌡️ Tmax moyenne : <b>{tmax_txt}</b>{coverage_txt}
    </div>
    """
    folium.CircleMarker(
        location=[float(r["lat"]), float(r["lon"])], radius=radius_for(value, vmin, vmax),
        color="#263238", weight=0.8, fill=True, fill_color=cmap(value), fill_opacity=0.82,
        tooltip=f"{r['name']} — {metric_format(value, metric)}", popup=folium.Popup(popup_html, max_width=320),
    ).add_to(m)
    if show_labels:
        folium.Marker(
            [float(r["lat"]), float(r["lon"])],
            icon=folium.DivIcon(icon_size=(150, 24), icon_anchor=(-8, 9), html=f"<div style='font-size:10px;font-weight:700;color:#263238;text-shadow:0 0 3px white,0 0 3px white'>{r['name']}</div>"),
        ).add_to(m)

cmap.add_to(m)
folium.LayerControl(collapsed=True).add_to(m)
st_folium(m, use_container_width=True, height=720, returned_objects=[], key=f"climate-{month}-{metric}-{scope}-{show_labels}")

st.subheader(f"Classement — {metric_label.lower()} en {month_name.lower()}")
rank_df = pd.DataFrame({
    "#": range(1, len(ranked) + 1),
    "Ville": ranked["name"].values,
    "Pays": [COUNTRY_NAMES.get(c, c) for c in ranked["country"]],
    "Jours >5 h soleil": ranked["sun_days_gt5h"].round(1).values,
    "Tmin moyenne (°C)": ranked["tmin"].round(1).values,
    "Tmax moyenne (°C)": ranked["tmax"].round(1).values,
})
st.dataframe(rank_df, hide_index=True, use_container_width=True, height=min(760, 42 + len(rank_df) * 35))

st.caption("Le calcul météo est fait hors ligne par `precompute_climate.py` puis stocké dans le dépôt. Une journée solaire correspond à tsun > 300 minutes.")
