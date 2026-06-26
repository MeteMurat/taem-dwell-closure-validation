# Phase 2 B6 Publication Figures Package

This package generates publication-ready figures from the existing B5D/B5E/B5F outputs.

It does not run new simulations and does not modify guidance or multiset files.

## Files

- `phase2_B6_make_publication_figures.py`
- `run_phase2_B6_publication_figures.bat`

## Install

Copy both files into:

```text
D:\savunma-makale-adımlar\savunma makale-2.adım\EntryGuidance-master
```

The files should be at the same level as `multi_main.py`, `multiset.py`, and `store`.

## Run

```powershell
cd "D:\savunma-makale-adımlar\savunma makale-2.adım\EntryGuidance-master"
.\run_phase2_B6_publication_figures.bat
```

or directly:

```powershell
$env:PYTHONUTF8="1"
$env:PYTHONIOENCODING="utf-8"
python .\phase2_B6_make_publication_figures.py
```

## Outputs

```text
store\data_saved\phase2_B6_publication_figures
```

Expected outputs:

- `fig01_phase2_success_rates.png/pdf`
- `fig02_failure_boundary_summary.png/pdf`
- `fig03_B5E_terminal_error_diagnostics.png/pdf`
- `fig04_B5F_range_closure_diagnostic.png/pdf`
- `fig05_representative_ground_track.png/pdf` if trajectory CSV exists
- `fig06_representative_3D_trajectory.html` if trajectory CSV exists and Plotly is installed
- `phase2_B6_figure_captions.txt`
- `phase2_B6_publication_figures_manifest.json`

## Important note about 3D

The script needs a trajectory CSV containing:

```text
longitude, latitude, height
```

It searches under:

```text
store\data_saved\phase2_B5D_tight_local_envelope_validation_report
store\data_saved\phase2_B5E_mis0_corner_robustness_refinement_bounded_diagnostic\runs
store\data_saved\phase2_B5F_mis0_long_propagation_pathspec_audit\runs
store\data_saved
```

If no trajectory CSV exists, the script still produces the summary figures and writes a note explaining that the 3D trajectory input is missing.
