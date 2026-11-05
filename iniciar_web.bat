@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Ambiente virtual ausente. Execute na pasta do projeto:
  echo py -m venv .venv
  echo .venv\Scripts\python.exe -m pip install -r requirements-web.txt
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0iniciar_web.py" %*
if errorlevel 1 pause
endlocal
