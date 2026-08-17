# Carte Climat

Application Streamlit interactive pour comparer le climat récent sur une carte OpenStreetMap zoomable.

## Données et zone couverte

Les données météo sont **pré-calculées** sur les 10 dernières années complètes puis stockées dans `data/climate_10y.csv`. L'application Streamlit ne télécharge donc aucune donnée météo au démarrage.

Le catalogue est généré automatiquement à partir de GeoNames :

- réseau dense de villes en France métropolitaine ;
- villes européennes jusqu'à environ **1000 km du pourtour français** ;
- sélection spatiale pour éviter des milliers de points redondants ;
- grandes villes conservées même dans les zones denses ;
- quelques petites villes prioritaires (Biot, Embrun, Valbonne, Mende, etc.) ;
- Oslo conservé comme référence hors rayon.

Le nombre exact de villes dépend du catalogue GeoNames utilisé lors du dernier pré-calcul et est affiché dans la sidebar de l'app.

## Indicateurs mensuels

Les 12 mois de l'année sont disponibles avec quatre indicateurs :

1. **jours avec >5 h de soleil** ;
2. **température minimale moyenne** ;
3. **température maximale moyenne** ;
4. **indice climatique global /100**.

### Indice climatique global

L'indice est volontairement pratique plutôt que scientifique :

- **50 %** ensoleillement ;
- **25 %** confort des Tmin ;
- **25 %** confort des Tmax.

Le soleil atteint son score maximum à 20 jours/mois avec plus de 5 h. La zone de confort des Tmin est 8–18 °C et celle des Tmax 18–27 °C. Les températures très froides comme les chaleurs excessives sont pénalisées : « plus chaud » n'est donc pas automatiquement « mieux ».

Meteostat n'offre pas `tsun` avec la même couverture partout. Les trous résiduels d'ensoleillement peuvent être complétés lors du pré-calcul par interpolation spatiale à partir des villes voisines ; ces valeurs sont signalées dans les popups.

## Lancer sous Windows

Si le dépôt est déjà cloné :

```powershell
git pull --ff-only
.\lancer_streamlit.bat
```

Sinon :

```powershell
git clone https://github.com/matthieuangeli-code/carte-climat.git
cd carte-climat
.\lancer_streamlit.bat
```

Le lanceur se met à jour depuis GitHub puis ouvre Streamlit. Si le CSV pré-calculé est présent, l'ouverture est immédiate.

## Pré-calcul

`precompute_climate.py` récupère les séries Meteostat sur les 10 dernières années complètes, en blocs de 2 ans pour respecter les limites du provider `daily_derived`.

Le workflow `.github/workflows/build-climate-data.yml` exécute ce calcul sur GitHub Actions et commit automatiquement :

- `data/climate_10y.csv`
- `data/climate_metadata.json`

Il est aussi possible de lancer manuellement :

```powershell
py -3 precompute_climate.py
```

## Fichiers principaux

- `streamlit_app.py` : carte et interface navigateur ;
- `city_catalog_generated.py` : génération du réseau de villes ;
- `precompute_climate.py` : pré-calcul 10 ans ;
- `data/climate_10y.csv` : données déjà agrégées ;
- `lancer_streamlit.bat` : lanceur Windows ;
- `carte_climat.py` / `climate_data.py` : ancienne version desktop Tkinter, conservée dans le dépôt.
