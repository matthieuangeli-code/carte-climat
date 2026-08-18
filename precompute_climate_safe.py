# -*- coding: utf-8 -*-
"""Pré-calcul robuste du climat 10 ans.

Cette version évite la corruption du cache/base de stations Meteostat :
1) initialisation du cache et de la base SQLite une seule fois ;
2) résolution des stations en série ;
3) téléchargements météo seulement ensuite en parallèle ;
4) validation stricte avant remplacement du CSV versionné.
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
MAX_WORKERS = 3
CHUNK_YEARS = 2
STATION_LIMIT = 2
SUN_FILL_RADIUS_KM = 450.0
MIN_SUCCESS_RATIO = 0.80


def date_chunks() -> list[tuple[date, date]]:
    chunks = []
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


def prepare_meteostat() -> None:
    """Initialise les répertoires et force le téléchargement complet de la DB stations."""
    cache_dir = Path(ms.config.cache_directory).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)

    db_file = Path(ms.config.stations_db_file).expanduser()
    db_file.parent.mkdir(parents=True, exist_ok=True)

    # Une première requête SÉRIE force l'initialisation de la DB SQLite avant tout thread.
    test_point = ms.Point(48.8566, 2.3522)
    try:
        stations = ms.stations.nearby(test_point, radius=100_000, limit=1)
        if stations is None or len(stations) == 0:
            raise RuntimeError("Base Meteostat initialisée mais aucune station trouvée près de Paris")
    except Exception:
        # Sur un runner neuf ce cas est rare ; s'il existe déjà un fichier incomplet, on repart proprement.
        if db_file.exists():
            db_file.unlink()
        stations = ms.stations.nearby(test_point, radius=100_000, limit=1)
        if stations is None or len(stations) == 0:
            raise RuntimeError("Impossible d'initialiser la base de stations Meteostat")


def resolve_station_jobs(cities: list[dict]) -> tuple[list[tuple[dict, pd.DataFrame]], dict[str, str]]:
    """Résout les stations proches en série pour éviter tout accès SQLite concurrent."""
    jobs: list[tuple[dict, pd.DataFrame]] = []
    failures: dict[str, str] = {}
    total = len(cities)

    for i, city in enumerate(cities, start=1):
        try:
            point = ms.Point(float(city["lat"]), float(city["lon"]))
            stations = ms.stations.nearby(point, radius=120_000, limit=STATION_LIMIT)
            if stations is None or len(stations) == 0:
                failures[city["name"]] = "aucune station proche"
            else:
                jobs.append((city, stations.copy()))
        except Exception as exc:
            failures[city["name"]] = f"station lookup: {type(exc).__name__}: {exc}"
        if i % 50 == 0 or i == total:
            print(f"Stations résolues : {i}/{total}", flush=True)

    return jobs, failures


def normalize_timeseries(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    numeric = [c for c in ("tmin", "tmax", "tsun") if c in df.columns]
    if not numeric:
        return pd.DataFrame()

    df = df[numeric].copy()
    if isinstance(df.index, pd.MultiIndex):
        # Meteostat peut retourner station + date en MultiIndex.
        datetime_level = None
        for level in range(df.index.nlevels):
            vals = df.index.get_level_values(level)
            if pd.api.types.is_datetime64_any_dtype(vals):
                datetime_level = level
                break
        if datetime_level is None:
            datetime_level = df.index.nlevels - 1
        df = df.groupby(level=datetime_level)[numeric].mean()
    else:
        # Avec plusieurs stations certains providers empilent des doublons sur la date.
        df.index = pd.to_datetime(df.index)
        if df.index.has_duplicates:
            df = df.groupby(df.index)[numeric].mean()
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def aggregate_city(city: dict, df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    df = normalize_timeseries(df)
    if df.empty:
        return []

    df = df[~df.index.duplicated(keep="last")].copy()
    df["year"] = df.index.year
    df["month"] = df.index.month
    rows = []

    for month in range(1, 13):
        subset = df[df["month"] == month]
        if subset.empty:
            continue
        tmin = float(subset["tmin"].mean()) if "tmin" in subset and subset["tmin"].notna().any() else None
        tmax = float(subset["tmax"].mean()) if "tmax" in subset and subset["tmax"].notna().any() else None

        sun_estimates = []
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
        coverage = sun_valid_days / sun_possible_days if sun_possible_days else 0.0

        rows.append({
            "name": city["name"],
            "country": city["country"],
            "lat": float(city["lat"]),
            "lon": float(city["lon"]),
            "month": month,
            "tmin": tmin,
            "tmax": tmax,
            "sun_days_gt5h": sun_days,
            "sun_coverage": coverage,
            "sun_source": "station" if sun_days is not None else "missing",
        })
    return rows


def fetch_city(job: tuple[dict, pd.DataFrame]) -> tuple[str, list[dict], str | None]:
    city, stations = job
    name = city["name"]
    try:
        frames = []
        for chunk_start, chunk_end in date_chunks():
            ts = ms.daily(
                stations,
                chunk_start,
                chunk_end,
                parameters=[ms.Parameter.TMIN, ms.Parameter.TMAX, ms.Parameter.TSUN],
                providers=[ms.Provider.DAILY, ms.Provider.DAILY_DERIVED],
            )
            df_chunk = ts.fetch()
            df_chunk = normalize_timeseries(df_chunk)
            if not df_chunk.empty:
                frames.append(df_chunk)

        if not frames:
            return name, [], "aucune donnée quotidienne"
        rows = aggregate_city(city, pd.concat(frames).sort_index())
        return name, rows, None if rows else "agrégation vide"
    except Exception as exc:
        return name, [], f"weather fetch: {type(exc).__name__}: {exc}"


def fill_missing_sun(out: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    out = out.copy()
    filled = 0
    for month in range(1, 13):
        month_mask = out["month"] == month
        valid = out[month_mask & out["sun_days_gt5h"].notna()].copy()
        missing = out.index[month_mask & out["sun_days_gt5h"].isna()].tolist()
        if valid.empty:
            continue
        for idx in missing:
            row = out.loc[idx]
            neighbours = []
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
    print(f"Pré-calcul SAFE {START_YEAR}-{END_YEAR} pour {len(cities)} villes", flush=True)

    prepare_meteostat()
    jobs, failures = resolve_station_jobs(cities)

    # Toutes les écritures de cache météo sont désactivées pendant le parallélisme.
    # La DB stations a déjà été initialisée/résolue en série.
    ms.config.cache_enable = False
    ms.config.cache_autoclean = False

    all_rows = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_city, job): job[0]["name"] for job in jobs}
        total = len(futures)
        for done, future in enumerate(as_completed(futures), start=1):
            name, rows, error = future.result()
            if rows:
                all_rows.extend(rows)
            if error:
                failures[name] = error
            if done % 20 == 0 or done == total:
                print(f"Météo : {done}/{total}", flush=True)

    if not all_rows:
        raise RuntimeError("Aucune donnée générée")

    out = pd.DataFrame(all_rows)
    cities_with_data = int(out["name"].nunique())
    success_ratio = cities_with_data / len(cities)
    if success_ratio < MIN_SUCCESS_RATIO:
        raise RuntimeError(
            f"Base refusée : seulement {cities_with_data}/{len(cities)} villes "
            f"({success_ratio:.1%}), seuil minimum {MIN_SUCCESS_RATIO:.0%}."
        )

    temp_ok = out[["tmin", "tmax"]].notna().all(axis=1).mean()
    if temp_ok < 0.75:
        raise RuntimeError(f"Base refusée : couverture Tmin/Tmax insuffisante ({temp_ok:.1%}).")

    out, filled_sun = fill_missing_sun(out)
    out = out.sort_values(["country", "name", "month"], kind="stable")
    for col in ("tmin", "tmax", "sun_days_gt5h", "sun_coverage"):
        out[col] = pd.to_numeric(out[col], errors="coerce").round(3)

    # Écriture atomique seulement APRÈS validation.
    tmp_csv = CSV_PATH.with_suffix(".tmp")
    tmp_meta = META_PATH.with_suffix(".tmp")
    out.to_csv(tmp_csv, index=False, encoding="utf-8")

    meta = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "start_year": START_YEAR,
        "end_year": END_YEAR,
        "source": "Meteostat daily + daily_derived",
        "catalog_method": "GeoNames dense France/Europe proche + dedicated Norway/Sweden/Denmark network",
        "cities_catalog": len(cities),
        "cities_with_data": cities_with_data,
        "success_ratio": round(success_ratio, 4),
        "rows": len(out),
        "failures": failures,
        "definition_sunny_day": "tsun > 300 minutes",
        "sun_spatial_fills": filled_sun,
        "sun_fill_radius_km": SUN_FILL_RADIUS_KM,
        "generator": "precompute_climate_safe.py",
    }
    tmp_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_csv.replace(CSV_PATH)
    tmp_meta.replace(META_PATH)

    print(f"VALIDÉ : {cities_with_data}/{len(cities)} villes ({success_ratio:.1%})", flush=True)
    print(f"Écrit : {CSV_PATH} — {len(out)} lignes", flush=True)


if __name__ == "__main__":
    main()
