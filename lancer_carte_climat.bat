@echo off
cd /d "%~dp0"
py -3 carte_climat.py 2>nul
if errorlevel 1 python carte_climat.py
