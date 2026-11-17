@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Installation de J.A.R.V.I.S. ===
python --version || (echo Installe Python 3.10+ depuis https://python.org en cochant "Add to PATH" & pause & exit /b)
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
echo.
echo Installation terminee. Ouvre le fichier .env et colle ta cle API, puis lance lancer_windows.bat
notepad .env
pause
