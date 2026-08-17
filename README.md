# Carte Climat

Petite application Python/Tkinter pour comparer le climat de villes françaises et voisines.

## Indicateurs

- température minimale moyenne par mois ;
- température maximale moyenne par mois ;
- nombre moyen de jours avec **au moins 5 h de soleil effectif** ;
- classement dynamique et carte interactive.

La sélection comprend notamment Biot, Embrun, Marseille, Montpellier, Toulouse, Annecy, Chambéry, La Rochelle, Paris, Oslo, Genève, Barcelone, Milan et plusieurs autres villes.

## Lancer sous Windows

1. Installer Python 3 (avec Tkinter, inclus dans l'installation standard de python.org).
2. Télécharger ou cloner ce dépôt.
3. Double-cliquer sur `lancer_carte_climat.bat`, ou lancer :

```powershell
py -3 carte_climat.py
```

Alternative :

```powershell
python carte_climat.py
```

Aucune dépendance `pip` n'est nécessaire.

## Données

L'application démarre hors ligne avec les données intégrées. Le bouton **Recalculer soleil exact 1991–2020** interroge l'archive Open-Meteo et recompte jour par jour les journées où `sunshine_duration >= 300 minutes`.

Les températures intégrées et les valeurs initiales servent de jeu comparatif ; pour l'indicateur soleil, le recalcul Open-Meteo permet d'obtenir une série homogène sur 1991–2020.
