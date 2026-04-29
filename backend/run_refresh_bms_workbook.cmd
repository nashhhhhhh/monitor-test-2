@echo off
cd /d "%~dp0.."
py -3 backend\refresh_bms_workbook.py
