@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === RE2 Outfit Converter rebuild ===
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: python not found on PATH.
  exit /b 1
)

echo [1/3] Ensuring PyInstaller...
python -m pip install -q -r requirements.txt pyinstaller
if errorlevel 1 (
  echo ERROR: pip install failed.
  exit /b 1
)

echo [2/3] Building with PyInstaller...
python -m PyInstaller --noconfirm --workpath pyi-work --distpath dist "RE2 Outfit Converter.spec"
if errorlevel 1 (
  echo ERROR: PyInstaller build failed.
  exit /b 1
)

if not exist "dist\RE2 Outfit Converter\RE2 Outfit Converter.exe" (
  echo ERROR: Built exe not found in dist\.
  exit /b 1
)

echo [3/3] Syncing to Build\RE2 Outfit Converter\...
if exist "Build\RE2 Outfit Converter" rmdir /s /q "Build\RE2 Outfit Converter"
mkdir "Build\RE2 Outfit Converter" >nul 2>&1
xcopy /e /i /y /q "dist\RE2 Outfit Converter\*" "Build\RE2 Outfit Converter\" >nul
if errorlevel 1 (
  echo ERROR: Failed to copy dist to Build.
  exit /b 1
)

echo.
echo DONE: Build\RE2 Outfit Converter\RE2 Outfit Converter.exe
exit /b 0
