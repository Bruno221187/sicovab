@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo Rode primeiro o iniciar.bat & pause & exit /b 1 )
set /p ARQ=Arraste aqui a planilha .xlsm e tecle Enter: 
".venv\Scripts\python.exe" migrar_planilha.py %ARQ%
pause
