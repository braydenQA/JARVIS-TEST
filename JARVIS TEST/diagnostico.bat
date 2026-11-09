@echo off
cd /d "%~dp0"
set PY=
py -3.12 -c "import sys" >nul 2>nul && set PY=py -3.12
if not defined PY py -3 -c "import sys" >nul 2>nul && set PY=py -3
if not defined PY set PY=python
%PY% asistente.py --diag
pause
