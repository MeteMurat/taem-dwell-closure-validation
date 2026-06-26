@echo off
cd /d C:\Users\PC\Desktop\EntryGuidance-master
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python .\phase2_B2_exact_single_orchestrator.py
pause
