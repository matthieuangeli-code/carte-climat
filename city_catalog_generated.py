# -*- coding: utf-8 -*-
"""Construction automatique d'un réseau dense de villes autour de la France.

Le catalogue est généré uniquement lors du pré-calcul. Streamlit lit ensuite
le CSV produit et n'a pas besoin de GeoNames au démarrage.
"""

from __future__ import annotations

import math

COUNTRY_NAMES = {
    "AD": "Andorre", "AT": "Autriche", "BA": "Bosnie-Herzégovine",
    "BE": "Belgique", "CH": "Suisse", "CZ": "Tchéquie", "DE": "Allemagne",
    "DK": "Danemark", "ES": "Espagne", "FR": "France", "GB": "Royaume-Uni",
    "HR": "Croatie", "HU": "Hongrie", "IE": "Irlande", "IT": "Italie",
    "LI": "Liechtenstein", "LU": "Luxembourg", "MC": "Monaco",
    "NL": "Pays-Bas", "NO": "Norvège", "PL": "Pologne", "PT": "Portugal",
    "SI": "Slovénie", "SK": "Slovaquie", "SM": "Saint-Marin", "VA": "Vatican",
}

# Pays européens susceptibles d'avoir des villes à moins de 1000 km de la
# France métropolitaine. Le test géographique est ensuite appliqué ville par ville.
ALLOWED_COUNTRIES = set(COUNTRY_NAMES) - {"NO"}

# Points répartis sur le pourtour métropolitain, Corse comprise. Pour cette app
# de comparaison, une distance au plus proche de ces points est une approximation
# simple et robuste de la distance aux frontières/côtes françaises.
FRANCE_EDGE_ANCHORS = [
    (51.035, 2.377), (50.629, 3.057), (50.138, 4.825), (49.520, 5.760),
    (48.573, 7.752), (47.750, 7.335), (46.204, 6.143), (45.923, 6.869),
    (44.899, 6.643), (43.775, 7.498), (43.124, 5.928), (42.689, 2.895),
    (42.432, 1.943), (43.163, -1.238), (43.359, -1.774), (44.652, -1.178),
    (46.160, -1.151), (48.390, -4.486), (49.633, -1.622), (50.951, 1.858),
    (41.919, 8.739), (42.697, 9.450),
]

# Petites villes importantes pour le projet qui ne survivraient pas toujours au
# filtre de population / maillage spatial.
PRIORITY_CITIES = [
    {"name": "Biot", "country": "FR", "lat": 43.628, "lon": 7.095, "population": 10000},
    {"name": "Valbonne", "country": "FR", "lat": 43.642, "lon": 7.009, "population": 13000},
    {"name": "Antibes", "country": "FR", "lat": 43.580, "lon": 7.125, "population": 75000},
    {"name": "Embrun", "country": "FR", "lat": 44.564, "lon": 6.495, "population": 6500},
    {"name": "Briançon", "country": "FR", "lat": 44.899, "lon": 6.643, "population": 12000},
    {"name": "Gap", "country": "FR", "lat": 44.559, "lon": 6.079, "population": 41000},
    {"name": "Mende", "country": "FR", "lat": 44.518, "lon": 3.501, "population": 12500},
    {"name": "Narbonne", "country": "FR", "lat": 43.184, "lon": 3.003, "population": 56000},
    {"name": "La Rochelle", "country": "FR", "lat": 46.160, "lon": -1.151, "population": 78000},
    {"name": "Annecy", "country": "FR", "lat": 45.899, "lon": 6.129, "population": 132000},
    {"name": "Chambéry", "country": "FR", "lat": 45.565, "lon": 5.918, "population": 60000},
    {"name": "Colmar", "country": "FR", "lat": 48.079, "lon": 7.359, "population": 70000},
    {"name": "Arcachon", "country": "FR", "lat": 44.652, "lon": -1.178, "population": 11500},
    {"name": "Pau", "country": "FR", "lat": 43.295, "lon": -0.371, "population": 77000},
    {"name": "Aix-en-Provence", "country": "FR", "lat": 43.529, "lon": 5.447, "population": 148000},
    {"name": "Carpentras", "country": "FR", "lat": 44.055, "lon": 5.048, "population": 30000},
    {"name": "Genève", "country": "CH", "lat": 46.204, "lon": 6.143, "population": 205000},
    {"name": "Sion", "country": "CH", "lat": 46.233, "lon": 7.360, "population": 36000},
    {"name": "Barcelone", "country": "ES", "lat": 41.387, "lon": 2.169, "population": 1660000},
    {"name": "Milan", "country": "IT", "lat": 45.464, "lon": 9.190, "population": 1370000},
    {"name": "Turin", "country": "IT", "lat": 45.070, "lon": 7.687, "population": 850000},
    {"name": "Aoste", "country": "IT", "lat": 45.737, "lon": 7.320, "population": 34000},
    {"name": "Sanremo", "country": "IT", "lat": 43.815, "lon": 7.776, "population": 54000},
    {"name": "Fribourg-en-Brisgau", "country": "DE", "lat": 47.999, "lon": 7.842, "population": 235000},
    {"name": "Andorre-la-Vieille", "country": "AD", "lat": 42.507, "lon": 1.522, "population": 23000},
    # Oslo reste volontairement hors rayon comme point de comparaison historique.
    {"name": "Oslo", "country": "NO", "lat": 59.914, "lon": 10.752, "population": 720000},
]

MAX_DISTANCE_KM = 1000.0
MIN_POP_FRANCE = 20_000
MIN_POP_FOREIGN = 60_000
MAJOR_CITY_POP = 300_000
GRID_LAT_DEG = 0.60
GRID_LON_DEG = 0.80


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def distance_to_france_km(lat: float, lon: float) -> float:
    return min(_haversine_km(lat, lon, a, b) for a, b in FRANCE_EDGE_ANCHORS)


def _metropolitan_france(lat: float, lon: float) -> bool:
    return 41.0 <= lat <= 51.6 and -5.5 <= lon <= 10.0


def build_cities() -> list[dict]:
    """Construit un maillage dense mais raisonnable pour le pré-calcul.

    GeoNames fournit le réservoir de villes. On garde la ville la plus peuplée
    de chaque cellule spatiale, toutes les grandes villes, puis les villes
    prioritaires ci-dessus. Cela donne une carte beaucoup plus continue sans
    demander des milliers de séries météo.
    """
    import geonamescache

    gc = geonamescache.GeonamesCache()
    candidates: list[dict] = []

    for raw in gc.get_cities().values():
        country = raw.get("countrycode")
        if country not in ALLOWED_COUNTRIES:
            continue
        try:
            lat = float(raw["latitude"])
            lon = float(raw["longitude"])
            population = int(raw.get("population") or 0)
        except (TypeError, ValueError, KeyError):
            continue

        if not (33.0 <= lat <= 61.5 and -16.0 <= lon <= 25.0):
            continue

        if country == "FR":
            if not _metropolitan_france(lat, lon) or population < MIN_POP_FRANCE:
                continue
            distance = 0.0
        else:
            if population < MIN_POP_FOREIGN:
                continue
            distance = distance_to_france_km(lat, lon)
            if distance > MAX_DISTANCE_KM:
                continue

        candidates.append({
            "name": raw["name"],
            "country": country,
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "population": population,
            "distance_france_km": round(distance, 1),
        })

    # Un point représentatif par cellule pour assurer un vrai maillage spatial.
    grid: dict[tuple[int, int], dict] = {}
    majors: list[dict] = []
    for city in candidates:
        key = (math.floor(city["lat"] / GRID_LAT_DEG), math.floor(city["lon"] / GRID_LON_DEG))
        old = grid.get(key)
        if old is None or city["population"] > old["population"]:
            grid[key] = city
        if city["population"] >= MAJOR_CITY_POP:
            majors.append(city)

    merged = list(grid.values()) + majors + PRIORITY_CITIES

    # Déduplication nom+pays puis déduplication de points quasi identiques.
    by_name: dict[tuple[str, str], dict] = {}
    for city in merged:
        key = (city["name"].casefold(), city["country"])
        old = by_name.get(key)
        if old is None or city.get("population", 0) > old.get("population", 0):
            by_name[key] = city

    cities = list(by_name.values())
    cities.sort(key=lambda c: (c["country"] != "FR", c["country"], c["name"]))
    return cities
