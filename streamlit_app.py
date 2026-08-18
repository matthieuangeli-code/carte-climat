# -*- coding: utf-8 -*-
"""Carte climat interactive — lecture instantanée du jeu pré-calculé."""

from __future__ import annotations

import json
import math
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import streamlit as st
from branca.colormap import LinearColormap
from folium.plugins import Fullscreen
from folium.raster_layers import ImageOverlay
from global_land_mask import globe
from streamlit_folium import st_folium

from city_catalog_generated import COUNTRY_NAMES

st.set_page_config(page_title="Carte climat — Europe", page_icon="☀️", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "climate_10y.csv"
META_PATH = BASE_DIR / "data" / "climate_metadata.json"
MONTHS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
METRICS = {
    "Jours avec > 5 h de soleil": "sun_days_gt5h",
    "Température minimale moyenne": "tmin",
    "Température maximale moyenne": "tmax",
    "Indice climatique global": "climate_score",
}

# Bornes fixes : une valeur conserve la même couleur quel que soit le mois ou la zone.
COLOR_SCALES = {
    "sun_days_gt5h": {
        "vmin": 0.0,
        "vmax": 31.0,
        "colors": ["#02040A", "#171A1F", "#3B3000", "#806000", "#D6A900", "#FFE600", "#FFF7A8"],
    },
    "temperature": {
        "vmin": -20.0,
        "vmax": 40.0,
        "colors": ["#061539", "#123B8D", "#0077D9", "#00C8FF", "#B9F5FF", "#FFE08A", "#FF8A00", "#FF304F", "#8F002E"],
    },
    "climate_score": {
        "vmin": 0.0,
        "vmax": 100.0,
        "colors": ["#9e0142", "#d73027", "#f46d43", "#fdae61", "#a6d96a", "#1a9850", "#006837"],
    },
}

SUN_WEIGHT = 0.50
TMIN_WEIGHT = 0.25
TMAX_WEIGHT = 0.25
NORDIC_COUNTRIES = {"NO", "SE", "DK"}


def metric_format(value: float, metric: str) -> str:
    if metric == "sun_days_gt5h":
        return f"{value:.1f} j"
    if metric == "climate_score":
        return f"{value:.0f}/100"
    return f"{value:.1f} °C"


def safe_format(value, suffix="") -> str:
    return "—" if pd.isna(value) else f"{float(value):.1f}{suffix}"


def radius_for(value: float, vmin: float, vmax: float) -> float:
    if vmax <= vmin:
        return 7.0
    t = max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
    return 3.8 + 6.2 * math.sqrt(t)


def warmth_score(value: float, zero_low: float, ideal_low: float) -> float:
    """Score croissant avec la chaleur, sans pénalité au-dessus du seuil confortable."""
    if pd.isna(value):
        return float("nan")
    x = float(value)
    if x <= zero_low:
        return 0.0
    if x >= ideal_low:
        return 100.0
    return 100.0 * (x - zero_low) / (ideal_low - zero_low)


def add_climate_score(df: pd.DataFrame) -> pd.DataFrame:
    """Indice mensuel 0–100 : 50 % soleil, 25 % Tmin, 25 % Tmax."""
    out = df.copy()
    sun = pd.to_numeric(out["sun_days_gt5h"], errors="coerce")
    tmin = pd.to_numeric(out["tmin"], errors="coerce")
    tmax = pd.to_numeric(out["tmax"], errors="coerce")

    sun_score = (sun / 20.0 * 100.0).clip(lower=0.0, upper=100.0)
    tmin_score = tmin.apply(lambda x: warmth_score(x, -8.0, 8.0))
    tmax_score = tmax.apply(lambda x: warmth_score(x, 4.0, 18.0))

    out["sun_score"] = sun_score
    out["tmin_score"] = tmin_score
    out["tmax_score"] = tmax_score
    out["climate_score"] = SUN_WEIGHT * sun_score + TMIN_WEIGHT * tmin_score + TMAX_WEIGHT * tmax_score
    return out


def scale_for(metric: str) -> dict:
    return COLOR_SCALES.get(metric, COLOR_SCALES["temperature"])


def build_colormap(metric: str, caption: str) -> LinearColormap:
    scale = scale_for(metric)
    return LinearColormap(
        colors=scale["colors"],
        vmin=scale["vmin"],
        vmax=scale["vmax"],
        caption=caption,
    )


@st.cache_data(show_spinner=False, max_entries=24)
def build_idw_surface(
    points: tuple[tuple[float, float, float], ...],
    vmin: float,
    vmax: float,
    metric: str,
    grid_size: int = 190,
) -> tuple[np.ndarray, list[list[float]]]:
    """Construit une surface IDW RGBA, transparente loin des observations."""
    values = np.asarray(points, dtype=float)
    lats, lons, observations = values.T
    lat_pad = max(0.35, (lats.max() - lats.min()) * 0.035)
    lon_pad = max(0.35, (lons.max() - lons.min()) * 0.035)
    south, north = float(lats.min() - lat_pad), float(lats.max() + lat_pad)
    west, east = float(lons.min() - lon_pad), float(lons.max() + lon_pad)
    grid_lats = np.linspace(south, north, grid_size)
    grid_lons = np.linspace(west, east, grid_size)
    surface = np.empty((grid_size, grid_size), dtype=np.float32)
    nearest = np.empty_like(surface)

    # Calcul ligne par ligne pour garder une consommation mémoire faible avec 699 villes.
    for row_index, latitude in enumerate(grid_lats):
        dy = (latitude - lats)[:, None] * 111.2
        dx = (grid_lons[None, :] - lons[:, None]) * 111.2 * np.cos(np.radians(latitude))
        distance_sq = dx * dx + dy * dy
        nearest[row_index] = np.sqrt(distance_sq.min(axis=0))
        exact = distance_sq < 0.04
        weights = 1.0 / np.maximum(distance_sq, 4.0)
        interpolated = (weights * observations[:, None]).sum(axis=0) / weights.sum(axis=0)
        if exact.any():
            exact_columns = exact.any(axis=0)
            interpolated[exact_columns] = observations[exact.argmax(axis=0)[exact_columns]]
        surface[row_index] = interpolated

    colors = scale_for(metric)["colors"]
    rgb_stops = np.asarray(
        [[int(color[i : i + 2], 16) for i in (1, 3, 5)] for color in colors], dtype=float
    )
    normalized = np.clip((surface - vmin) / max(vmax - vmin, 1e-9), 0.0, 1.0)
    positions = normalized * (len(colors) - 1)
    lower = np.floor(positions).astype(int)
    upper = np.minimum(lower + 1, len(colors) - 1)
    fraction = (positions - lower)[..., None]
    rgb = rgb_stops[lower] * (1.0 - fraction) + rgb_stops[upper] * fraction
    lon_grid, lat_grid = np.meshgrid(grid_lons, grid_lats)
    land_mask = globe.is_land(lat_grid, lon_grid)
    alpha = np.where((nearest <= 300.0) & land_mask, 178, 0)[..., None]
    rgba = np.concatenate([rgb, alpha], axis=2).astype(np.uint8)
    return rgba, [[south, west], [north, east]]


@st.cache_data(show_spinner=False)
def load_data() -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(DATA_PATH)
    meta = json.loads(META_PATH.read_text(encoding="utf-8")) if META_PATH.exists() else {}
    required = {"name", "country", "lat", "lon", "month", "tmin", "tmax", "sun_days_gt5h"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Colonnes absentes du CSV : {', '.join(missing)}")
    if df.empty:
        raise ValueError("Le CSV ne contient aucune observation.")
    df["month"] = pd.to_numeric(df["month"], errors="coerce")
    if not df["month"].dropna().between(1, 12).all():
        raise ValueError("La colonne month doit contenir uniquement des valeurs de 1 à 12.")
    return add_climate_score(df), meta


st.sidebar.title("☀️ Carte climat")
st.sidebar.caption("Les données météo sont pré-calculées. L'application ne fait aucun téléchargement météo au démarrage.")

if not DATA_PATH.exists():
    st.error("Le fichier pré-calculé `data/climate_10y.csv` n'est pas encore disponible.")
    st.code("python precompute_climate.py")
    st.stop()

try:
    climate, meta = load_data()
except (OSError, ValueError, json.JSONDecodeError, pd.errors.ParserError) as exc:
    st.error("Les données climatiques sont présentes mais ne peuvent pas être chargées.")
    st.exception(exc)
    st.stop()

start_year = meta.get("start_year", "?")
end_year = meta.get("end_year", "?")
available_countries = set(climate["country"].dropna().astype(str))
city_count = int(climate["name"].nunique())
country_count = len(available_countries)

scope_filters = {"Toutes les villes disponibles": available_countries}
if "FR" in available_countries:
    scope_filters["France seulement"] = {"FR"}
nearby = available_countries.difference({"FR"}, NORDIC_COUNTRIES)
if nearby:
    scope_filters["Europe proche hors France"] = nearby
nordic = available_countries.intersection(NORDIC_COUNTRIES)
if nordic:
    scope_filters["Scandinavie disponible"] = nordic
for code, label in (("NO", "Norvège"), ("SE", "Suède"), ("DK", "Danemark")):
    if code in available_countries:
        scope_filters[f"{label} seulement"] = {code}

month_name = st.sidebar.selectbox("Mois", MONTHS, index=0)
month = MONTHS.index(month_name) + 1
metric_label = st.sidebar.selectbox("Indicateur", list(METRICS), index=0)
metric = METRICS[metric_label]
scope = st.sidebar.selectbox("Zone", list(scope_filters))
map_mode = st.sidebar.segmented_control(
    "Affichage",
    ["Points", "Surface continue"],
    default="Points",
    required=True,
    width="stretch",
)
show_labels = st.sidebar.checkbox("Afficher les noms sur la carte", value=False)

st.sidebar.divider()
st.sidebar.caption(f"Période : {start_year}–{end_year} · source Meteostat · {city_count} villes pré-calculées.")
st.sidebar.caption("Changer de mois, d'indicateur ou de zone ne déclenche aucun appel météo.")
st.sidebar.caption("Les échelles de couleur sont fixes : les mois et les zones restent directement comparables.")
if metric == "climate_score":
    st.sidebar.info(
        "Indice global : 50 % soleil, 25 % Tmin, 25 % Tmax. "
        "Le froid est pénalisé, mais la chaleur ne l'est pas : la climatisation est supposée disponible."
    )

rows = climate[climate["month"] == month].copy()
rows = rows[rows["country"].isin(scope_filters[scope])]

rows = rows[rows[metric].notna()].copy()
if rows.empty:
    st.error("Aucune donnée exploitable pour cet indicateur et ce mois dans cette zone.")
    st.stop()

values = rows[metric].astype(float)
scale = scale_for(metric)
vmin, vmax = float(scale["vmin"]), float(scale["vmax"])
ranked = rows.sort_values(metric, ascending=False).copy()
cmap = build_colormap(metric, f"{metric_label} · échelle fixe")

st.title("Carte climat interactive")
st.caption(
    f"Moyennes mensuelles {start_year}–{end_year} · {city_count} villes dans {country_count} pays · carte OpenStreetMap interactive."
)

catalog_count = int(meta.get("cities_catalog", city_count) or city_count)
reported_count = int(meta.get("cities_with_data", city_count) or city_count)
success_ratio = reported_count / catalog_count if catalog_count else 1.0
if success_ratio < 0.8 or available_countries == {"FR"}:
    st.warning(
        f"Jeu de données partiel : {city_count} villes disponibles sur {catalog_count} prévues. "
        "L'application fonctionne avec les données présentes ; le workflow GitHub doit être relancé pour compléter la couverture européenne."
    )

best = ranked.iloc[0]
with st.container(horizontal=True):
    st.metric("Meilleure ville", best["name"], metric_format(float(best[metric]), metric), border=True)
    st.metric("Villes affichées", len(rows), border=True)
    st.metric("Pays affichés", rows["country"].nunique(), border=True)
    st.metric("Période", f"{start_year}–{end_year}", border=True)

# Centre initial puis cadrage automatique sur les points visibles.
map_center = [float(rows["lat"].mean()), float(rows["lon"].mean())]
m = folium.Map(location=map_center, zoom_start=4, tiles=None, control_scale=True, prefer_canvas=True)
folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=True).add_to(m)
folium.TileLayer("CartoDB positron", name="Carte claire", show=False).add_to(m)
Fullscreen(position="topright", title="Plein écran", title_cancel="Quitter le plein écran").add_to(m)

if map_mode == "Surface continue":
    surface_points = tuple(
        (float(r.lat), float(r.lon), float(getattr(r, metric))) for r in rows.itertuples()
    )
    with st.spinner("Interpolation de la surface climatique…", show_time=True):
        surface, surface_bounds = build_idw_surface(surface_points, vmin, vmax, metric)
    ImageOverlay(
        image=surface,
        bounds=surface_bounds,
        origin="lower",
        name="Surface climatique interpolée",
        opacity=0.78,
        pixelated=False,
        mercator_project=True,
        zindex=2,
    ).add_to(m)

for _, r in rows.iterrows():
    value = float(r[metric])
    country = COUNTRY_NAMES.get(r["country"], r["country"])
    sun_txt = safe_format(r.get("sun_days_gt5h"))
    tmin_txt = safe_format(r.get("tmin"), " °C")
    tmax_txt = safe_format(r.get("tmax"), " °C")
    score_txt = safe_format(r.get("climate_score"), "/100")
    sun_source = r.get("sun_source", "station")
    if pd.isna(sun_source):
        sun_source = "station"
    sun_note = "<br><small>☀️ valeur interpolée depuis les villes voisines</small>" if sun_source == "spatial_fill" else ""

    popup_html = f"""
    <div style='font-family:Arial,sans-serif; min-width:245px'>
      <h4 style='margin:0 0 8px'>{r['name']} <span style='font-weight:normal'>({country})</span></h4>
      <b>{month_name} · moyenne {start_year}–{end_year}</b><br>
      ☀️ Jours &gt;5 h : <b>{sun_txt}</b><br>
      🌡️ Tmin moyenne : <b>{tmin_txt}</b><br>
      🌡️ Tmax moyenne : <b>{tmax_txt}</b><br>
      🌤️ Indice climatique : <b>{score_txt}</b>{sun_note}
    </div>
    """
    point_style = (
        {"radius": radius_for(value, vmin, vmax), "color": "#263238", "weight": 0.55,
         "fill_color": cmap(value), "fill_opacity": 0.82, "opacity": 1.0}
        if map_mode == "Points"
        else {"radius": 5.0, "color": "#000000", "weight": 0, "fill_color": "#000000",
              "fill_opacity": 0.0, "opacity": 0.0}
    )
    folium.CircleMarker(
        location=[float(r["lat"]), float(r["lon"])],
        fill=True,
        tooltip=f"{r['name']} — {metric_format(value, metric)}",
        popup=folium.Popup(popup_html, max_width=330),
        **point_style,
    ).add_to(m)
    if show_labels:
        folium.Marker(
            [float(r["lat"]), float(r["lon"])],
            icon=folium.DivIcon(
                icon_size=(150, 24), icon_anchor=(-6, 8),
                html=f"<div style='font-size:9px;font-weight:700;color:#263238;text-shadow:0 0 3px white,0 0 3px white'>{r['name']}</div>"
            ),
        ).add_to(m)

# Folium ajuste le zoom à la sélection : France seule, Scandinavie, Norvège, etc.
if len(rows) > 1:
    m.fit_bounds(
        [[float(rows["lat"].min()), float(rows["lon"].min())],
         [float(rows["lat"].max()), float(rows["lon"].max())]],
        padding=(24, 24),
    )

cmap.add_to(m)
folium.LayerControl(collapsed=True).add_to(m)
st_folium(
    m,
    width=None,
    height=740,
    returned_objects=[],
    key=f"climate-{month}-{metric}-{scope}-{map_mode}-{show_labels}",
)

st.subheader(f"Classement — {metric_label.lower()} en {month_name.lower()}")
rank_df = pd.DataFrame({
    "#": range(1, len(ranked) + 1),
    "Ville": ranked["name"].values,
    "Pays": [COUNTRY_NAMES.get(c, c) for c in ranked["country"]],
    "Indice global /100": ranked["climate_score"].round(0).values,
    "Jours >5 h soleil": ranked["sun_days_gt5h"].round(1).values,
    "Tmin moyenne (°C)": ranked["tmin"].round(1).values,
    "Tmax moyenne (°C)": ranked["tmax"].round(1).values,
})
st.dataframe(rank_df, hide_index=True, width="stretch", height=min(760, 42 + len(rank_df) * 35))

st.caption(
    "Indice global mensuel : 50 % ensoleillement, 25 % Tmin, 25 % Tmax. "
    "Soleil = score max à 20 jours/mois avec >5 h ; score thermique maximal dès 8 °C de Tmin et 18 °C de Tmax, "
    "sans pénalité supplémentaire quand il fait plus chaud. "
    "Les rares trous d'ensoleillement Meteostat peuvent être interpolés spatialement lors du pré-calcul."
)
if map_mode == "Surface continue":
    st.caption(
        "Surface continue : interpolation IDW (pondération inverse de la distance), limitée aux terres émergées "
        "et masquée à plus de 300 km de la ville disponible la plus proche. Cette visualisation est indicative "
        "et ne remplace pas un modèle climatique local."
    )
