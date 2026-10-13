@echo off
cd /d "%~dp0"
echo Abriendo Verifica CUSA en http://localhost:8000 ...
start "" http://localhost:8000/index.html
py -m http.server 8000
pause
