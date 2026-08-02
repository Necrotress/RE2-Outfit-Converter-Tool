@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Dev/test rebuild: PyInstaller work + runnable app under .\build\ (in-repo).
rem Override: set RE2OC_BUILD_DIR to an absolute path before running.

if not defined RE2OC_BUILD_DIR set "RE2OC_BUILD_DIR=%~dp0build"
for %%I in ("%RE2OC_BUILD_DIR%") do set "BUILD=%%~fI"
set "APPDIR=%BUILD%\RE2 Outfit Converter"
set "DIST=%BUILD%\dist"
set "WORK=%BUILD%\pyi-work"

echo === RE2 Outfit Converter rebuild ===
echo Output: %BUILD%
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: python not found on PATH.
  exit /b 1
)

echo [1/3] Checking PyInstaller...
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
  echo PyInstaller missing — installing requirements...
  python -m pip install -q -r requirements.txt pyinstaller
  if errorlevel 1 (
    echo ERROR: pip install failed.
    exit /b 1
  )
) else (
  echo PyInstaller already installed — skipping pip.
)

echo [2/3] Building with PyInstaller into build\...
if not exist "%BUILD%" mkdir "%BUILD%" >nul 2>&1
python -m PyInstaller --noconfirm --workpath "%WORK%" --distpath "%DIST%" "RE2 Outfit Converter.spec"
if errorlevel 1 (
  echo ERROR: PyInstaller build failed.
  exit /b 1
)

if not exist "%DIST%\RE2 Outfit Converter\RE2 Outfit Converter.exe" (
  echo ERROR: Built exe not found in build\dist\.
  exit /b 1
)

echo [3/3] Syncing to build\RE2 Outfit Converter\...
if not exist "%APPDIR%" mkdir "%APPDIR%" >nul 2>&1
rem Preserve local prefs / output created by running the test copy.
robocopy "%DIST%\RE2 Outfit Converter" "%APPDIR%" /MIR /XF settings.json /XD Output /NFL /NDL /NJH /NJS /nc /ns /np >nul
set "RC=%ERRORLEVEL%"
if %RC% GEQ 8 (
  echo ERROR: Failed to sync dist to build app folder ^(robocopy %RC%^).
  exit /b 1
)

echo.
echo DONE: %APPDIR%\RE2 Outfit Converter.exe
exit /b 0
