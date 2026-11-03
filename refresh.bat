@echo off
rem Локальный запуск сервиса на Windows: проверка нод + сборка страницы.
rem Для публикации добавьте --publish и переменные GITHUB_TOKEN / PUBLISH_REPO.
cd /d "%~dp0"

set "XRAY_BIN=D:\Software\v2rayN\v2rayN-windows-64\bin\xray\xray.exe"
set "SITE_SLUG=demo"
set "PAGES_URL=http://192.168.1.10:8099"

rem убрать перед запуском, если venv создавался через uv: pip не нужен
.venv\Scripts\python.exe -m qrservice.run --config config.json --out dist %*
