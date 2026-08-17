# -*- coding: utf-8 -*-
"""Pré-calcule le climat récent et écrit un petit CSV consommé par Streamlit.

Le calcul est volontairement séparé de l'application. Le catalogue de villes
est généré automatiquement jusqu'à environ 1000 km du pourtour français, puis
les séries 10 ans sont téléchargées par blocs de 2 ans pour respecter les
garde-fous Meteostat.
"""

from __future__ import annotations

import calendar
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

import meteostat as ms
import pandas as pd

from city_catalog_generated import build_cities

END_YEAR = date.today().year - 1
START_YEAR = END_YEAR - 9
OUT_DIR = Path("data")
CSV_PATH = OUT_DIR / "climate_10y.csv"
META_PATH = OUT_DIR / "climate_metadata.json"
MAX_WORKERS = 4
CHUNK_YEARS = 2
STATION_LIMIT = 2
SUN_FILL_RADIUS_KM = 450.0


def date_chunks() -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    year = START_YEAR
    while year <= END_YEAR:
        end_year = min(year + CHUNK_YEARS - 1, END_YEAR)
        chunks.append((date(year, 1, 1), date(end_year, 12, 31)))
        year = end_year + 1
    return chunks


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def aggregate_city(city: dict, df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []

    df = df.copy()
    df.index = pd.to_datetime(df.index)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df["year"] = df.index.year
    df["month"] = df.index.month
    rows: list[dict] = []

    for month in range(1, 13):
        subset = df[df["month"] == month]
        if subset.empty:
            continue

        tmin = float(subset["tmin"].mean()) if "tmin" in subset and subset["tmin"].notna().any() else None
        tmax = float(subset["tmax"].mean()) if "tmax" in subset and subset["tmax"].notna().any() else None

        sun_estimates: list[float] = []
        sun_valid_days = 0
        sun_possible_days = 0
        if "tsun" in subset.columns:
            for year in range(START_YEAR, END_YEAR + 1):
                ys = subset[subset["year"] == year]["tsun"].dropna()
                days_in_month = calendar.monthrange(year, month)[1]
                sun_valid_days += len(ys)
                sun_possible_days += days_in_month
                if len(ys) < 12:
                    continue
                sunny = int((ys > 300).sum())
                estimate = sunny * days_in_month / len(ys)
                sun_estimates.append(min(float(days_in_month), estimate))

        sun_days = float(sum(sun_estimates) / len(sun_estimates)) if sun_estimates else None
        sun_coverage = (sun_valid_days / sun_possible_days) if sun_possible_days else 0.0

        rows.append({
            "name": city["name"],
            "country": city["country"],
            "lat": float(city["lat"]),
            "lon": float(city["lon"]),
            "month": month,
            "tmin": tmin,
            "tmax": tmax,
            "sun_days_gt5h": sun_days,
            "sun_coverage": sun_coverage,
            "sun_source": "station" if sun_days is not None else "missing",
        })
    return rows


def fetch_city(city: dict) -> tuple[str, list[dict], str | None]:
    name = city["name"]
    try:
        point = ms.Point(float(city["lat"]), float(city["lon"]))
        stations = ms.stations.nearby(point, radius=100_000, limit=STATION_LIMIT)
        if stations is None or len(stations) == 0:
            return name, [], "aucune station proche"

        frames: list[pd.DataFrame] = []
        for chunk_start, chunk_end in date_chunks():
            ts = ms.daily(
                stations,
                chunk_start,
                chunk_end,
                parameters=[ms.Parameter.TMIN, ms.Parameter.TMAX, ms.Parameter.TSUN],
                providers=[ms.Provider.DAILY, ms.Provider.DAILY_DERIVED],
            )
            try:
                df_chunk = ms.interpolate(
                    ts,
                    point,
                    distance_threshold=100_000,
                    elevation_threshold=1000,
                ).fetch()
            except Exception:
                df_chunk = ts.fetch()
                if df_chunk is not None and not df_chunk.empty:
                    numeric = [c for c in ("tmin", "tmax", "tsun") if c in df_chunk.columns]
                    if numeric:
                        df_chunk = df_chunk.groupby(df_chunk.index)[numeric].mean()
            if df_chunk is not None and not df_chunk.empty:
                frames.append(df_chunk)

        if not frames:
            return name, [], "aucune donnée quotidienne"

        df = pd.concat(frames).sort_index()
        rows = aggregate_city(city, df)
        return name, rows, None if rows else "agrégation vide"
    except Exception as exc:
        return name, [], f"{type(exc).__name__}: {exc}"


def fill_missing_sun(out: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Complète les trous d'ensoleillement par interpolation spatiale simple.

    Meteostat ne fournit pas tsun avec la même couverture partout. Pour une carte
    exploratoire, on utilise la moyenne pondérée des trois points valides les plus
    proches du même mois, dans un rayon maximal de 450 km. Les points interpolés
    sont explicitement marqués dans le CSV et le popup Streamlit.
    """
    out = out.copy()
    filled = 0

    for month in range(1, 13):
        month_mask = out["month"] == month
        valid = out[month_mask & out["sun_days_gt5h"].notna()].copy()
        missing_indices = out.index[month_mask & out["sun_days_gt5h"].isna()].tolist()
        if valid.empty:
            continue

        for idx in missing_indices:
            row = out.loc[idx]
            neighbours: list[tuple[float, float]] = []
            for _, v in valid.iterrows():
                d = haversine_km(float(row["lat"]), float(row["lon"]), float(v["lat"]), float(v["lon"]))
                if d <= SUN_FILL_RADIUS_KM:
                    neighbours.append((d, float(v["sun_days_gt5h"])))
            neighbours.sort(key=lambda x: x[0])
            neighbours = neighbours[:3]
            if not neighbours:
                continue
            weights = [1.0 / (d + 30.0) for d, _ in neighbours]
            value = sum(w * v for w, (_, v) in zip(weights, neighbours)) / sum(weights)
            out.at[idx, "sun_days_gt5h"] = value
            out.at[idx, "sun_source"] = "spatial_fill"
            filled += 1

    return out, filled


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cities = build_cities()
    all_rows: list[dict] = []
    failures: dict[str, str] = {}

    print(f"Pré-calcul {START_YEAR}-{END_YEAR} pour {len(cities)} villes")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_city, city): city["name"] for city in cities}
        done = 0
        for future in as_completed(futures):
            done += 1
            name, rows, error = future.result()
            if rows:
                all_rows.extend(rows)
            if error:
                failures[name] = error
            print(f"[{done:3}/{len(cities)}] {name}: {len(rows)} mois" + (f" — {error}" if error else ""), flush=True)

    if not all_rows:
        raise RuntimeError("Aucune donnée n'a pu être générée")

    out = pd.DataFrame(all_rows)
    out, filled_sun = fill_missing_sun(out)
    out = out.sort_values(["country", "name", "month"], kind="stable")
    for col in ("tmin", "tmax", "sun_days_gt5h", "sun_coverage"):
        out[col] = pd.to_numeric(out[col], errors="coerce").round(3)

    tmp = CSV_PATH.with_suffix(".tmp")
    out.to_csv(tmp, index=False, encoding="utf-8")
    tmp.replace(CSV_PATH)

    meta = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "start_year": START_YEAR,
        "end_year": END_YEAR,
        "source": "Meteostat daily + daily_derived",
        "catalog_method": "GeoNames spatial grid, foreign cities within ~1000 km of French perimeter + priority cities",
        "cities_catalog": len(cities),
        "cities_with_data": int(out["name"].nunique()),
        "rows": len(out),
        "failures": failures,
        "definition_sunny_day": "tsun > 300 minutes",
        "sun_spatial_fills": filled_sun,
        "sun_fill_radius_km": SUN_FILL_RADIUS_KM,
    }
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Écrit: {CSV_PATH} ({len(out)} lignes, {out['name'].nunique()} villes)")
    print(f"Ensoleillement interpolé pour {filled_sun} lignes mensuelles")
    print(f"Écrit: {META_PATH}")
    if failures:
        print(f"Villes avec avertissement: {len(failures)}")


if __name__ == "__main__":
    main()
