@echo off
setlocal

set "BASE_DIR=%~dp0"
set "EXE_PATH=%BASE_DIR%dist\ProgramLauncher\ProgramLauncher.exe"
set "ALT_EXE_PATH=%BASE_DIR%release\ProgramLauncher\ProgramLauncher.exe"
set "PYTHON=python"

if exist "%BASE_DIR%ProgramLauncher.exe" (
    start "" "%BASE_DIR%ProgramLauncher.exe"
    exit /b 0
)

if exist "%EXE_PATH%" (
    start "" "%EXE_PATH%"
    exit /b 0
)

if exist "%ALT_EXE_PATH%" (
    start "" "%ALT_EXE_PATH%"
    exit /b 0
)

if exist "%BASE_DIR%main.py" (
    start "" %PYTHON% "%BASE_DIR%main.py"
    exit /b 0
)

echo ProgramLauncher.exe or main.py was not found.
exit /b 1
