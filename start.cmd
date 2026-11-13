@echo off
rem Starts Marking Colleague on Windows:   start.cmd        (then open http://localhost:8000)
rem Live-reload mode for editing the UI:   start.cmd dev    (then open http://localhost:5173)
rem Works even when Node and Python are not on PATH in this terminal.
setlocal
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\nodejs;%PATH%"
cd /d "%~dp0"

rem Check the packages every time, not only the first time: a pull can add packages (the 3D viewer did), and without
rem them the build fails and the page quietly shows the last version that built. The check is offline and quick;
rem npm install, which needs the internet, runs only when something is missing.
set "INSTALL_FAILED=0"
pushd web
call node check-packages.mjs
if errorlevel 1 (
  echo Installing dashboard packages that are missing or out of date...
  call npm install --no-audit --no-fund
  if errorlevel 1 set "INSTALL_FAILED=1"
)
popd
if not "%INSTALL_FAILED%"=="0" (
  echo.
  echo WARNING: npm install failed, so the dashboard may be missing packages. Read the messages above.
  echo.
)

if /i "%~1"=="dev" goto dev

rem Rebuild every time, so the page always matches the code in web\src.
echo Building the dashboard...
pushd web
call npm run build
set "BUILD_FAILED=%ERRORLEVEL%"
popd
if not exist "web\dist\index.html" (
  echo.
  echo The dashboard could not be built. Read the messages above, fix the problem and run start.cmd again.
  exit /b 1
)
if not "%BUILD_FAILED%"=="0" (
  echo.
  echo WARNING: the build failed, so the page shown is the last one that built. Read the messages above.
  echo.
)
python run.py
exit /b %ERRORLEVEL%

:dev
echo Starting the Python server in a second window, and the live-reload dashboard here.
start "Marking Colleague server" cmd /k python run.py
pushd web
call npm run dev
popd
