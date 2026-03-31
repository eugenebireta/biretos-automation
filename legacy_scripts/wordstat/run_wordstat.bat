@echo off
setlocal
cd /d "%~dp0"
rem Пытаемся использовать py (Python Launcher), иначе python
where py >nul 2>nul && set "PY=py" || set "PY=python"
"%PY%" combine_wordstat_v3.py "%~dp0csv"
echo.
echo Готово. Результаты: wordstat_monthly.csv и wordstat_yearly.xlsx в этой папке.
pause