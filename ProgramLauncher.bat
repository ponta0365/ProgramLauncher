@echo off
setlocal EnableExtensions

set "BASE_DIR=%~dp0"
set "ROOT_EXE=%BASE_DIR%ProgramLauncher.exe"
set "DIST_EXE=%BASE_DIR%dist\ProgramLauncher\ProgramLauncher.exe"
set "RELEASE_EXE=%BASE_DIR%release\ProgramLauncher\ProgramLauncher.exe"
set "MAIN_PY=%BASE_DIR%main.py"

if exist "%MAIN_PY%" (
    py -3.12 "%MAIN_PY%"
    if not errorlevel 1 exit /b 0

    python "%MAIN_PY%"
    if not errorlevel 1 exit /b 0
)

if exist "%ROOT_EXE%" (
    start "" "%ROOT_EXE%"
    exit /b 0
)

if exist "%DIST_EXE%" (
    start "" "%DIST_EXE%"
    exit /b 0
)

if exist "%RELEASE_EXE%" (
    start "" "%RELEASE_EXE%"
    exit /b 0
)

echo ProgramLauncher.exe or main.py was not found.
echo Python 3.12 / py / python ????????????
exit /b 1
