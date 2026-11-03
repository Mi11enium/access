@echo off
rem Локальное обновление: проверка серверов + публикация на GitHub Pages.
rem Все значения (токен, адреса, путь к xray) берутся из .env.local рядом.
cd /d "%~dp0"
if not exist logs mkdir logs
.venv\Scripts\python.exe -m qrservice.run --config config.json --out dist %* >> logs\local_refresh.log 2>&1
