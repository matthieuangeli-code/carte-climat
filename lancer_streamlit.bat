@echo off
cd /d "%~dp0"

echo Mise a jour du depot...
where git >nul 2>&1
if not errorlevel 1 (
  git rev-parse --is-inside-work-tree >nul 2>&1
  if not errorlevel 1 (
    rem Les anciennes versions generaients ces fichiers localement avant qu'ils
    rem soient versionnes dans GitHub. S'ils sont encore non suivis, ils bloquent
    rem git pull. On ne supprime que ces deux fichiers generes et uniquement
    rem lorsqu'ils ne sont pas deja suivis par Git.
    git ls-files --error-unmatch "data/climate_10y.csv" >nul 2>&1
    if errorlevel 1 if exist "data\climate_10y.csv" del /q "data\climate_10y.csv"
    git ls-files --error-unmatch "data/climate_metadata.json" >nul 2>&1
    if errorlevel 1 if exist "data\climate_metadata.json" del /q "data\climate_metadata.json"

    git pull --ff-only
    if errorlevel 1 echo Mise a jour Git ignoree - fichiers locaux conserves.
  )
)

if not exist "data\climate_10y.csv" (
  echo.
  echo ================================================
  echo Premier lancement : preparation des donnees climat
  echo avant ouverture du navigateur.
  echo ================================================
  echo.
  py -3 -c "import pandas, meteostat, geonamescache" >nul 2>&1
  if errorlevel 1 (
    echo Installation des dependances de calcul...
    py -3 -m pip install --upgrade pandas "meteostat>=2.1.4" "geonamescache>=2.0.0"
    if errorlevel 1 goto :error
  )
  py -3 precompute_climate_safe.py
  if errorlevel 1 goto :error_data
)

echo Verification des dependances Streamlit...
py -3 -c "import streamlit, folium, streamlit_folium, pandas" >nul 2>&1
if errorlevel 1 (
  echo Installation des dependances de l'application...
  py -3 -m pip install streamlit folium streamlit-folium pandas
  if errorlevel 1 goto :error
)

echo Lancement de la carte dans le navigateur...
py -3 -m streamlit run streamlit_app.py
exit /b 0

:error_data
echo.
echo Le pre-calcul des donnees a echoue. Le navigateur n'est pas lance avec un jeu incomplet.
pause
exit /b 1

:error
echo.
echo Erreur pendant l'installation. Verifie que Python 3 est installe et accessible avec la commande py.
pause
exit /b 1
