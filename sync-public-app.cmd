@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync-public-app.ps1" %*
