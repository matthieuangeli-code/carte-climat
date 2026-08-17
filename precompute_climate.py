# -*- coding: utf-8 -*-
"""Pré-calcule le climat récent et écrit un petit CSV consommé par Streamlit.

Le calcul est volontairement séparé de l'application : il peut prendre quelques
minutes, mais il ne s'exécute qu'en tâche de fond (GitHub Actions ou manuellement).
L'application Streamlit, elle, ne fait ensuite que lire le CSV.
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
START = date(START_YEAR, 1, 1)
END = date(END_YEAR, 12, 31)
OUT_DIR = Path("data")
CSV_PATH = OUT_DIR / "climate_10y.csv"
META_PATH = OUT_DIR / "climate_metadata.json"
MAX_WORKERS = 4


def aggregate_city(city: dict, df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []

    df = df.copy()
    df.index = pd.to_datetime(df.index)
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


def fetch_city(city: dict) -> tuple[str, list[dict], str | None]:
    name = city["name"]
    try:
        point = ms.Point(float(city["lat"]), float(city["lon"]))
        stations = ms.stations.nearby(point, radius=100_000, limit=4)
        if stations is None or len(stations) == 0:
            return name, [], "aucune station proche"

        ts = ms.daily(
            stations,
            START,
            END,
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
                # Selon le provider, plusieurs stations peuvent être empilées.
                numeric = [c for c in ("tmin", "tmax", "tsun") if c in df.columns]
                if numeric:
                    df = df.groupby(df.index)[numeric].mean()

        rows = aggregate_city(city, df)
        return name, rows, None if rows else "aucune donnée quotidienne"
    except Exception as exc:  # une ville ne doit pas bloquer tout le fichier
        return name, [], f"{type(exc).__name__}: {exc}"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    failures: dict[str, str] = {}

    print(f"Pré-calcul {START_YEAR}-{END_YEAR} pour {len(CITIES)} villes")
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
            print(f"[{done:3}/{len(CITIES)}] {name}: {len(rows)} mois" + (f" — {error}" if error else ""), flush=True)

    if not all_rows:
        raise RuntimeError("Aucune donnée n'a pu être générée")

    out = pd.DataFrame(all_rows)
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
