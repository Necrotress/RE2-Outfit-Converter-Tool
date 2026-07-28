@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === Pack RE2 Outfit Converter (Linux) ===
echo.

set "STAGE=%TEMP%\RE2-Outfit-Converter-Linux-pack"
set "OUTZIP=%~dp0RE2 Outfit Converter (Linux).zip"
set "WIN_TAR=%SystemRoot%\System32\tar.exe"

if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%" || (
  echo ERROR: Could not create staging folder.
  exit /b 1
)

echo [1/3] Copying package files...
copy /y "linux\run.sh" "%STAGE%\run.sh" >nul
copy /y "linux\setup.sh" "%STAGE%\setup.sh" >nul
copy /y "linux\convert.sh" "%STAGE%\convert.sh" >nul
copy /y "linux\menu.sh" "%STAGE%\menu.sh" >nul
copy /y "linux\README.txt" "%STAGE%\README.txt" >nul
copy /y "requirements-linux.txt" "%STAGE%\requirements-linux.txt" >nul
copy /y "main.py" "%STAGE%\main.py" >nul
if errorlevel 1 (
  echo ERROR: Failed to copy root package files.
  exit /b 1
)

xcopy /e /i /y /q "re2_outfit_converter" "%STAGE%\re2_outfit_converter\" >nul
if errorlevel 1 (
  echo ERROR: Failed to copy re2_outfit_converter\.
  exit /b 1
)

if not exist "%STAGE%\main.py" (
  echo ERROR: Staging incomplete - main.py missing.
  exit /b 1
)
if not exist "%STAGE%\re2_outfit_converter\gui.py" (
  echo ERROR: Staging incomplete - gui.py missing.
  exit /b 1
)

for /d /r "%STAGE%" %%D in (__pycache__) do @if exist "%%D" rmdir /s /q "%%D"

echo [2/3] Creating zip...
if exist "%OUTZIP%" del /f /q "%OUTZIP%"

if exist "%WIN_TAR%" (
  pushd "%STAGE%"
  "%WIN_TAR%" -a -cf "%OUTZIP%" *
  if errorlevel 1 (
    popd
    echo ERROR: Failed to create zip with System32 tar.
    rmdir /s /q "%STAGE%"
    exit /b 1
  )
  popd
) else (
  powershell -NoProfile -Command ^
    "Compress-Archive -Path (Join-Path -Path $env:TEMP -ChildPath 'RE2-Outfit-Converter-Linux-pack\*') -DestinationPath '%OUTZIP%' -Force"
  if errorlevel 1 (
    echo ERROR: Failed to create zip with Compress-Archive.
    rmdir /s /q "%STAGE%"
    exit /b 1
  )
)

echo [3/3] Cleaning staging...
rmdir /s /q "%STAGE%"

echo.
echo Done: "%OUTZIP%"
echo Extract on Linux and run: chmod +x run.sh ^&^& ./run.sh
exit /b 0
