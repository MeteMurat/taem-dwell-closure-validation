@echo off
cd /d %~dp0
chcp 65001
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python phase2_B5AR_positive_velocity_refinement.py
