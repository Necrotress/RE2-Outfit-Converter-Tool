@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Build the single-file Windows release and stage it under CL2.
set "PROD=O:\Libraries\CL2\RE2 Outfit Converter - Production"

echo === RE2 Outfit Converter — Windows production pack ===
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: python not found on PATH.
  exit /b 1
)

echo [1/3] Checking PyInstaller...
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
  echo PyInstaller missing — installing...
  python -m pip install -q -r requirements.txt pyinstaller
  if errorlevel 1 (
    echo ERROR: pip install failed.
    exit /b 1
  )
) else (
  echo PyInstaller OK.
)

echo [2/3] Building onefile exe...
python -m PyInstaller --noconfirm --workpath pyi-work-onefile --distpath dist-onefile "RE2 Outfit Converter.onefile.spec"
if errorlevel 1 (
  echo ERROR: PyInstaller build failed.
  exit /b 1
)

if not exist "dist-onefile\RE2 Outfit Converter.exe" (
  echo ERROR: Built exe not found in dist-onefile\.
  exit /b 1
)

echo [3/3] Staging production folder...
if not exist "%PROD%" mkdir "%PROD%" >nul 2>&1
copy /Y "dist-onefile\RE2 Outfit Converter.exe" "%PROD%\RE2 Outfit Converter.exe" >nul
if errorlevel 1 (
  echo ERROR: Failed to copy exe to production folder.
  exit /b 1
)
copy /Y "USER GUIDE.txt" "%PROD%\USER GUIDE.txt" >nul
if exist "LICENSE" copy /Y "LICENSE" "%PROD%\LICENSE.txt" >nul

echo.
echo DONE: %PROD%
echo   - RE2 Outfit Converter.exe
echo   - USER GUIDE.txt
if exist "%PROD%\LICENSE.txt" echo   - LICENSE.txt
exit /b 0
