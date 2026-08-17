# -*- coding: utf-8 -*-
"""Catalogue de villes pour la carte climat Streamlit."""

CITIES = [
    # France — nord / ouest
    {"name": "Paris", "country": "FR", "lat": 48.857, "lon": 2.352},
    {"name": "Lille", "country": "FR", "lat": 50.629, "lon": 3.057},
    {"name": "Dunkerque", "country": "FR", "lat": 51.035, "lon": 2.377},
    {"name": "Calais", "country": "FR", "lat": 50.951, "lon": 1.858},
    {"name": "Amiens", "country": "FR", "lat": 49.895, "lon": 2.302},
    {"name": "Rouen", "country": "FR", "lat": 49.443, "lon": 1.100},
    {"name": "Le Havre", "country": "FR", "lat": 49.494, "lon": 0.108},
    {"name": "Caen", "country": "FR", "lat": 49.182, "lon": -0.370},
    {"name": "Cherbourg", "country": "FR", "lat": 49.633, "lon": -1.622},
    {"name": "Rennes", "country": "FR", "lat": 48.117, "lon": -1.678},
    {"name": "Saint-Malo", "country": "FR", "lat": 48.649, "lon": -2.025},
    {"name": "Brest", "country": "FR", "lat": 48.390, "lon": -4.486},
    {"name": "Quimper", "country": "FR", "lat": 47.996, "lon": -4.102},
    {"name": "Lorient", "country": "FR", "lat": 47.748, "lon": -3.367},
    {"name": "Vannes", "country": "FR", "lat": 47.658, "lon": -2.760},
    {"name": "Nantes", "country": "FR", "lat": 47.218, "lon": -1.553},
    {"name": "La Roche-sur-Yon", "country": "FR", "lat": 46.671, "lon": -1.426},
    {"name": "Angers", "country": "FR", "lat": 47.478, "lon": -0.563},
    {"name": "Le Mans", "country": "FR", "lat": 48.007, "lon": 0.199},
    {"name": "Tours", "country": "FR", "lat": 47.394, "lon": 0.685},
    {"name": "Orléans", "country": "FR", "lat": 47.903, "lon": 1.909},
    {"name": "Chartres", "country": "FR", "lat": 48.447, "lon": 1.489},
    {"name": "La Rochelle", "country": "FR", "lat": 46.160, "lon": -1.151},
    {"name": "Poitiers", "country": "FR", "lat": 46.580, "lon": 0.340},

    # France — nord-est / centre / est
    {"name": "Reims", "country": "FR", "lat": 49.258, "lon": 4.031},
    {"name": "Troyes", "country": "FR", "lat": 48.297, "lon": 4.074},
    {"name": "Metz", "country": "FR", "lat": 49.119, "lon": 6.176},
    {"name": "Nancy", "country": "FR", "lat": 48.693, "lon": 6.184},
    {"name": "Strasbourg", "country": "FR", "lat": 48.573, "lon": 7.752},
    {"name": "Colmar", "country": "FR", "lat": 48.079, "lon": 7.359},
    {"name": "Mulhouse", "country": "FR", "lat": 47.750, "lon": 7.335},
    {"name": "Dijon", "country": "FR", "lat": 47.322, "lon": 5.042},
    {"name": "Besançon", "country": "FR", "lat": 47.238, "lon": 6.024},
    {"name": "Auxerre", "country": "FR", "lat": 47.798, "lon": 3.573},
    {"name": "Bourges", "country": "FR", "lat": 47.081, "lon": 2.399},
    {"name": "Nevers", "country": "FR", "lat": 46.990, "lon": 3.159},
    {"name": "Châteauroux", "country": "FR", "lat": 46.811, "lon": 1.692},
    {"name": "Limoges", "country": "FR", "lat": 45.833, "lon": 1.261},
    {"name": "Clermont-Ferrand", "country": "FR", "lat": 45.777, "lon": 3.087},
    {"name": "Mâcon", "country": "FR", "lat": 46.306, "lon": 4.831},
    {"name": "Bourg-en-Bresse", "country": "FR", "lat": 46.205, "lon": 5.226},
    {"name": "Lyon", "country": "FR", "lat": 45.764, "lon": 4.836},
    {"name": "Saint-Étienne", "country": "FR", "lat": 45.440, "lon": 4.387},
    {"name": "Grenoble", "country": "FR", "lat": 45.189, "lon": 5.725},
    {"name": "Annecy", "country": "FR", "lat": 45.899, "lon": 6.129},
    {"name": "Chambéry", "country": "FR", "lat": 45.565, "lon": 5.918},
    {"name": "Valence", "country": "FR", "lat": 44.933, "lon": 4.893},
    {"name": "Gap", "country": "FR", "lat": 44.559, "lon": 6.079},
    {"name": "Embrun", "country": "FR", "lat": 44.564, "lon": 6.495},
    {"name": "Briançon", "country": "FR", "lat": 44.899, "lon": 6.643},

    # France — sud-ouest
    {"name": "Bordeaux", "country": "FR", "lat": 44.838, "lon": -0.579},
    {"name": "Arcachon", "country": "FR", "lat": 44.652, "lon": -1.178},
    {"name": "Bayonne", "country": "FR", "lat": 43.493, "lon": -1.475},
    {"name": "Pau", "country": "FR", "lat": 43.295, "lon": -0.371},
    {"name": "Tarbes", "country": "FR", "lat": 43.233, "lon": 0.078},
    {"name": "Agen", "country": "FR", "lat": 44.204, "lon": 0.621},
    {"name": "Montauban", "country": "FR", "lat": 44.017, "lon": 1.355},
    {"name": "Toulouse", "country": "FR", "lat": 43.605, "lon": 1.444},
    {"name": "Albi", "country": "FR", "lat": 43.929, "lon": 2.148},
    {"name": "Rodez", "country": "FR", "lat": 44.351, "lon": 2.573},
    {"name": "Carcassonne", "country": "FR", "lat": 43.213, "lon": 2.351},

    # France — Méditerranée / Alpes du Sud / Corse
    {"name": "Perpignan", "country": "FR", "lat": 42.689, "lon": 2.895},
    {"name": "Narbonne", "country": "FR", "lat": 43.184, "lon": 3.003},
    {"name": "Béziers", "country": "FR", "lat": 43.344, "lon": 3.215},
    {"name": "Montpellier", "country": "FR", "lat": 43.611, "lon": 3.877},
    {"name": "Nîmes", "country": "FR", "lat": 43.837, "lon": 4.360},
    {"name": "Mende", "country": "FR", "lat": 44.518, "lon": 3.501},
    {"name": "Avignon", "country": "FR", "lat": 43.949, "lon": 4.806},
    {"name": "Arles", "country": "FR", "lat": 43.677, "lon": 4.628},
    {"name": "Aix-en-Provence", "country": "FR", "lat": 43.529, "lon": 5.447},
    {"name": "Marseille", "country": "FR", "lat": 43.297, "lon": 5.370},
    {"name": "Toulon", "country": "FR", "lat": 43.124, "lon": 5.928},
    {"name": "Fréjus", "country": "FR", "lat": 43.433, "lon": 6.737},
    {"name": "Cannes", "country": "FR", "lat": 43.552, "lon": 7.017},
    {"name": "Biot", "country": "FR", "lat": 43.628, "lon": 7.095},
    {"name": "Nice", "country": "FR", "lat": 43.710, "lon": 7.262},
    {"name": "Menton", "country": "FR", "lat": 43.775, "lon": 7.498},
    {"name": "Ajaccio", "country": "FR", "lat": 41.919, "lon": 8.739},
    {"name": "Bastia", "country": "FR", "lat": 42.697, "lon": 9.450},

    # Belgique
    {"name": "Bruxelles", "country": "BE", "lat": 50.850, "lon": 4.352},
    {"name": "Gand", "country": "BE", "lat": 51.054, "lon": 3.717},
    {"name": "Anvers", "country": "BE", "lat": 51.219, "lon": 4.402},
    {"name": "Charleroi", "country": "BE", "lat": 50.411, "lon": 4.444},
    {"name": "Liège", "country": "BE", "lat": 50.633, "lon": 5.579},

    # Luxembourg
    {"name": "Luxembourg", "country": "LU", "lat": 49.612, "lon": 6.132},

    # Allemagne
    {"name": "Sarrebruck", "country": "DE", "lat": 49.240, "lon": 6.997},
    {"name": "Trèves", "country": "DE", "lat": 49.750, "lon": 6.637},
    {"name": "Karlsruhe", "country": "DE", "lat": 49.006, "lon": 8.404},
    {"name": "Fribourg-en-Brisgau", "country": "DE", "lat": 47.999, "lon": 7.842},
    {"name": "Stuttgart", "country": "DE", "lat": 48.776, "lon": 9.183},
    {"name": "Francfort", "country": "DE", "lat": 50.110, "lon": 8.682},
    {"name": "Cologne", "country": "DE", "lat": 50.938, "lon": 6.960},
    {"name": "Munich", "country": "DE", "lat": 48.137, "lon": 11.576},

    # Suisse
    {"name": "Genève", "country": "CH", "lat": 46.204, "lon": 6.143},
    {"name": "Lausanne", "country": "CH", "lat": 46.520, "lon": 6.633},
    {"name": "Neuchâtel", "country": "CH", "lat": 46.990, "lon": 6.929},
    {"name": "Sion", "country": "CH", "lat": 46.233, "lon": 7.360},
    {"name": "Berne", "country": "CH", "lat": 46.948, "lon": 7.447},
    {"name": "Bâle", "country": "CH", "lat": 47.559, "lon": 7.588},
    {"name": "Zurich", "country": "CH", "lat": 47.376, "lon": 8.541},

    # Italie du Nord
    {"name": "Aoste", "country": "IT", "lat": 45.737, "lon": 7.320},
    {"name": "Turin", "country": "IT", "lat": 45.070, "lon": 7.687},
    {"name": "Cuneo", "country": "IT", "lat": 44.384, "lon": 7.542},
    {"name": "Milan", "country": "IT", "lat": 45.464, "lon": 9.190},
    {"name": "Gênes", "country": "IT", "lat": 44.405, "lon": 8.946},
    {"name": "Sanremo", "country": "IT", "lat": 43.815, "lon": 7.776},
    {"name": "Bologne", "country": "IT", "lat": 44.494, "lon": 11.342},

    # Espagne nord / Catalogne
    {"name": "Saint-Sébastien", "country": "ES", "lat": 43.318, "lon": -1.981},
    {"name": "Bilbao", "country": "ES", "lat": 43.263, "lon": -2.935},
    {"name": "Pampelune", "country": "ES", "lat": 42.813, "lon": -1.645},
    {"name": "Saragosse", "country": "ES", "lat": 41.648, "lon": -0.889},
    {"name": "Lleida", "country": "ES", "lat": 41.617, "lon": 0.620},
    {"name": "Gérone", "country": "ES", "lat": 41.979, "lon": 2.821},
    {"name": "Figueres", "country": "ES", "lat": 42.267, "lon": 2.961},
    {"name": "Barcelone", "country": "ES", "lat": 41.387, "lon": 2.169},

    # Micro-États frontaliers
    {"name": "Andorre-la-Vieille", "country": "AD", "lat": 42.507, "lon": 1.522},
    {"name": "Monaco", "country": "MC", "lat": 43.738, "lon": 7.424},

    # Référence historique de la comparaison
    {"name": "Oslo", "country": "NO", "lat": 59.914, "lon": 10.752},
]

COUNTRY_NAMES = {
    "FR": "France",
    "BE": "Belgique",
    "LU": "Luxembourg",
    "DE": "Allemagne",
    "CH": "Suisse",
    "IT": "Italie",
    "ES": "Espagne",
    "AD": "Andorre",
    "MC": "Monaco",
    "NO": "Norvège",
}
