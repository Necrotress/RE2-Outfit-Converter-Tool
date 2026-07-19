@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo ========================================
echo  RE2 Outfit Converter - Upload to GitHub
echo ========================================
echo.
echo This script commits and pushes AS YOU (your Git identity).
echo Cursor will NOT be added as author or co-author.
echo.
echo Run this yourself in a normal terminal / double-click.
echo Do not ask an AI agent to push for you if you want
echo Cursor absent from the contributor list.
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: git not found on PATH.
  exit /b 1
)

REM --- Use your existing Git identity without changing git config ---
for /f "usebackq delims=" %%A in (`git config --get user.name 2^>nul`) do set "GIT_NAME=%%A"
for /f "usebackq delims=" %%A in (`git config --get user.email 2^>nul`) do set "GIT_EMAIL=%%A"

if not defined GIT_NAME (
  echo ERROR: git user.name is not set.
  echo Set it once for your account, e.g.:
  echo   git config --global user.name "YourName"
  exit /b 1
)
if not defined GIT_EMAIL (
  echo ERROR: git user.email is not set.
  echo Set it once for your account, e.g.:
  echo   git config --global user.email "you@example.com"
  exit /b 1
)

REM Force author + committer for this session only (no Cursor trailer / identity)
set "GIT_AUTHOR_NAME=%GIT_NAME%"
set "GIT_AUTHOR_EMAIL=%GIT_EMAIL%"
set "GIT_COMMITTER_NAME=%GIT_NAME%"
set "GIT_COMMITTER_EMAIL=%GIT_EMAIL%"
REM Prevent helpers from injecting Co-authored-by / Cursor trailers
set "GIT_EDITOR=true"
set "CURSOR_AGENT="
set "CURSOR_TRACE_ID="

echo Committing as: %GIT_AUTHOR_NAME% ^<%GIT_AUTHOR_EMAIL%^>
echo.

if not exist ".git" (
  echo Initializing new git repository...
  git init -b main
  if errorlevel 1 (
    git init
    git branch -M main
  )
)

echo Staging source (respects .gitignore)...
git add -A
if errorlevel 1 (
  echo ERROR: git add failed.
  exit /b 1
)

git status --short
echo.

REM Only commit if there is something to commit
git diff --cached --quiet
if %errorlevel%==0 (
  echo No new changes to commit.
) else (
  echo Creating commit...
  REM Plain message only — no Co-authored-by / Made-with Cursor trailers
  if exist ".git\refs\heads\main" (
    set "COMMIT_MSG=Update RE2 Outfit Converter source"
  ) else if exist ".git\refs\heads\master" (
    set "COMMIT_MSG=Update RE2 Outfit Converter source"
  ) else (
    set "COMMIT_MSG=Add RE2 Outfit Converter source"
  )
  git -c user.name="%GIT_NAME%" -c user.email="%GIT_EMAIL%" commit -m "!COMMIT_MSG!"
  if errorlevel 1 (
    echo ERROR: git commit failed.
    exit /b 1
  )
  echo Commit OK.
)

echo.
REM Ensure remote
git remote get-url origin >nul 2>&1
if errorlevel 1 (
  echo No "origin" remote yet.
  echo.
  echo Create an empty repo on GitHub first (no README), then paste the URL.
  echo Example: https://github.com/YourUser/RE2-Outfit-Converter.git
  echo.
  set /p "REMOTE_URL=GitHub repo URL: "
  if "!REMOTE_URL!"=="" (
    echo ERROR: No URL provided.
    exit /b 1
  )
  git remote add origin "!REMOTE_URL!"
  if errorlevel 1 (
    echo ERROR: Could not add remote.
    exit /b 1
  )
) else (
  echo Remote origin:
  git remote get-url origin
)

echo.
echo Pushing to origin (main)...
git push -u origin main
if errorlevel 1 (
  echo.
  echo Push failed. If the remote has commits already, try:
  echo   git pull --rebase origin main
  echo   git push -u origin main
  echo.
  echo Or create a brand-new empty GitHub repo and re-run this script.
  exit /b 1
)

echo.
echo DONE. Repo is on GitHub under your account only.
echo Contributors should show: %GIT_AUTHOR_NAME%
echo.
pause
exit /b 0
