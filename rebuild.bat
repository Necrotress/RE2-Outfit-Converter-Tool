@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Dev/test rebuild: runnable app under .\build\ (in-repo).
rem PyInstaller scratch stays in TEMP and is removed after the app is copied.
rem Override: set RE2OC_BUILD_DIR to an absolute path before running.

if not defined RE2OC_BUILD_DIR set "RE2OC_BUILD_DIR=%~dp0build"
for %%I in ("%RE2OC_BUILD_DIR%") do set "BUILD=%%~fI"
set "APPDIR=%BUILD%\RE2 Outfit Converter"
set "SCRATCH=%TEMP%\RE2-Outfit-Converter-build"
set "DIST=%SCRATCH%\dist"
set "WORK=%SCRATCH%\pyi-work"

echo === RE2 Outfit Converter rebuild ===
echo Output: %APPDIR%
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: python not found on PATH.
  exit /b 1
)

if exist "%BUILD%\dist" rmdir /S /Q "%BUILD%\dist"
if exist "%BUILD%\pyi-work" rmdir /S /Q "%BUILD%\pyi-work"
if exist "%SCRATCH%" rmdir /S /Q "%SCRATCH%"

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

echo [2/3] Building with PyInstaller...
if not exist "%BUILD%" mkdir "%BUILD%" >nul 2>&1
mkdir "%DIST%" >nul 2>&1
python -m PyInstaller --noconfirm --workpath "%WORK%" --distpath "%DIST%" "RE2 Outfit Converter.spec"
if errorlevel 1 (
  echo ERROR: PyInstaller build failed.
  if exist "%SCRATCH%" rmdir /S /Q "%SCRATCH%" 2>nul
  exit /b 1
)

if not exist "%DIST%\RE2 Outfit Converter\RE2 Outfit Converter.exe" (
  echo ERROR: Built exe not found.
  if exist "%SCRATCH%" rmdir /S /Q "%SCRATCH%" 2>nul
  exit /b 1
)

echo [3/3] Syncing to build\RE2 Outfit Converter\...
if not exist "%APPDIR%" mkdir "%APPDIR%" >nul 2>&1
rem Preserve local prefs / output created by running the test copy.
robocopy "%DIST%\RE2 Outfit Converter" "%APPDIR%" /MIR /XF settings.json /XD Output /NFL /NDL /NJH /NJS /nc /ns /np >nul
set "RC=%ERRORLEVEL%"
if %RC% GEQ 8 (
  echo ERROR: Failed to sync to build app folder ^(robocopy %RC%^).
  if exist "%SCRATCH%" rmdir /S /Q "%SCRATCH%" 2>nul
  exit /b 1
)

rmdir /S /Q "%SCRATCH%" 2>nul

echo.
echo DONE: %APPDIR%\RE2 Outfit Converter.exe
exit /b 0
