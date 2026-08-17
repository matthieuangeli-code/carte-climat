# -*- coding: utf-8 -*-
"""Carte climat interactive — Streamlit + Folium/OpenStreetMap.

Les normales sont calculées de manière homogène à partir de la réanalyse
ERA5-Land via l'API historique Open-Meteo, sur la période 1991-2020.
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request

import folium
import pandas as pd
import streamlit as st
from branca.colormap import LinearColormap
from folium.plugins import Fullscreen
from streamlit_folium import st_folium

from city_catalog import CITIES, COUNTRY_NAMES

st.set_page_config(
    page_title="Carte climat — France & voisins",
    page_icon="☀️",
    layout="wide",
)

MONTHS = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]
METRICS = {
    "Jours avec > 5 h de soleil": "sun_days_gt5h",
    "Température minimale moyenne": "tmin",
    "Température maximale moyenne": "tmax",
}
BATCH_SIZE = 8
YEARS = range(1991, 2021)


def metric_format(value: float, metric: str) -> str:
    return f"{value:.1f} j" if metric == "sun_days_gt5h" else f"{value:.1f} °C"


def radius_for(value: float, vmin: float, vmax: float) -> float:
    if vmax <= vmin:
        return 9.0
    t = max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
    return 5.5 + 8.5 * math.sqrt(t)


def build_colormap(metric: str, vmin: float, vmax: float, caption: str) -> LinearColormap:
    if metric == "sun_days_gt5h":
        colors = ["#fff7bc", "#fec44f", "#fe9929", "#d95f0e"]
    else:
        colors = ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"]
    return LinearColormap(colors=colors, vmin=vmin, vmax=vmax, caption=caption)


def catalog_for_scope(scope: str) -> list[dict]:
    if scope == "France seulement":
        return [c for c in CITIES if c["country"] == "FR"]
    if scope == "Pays voisins seulement":
        return [c for c in CITIES if c["country"] not in {"FR", "NO"}]
    return CITIES


def chunked(items: list[dict], size: int) -> list[list[dict]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _aggregate_climate(city: dict, daily: dict) -> dict:
    """Transforme 30 ans de données quotidiennes en normales mensuelles."""
    tmin_sum = [0.0] * 12
    tmin_n = [0] * 12
    tmax_sum = [0.0] * 12
    tmax_n = [0] * 12
    sunny_counts = {month: {year: 0 for year in YEARS} for month in range(1, 13)}

    times = daily.get("time", [])
    tmins = daily.get("temperature_2m_min", [])
    tmaxs = daily.get("temperature_2m_max", [])
    sunshine = daily.get("sunshine_duration", [])

    for date_s, tmin, tmax, seconds in zip(times, tmins, tmaxs, sunshine):
        year, month, _day = map(int, date_s.split("-"))
        idx = month - 1

        if tmin is not None:
            tmin_sum[idx] += float(tmin)
            tmin_n[idx] += 1
        if tmax is not None:
            tmax_sum[idx] += float(tmax)
            tmax_n[idx] += 1
        if seconds is not None and float(seconds) > 18_000:
            sunny_counts[month][year] += 1

    return {
        "name": city["name"],
        "country": city["country"],
        "lat": city["lat"],
        "lon": city["lon"],
        "tmin": [tmin_sum[i] / tmin_n[i] if tmin_n[i] else None for i in range(12)],
        "tmax": [tmax_sum[i] / tmax_n[i] if tmax_n[i] else None for i in range(12)],
        "sun_days_gt5h": [
            sum(sunny_counts[month].values()) / len(sunny_counts[month])
            for month in range(1, 13)
        ],
    }


@st.cache_data(show_spinner=False, persist="disk")
def fetch_batch(batch_signature: tuple[tuple[str, str, float, float], ...]) -> list[dict]:
    """Télécharge et agrège un lot de villes. Le résultat est persisté sur disque."""
    batch = [
        {"name": name, "country": country, "lat": lat, "lon": lon}
        for name, country, lat, lon in batch_signature
    ]
    params = {
        "latitude": ",".join(str(c["lat"]) for c in batch),
        "longitude": ",".join(str(c["lon"]) for c in batch),
        "start_date": "1991-01-01",
        "end_date": "2020-12-31",
        "daily": "temperature_2m_min,temperature_2m_max,sunshine_duration",
        "timezone": "auto",
        "models": "era5_land",
    }
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(params)

    with urllib.request.urlopen(url, timeout=180) as response:
        payload = json.loads(response.read().decode("utf-8"))

    payloads = payload if isinstance(payload, list) else [payload]
    if len(payloads) != len(batch):
        raise RuntimeError("Réponse Open-Meteo inattendue pour un lot de villes.")

    return [
        _aggregate_climate(city, item["daily"])
        for city, item in zip(batch, payloads)
    ]


def load_normals(catalog: list[dict]) -> list[dict]:
    batches = chunked(catalog, BATCH_SIZE)
    progress = st.progress(0, text="Chargement des normales climatiques 1991–2020…")
    rows: list[dict] = []

    for index, batch in enumerate(batches, start=1):
        signature = tuple(
            (c["name"], c["country"], float(c["lat"]), float(c["lon"]))
            for c in batch
        )
        rows.extend(fetch_batch(signature))
        progress.progress(
            index / len(batches),
            text=f"Normales climatiques : lot {index}/{len(batches)}",
        )

    progress.empty()
    return rows


def rows_for_month(normals: list[dict], month_idx: int) -> list[dict]:
    return [
        {
            "name": city["name"],
            "country": city["country"],
            "lat": city["lat"],
            "lon": city["lon"],
            "tmin": float(city["tmin"][month_idx]),
            "tmax": float(city["tmax"][month_idx]),
            "sun_days_gt5h": float(city["sun_days_gt5h"][month_idx]),
        }
        for city in normals
    ]


st.sidebar.title("☀️ Carte climat")
st.sidebar.caption(
    "Normales homogènes 1991–2020. Températures et soleil sont calculés depuis la même réanalyse ERA5-Land."
)

month_name = st.sidebar.selectbox("Mois", MONTHS, index=0)
month_idx = MONTHS.index(month_name)
metric_label = st.sidebar.selectbox("Indicateur", list(METRICS), index=0)
metric = METRICS[metric_label]
scope = st.sidebar.selectbox(
    "Zone",
    ["France + voisins + Oslo", "France seulement", "Pays voisins seulement"],
)
show_labels = st.sidebar.checkbox("Afficher les noms sur la carte", value=False)

st.sidebar.divider()
st.sidebar.caption(
    f"{len(CITIES)} villes au catalogue. Le premier chargement télécharge les normales ; les suivants réutilisent le cache local."
)
if st.sidebar.button("Vider le cache climat et recalculer"):
    fetch_batch.clear()
    st.rerun()

catalog = catalog_for_scope(scope)

try:
    normals = load_normals(catalog)
except Exception as exc:
    st.error(
        "Impossible de charger les normales Open-Meteo. Vérifie la connexion Internet puis recharge la page."
    )
    st.exception(exc)
    st.stop()

rows = rows_for_month(normals, month_idx)
values = [r[metric] for r in rows]
vmin, vmax = min(values), max(values)
ranked = sorted(rows, key=lambda r: r[metric], reverse=True)
cmap = build_colormap(metric, vmin, vmax, f"{metric_label} — {month_name}")

st.title("Carte climat — France & pays voisins")
st.caption(
    "OpenStreetMap interactif : zoome à la molette, déplace la carte et clique sur une ville pour les trois valeurs du mois."
)

cols = st.columns(4)
cols[0].metric("🥇 Meilleur", f"{ranked[0]['name']} — {metric_format(ranked[0][metric], metric)}")
for col, ref_name in zip(cols[1:], ["Biot", "Embrun", "Oslo"]):
    ref = next((r for r in rows if r["name"] == ref_name), None)
    if ref is not None:
        col.metric(ref_name, metric_format(ref[metric], metric))
    else:
        ref_catalog = [c for c in CITIES if c["name"] == ref_name]
        if ref_catalog:
            try:
                ref_normals = load_normals(ref_catalog)
                ref_row = rows_for_month(ref_normals, month_idx)[0]
                col.metric(ref_name, metric_format(ref_row[metric], metric))
            except Exception:
                col.metric(ref_name, "—")

if scope == "Pays voisins seulement":
    map_center, zoom = [46.4, 5.0], 5
else:
    map_center, zoom = [46.3, 3.0], 5

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
    <div style='font-family:Arial,sans-serif; min-width:230px'>
      <h4 style='margin:0 0 8px'>{r['name']} <span style='font-weight:normal'>({country})</span></h4>
      <b>{month_name}</b><br>
      ☀️ Jours &gt;5 h : <b>{r['sun_days_gt5h']:.1f}</b><br>
      🌡️ Tmin moyenne : <b>{r['tmin']:.1f} °C</b><br>
      🌡️ Tmax moyenne : <b>{r['tmax']:.1f} °C</b><br>
    </div>
    """
    folium.CircleMarker(
        location=[r["lat"], r["lon"]],
        radius=radius_for(value, vmin, vmax),
        color="#263238",
        weight=0.8,
        fill=True,
        fill_color=cmap(value),
        fill_opacity=0.82,
        tooltip=f"{r['name']} — {metric_format(value, metric)}",
        popup=folium.Popup(popup_html, max_width=320),
    ).add_to(m)

    if show_labels:
        folium.Marker(
            [r["lat"], r["lon"]],
            icon=folium.DivIcon(
                icon_size=(150, 24),
                icon_anchor=(-8, 9),
                html=(
                    "<div style='font-size:10px;font-weight:700;color:#263238;"
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
    height=720,
    returned_objects=[],
    key=f"climate-map-{month_idx}-{metric}-{scope}-{show_labels}",
)

st.subheader(f"Classement — {metric_label.lower()} en {month_name.lower()}")
rank_df = pd.DataFrame(
    [
        {
            "#": i,
            "Ville": r["name"],
            "Pays": COUNTRY_NAMES.get(r["country"], r["country"]),
            "Jours >5 h soleil": round(r["sun_days_gt5h"], 1),
            "Tmin moyenne (°C)": round(r["tmin"], 1),
            "Tmax moyenne (°C)": round(r["tmax"], 1),
        }
        for i, r in enumerate(ranked, start=1)
    ]
)
st.dataframe(
    rank_df,
    hide_index=True,
    use_container_width=True,
    height=min(760, 42 + len(rank_df) * 35),
)

st.caption(
    "Période 1991–2020. Tmin = moyenne des minima quotidiens du mois ; Tmax = moyenne des maxima quotidiens. "
    "Un jour solaire est compté lorsque sunshine_duration est strictement supérieure à 5 h."
)
