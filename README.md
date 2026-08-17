# Carte Climat

Application Python pour comparer le climat de villes françaises et voisines, avec deux interfaces :

- **Streamlit + OpenStreetMap** : version recommandée, dans le navigateur, avec zoom/pan et popups ;
- **Tkinter** : version desktop légère et hors ligne.

## Indicateurs

- température minimale moyenne par mois ;
- température maximale moyenne par mois ;
- nombre moyen de jours avec **au moins 5 h de soleil effectif** ;
- classement dynamique des villes.

La sélection comprend notamment Biot, Embrun, Marseille, Montpellier, Toulouse, Annecy, Chambéry, La Rochelle, Paris, Oslo, Genève, Barcelone, Milan et plusieurs autres villes.

## Version Streamlit — recommandée

### Windows : le plus simple

Double-cliquer sur :

```text
lancer_streamlit.bat
```

Le script installe les dépendances si nécessaire, démarre Streamlit et ouvre automatiquement l'application dans le navigateur.

### En ligne de commande

```powershell
py -3 -m pip install -r requirements.txt
py -3 -m streamlit run streamlit_app.py
```

Puis ouvrir, si nécessaire :

```text
http://localhost:8501
```

### Carte

La version Streamlit utilise **Folium/Leaflet avec OpenStreetMap**. On peut :

- zoomer avec la molette ;
- déplacer la carte ;
- passer en plein écran ;
- cliquer sur une ville pour afficher soleil, Tmin et Tmax ;
- changer de mois et d'indicateur ;
- filtrer France / étranger ;
- afficher une carte claire alternative.

## Données soleil Open-Meteo

Dans la sidebar Streamlit, choisir **Open-Meteo 1991–2020** pour recompter les jours à partir de `sunshine_duration` quotidien. Une journée solaire correspond ici à :

```text
sunshine_duration >= 18 000 secondes = 5 heures
```

Le résultat est mis en cache par Streamlit pour éviter de refaire les requêtes à chaque interaction.

## Version desktop Tkinter

Elle reste disponible :

```powershell
py -3 carte_climat.py
```

ou double-cliquer sur :

```text
lancer_carte_climat.bat
```

Tkinter fonctionne avec les données intégrées sans dépendance `pip`.
