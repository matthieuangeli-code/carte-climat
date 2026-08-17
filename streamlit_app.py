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

from city_catalog_generated import COUNTRY_NAMES

st.set_page_config(page_title="Carte climat — Europe", page_icon="☀️", layout="wide")

DATA_PATH = Path("data/climate_10y.csv")
META_PATH = Path("data/climate_metadata.json")
MONTHS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
METRICS = {
    "Jours avec > 5 h de soleil": "sun_days_gt5h",
    "Température minimale moyenne": "tmin",
    "Température maximale moyenne": "tmax",
    "Indice climatique global": "climate_score",
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


def comfort_score(value: float, zero_low: float, ideal_low: float, ideal_high: float, zero_high: float) -> float:
    if pd.isna(value):
        return float("nan")
    x = float(value)
    if x <= zero_low or x >= zero_high:
        return 0.0
    if ideal_low <= x <= ideal_high:
        return 100.0
    if x < ideal_low:
        return 100.0 * (x - zero_low) / (ideal_low - zero_low)
    return 100.0 * (zero_high - x) / (zero_high - ideal_high)


def add_climate_score(df: pd.DataFrame) -> pd.DataFrame:
    """Indice mensuel 0–100 : 50 % soleil, 25 % Tmin, 25 % Tmax."""
    out = df.copy()
    sun = pd.to_numeric(out["sun_days_gt5h"], errors="coerce")
    tmin = pd.to_numeric(out["tmin"], errors="coerce")
    tmax = pd.to_numeric(out["tmax"], errors="coerce")

    sun_score = (sun / 20.0 * 100.0).clip(lower=0.0, upper=100.0)
    tmin_score = tmin.apply(lambda x: comfort_score(x, -8.0, 8.0, 18.0, 28.0))
    tmax_score = tmax.apply(lambda x: comfort_score(x, 4.0, 18.0, 27.0, 39.0))

    out["sun_score"] = sun_score
    out["tmin_score"] = tmin_score
    out["tmax_score"] = tmax_score
    out["climate_score"] = SUN_WEIGHT * sun_score + TMIN_WEIGHT * tmin_score + TMAX_WEIGHT * tmax_score
    return out


def build_colormap(metric: str, vmin: float, vmax: float, caption: str) -> LinearColormap:
    if metric == "sun_days_gt5h":
        colors = ["#fff7bc", "#fec44f", "#fe9929", "#d95f0e"]
    elif metric == "climate_score":
        colors = ["#b2182b", "#ef8a62", "#fddbc7", "#d9f0d3", "#1a9850"]
    else:
        colors = ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"]
    return LinearColormap(colors=colors, vmin=vmin, vmax=vmax, caption=caption)


@st.cache_data(show_spinner=False)
def load_data() -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(DATA_PATH)
    meta = json.loads(META_PATH.read_text(encoding="utf-8")) if META_PATH.exists() else {}
    return add_climate_score(df), meta


st.sidebar.title("☀️ Carte climat")
st.sidebar.caption("Les données météo sont pré-calculées. L'application ne fait aucun téléchargement météo au démarrage.")

if not DATA_PATH.exists():
    st.error("Le fichier pré-calculé `data/climate_10y.csv` n'est pas encore disponible.")
    st.code("python precompute_climate.py")
    st.stop()

climate, meta = load_data()
start_year = meta.get("start_year", "?")
end_year = meta.get("end_year", "?")

month_name = st.sidebar.selectbox("Mois", MONTHS, index=0)
month = MONTHS.index(month_name) + 1
metric_label = st.sidebar.selectbox("Indicateur", list(METRICS), index=0)
metric = METRICS[metric_label]
scope = st.sidebar.selectbox(
    "Zone",
    [
        "France + Europe proche + Nordiques",
        "France seulement",
        "Europe proche hors France",
        "Scandinavie — NO + SE + DK",
        "Norvège seulement",
        "Suède seulement",
        "Danemark seulement",
    ],
)
show_labels = st.sidebar.checkbox("Afficher les noms sur la carte", value=False)

st.sidebar.divider()
st.sidebar.caption(f"Période : {start_year}–{end_year} · source Meteostat · {climate['name'].nunique()} villes pré-calculées.")
st.sidebar.caption("Changer de mois, d'indicateur ou de zone ne déclenche aucun appel météo.")
if metric == "climate_score":
    st.sidebar.info(
        "Indice global : 50 % soleil, 25 % Tmin, 25 % Tmax. "
        "Le chaud extrême est pénalisé : plus chaud n'est pas automatiquement meilleur."
    )

rows = climate[climate["month"] == month].copy()
if scope == "France seulement":
    rows = rows[rows["country"] == "FR"]
elif scope == "Europe proche hors France":
    rows = rows[(rows["country"] != "FR") & (~rows["country"].isin(NORDIC_COUNTRIES))]
elif scope == "Scandinavie — NO + SE + DK":
    rows = rows[rows["country"].isin(NORDIC_COUNTRIES)]
elif scope == "Norvège seulement":
    rows = rows[rows["country"] == "NO"]
elif scope == "Suède seulement":
    rows = rows[rows["country"] == "SE"]
elif scope == "Danemark seulement":
    rows = rows[rows["country"] == "DK"]

rows = rows[rows[metric].notna()].copy()
if rows.empty:
    st.error("Aucune donnée exploitable pour cet indicateur et ce mois dans cette zone.")
    st.stop()

values = rows[metric].astype(float)
vmin, vmax = float(values.min()), float(values.max())
ranked = rows.sort_values(metric, ascending=False).copy()
cmap = build_colormap(metric, vmin, vmax, f"{metric_label} — {month_name}")

st.title("Carte climat — France, Europe proche & pays nordiques")
st.caption(
    f"Climat récent {start_year}–{end_year} · réseau dense autour de la France + Norvège/Suède/Danemark · OpenStreetMap interactif."
)

cols = st.columns(4)
best = ranked.iloc[0]
cols[0].metric("🥇 Meilleur", f"{best['name']} — {metric_format(float(best[metric]), metric)}")
for col, ref_name in zip(cols[1:], ["Biot", "Embrun", "Oslo"]):
    ref = rows[rows["name"] == ref_name]
    col.metric(ref_name, metric_format(float(ref.iloc[0][metric]), metric) if not ref.empty else "—")

# Centre initial puis cadrage automatique sur les points visibles.
map_center = [float(rows["lat"].mean()), float(rows["lon"].mean())]
m = folium.Map(location=map_center, zoom_start=4, tiles=None, control_scale=True, prefer_canvas=True)
folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=True).add_to(m)
folium.TileLayer("CartoDB positron", name="Carte claire", show=False).add_to(m)
Fullscreen(position="topright", title="Plein écran", title_cancel="Quitter le plein écran").add_to(m)

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
    folium.CircleMarker(
        location=[float(r["lat"]), float(r["lon"])],
        radius=radius_for(value, vmin, vmax),
        color="#263238", weight=0.55, fill=True, fill_color=cmap(value), fill_opacity=0.82,
        tooltip=f"{r['name']} — {metric_format(value, metric)}",
        popup=folium.Popup(popup_html, max_width=330),
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
st_folium(m, use_container_width=True, height=740, returned_objects=[], key=f"climate-{month}-{metric}-{scope}-{show_labels}")

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
st.dataframe(rank_df, hide_index=True, use_container_width=True, height=min(760, 42 + len(rank_df) * 35))

st.caption(
    "Indice global mensuel : 50 % ensoleillement, 25 % Tmin, 25 % Tmax. "
    "Soleil = score max à 20 jours/mois avec >5 h ; Tmin idéale 8–18 °C ; Tmax idéale 18–27 °C. "
    "Les rares trous d'ensoleillement Meteostat peuvent être interpolés spatialement lors du pré-calcul."
)
