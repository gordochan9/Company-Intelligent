@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\project30_demo.ps1" stop %*
set "DEMO_EXIT_CODE=%ERRORLEVEL%"

if /I not "%PROJECT3_DEMO_NO_PAUSE%"=="true" pause
exit /b %DEMO_EXIT_CODE%
