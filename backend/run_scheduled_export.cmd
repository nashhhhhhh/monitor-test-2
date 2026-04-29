@echo off
cd /d "%~dp0.."
"C:\Users\merri\AppData\Local\Python\pythoncore-3.14-64\python.exe" backend\refresh_bms_workbook.py
if errorlevel 1 exit /b %errorlevel%
"C:\Users\merri\AppData\Local\Python\pythoncore-3.14-64\python.exe" backend\export_live_dashboard_data.py
