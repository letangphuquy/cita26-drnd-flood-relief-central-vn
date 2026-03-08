call .\venv\Scripts\activate.bat
python data\prep\patch_coords.py --dry-run

set /p run_patch="Do you want to run patch_coords? (y/n): "
if /I "%run_patch%"=="y" (
    python data\prep\patch_coords.py
)

python src\scripts\generate_cv.py --outdir data\cv
python data\prep\dataset_visualizer.py