@echo off
rem ===========================================================================
rem  Build the desktop app and zip it for a GitHub release (program files only:
rem  SteamStudyTool.exe, _internal\ and README.txt - never settings.json or data).
rem  Output: dist\SteamStudyTool-<version>-windows.zip   (git-ignored)
rem  Usage:  double-click release.bat, or run "release.bat --no-pause" in a terminal.
rem ===========================================================================
setlocal
cd /d "%~dp0"

rem --- Always package a fresh, self-tested build ------------------------------
call "%~dp0build.bat" --no-pause || goto :fail

rem build.bat has put uv on PATH for its own session only; find it again here.
where uv >nul 2>nul || set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul || for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv_*") do set "PATH=%%D;%PATH%"

echo.
echo ==^> Packaging the release zip
call uv run python "%~dp0scripts\package_release.py" || goto :fail

rem Show the zip in Explorer, ready to drag onto the GitHub release page.
for /f "delims=" %%Z in ('dir /b /o-d "dist\SteamStudyTool-*-windows.zip" 2^>nul') do (
  set "ZIP=%~dp0dist\%%Z"
  goto :show
)
:show
if defined ZIP explorer /select,"%ZIP%"

echo.
echo RELEASE ZIP READY. Upload it to a new GitHub release:
echo     https://github.com/IRCSS/Steam-Game-Suggestor/releases/new
if /i not "%~1"=="--no-pause" pause
exit /b 0

:fail
echo.
echo RELEASE FAILED - see the messages above.
if /i not "%~1"=="--no-pause" pause
exit /b 1
