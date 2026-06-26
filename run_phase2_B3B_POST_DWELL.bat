@echo off
cd /d C:\Users\PC\Desktop\EntryGuidance-master
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python .\phase2_B3B_post_dwell_sensitivity.py
pause
