@echo off
REM ============================================================
REM eu-macro-dashboard — Main launcher
REM Double-click този файл и ползвай менюто.
REM ============================================================

REM UTF-8 за кирилица в терминала
chcp 65001 >nul

REM Отива в директорията на .bat файла
cd /d "%~dp0"

:MENU
cls
echo ============================================================
echo   eu-macro-dashboard
echo ============================================================
echo.
echo   1. Data status         (бърза проверка кои серии са свежи)
echo   2. Briefing - бърз      (без historical analogs)
echo   3. Briefing - пълен     (analogs + journal)
echo   4. Run tests
echo   5. Open output folder
echo   6. Git status
echo.
echo   0. Exit
echo.
set /p choice="Избор: "

if "%choice%"=="1" goto STATUS
if "%choice%"=="2" goto BRIEF_QUICK
if "%choice%"=="3" goto BRIEF_FULL
if "%choice%"=="4" goto TESTS
if "%choice%"=="5" goto OPEN_OUTPUT
if "%choice%"=="6" goto GIT_STATUS
if "%choice%"=="0" exit /b 0
goto MENU

:STATUS
echo.
echo --- Running: python run.py --status
echo.
python run.py --status
echo.
pause
goto MENU

:BRIEF_QUICK
echo.
echo --- Running: python run.py --briefing --with-journal
echo.
python run.py --briefing --with-journal
echo.
pause
goto MENU

:BRIEF_FULL
echo.
echo --- Running: python run.py --briefing --with-analogs --with-journal
echo.
python run.py --briefing --with-analogs --with-journal
echo.
pause
goto MENU

:TESTS
echo.
echo --- Running: pytest tests/ -q
echo.
pytest tests/ -q
echo.
pause
goto MENU

:OPEN_OUTPUT
if not exist "output" mkdir output
start "" "output"
goto MENU

:GIT_STATUS
echo.
git status
echo.
pause
goto MENU
