@echo off
setlocal enabledelayedexpansion
title NSE Stock Prediction - Launcher

REM ============================================================
REM  NSE Stock Prediction — single-command launcher (Windows)
REM  Starts the FastAPI backend and the Astro frontend together.
REM
REM  Expected layout (edit BACKEND_DIR below if yours differs):
REM
REM    project-root/
REM      backend/            <- server.py, services.py, requirements.txt
REM      frontend/           <- this folder (package.json, src/, ...)
REM      start.bat           <- this script (run from project-root)
REM ============================================================

set "BACKEND_DIR=backend"
set "FRONTEND_DIR=frontend"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=4321"

echo.
echo === NSE Stock Prediction — starting backend + frontend ===
echo.

if not exist "%BACKEND_DIR%\server.py" (
    echo [ERROR] Could not find "%BACKEND_DIR%\server.py".
    echo         Edit BACKEND_DIR at the top of start.bat to point at your backend folder.
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo [ERROR] Could not find "%FRONTEND_DIR%\package.json".
    echo         Edit FRONTEND_DIR at the top of start.bat to point at this frontend folder.
    pause
    exit /b 1
)

REM --- Backend: create venv on first run, install deps, launch uvicorn -----
pushd "%BACKEND_DIR%"

if not exist ".venv\Scripts\python.exe" (
    echo [backend] Creating virtual environment...
    python -m venv .venv
)

echo [backend] Installing/checking Python dependencies...
call ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
if exist "requirements.txt" (
    call ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
) else (
    echo [backend] WARNING: requirements.txt not found — skipping dependency install.
)

echo [backend] Launching FastAPI on http://localhost:%BACKEND_PORT% ...
start "NSE Backend (FastAPI)" cmd /k "%CD%\.venv\Scripts\python.exe -m uvicorn server:app --host 0.0.0.0 --port %BACKEND_PORT%"

popd

REM --- Frontend: install deps, launch Astro dev server ----------------------
pushd "%FRONTEND_DIR%"

if not exist "node_modules" (
    echo [frontend] Installing npm dependencies (first run only)...
    call npm install
)

echo [frontend] Launching Astro dev server on http://localhost:%FRONTEND_PORT% ...
start "NSE Frontend (Astro)" cmd /k "npm run dev -- --port %FRONTEND_PORT%"

popd

echo.
echo === Both servers are starting in separate windows ===
echo   Backend:  http://localhost:%BACKEND_PORT%/docs
echo   Frontend: http://localhost:%FRONTEND_PORT%
echo.
echo Close this window any time — the two server windows will keep running.
echo To stop everything, close the "NSE Backend" and "NSE Frontend" windows.
echo.
pause
