@echo off
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AsistenteAplausos.bat" 2>nul
taskkill /f /im pythonw.exe 2>nul
echo Desinstalado.
pause
