# -*- coding: utf-8 -*-
"""Pré-calcule le climat récent et écrit un petit CSV consommé par Streamlit.

Le calcul est volontairement séparé de l'application : il peut prendre quelques
minutes, mais il ne s'exécute qu'en tâche de fond (GitHub Actions ou manuellement).
L'application Streamlit, elle, ne fait ensuite que lire le CSV.

Meteostat bloque par défaut les requêtes horaires de plus de 3 ans. Le provider
``daily_derived`` pouvant s'appuyer sur l'horaire, la période 10 ans est donc
chargée en blocs de 2 ans puis concaténée avant agrégation.
"""

from __future__ import annotations

import calendar
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

import meteostat as ms
import pandas as pd

from city_catalog import CITIES

END_YEAR = date.today().year - 1
START_YEAR = END_YEAR - 9
OUT_DIR = Path("data")
CSV_PATH = OUT_DIR / "climate_10y.csv"
META_PATH = OUT_DIR / "climate_metadata.json"
MAX_WORKERS = 3
CHUNK_YEARS = 2
STATION_LIMIT = 2


def date_chunks() -> list[tuple[date, date]]:
    """Découpe les 10 ans en fenêtres <= 2 ans, compatibles avec Meteostat."""
    chunks: list[tuple[date, date]] = []
    year = START_YEAR
    while year <= END_YEAR:
        end_year = min(year + CHUNK_YEARS - 1, END_YEAR)
        chunks.append((date(year, 1, 1), date(end_year, 12, 31)))
        year = end_year + 1
    return chunks


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
                # On ne projette le compte que si au moins ~40 % du mois est couvert.
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
        })
    return rows


def fetch_window(point: ms.Point, stations, start: date, end: date) -> pd.DataFrame:
    """Charge une fenêtre courte. daily_derived reste sous la garde des 3 ans."""
    ts = ms.daily(
        stations,
        start,
        end,
        parameters=[ms.Parameter.TMIN, ms.Parameter.TMAX, ms.Parameter.TSUN],
        providers=[ms.Provider.DAILY, ms.Provider.DAILY_DERIVED],
    )

    try:
        df = ms.interpolate(
            ts,
            point,
            distance_threshold=100_000,
            elevation_threshold=1000,
        ).fetch()
    except Exception:
        df = ts.fetch()
        if df is not None and not df.empty:
            numeric = [c for c in ("tmin", "tmax", "tsun") if c in df.columns]
            if numeric:
                # Plusieurs stations peuvent partager une même date.
                if isinstance(df.index, pd.MultiIndex):
                    date_level = "time" if "time" in df.index.names else df.index.names[-1]
                    df = df.reset_index().groupby(date_level, as_index=True)[numeric].mean()
                else:
                    df = df.groupby(df.index)[numeric].mean()
    return df


def fetch_city(city: dict) -> tuple[str, list[dict], str | None]:
    name = city["name"]
    try:
        point = ms.Point(float(city["lat"]), float(city["lon"]))
        stations = ms.stations.nearby(point, radius=100_000, limit=STATION_LIMIT)
        if stations is None or len(stations) == 0:
            return name, [], "aucune station proche"

        frames: list[pd.DataFrame] = []
        chunk_errors: list[str] = []
        for start, end in date_chunks():
            try:
                frame = fetch_window(point, stations, start, end)
                if frame is not None and not frame.empty:
                    frames.append(frame)
            except Exception as exc:
                chunk_errors.append(f"{start.year}-{end.year}: {type(exc).__name__}: {exc}")

        if not frames:
            error = "; ".join(chunk_errors[:2]) if chunk_errors else "aucune donnée quotidienne"
            return name, [], error

        df = pd.concat(frames, axis=0, sort=False)
        if isinstance(df.index, pd.MultiIndex):
            # Sécurité supplémentaire si un provider conserve un index station/date.
            numeric = [c for c in ("tmin", "tmax", "tsun") if c in df.columns]
            reset = df.reset_index()
            date_col = "time" if "time" in reset.columns else reset.columns[-1]
            df = reset.groupby(date_col, as_index=True)[numeric].mean()
        else:
            df = df[~df.index.duplicated(keep="last")].sort_index()

        rows = aggregate_city(city, df)
        warning = None
        if chunk_errors:
            warning = f"{len(chunk_errors)} bloc(s) manquant(s)"
        return name, rows, warning if rows else "aucune donnée quotidienne"
    except Exception as exc:  # une ville ne doit pas bloquer tout le fichier
        return name, [], f"{type(exc).__name__}: {exc}"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    failures: dict[str, str] = {}

    chunks = date_chunks()
    print(
        f"Pré-calcul {START_YEAR}-{END_YEAR} pour {len(CITIES)} villes "
        f"({len(chunks)} blocs de {CHUNK_YEARS} ans max, {STATION_LIMIT} stations max)"
    )

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_city, city): city["name"] for city in CITIES}
        done = 0
        for future in as_completed(futures):
            done += 1
            name, rows, error = future.result()
            if rows:
                all_rows.extend(rows)
            if error:
                failures[name] = error
            print(
                f"[{done:3}/{len(CITIES)}] {name}: {len(rows)} mois"
                + (f" — {error}" if error else ""),
                flush=True,
            )

    if not all_rows:
        raise RuntimeError("Aucune donnée n'a pu être générée")

    out = pd.DataFrame(all_rows)
    out = out.sort_values(["country", "name", "month"], kind="stable")
    for col in ("tmin", "tmax", "sun_days_gt5h", "sun_coverage"):
        out[col] = pd.to_numeric(out[col], errors="coerce").round(3)

    # Écriture atomique : si le calcul échoue, on ne laisse pas un faux CSV complet.
    tmp = CSV_PATH.with_suffix(".tmp")
    out.to_csv(tmp, index=False, encoding="utf-8")
    tmp.replace(CSV_PATH)

    meta = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "start_year": START_YEAR,
        "end_year": END_YEAR,
        "source": "Meteostat daily + daily_derived",
        "request_chunks_years": CHUNK_YEARS,
        "station_limit": STATION_LIMIT,
        "cities_catalog": len(CITIES),
        "cities_with_data": int(out["name"].nunique()),
        "rows": len(out),
        "failures": failures,
        "definition_sunny_day": "tsun > 300 minutes",
    }
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Écrit: {CSV_PATH} ({len(out)} lignes)")
    print(f"Écrit: {META_PATH}")
    if failures:
        print(f"Villes avec avertissement: {len(failures)}")


if __name__ == "__main__":
    main()
