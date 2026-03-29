@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%.") do set "ROOT_DIR=%%~fI"
for %%I in ("%ROOT_DIR%\..\..\..\..") do set "WORKSPACE_ROOT=%%~fI"

if defined AI_MANGA_FACTORY_PYTHON (
    set "PYTHON=%AI_MANGA_FACTORY_PYTHON%"
) else if exist "%WORKSPACE_ROOT%\.venvs\ai-manga-factory\Scripts\python.exe" (
    set "PYTHON=%WORKSPACE_ROOT%\.venvs\ai-manga-factory\Scripts\python.exe"
) else if exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
    set "PYTHON=%ROOT_DIR%\.venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [error] Python executable not found.
        exit /b 1
    )
    set "PYTHON=python"
)

"%PYTHON%" "%ROOT_DIR%\start_project.py" backend %*
exit /b %ERRORLEVEL%
