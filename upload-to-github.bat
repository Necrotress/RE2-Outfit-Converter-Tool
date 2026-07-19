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
echo Run this yourself (double-click or a normal terminal).
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: git not found on PATH.
  goto :fail
)

REM --- Use your existing Git identity without changing git config ---
for /f "usebackq delims=" %%A in (`git config --get user.name 2^>nul`) do set "GIT_NAME=%%A"
for /f "usebackq delims=" %%A in (`git config --get user.email 2^>nul`) do set "GIT_EMAIL=%%A"

if not defined GIT_NAME (
  echo ERROR: git user.name is not set.
  echo Example: git config --global user.name "YourName"
  goto :fail
)
if not defined GIT_EMAIL (
  echo ERROR: git user.email is not set.
  echo Example: git config --global user.email "you@example.com"
  goto :fail
)

set "GIT_AUTHOR_NAME=%GIT_NAME%"
set "GIT_AUTHOR_EMAIL=%GIT_EMAIL%"
set "GIT_COMMITTER_NAME=%GIT_NAME%"
set "GIT_COMMITTER_EMAIL=%GIT_EMAIL%"
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
    if errorlevel 1 (
      echo ERROR: git init failed.
      goto :fail
    )
    git branch -M main
  )
)

echo Staging source (respects .gitignore)...
git add -A
if errorlevel 1 (
  echo ERROR: git add failed.
  goto :fail
)

echo.
git status --short
echo.

REM Commit only when the index differs from HEAD (or there is no HEAD yet)
set "NEED_COMMIT=0"
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 (
  REM No commits yet — commit if anything is staged
  git diff --cached --quiet
  if errorlevel 1 set "NEED_COMMIT=1"
) else (
  git diff --cached --quiet
  if errorlevel 1 set "NEED_COMMIT=1"
)

if "!NEED_COMMIT!"=="1" (
  echo Creating commit...
  git rev-parse --verify HEAD >nul 2>&1
  if errorlevel 1 (
    set "COMMIT_MSG=Add RE2 Outfit Converter source"
  ) else (
    set "COMMIT_MSG=Update RE2 Outfit Converter source"
  )
  git -c user.name="%GIT_NAME%" -c user.email="%GIT_EMAIL%" commit -m "!COMMIT_MSG!"
  if errorlevel 1 (
    echo ERROR: git commit failed.
    goto :fail
  )
  echo Commit OK.
) else (
  echo No new changes to commit ^(already up to date locally^).
)

git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 (
  echo ERROR: Nothing was committed. Check .gitignore / that files exist.
  goto :fail
)

echo.
git remote get-url origin >nul 2>&1
if errorlevel 1 (
  echo No "origin" remote yet.
  echo.
  echo Create an EMPTY GitHub repo first:
  echo   - README off, no .gitignore, no license
  echo Then paste the URL below.
  echo Example: https://github.com/YourUser/RE2-Outfit-Converter.git
  echo.
  set /p "REMOTE_URL=GitHub repo URL: "
  if "!REMOTE_URL!"=="" (
    echo ERROR: No URL provided.
    goto :fail
  )
  git remote add origin "!REMOTE_URL!"
  if errorlevel 1 (
    echo ERROR: Could not add remote. If origin exists, remove it with:
    echo   git remote remove origin
    goto :fail
  )
) else (
  echo Remote origin:
  git remote get-url origin
)

echo.
echo Pushing to origin (main)...
git branch -M main >nul 2>&1
git push -u origin main
if errorlevel 1 (
  echo.
  echo Push failed. Common fixes:
  echo   1^) Repo on GitHub must be empty ^(no README^)
  echo   2^) Sign in when Git Credential Manager prompts
  echo   3^) Or run:  gh auth login
  echo.
  goto :fail
)

echo.
echo DONE. Uploaded as: %GIT_AUTHOR_NAME%
echo.
goto :done

:fail
echo.
echo *** Failed or cancelled. Window will stay open so you can read this. ***
echo.
pause
exit /b 1

:done
pause
exit /b 0
