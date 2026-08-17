@echo off
cd /d "%~dp0"

echo Mise a jour du depot...
where git >nul 2>&1
if not errorlevel 1 (
  git rev-parse --is-inside-work-tree >nul 2>&1
  if not errorlevel 1 (
    git pull --ff-only
    if errorlevel 1 echo Mise a jour Git ignoree - fichiers locaux conserves.
  )
)

echo Verification des dependances Streamlit...
py -3 -c "import streamlit, folium, streamlit_folium, pandas, meteostat" >nul 2>&1
if errorlevel 1 (
  echo Installation ou mise a jour des dependances...
  py -3 -m pip install -r requirements.txt
  if errorlevel 1 goto :error
)

echo Lancement de la carte dans le navigateur...
py -3 -m streamlit run streamlit_app.py
exit /b 0

:error
echo.
echo Erreur pendant l'installation. Verifie que Python 3 est installe et accessible avec la commande py.
pause
exit /b 1
