@echo off
rem Double-click this file to start the backend, frontend and AI service together.
rem Close this window (or press Ctrl+C) to stop all of them.
title MINI - all services
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-all.ps1" %*
echo.
echo Finished. Press any key to close this window.
pause >nul
