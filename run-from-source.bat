@echo off
rem Run Maps Studio from the source code (needs Python 3.10+ from python.org).
cd /d "%~dp0"
py -3 MapsStudio.py
if errorlevel 1 pause
