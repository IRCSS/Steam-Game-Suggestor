@echo off
rem ===========================================================================
rem  Build the desktop app from the current repository state.
rem  Output: dist\SteamStudyTool\SteamStudyTool.exe   (git-ignored)
rem  Usage:  double-click build.bat, or run "build.bat --no-pause" in a terminal.
rem ===========================================================================
setlocal
cd /d "%~dp0"

rem --- Locate tools (fall back to default winget/installer locations) --------
where uv >nul 2>nul || set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul || for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv_*") do set "PATH=%%D;%PATH%"
where npm >nul 2>nul || set "PATH=%ProgramFiles%\nodejs;%PATH%"

where uv >nul 2>nul || (echo ERROR: uv not found. Install with: winget install astral-sh.uv & goto :fail)
where npm >nul 2>nul || (echo ERROR: npm not found. Install with: winget install OpenJS.NodeJS.LTS & goto :fail)

echo.
echo ==^> Installing Python dependencies (uv)
call uv sync --group desktop || goto :fail

echo.
echo ==^> Installing UI dependencies (npm)
rem A clean install is only needed when package-lock.json changed since the last one: its
rem SHA-256 is stamped into node_modules after each install. No stamp or no hash = install.
set "LOCK_HASH="
for /f "skip=1 delims=" %%H in ('certutil -hashfile "frontend\package-lock.json" SHA256 2^>nul') do if not defined LOCK_HASH set "LOCK_HASH=%%H"
set "LOCK_STAMP=frontend\node_modules\.lock-sha256"
set "OLD_HASH="
if exist "%LOCK_STAMP%" set /p OLD_HASH=<"%LOCK_STAMP%"
if defined LOCK_HASH if "%LOCK_HASH%"=="%OLD_HASH%" (
  echo     package-lock.json unchanged since the last install - skipping
  goto :ui_deps_done
)
call npm --prefix frontend ci --no-audit --no-fund || goto :fail
if defined LOCK_HASH >"%LOCK_STAMP%" echo %LOCK_HASH%
:ui_deps_done

echo.
echo ==^> Building UI
call npm --prefix frontend run build || goto :fail

call uv run --group desktop python scripts\build_desktop.py || goto :fail

echo.
echo BUILD SUCCEEDED. Start the app with:
echo     dist\SteamStudyTool\SteamStudyTool.exe
if /i not "%~1"=="--no-pause" pause
exit /b 0

:fail
echo.
echo BUILD FAILED - see the messages above.
if /i not "%~1"=="--no-pause" pause
exit /b 1
