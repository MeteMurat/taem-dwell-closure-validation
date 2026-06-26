@echo off
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python .\phase2_B5C_local_envelope_validation.py --n 30 --seed 101
