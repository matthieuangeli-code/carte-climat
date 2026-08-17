# -*- coding: utf-8 -*-
"""Carte climat interactive — Streamlit + Folium/OpenStreetMap."""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from collections import defaultdict

import folium
import pandas as pd
import streamlit as st
from branca.colormap import LinearColormap
from folium.plugins import Fullscreen
from streamlit_folium import st_folium

from climate_data import DATA

st.set_page_config(
    page_title="Carte climat — soleil & températures",
    page_icon="☀️",
    layout="wide",
)

MONTHS = ["Septembre", "Octobre", "Novembre", "Décembre", "Janvier", "Février", "Mars", "Avril"]
MONTH_NUMBERS = [9, 10, 11, 12, 1, 2, 3, 4]
METRICS = {
    "Jours avec ≥ 5 h de soleil": "sun",
    "Température maximale moyenne": "tmax",
    "Température minimale moyenne": "tmin",
}
COUNTRY_NAMES = {
    "FR": "France",
    "NO": "Norvège",
    "CH": "Suisse",
    "ES": "Espagne",
    "IT": "Italie",
    "LU": "Luxembourg",
    "DE": "Allemagne",
}


def metric_format(value: float, metric: str) -> str:
    return f"{value:.1f} j" if metric == "sun" else f"{value:.1f} °C"


def radius_for(value: float, vmin: float, vmax: float) -> float:
    if vmax <= vmin:
        return 11.0
    t = max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
    return 7.0 + 12.0 * math.sqrt(t)


def build_colormap(metric: str, vmin: float, vmax: float, caption: str) -> LinearColormap:
    if metric == "sun":
        colors = ["#fff7bc", "#fec44f", "#fe9929", "#d95f0e"]
    else:
        colors = ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"]
    cmap = LinearColormap(colors=colors, vmin=vmin, vmax=vmax, caption=caption)
    return cmap


def country_scope(rows: list[dict], scope: str) -> list[dict]:
    if scope == "France seulement":
        return [r for r in rows if r["country"] == "FR"]
    if scope == "Étranger seulement":
        return [r for r in rows if r["country"] != "FR"]
    return rows


def data_for_month(month_idx: int, sunshine_override: dict[str, list[float]] | None = None) -> list[dict]:
    rows = []
    for city in DATA:
        sun = city["sun"][month_idx]
        if sunshine_override and city["name"] in sunshine_override:
            sun = sunshine_override[city["name"]][month_idx]
        rows.append(
            {
                "name": city["name"],
                "country": city["country"],
                "lat": city["lat"],
                "lon": city["lon"],
                "sun": float(sun),
                "tmin": float(city["tmin"][month_idx]),
                "tmax": float(city["tmax"][month_idx]),
            }
        )
    return rows


@st.cache_data(show_spinner=False, ttl=24 * 3600)
def fetch_openmeteo_sunshine() -> dict[str, list[float]]:
    """Compte les jours >= 5 h de soleil, 1991-2020, depuis Open-Meteo.

    Retourne une moyenne annuelle par mois (septembre -> avril) pour chaque ville.
    Le calcul repose sur sunshine_duration quotidien en secondes.
    """
    result: dict[str, list[float]] = {}
    batch_size = 6

    for start in range(0, len(DATA), batch_size):
        batch = DATA[start : start + batch_size]
        params = {
            "latitude": ",".join(str(c["lat"]) for c in batch),
            "longitude": ",".join(str(c["lon"]) for c in batch),
            "start_date": "1991-01-01",
            "end_date": "2020-12-31",
            "daily": "sunshine_duration",
            "timezone": "auto",
        }
        url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))

        payloads = payload if isinstance(payload, list) else [payload]
        if len(payloads) != len(batch):
            raise RuntimeError("Réponse Open-Meteo inattendue pour un lot de villes.")

        for city, item in zip(batch, payloads):
            counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
            times = item["daily"]["time"]
            values = item["daily"]["sunshine_duration"]
            for date_s, seconds in zip(times, values):
                if seconds is None:
                    continue
                year, month, _day = map(int, date_s.split("-"))
                if month in MONTH_NUMBERS and float(seconds) >= 18_000:
                    counts[month][year] += 1
                elif month in MONTH_NUMBERS:
                    counts[month].setdefault(year, 0)

            month_means: list[float] = []
            for month in MONTH_NUMBERS:
                yearly = counts[month]
                month_means.append(sum(yearly.values()) / len(yearly) if yearly else 0.0)
            result[city["name"]] = month_means

    return result


st.sidebar.title("☀️ Carte climat")
st.sidebar.caption("Comparer la lumière hivernale et les températures sur une vraie carte OpenStreetMap.")

month_name = st.sidebar.selectbox("Mois", MONTHS, index=4)
month_idx = MONTHS.index(month_name)
metric_label = st.sidebar.selectbox("Indicateur", list(METRICS), index=0)
metric = METRICS[metric_label]
scope = st.sidebar.selectbox("Zone", ["Toutes les villes", "France seulement", "Étranger seulement"])
show_labels = st.sidebar.checkbox("Afficher les noms sur la carte", value=False)

st.sidebar.divider()
st.sidebar.subheader("Données soleil")
source = st.sidebar.radio(
    "Source pour les jours ≥5 h",
    ["Données intégrées", "Open-Meteo 1991–2020"],
    index=0,
    help="Open-Meteo recompte les jours à partir de la durée quotidienne d'ensoleillement. Le premier chargement peut prendre un peu de temps.",
)

sun_override = None
if source == "Open-Meteo 1991–2020":
    try:
        with st.spinner("Calcul des normales de soleil 1991–2020…"):
            sun_override = fetch_openmeteo_sunshine()
        st.sidebar.success("Open-Meteo chargé et mis en cache.")
    except Exception as exc:
        st.sidebar.error("Open-Meteo indisponible : données intégrées utilisées.")
        st.sidebar.caption(str(exc))
        sun_override = None

rows = country_scope(data_for_month(month_idx, sun_override), scope)
if not rows:
    st.error("Aucune ville dans cette sélection.")
    st.stop()

values = [r[metric] for r in rows]
vmin, vmax = min(values), max(values)
ranked = sorted(rows, key=lambda r: r[metric], reverse=True)
cmap = build_colormap(metric, vmin, vmax, f"{metric_label} — {month_name}")

st.title("Carte climat — France & voisins")
st.caption(
    "Carte interactive OpenStreetMap : molette pour zoomer, glisser pour se déplacer, clic sur un point pour le détail."
)

cols = st.columns(4)
cols[0].metric("🥇 Meilleur", f"{ranked[0]['name']} — {metric_format(ranked[0][metric], metric)}")
for col, ref_name in zip(cols[1:], ["Biot", "Embrun", "Oslo"]):
    ref = next((r for r in data_for_month(month_idx, sun_override) if r["name"] == ref_name), None)
    if ref:
        col.metric(ref_name, metric_format(ref[metric], metric))

if scope == "Étranger seulement":
    map_center, zoom = [48.0, 6.0], 4
else:
    map_center, zoom = [46.3, 3.3], 5

m = folium.Map(
    location=map_center,
    zoom_start=zoom,
    tiles=None,
    control_scale=True,
    prefer_canvas=True,
)
folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=True).add_to(m)
folium.TileLayer("CartoDB positron", name="Carte claire", show=False).add_to(m)
Fullscreen(position="topright", title="Plein écran", title_cancel="Quitter le plein écran").add_to(m)

for r in rows:
    value = r[metric]
    country = COUNTRY_NAMES.get(r["country"], r["country"])
    popup_html = f"""
    <div style='font-family:Arial,sans-serif; min-width:220px'>
      <h4 style='margin:0 0 8px'>{r['name']} <span style='font-weight:normal'>({country})</span></h4>
      <b>{month_name}</b><br>
      ☀️ Jours ≥5 h : <b>{r['sun']:.1f}</b><br>
      🌡️ Tmin moyenne : <b>{r['tmin']:.1f} °C</b><br>
      🌡️ Tmax moyenne : <b>{r['tmax']:.1f} °C</b><br>
    </div>
    """
    folium.CircleMarker(
        location=[r["lat"], r["lon"]],
        radius=radius_for(value, vmin, vmax),
        color="#263238",
        weight=1,
        fill=True,
        fill_color=cmap(value),
        fill_opacity=0.88,
        tooltip=f"{r['name']} — {metric_format(value, metric)}",
        popup=folium.Popup(popup_html, max_width=300),
    ).add_to(m)

    if show_labels:
        folium.Marker(
            [r["lat"], r["lon"]],
            icon=folium.DivIcon(
                icon_size=(150, 24),
                icon_anchor=(-10, 10),
                html=(
                    "<div style='font-size:11px;font-weight:700;color:#263238;"
                    "text-shadow:0 0 3px white,0 0 3px white,0 0 3px white'>"
                    f"{r['name']}</div>"
                ),
            ),
        ).add_to(m)

cmap.add_to(m)
folium.LayerControl(collapsed=True).add_to(m)

st_folium(
    m,
    use_container_width=True,
    height=690,
    returned_objects=[],
    key=f"climate-map-{month_idx}-{metric}-{scope}-{source}-{show_labels}",
)

st.subheader(f"Classement — {metric_label.lower()} en {month_name.lower()}")
rank_df = pd.DataFrame(
    [
        {
            "#": i,
            "Ville": r["name"],
            "Pays": COUNTRY_NAMES.get(r["country"], r["country"]),
            "Jours ≥5 h soleil": round(r["sun"], 1),
            "Tmin moyenne (°C)": round(r["tmin"], 1),
            "Tmax moyenne (°C)": round(r["tmax"], 1),
        }
        for i, r in enumerate(ranked, start=1)
    ]
)
st.dataframe(rank_df, hide_index=True, use_container_width=True, height=min(720, 42 + len(rank_df) * 35))

st.caption(
    "Les températures et les données intégrées proviennent du jeu de comparaison préparé pour cette app. "
    "Le mode Open-Meteo recalcule uniquement le nombre de jours avec ≥5 h de soleil à partir de sunshine_duration quotidien."
)
