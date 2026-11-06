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
call npm --prefix frontend ci --no-audit --no-fund || goto :fail

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
