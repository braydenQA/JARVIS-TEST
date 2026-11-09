@echo off
cd /d "%~dp0"
set PY=
py -3.12 -c "import sys" >nul 2>nul && set PY=py -3.12
if not defined PY py -3 -c "import sys" >nul 2>nul && set PY=py -3
if not defined PY python -c "import sys" >nul 2>nul && set PY=python
if defined PY goto tengo

echo Python no esta instalado. Instalando Python 3.12 automaticamente...
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
set PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe
if not exist "%PYEXE%" goto sinpython
set PY="%PYEXE%"
goto tengo

:sinpython
echo No se pudo instalar Python automaticamente.
echo Descargalo de https://www.python.org/downloads/ , marca "Add python.exe to PATH" al instalar y vuelve a ejecutar este archivo.
pause
exit /b

:tengo
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto fallo
for /f "delims=" %%i in ('%PY% -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set PYW=%%i
set S=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AsistenteAplausos.bat
> "%S%" echo @echo off
>> "%S%" echo start "" "%PYW%" "%~dp0asistente.py"
start "" "%PYW%" "%~dp0asistente.py"
echo.
echo Listo. Se inicia solo al prender el equipo. No muevas esta carpeta de lugar.
pause
exit /b

:fallo
echo Fallo la instalacion de librerias. Copia el error de arriba y envialo.
pause
exit /b
