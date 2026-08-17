# -*- coding: utf-8 -*-
"""Construction automatique d'un réseau dense de villes autour de la France.

Le catalogue est généré uniquement lors du pré-calcul. Streamlit lit ensuite
le CSV produit et n'a pas besoin de GeoNames au démarrage.

Zone couverte :
- France métropolitaine : réseau dense ;
- reste de l'Europe : villes jusqu'à ~1000 km du pourtour français ;
- Norvège, Suède et Danemark : réseau nordique dédié, sans limite de distance ;
- petites villes prioritaires conservées explicitement.
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
    "SE": "Suède", "SI": "Slovénie", "SK": "Slovaquie",
    "SM": "Saint-Marin", "VA": "Vatican",
}

# Les pays nordiques sont traités séparément : ils sont inclus même au-delà des
# 1000 km de la France et avec un seuil de population plus bas.
NORDIC_COUNTRIES = {"NO", "SE", "DK"}
ALLOWED_COUNTRIES = set(COUNTRY_NAMES)

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
    # France / Alpes / Méditerranée
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

    # Europe proche
    {"name": "Genève", "country": "CH", "lat": 46.204, "lon": 6.143, "population": 205000},
    {"name": "Sion", "country": "CH", "lat": 46.233, "lon": 7.360, "population": 36000},
    {"name": "Barcelone", "country": "ES", "lat": 41.387, "lon": 2.169, "population": 1660000},
    {"name": "Milan", "country": "IT", "lat": 45.464, "lon": 9.190, "population": 1370000},
    {"name": "Turin", "country": "IT", "lat": 45.070, "lon": 7.687, "population": 850000},
    {"name": "Aoste", "country": "IT", "lat": 45.737, "lon": 7.320, "population": 34000},
    {"name": "Sanremo", "country": "IT", "lat": 43.815, "lon": 7.776, "population": 54000},
    {"name": "Fribourg-en-Brisgau", "country": "DE", "lat": 47.999, "lon": 7.842, "population": 235000},
    {"name": "Andorre-la-Vieille", "country": "AD", "lat": 42.507, "lon": 1.522, "population": 23000},

    # Norvège — côtes, intérieur et nord
    {"name": "Oslo", "country": "NO", "lat": 59.914, "lon": 10.752, "population": 720000},
    {"name": "Bergen", "country": "NO", "lat": 60.392, "lon": 5.323, "population": 290000},
    {"name": "Trondheim", "country": "NO", "lat": 63.430, "lon": 10.395, "population": 215000},
    {"name": "Stavanger", "country": "NO", "lat": 58.970, "lon": 5.733, "population": 145000},
    {"name": "Kristiansand", "country": "NO", "lat": 58.147, "lon": 7.995, "population": 115000},
    {"name": "Drammen", "country": "NO", "lat": 59.744, "lon": 10.204, "population": 103000},
    {"name": "Tønsberg", "country": "NO", "lat": 59.267, "lon": 10.407, "population": 58000},
    {"name": "Fredrikstad", "country": "NO", "lat": 59.218, "lon": 10.929, "population": 84000},
    {"name": "Skien", "country": "NO", "lat": 59.209, "lon": 9.609, "population": 55000},
    {"name": "Arendal", "country": "NO", "lat": 58.461, "lon": 8.772, "population": 46000},
    {"name": "Haugesund", "country": "NO", "lat": 59.414, "lon": 5.268, "population": 38000},
    {"name": "Ålesund", "country": "NO", "lat": 62.472, "lon": 6.149, "population": 58000},
    {"name": "Molde", "country": "NO", "lat": 62.737, "lon": 7.160, "population": 33000},
    {"name": "Lillehammer", "country": "NO", "lat": 61.115, "lon": 10.466, "population": 29000},
    {"name": "Hamar", "country": "NO", "lat": 60.794, "lon": 11.068, "population": 33000},
    {"name": "Bodø", "country": "NO", "lat": 67.280, "lon": 14.405, "population": 53000},
    {"name": "Narvik", "country": "NO", "lat": 68.439, "lon": 17.427, "population": 22000},
    {"name": "Harstad", "country": "NO", "lat": 68.799, "lon": 16.541, "population": 25000},
    {"name": "Tromsø", "country": "NO", "lat": 69.649, "lon": 18.956, "population": 78000},
    {"name": "Alta", "country": "NO", "lat": 69.968, "lon": 23.271, "population": 21000},

    # Suède — sud, centre, côte baltique et nord
    {"name": "Stockholm", "country": "SE", "lat": 59.329, "lon": 18.069, "population": 990000},
    {"name": "Göteborg", "country": "SE", "lat": 57.708, "lon": 11.974, "population": 605000},
    {"name": "Malmö", "country": "SE", "lat": 55.605, "lon": 13.003, "population": 365000},
    {"name": "Uppsala", "country": "SE", "lat": 59.859, "lon": 17.639, "population": 180000},
    {"name": "Västerås", "country": "SE", "lat": 59.609, "lon": 16.545, "population": 130000},
    {"name": "Örebro", "country": "SE", "lat": 59.275, "lon": 15.214, "population": 126000},
    {"name": "Linköping", "country": "SE", "lat": 58.410, "lon": 15.621, "population": 116000},
    {"name": "Jönköping", "country": "SE", "lat": 57.782, "lon": 14.161, "population": 100000},
    {"name": "Karlstad", "country": "SE", "lat": 59.379, "lon": 13.504, "population": 68000},
    {"name": "Helsingborg", "country": "SE", "lat": 56.046, "lon": 12.695, "population": 115000},
    {"name": "Kalmar", "country": "SE", "lat": 56.663, "lon": 16.356, "population": 42000},
    {"name": "Sundsvall", "country": "SE", "lat": 62.391, "lon": 17.307, "population": 59000},
    {"name": "Östersund", "country": "SE", "lat": 63.179, "lon": 14.636, "population": 53000},
    {"name": "Umeå", "country": "SE", "lat": 63.825, "lon": 20.263, "population": 92000},
    {"name": "Luleå", "country": "SE", "lat": 65.584, "lon": 22.154, "population": 49000},
    {"name": "Kiruna", "country": "SE", "lat": 67.856, "lon": 20.225, "population": 23000},

    # Danemark
    {"name": "Copenhague", "country": "DK", "lat": 55.676, "lon": 12.568, "population": 660000},
    {"name": "Aarhus", "country": "DK", "lat": 56.163, "lon": 10.204, "population": 290000},
    {"name": "Odense", "country": "DK", "lat": 55.403, "lon": 10.402, "population": 185000},
    {"name": "Aalborg", "country": "DK", "lat": 57.048, "lon": 9.919, "population": 120000},
    {"name": "Esbjerg", "country": "DK", "lat": 55.477, "lon": 8.459, "population": 72000},
    {"name": "Randers", "country": "DK", "lat": 56.460, "lon": 10.036, "population": 64000},
    {"name": "Kolding", "country": "DK", "lat": 55.491, "lon": 9.472, "population": 62000},
    {"name": "Roskilde", "country": "DK", "lat": 55.642, "lon": 12.080, "population": 52000},
]

MAX_DISTANCE_KM = 1000.0
MIN_POP_FRANCE = 20_000
MIN_POP_FOREIGN = 60_000
MIN_POP_NORDIC = {"NO": 15_000, "SE": 20_000, "DK": 15_000}
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

    France et Europe proche sont spatialement échantillonnées pour éviter des
    milliers de points redondants. Dans NO/SE/DK, toutes les villes GeoNames au-
    dessus du seuil nordique sont conservées : le réseau y est volontairement
    plus dense pour permettre une vraie comparaison régionale.
    """
    import geonamescache

    gc = geonamescache.GeonamesCache()
    regular_candidates: list[dict] = []
    nordic_candidates: list[dict] = []

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

        # Europe élargie, y compris tout le nord de la Scandinavie.
        if not (33.0 <= lat <= 72.5 and -16.0 <= lon <= 32.0):
            continue

        if country == "FR":
            if not _metropolitan_france(lat, lon) or population < MIN_POP_FRANCE:
                continue
            distance = 0.0
        elif country in NORDIC_COUNTRIES:
            if population < MIN_POP_NORDIC[country]:
                continue
            distance = distance_to_france_km(lat, lon)
        else:
            if population < MIN_POP_FOREIGN:
                continue
            distance = distance_to_france_km(lat, lon)
            if distance > MAX_DISTANCE_KM:
                continue

        city = {
            "name": raw["name"],
            "country": country,
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "population": population,
            "distance_france_km": round(distance, 1),
        }
        if country in NORDIC_COUNTRIES:
            nordic_candidates.append(city)
        else:
            regular_candidates.append(city)

    # France + Europe proche : un point représentatif par cellule, avec toutes
    # les grandes villes conservées. Le pays fait partie de la clé pour éviter
    # qu'une ville située juste de l'autre côté d'une frontière en masque une autre.
    grid: dict[tuple[str, int, int], dict] = {}
    majors: list[dict] = []
    for city in regular_candidates:
        key = (
            city["country"],
            math.floor(city["lat"] / GRID_LAT_DEG),
            math.floor(city["lon"] / GRID_LON_DEG),
        )
        old = grid.get(key)
        if old is None or city["population"] > old["population"]:
            grid[key] = city
        if city["population"] >= MAJOR_CITY_POP:
            majors.append(city)

    # NO/SE/DK : toutes les villes au-dessus du seuil sont gardées. Avec les
    # seuils 15–20k, la densité reste bonne sans faire exploser le pré-calcul.
    merged = list(grid.values()) + majors + nordic_candidates + PRIORITY_CITIES

    by_name: dict[tuple[str, str], dict] = {}
    for city in merged:
        key = (city["name"].casefold(), city["country"])
        old = by_name.get(key)
        if old is None or city.get("population", 0) > old.get("population", 0):
            by_name[key] = city

    cities = list(by_name.values())
    cities.sort(key=lambda c: (c["country"] != "FR", c["country"], c["name"]))
    return cities
