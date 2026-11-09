@echo off
cd /d "%~dp0"
set PY=
py -3.12 -c "import sys" >nul 2>nul && set PY=py -3.12
if not defined PY py -3 -c "import sys" >nul 2>nul && set PY=py -3
if not defined PY python -c "import sys" >nul 2>nul && set PY=python
%PY% -c "import sounddevice as sd;print(sd.query_devices())"
echo.
echo Si quieres otro microfono, escribe parte de su nombre en config.json en "microfono".
echo Registro de la app: %APPDATA%\AsistenteAplausos\log.txt
pause
