@echo off
setlocal
cd /d "%~dp0"
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo ============================================================
echo General CSV report - professional labels
echo Usage note: edit INPUT_CSV below if needed.
echo ============================================================
set INPUT_CSV=store\data_saved\multiSimulation_case.csv
set OUT_DIR=store\data_saved\plots_professional
python .\plot_csv_report.py --input "%INPUT_CSV%" --outdir "%OUT_DIR%" --downsample 10 --idcol mis_id
pause
endlocal
