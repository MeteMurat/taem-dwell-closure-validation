B6 Revised Code Package v3
==========================

Purpose
-------
This package replaces the two main B6 figure-generation scripts with professional-label, FAST versions:

1) phase2_B6_make_publication_figures.py
   - Produces the main B6 publication figures.
   - Corrects the 99.3% label touching the top border by using more headroom.
   - Moves the failure-boundary legend out of the bar field.
   - Replaces code-style s_go labels with publication-style "Range-to-go" wording.
   - Moves the B5F initial/final range-to-go legend to a non-overlapping upper-right position.
   - Avoids broad recursive trajectory scans by default.

2) phase2_B6_trajectory_figures.py
   - Produces representative trajectory figures.
   - Uses Vehicle 1 / Vehicle 2 / Vehicle 3 instead of mis_id=0/1/2.
   - Uses Range-to-go (km) instead of s_go notation in visible axes/captions.
   - Uses the known B5D tight-local-envelope success CSV first, then inventory, and only searches narrowly when allowed.

Copy target
-----------
Copy all files in this package into the EntryGuidance-master root, for example:

D:\savunma-makale-adımlar\savunma makale-2.adım\EntryGuidance-master

Allow Windows to overwrite the existing two .py files and add the new .bat files.

Recommended run order
---------------------
1) Main B6 publication figures:

   .\run_phase2_B6_publication_figures_professional_FAST_v3.bat

   Expected output folder:

   store\data_saved\phase2_B6_publication_figures_professional_fast_v3

2) Trajectory figures:

   .\run_phase2_B6_trajectory_figures_professional_FAST_v3.bat

   Expected output folder:

   store\data_saved\phase2_B6_trajectory_figures_professional_fast_v3

Manual fallback
---------------
If the automatic B5D success CSV is not found, edit the SUCCESS_CSV line in the manual BAT file and run:

   .\run_phase2_B6_publication_figures_professional_FAST_v3_manual.bat

or

   .\run_phase2_B6_trajectory_figures_professional_FAST_v3_manual.bat

Notes
-----
- These scripts are post-processing only.
- They do not run simulations.
- They do not modify guidance files.
- They do not modify multiset.py.
