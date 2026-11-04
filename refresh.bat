@echo off
rem Локальное обновление: проверка серверов + публикация на GitHub Pages.
rem Все значения (токен, адреса, путь к xray) берутся из .env.local рядом.
cd /d "%~dp0"
if not exist logs mkdir logs
set GIT_TERMINAL_PROMPT=0
set GCM_INTERACTIVE=never
set PYTHONIOENCODING=utf-8

.venv\Scripts\python.exe -m qrservice.run --config config.json --out dist %* >> logs\local_refresh.log 2>&1
if errorlevel 3 (
  echo [retry %DATE% %TIME%] код %ERRORLEVEL%, повтор через 60 с >> logs\local_refresh.log
  timeout /t 60 /nobreak >nul
  .venv\Scripts\python.exe -m qrservice.run --config config.json --out dist %* >> logs\local_refresh.log 2>&1
)

