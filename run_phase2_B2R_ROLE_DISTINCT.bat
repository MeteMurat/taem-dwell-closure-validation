@echo off
cd /d C:\Users\PC\Desktop\EntryGuidance-master
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python .\phase2_B2R_role_distinct_orchestrator.py
pause
