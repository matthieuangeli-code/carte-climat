# -*- coding: utf-8 -*-
"""Carte climat interactive — Streamlit + Folium/OpenStreetMap.

Objectif pratique : capturer le climat récent plutôt qu'une normale scientifique.
Les indicateurs sont calculés sur les 10 dernières années complètes : 2016-2025.
Source : Meteostat (observations + données dérivées quand disponibles).
"""

from __future__ import annotations

import calendar
from datetime import date
import math

import folium
import pandas as pd
import streamlit as st
from branca.colormap import LinearColormap
from folium.plugins import Fullscreen
from streamlit_folium import st_folium
import meteostat as ms

from city_catalog import CITIES, COUNTRY_NAMES

st.set_page_config(
    page_title="Carte climat — France & voisins",
    page_icon="☀️",
    layout="wide",
)

START = date(2016, 1, 1)
END = date(2025, 12, 31)
MONTHS = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]
METRICS = {
    "Jours avec > 5 h de soleil": "sun_days_gt5h",
    "Température minimale moyenne": "tmin",
    "Température maximale moyenne": "tmax",
}


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


def _empty_months() -> dict:
    return {
        "tmin": [None] * 12,
        "tmax": [None] * 12,
        "sun_days_gt5h": [None] * 12,
    }


def _aggregate_daily(city: dict, df: pd.DataFrame) -> dict:
    """Agrège une série quotidienne 2016-2025 en 12 valeurs mensuelles."""
    result = {
        "name": city["name"],
        "country": city["country"],
        "lat": city["lat"],
        "lon": city["lon"],
        **_empty_months(),
    }

    if df is None or df.empty:
        return result

    df = df.copy()
    df.index = pd.to_datetime(df.index)
    df["year"] = df.index.year
    df["month"] = df.index.month

    for month in range(1, 13):
        subset = df[df["month"] == month]
        idx = month - 1

        if "tmin" in subset.columns and subset["tmin"].notna().any():
            result["tmin"][idx] = float(subset["tmin"].mean())
        if "tmax" in subset.columns and subset["tmax"].notna().any():
            result["tmax"][idx] = float(subset["tmax"].mean())

        # Meteostat exprime tsun en minutes/jour. On estime le nombre de jours
        # > 300 min pour chaque année, en corrigeant seulement les petits trous
        # de données lorsque la couverture mensuelle reste suffisante.
        if "tsun" in subset.columns:
            yearly_estimates = []
            for year in range(START.year, END.year + 1):
                ys = subset[subset["year"] == year]["tsun"].dropna()
                if len(ys) < 12:
                    continue
                days_in_month = calendar.monthrange(year, month)[1]
                sunny = int((ys > 300).sum())
                estimate = sunny * days_in_month / len(ys)
                yearly_estimates.append(min(float(days_in_month), estimate))
            if yearly_estimates:
                result["sun_days_gt5h"][idx] = float(sum(yearly_estimates) / len(yearly_estimates))

    return result


@st.cache_data(show_spinner=False, persist="disk")
def fetch_city_climate(signature: tuple[str, str, float, float]) -> dict:
    """Récupère 2016-2025 pour une ville à partir des stations Meteostat proches."""
    name, country, lat, lon = signature
    city = {"name": name, "country": country, "lat": lat, "lon": lon}
    point = ms.Point(float(lat), float(lon))

    # Deux stations proches suffisent pour une carte comparative et limitent
    # fortement la quantité de données téléchargée. Meteostat met ses fichiers
    # en cache local, donc les stations partagées entre villes sont réutilisées.
    stations = ms.stations.nearby(point, radius=100_000, limit=2)
    if stations is None or len(stations) == 0:
        return _aggregate_daily(city, pd.DataFrame())

    parameters = [ms.Parameter.TMIN, ms.Parameter.TMAX, ms.Parameter.TSUN]
    providers = [ms.Provider.DAILY, ms.Provider.DAILY_DERIVED]
    ts = ms.daily(stations, START, END, parameters=parameters, providers=providers)

    try:
        interpolated = ms.interpolate(
            ts,
            point,
            distance_threshold=100_000,
            elevation_threshold=1000,
        )
        df = interpolated.fetch()
    except Exception:
        # Repli simple : Meteostat fusionne les sources disponibles lors du fetch.
        df = ts.fetch()
        if "station" in df.columns:
            numeric_cols = [c for c in ["tmin", "tmax", "tsun"] if c in df.columns]
            if numeric_cols:
                df = df.groupby(df.index)[numeric_cols].mean()

    return _aggregate_daily(city, df)


def load_climate(catalog: list[dict]) -> tuple[list[dict], list[str]]:
    progress = st.progress(0, text="Chargement du climat récent 2016–2025…")
    rows: list[dict] = []
    failed: list[str] = []

    for i, city in enumerate(catalog, start=1):
        signature = (
            city["name"], city["country"], float(city["lat"]), float(city["lon"])
        )
        try:
            rows.append(fetch_city_climate(signature))
        except Exception:
            failed.append(city["name"])
        progress.progress(
            i / len(catalog),
            text=f"Climat récent : {i}/{len(catalog)} villes — {city['name']}",
        )

    progress.empty()
    return rows, failed


def rows_for_month(normals: list[dict], month_idx: int, metric: str) -> list[dict]:
    rows = []
    for city in normals:
        value = city.get(metric, [None] * 12)[month_idx]
        if value is None or pd.isna(value):
            continue
        rows.append(
            {
                "name": city["name"],
                "country": city["country"],
                "lat": city["lat"],
                "lon": city["lon"],
                "tmin": city["tmin"][month_idx],
                "tmax": city["tmax"][month_idx],
                "sun_days_gt5h": city["sun_days_gt5h"][month_idx],
            }
        )
    return rows


st.sidebar.title("☀️ Carte climat")
st.sidebar.caption(
    "Climat récent 2016–2025 : assez long pour lisser une année bizarre, assez récent pour représenter la situation actuelle."
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
    f"{len(CITIES)} villes au catalogue · source Meteostat · période 2016–2025."
)
st.sidebar.caption(
    "Le premier lancement peut prendre un peu de temps. Ensuite les données sont gardées en cache sur le PC."
)
if st.sidebar.button("Vider le cache climat et recalculer"):
    fetch_city_climate.clear()
    st.rerun()

catalog = catalog_for_scope(scope)
normals, failed = load_climate(catalog)
if failed:
    st.warning(
        f"{len(failed)} ville(s) n'ont pas pu être chargées et sont ignorées pour cette session : "
        + ", ".join(failed[:12])
        + ("…" if len(failed) > 12 else "")
    )

rows = rows_for_month(normals, month_idx, metric)
if not rows:
    st.error("Aucune donnée exploitable pour cet indicateur et ce mois.")
    st.stop()

values = [float(r[metric]) for r in rows]
vmin, vmax = min(values), max(values)
ranked = sorted(rows, key=lambda r: r[metric], reverse=True)
cmap = build_colormap(metric, vmin, vmax, f"{metric_label} — {month_name}")

st.title("Carte climat — France & pays voisins")
st.caption(
    "Période récente 2016–2025 · OpenStreetMap interactif : zoome, déplace la carte et clique sur une ville."
)

cols = st.columns(4)
cols[0].metric("🥇 Meilleur", f"{ranked[0]['name']} — {metric_format(ranked[0][metric], metric)}")
for col, ref_name in zip(cols[1:], ["Biot", "Embrun", "Oslo"]):
    ref = next((r for r in rows if r["name"] == ref_name), None)
    if ref is not None:
        col.metric(ref_name, metric_format(float(ref[metric]), metric))
    else:
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
    value = float(r[metric])
    country = COUNTRY_NAMES.get(r["country"], r["country"])
    tmin_txt = "—" if r["tmin"] is None or pd.isna(r["tmin"]) else f"{r['tmin']:.1f} °C"
    tmax_txt = "—" if r["tmax"] is None or pd.isna(r["tmax"]) else f"{r['tmax']:.1f} °C"
    sun_txt = (
        "—" if r["sun_days_gt5h"] is None or pd.isna(r["sun_days_gt5h"])
        else f"{r['sun_days_gt5h']:.1f}"
    )
    popup_html = f"""
    <div style='font-family:Arial,sans-serif; min-width:230px'>
      <h4 style='margin:0 0 8px'>{r['name']} <span style='font-weight:normal'>({country})</span></h4>
      <b>{month_name} · moyenne 2016–2025</b><br>
      ☀️ Jours &gt;5 h : <b>{sun_txt}</b><br>
      🌡️ Tmin moyenne : <b>{tmin_txt}</b><br>
      🌡️ Tmax moyenne : <b>{tmax_txt}</b><br>
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
            "Jours >5 h soleil": None if r["sun_days_gt5h"] is None else round(r["sun_days_gt5h"], 1),
            "Tmin moyenne (°C)": None if r["tmin"] is None else round(r["tmin"], 1),
            "Tmax moyenne (°C)": None if r["tmax"] is None else round(r["tmax"], 1),
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
    "Période 2016–2025. Tmin/Tmax = moyenne des minima/maxima quotidiens. "
    "Jours >5 h = nombre moyen de jours par mois où Meteostat indique plus de 300 minutes de soleil. "
    "L'objectif est une comparaison récente et pratique, pas une normale climatologique officielle."
)
