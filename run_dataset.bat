call .\venv\Scripts\activate.bat
python data_prep\patch_coords.py --dry-run

set /p run_patch="Do you want to run patch_coords? (y/n): "
if /I "%run_patch%"=="y" (
    python data_prep\patch_coords.py
)

python scripts\generate_cv.py --outdir data\cv
python data_prep\dataset_visualizer.py