@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Production Windows pack: onedir build -> ..\Production + versioned Nexus zip.

set "ROOT=%~dp0"
for %%I in ("%ROOT%..\Production") do set "PROD=%%~fI"
for %%I in ("%ROOT%..\Build") do set "BUILD=%%~fI"
for %%I in ("%ROOT%..\..") do set "ZIPDIR=%%~fI"
set "APPNAME=RE2 Outfit Converter"
set "VER=1.1.8"
set "ZIPNAME=RE2.Outfit.Converter.v%VER%.Windows.zip"
set "STAGE=%TEMP%\RE2-Outfit-Converter-Windows-pack"
set "DIST=%BUILD%\dist"
set "WORK=%BUILD%\pyi-work"
set "BUILT_DIR=%DIST%\%APPNAME%"
set "BUILT_EXE=%BUILT_DIR%\%APPNAME%.exe"

echo === RE2 Outfit Converter - Windows production pack (onedir) ===
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

echo [2/4] Building onedir app into Build\...
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

echo [3/4] Staging Production folder...
if exist "%PROD%" rmdir /S /Q "%PROD%"
if errorlevel 1 (
  echo ERROR: Could not clear Production. Close RE2 Outfit Converter.exe and retry.
  exit /b 1
)
mkdir "%PROD%" >nul 2>&1
robocopy "%BUILT_DIR%" "%PROD%" /E /NFL /NDL /NJH /NJS /nc /ns /np >nul
if errorlevel 8 (
  echo ERROR: Failed to stage production folder.
  exit /b 1
)
copy /Y "USER GUIDE.txt" "%PROD%\USER GUIDE.txt" >nul
if exist "LICENSE" copy /Y "LICENSE" "%PROD%\LICENSE.txt" >nul

echo [4/4] Writing Nexus zip...
if exist "%STAGE%" rmdir /S /Q "%STAGE%"
mkdir "%STAGE%\%APPNAME%" >nul 2>&1
robocopy "%PROD%" "%STAGE%\%APPNAME%" /E /NFL /NDL /NJH /NJS /nc /ns /np >nul
if errorlevel 8 (
  echo ERROR: Failed to stage zip tree.
  exit /b 1
)

if exist "%ZIPDIR%\%ZIPNAME%" del /F /Q "%ZIPDIR%\%ZIPNAME%"
powershell -NoProfile -Command "Compress-Archive -Path (Join-Path $env:TEMP 'RE2-Outfit-Converter-Windows-pack\*') -DestinationPath '%ZIPDIR%\%ZIPNAME%' -Force"
if errorlevel 1 (
  echo ERROR: Failed to create zip.
  exit /b 1
)

rmdir /S /Q "%STAGE%" 2>nul

echo.
echo DONE - extract the zip, then run %APPNAME%.exe inside the folder.
echo   Folder: %PROD%
echo   Zip:    %ZIPDIR%\%ZIPNAME%
echo.
exit /b 0
