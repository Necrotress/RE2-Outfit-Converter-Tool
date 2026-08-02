@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Production Windows pack: onedir build -> .\release\ + versioned zip (in-repo).
rem Override: set RE2OC_BUILD_DIR / RE2OC_RELEASE_DIR before running.

if not defined RE2OC_BUILD_DIR set "RE2OC_BUILD_DIR=%~dp0build"
if not defined RE2OC_RELEASE_DIR set "RE2OC_RELEASE_DIR=%~dp0release"
for %%I in ("%RE2OC_BUILD_DIR%") do set "BUILD=%%~fI"
for %%I in ("%RE2OC_RELEASE_DIR%") do set "PROD=%%~fI"
set "APPNAME=RE2 Outfit Converter"
set "VER=1.1.8"
set "ZIPNAME=RE2.Outfit.Converter.v%VER%.Windows.zip"
set "STAGE=%TEMP%\RE2-Outfit-Converter-Windows-pack"
set "DIST=%BUILD%\dist"
set "WORK=%BUILD%\pyi-work"
set "BUILT_DIR=%DIST%\%APPNAME%"
set "BUILT_EXE=%BUILT_DIR%\%APPNAME%.exe"

echo === RE2 Outfit Converter - Windows production pack (onedir) ===
echo Build:   %BUILD%
echo Release: %PROD%
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: python not found on PATH.
  exit /b 1
)

echo [1/4] Checking PyInstaller...
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
  echo PyInstaller missing - installing...
  python -m pip install -q -r requirements.txt pyinstaller
  if errorlevel 1 (
    echo ERROR: pip install failed.
    exit /b 1
  )
) else (
  echo PyInstaller OK.
)

echo [2/4] Building onedir app...
if not exist "%BUILD%" mkdir "%BUILD%" >nul 2>&1
python -m PyInstaller --noconfirm --workpath "%WORK%" --distpath "%DIST%" "RE2 Outfit Converter.spec"
if errorlevel 1 (
  echo ERROR: PyInstaller build failed.
  exit /b 1
)

dir "%BUILT_EXE%" >nul 2>&1
if errorlevel 1 (
  echo ERROR: Built exe not found:
  echo   %BUILT_EXE%
  exit /b 1
)

echo [3/4] Staging release folder...
if not exist "%PROD%" mkdir "%PROD%" >nul 2>&1
if exist "%PROD%\%APPNAME%" (
  rmdir /S /Q "%PROD%\%APPNAME%"
  if errorlevel 1 (
    echo ERROR: Could not clear release app folder. Close %APPNAME%.exe and retry.
    exit /b 1
  )
)
mkdir "%PROD%\%APPNAME%" >nul 2>&1
robocopy "%BUILT_DIR%" "%PROD%\%APPNAME%" /E /NFL /NDL /NJH /NJS /nc /ns /np >nul
if errorlevel 8 (
  echo ERROR: Failed to stage release folder.
  exit /b 1
)
copy /Y "USER GUIDE.txt" "%PROD%\%APPNAME%\USER GUIDE.txt" >nul
if exist "LICENSE" copy /Y "LICENSE" "%PROD%\%APPNAME%\LICENSE.txt" >nul

echo [4/4] Writing Nexus zip...
if exist "%STAGE%" rmdir /S /Q "%STAGE%"
mkdir "%STAGE%\%APPNAME%" >nul 2>&1
robocopy "%PROD%\%APPNAME%" "%STAGE%\%APPNAME%" /E /NFL /NDL /NJH /NJS /nc /ns /np >nul
if errorlevel 8 (
  echo ERROR: Failed to stage zip tree.
  exit /b 1
)

if exist "%PROD%\%ZIPNAME%" del /F /Q "%PROD%\%ZIPNAME%"
powershell -NoProfile -Command "Compress-Archive -Path (Join-Path $env:TEMP 'RE2-Outfit-Converter-Windows-pack\*') -DestinationPath '%PROD%\%ZIPNAME%' -Force"
if errorlevel 1 (
  echo ERROR: Failed to create zip.
  exit /b 1
)

rmdir /S /Q "%STAGE%" 2>nul

echo.
echo DONE - extract the zip, then run %APPNAME%.exe inside the folder.
echo   Folder: %PROD%\%APPNAME%
echo   Zip:    %PROD%\%ZIPNAME%
echo.
exit /b 0
