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
        echo [hint] Expected "%WORKSPACE_ROOT%\.venvs\ai-manga-factory\Scripts\python.exe"
        echo [hint] Or set AI_MANGA_FACTORY_PYTHON.
        exit /b 1
    )
    set "PYTHON=python"
)

set "PACK_NAME=%~1"
if not defined PACK_NAME set "PACK_NAME=dpcq_ch1_20"

set "SCENE_COUNT=%~2"
if not defined SCENE_COUNT set "SCENE_COUNT=20"

set "MODE=%~3"
if not defined MODE set "MODE=placeholder"

set "EXTRA_ARGS=%~4 %~5 %~6 %~7 %~8 %~9"
set "REAL_FLAG="
if /I "%MODE%"=="real" set "REAL_FLAG=--real-images"

pushd "%ROOT_DIR%" >nul
echo [run] project root: %ROOT_DIR%
echo [run] pack: %PACK_NAME% scene_count: %SCENE_COUNT% mode: %MODE%
"%PYTHON%" "%ROOT_DIR%\scripts\run_adaptation_pack.py" --pack-name "%PACK_NAME%" --scene-count "%SCENE_COUNT%" %REAL_FLAG% %EXTRA_ARGS%
set "RUN_EXIT=%ERRORLEVEL%"
if not "%RUN_EXIT%"=="0" (
    echo [error] run_adaptation_pack.py failed with exit code %RUN_EXIT%.
    popd >nul
    exit /b %RUN_EXIT%
)

"%PYTHON%" "%ROOT_DIR%\scripts\validate_job_output.py" --pack-name "%PACK_NAME%"
set "VALIDATE_EXIT=%ERRORLEVEL%"
if not "%VALIDATE_EXIT%"=="0" (
    echo [warn] validation reported FAIL for pack %PACK_NAME%.
    popd >nul
    exit /b %VALIDATE_EXIT%
)

echo [run] done
popd >nul
exit /b 0
