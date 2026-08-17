# Carte Climat

Application Streamlit interactive pour comparer le climat en France et dans les pays voisins sur une carte OpenStreetMap zoomable.

## Version Streamlit recommandée

La carte contient maintenant **118 villes** : 79 en France, un maillage de la Belgique, du Luxembourg, de l'Allemagne du Sud/Ouest, de la Suisse, de l'Italie du Nord, de l'Espagne du Nord, Andorre et Monaco, plus Oslo comme référence.

Les données sont calculées sur **tous les mois de l'année** avec trois indicateurs :

- **température minimale moyenne** du mois ;
- **température maximale moyenne** du mois ;
- **nombre moyen de jours par mois avec plus de 5 h de soleil effectif**.

Toutes les valeurs Streamlit utilisent la même méthode : données quotidiennes ERA5-Land via l'API historique Open-Meteo sur la période **1991–2020**. Le premier chargement récupère les normales par lots ; Streamlit les met ensuite en cache sur disque.

### Lancer sous Windows

Si le dépôt est déjà cloné :

```powershell
git pull
.\lancer_streamlit.bat
```

Sinon :

```powershell
git clone https://github.com/matthieuangeli-code/carte-climat.git
cd carte-climat
.\lancer_streamlit.bat
```

Le lanceur vérifie les dépendances, les installe si nécessaire, puis ouvre l'application Streamlit dans le navigateur.

## Carte

- fond OpenStreetMap ;
- zoom à la molette et déplacement libre ;
- plein écran ;
- popups par ville avec les trois indicateurs du mois ;
- filtre France / pays voisins ;
- affichage optionnel des noms ;
- classement dynamique sous la carte.

## Fichiers principaux

- `streamlit_app.py` : application navigateur ;
- `city_catalog.py` : catalogue dense des villes ;
- `requirements.txt` : dépendances ;
- `lancer_streamlit.bat` : lanceur Windows ;
- `carte_climat.py` / `climate_data.py` : ancienne version desktop Tkinter, conservée dans le dépôt.
