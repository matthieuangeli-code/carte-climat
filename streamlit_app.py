# -*- coding: utf-8 -*-
"""Carte climat interactive — Streamlit + Folium/OpenStreetMap.

Pour rester compatible avec le quota gratuit Open-Meteo, l'application
n'essaye pas de télécharger 30 années quotidiennes pour plus de 100 villes.
Elle construit à la place un échantillon climatologique ERA5-Land réparti
sur le mois et sur 8 années entre 1992 et 2020.
"""

from __future__ import annotations

import calendar
import json
import math
import time
import urllib.error
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

SAMPLE_YEARS = [1992, 1996, 2000, 2004, 2008, 2012, 2016, 2020]
SAMPLE_START_DAYS = [2, 6, 10, 14, 18, 22, 25, 28]
CATALOG_VERSION = "dense-118-v2"


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


def filter_scope(rows: list[dict], scope: str) -> list[dict]:
    if scope == "France seulement":
        return [r for r in rows if r["country"] == "FR"]
    if scope == "Pays voisins seulement":
        return [r for r in rows if r["country"] not in {"FR", "NO"}]
    return rows


def _open_json_with_retry(url: str, attempts: int = 4) -> object:
    delays = [5, 12, 25, 45]
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "carte-climat-streamlit/2.0"},
    )

    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt == attempts - 1:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = max(delays[attempt], float(retry_after)) if retry_after else delays[attempt]
            except (TypeError, ValueError):
                delay = delays[attempt]
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts - 1:
                raise
            time.sleep(delays[attempt])

    raise RuntimeError("Téléchargement Open-Meteo impossible.")


@st.cache_data(show_spinner=False, persist="disk")
def fetch_sample_window(
    month: int,
    year: int,
    start_day: int,
    _catalog_version: str,
) -> list[dict]:
    last_day = calendar.monthrange(year, month)[1]
    start_day = min(start_day, last_day)
    end_day = min(start_day + 2, last_day)

    params = {
        "latitude": ",".join(str(c["lat"]) for c in CITIES),
        "longitude": ",".join(str(c["lon"]) for c in CITIES),
        "start_date": f"{year:04d}-{month:02d}-{start_day:02d}",
        "end_date": f"{year:04d}-{month:02d}-{end_day:02d}",
        "daily": "temperature_2m_min,temperature_2m_max,sunshine_duration",
        "timezone": "auto",
        "models": "era5_land",
    }
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(params)
    payload = _open_json_with_retry(url)
    payloads = payload if isinstance(payload, list) else [payload]

    if len(payloads) != len(CITIES):
        raise RuntimeError(
            f"Open-Meteo a renvoyé {len(payloads)} lieux pour {len(CITIES)} demandés."
        )

    rows: list[dict] = []
    for city, item in zip(CITIES, payloads):
        daily = item.get("daily", {})
        tmins = [float(v) for v in daily.get("temperature_2m_min", []) if v is not None]
        tmaxs = [float(v) for v in daily.get("temperature_2m_max", []) if v is not None]
        sunshine = [float(v) for v in daily.get("sunshine_duration", []) if v is not None]
        rows.append(
            {
                "name": city["name"],
                "country": city["country"],
                "lat": city["lat"],
                "lon": city["lon"],
                "tmin_sum": sum(tmins),
                "tmin_n": len(tmins),
                "tmax_sum": sum(tmaxs),
                "tmax_n": len(tmaxs),
                "sunny_n": sum(1 for seconds in sunshine if seconds > 18_000),
                "sun_n": len(sunshine),
            }
        )
    return rows


@st.cache_data(show_spinner=False, persist="disk")
def load_month_climate(month_idx: int, _catalog_version: str) -> list[dict]:
    month = month_idx + 1
    accum = {
        c["name"]: {
            "name": c["name"], "country": c["country"],
            "lat": c["lat"], "lon": c["lon"],
            "tmin_sum": 0.0, "tmin_n": 0,
            "tmax_sum": 0.0, "tmax_n": 0,
            "sunny_n": 0, "sun_n": 0,
        }
        for c in CITIES
    }

    progress = st.progress(0, text=f"Chargement climatologique — {MONTHS[month_idx]}…")
    total = len(SAMPLE_YEARS)

    for i, (year, start_day) in enumerate(zip(SAMPLE_YEARS, SAMPLE_START_DAYS), start=1):
        window_rows = fetch_sample_window(month, year, start_day, CATALOG_VERSION)
        for row in window_rows:
            a = accum[row["name"]]
            for key in ("tmin_sum", "tmin_n", "tmax_sum", "tmax_n", "sunny_n", "sun_n"):
                a[key] += row[key]
        progress.progress(i / total, text=f"Climat {MONTHS[month_idx]} : échantillon {i}/{total}")
        if i < total:
            time.sleep(0.35)

    progress.empty()
    days_in_month = calendar.monthrange(2019, month)[1]
    result: list[dict] = []

    for city in CITIES:
        a = accum[city["name"]]
        if not a["tmin_n"] or not a["tmax_n"] or not a["sun_n"]:
            continue
        result.append(
            {
                "name": a["name"],
                "country": a["country"],
                "lat": a["lat"],
                "lon": a["lon"],
                "tmin": a["tmin_sum"] / a["tmin_n"],
                "tmax": a["tmax_sum"] / a["tmax_n"],
                "sun_days_gt5h": (a["sunny_n"] / a["sun_n"]) * days_in_month,
            }
        )
    return result


st.sidebar.title("☀️ Carte climat")
st.sidebar.caption(
    "Comparaison ERA5-Land. Le calcul léger échantillonne plusieurs années et plusieurs moments du mois pour éviter les quotas de l'API publique."
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
    f"{len(CITIES)} villes. Une fois un mois chargé, changer d'indicateur ou de zone ne refait aucun appel réseau."
)
if st.sidebar.button("Vider le cache climat"):
    fetch_sample_window.clear()
    load_month_climate.clear()
    st.rerun()

try:
    all_rows = load_month_climate(month_idx, CATALOG_VERSION)
except urllib.error.HTTPError as exc:
    if exc.code == 429:
        st.error(
            "Open-Meteo limite encore temporairement les requêtes (HTTP 429). "
            "Attends une minute puis recharge : les échantillons déjà reçus restent en cache."
        )
    else:
        st.error(f"Erreur Open-Meteo HTTP {exc.code}.")
    st.exception(exc)
    st.stop()
except Exception as exc:
    st.error("Impossible de charger les données climatiques. Recharge la page dans quelques instants.")
    st.exception(exc)
    st.stop()

rows = filter_scope(all_rows, scope)
if not rows:
    st.error("Aucune ville disponible dans cette sélection.")
    st.stop()

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
    ref = next((r for r in all_rows if r["name"] == ref_name), None)
    col.metric(ref_name, metric_format(ref[metric], metric) if ref else "—")

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
    "Méthode légère : ERA5-Land via Open-Meteo, 24 jours échantillonnés par mois et par ville, "
    "répartis sur 8 années entre 1992 et 2020. Tmin/Tmax sont les moyennes de cet échantillon ; "
    "les jours >5 h sont la fréquence observée ramenée au nombre de jours du mois. "
    "Ce mode privilégie la comparaison géographique et évite le quota 429 de l'API gratuite."
)
