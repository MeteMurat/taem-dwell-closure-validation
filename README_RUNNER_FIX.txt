B5E FIG.4 RUNNER FIX — NO POWERSHELL EXECUTION POLICY PROBLEM
================================================================

Your error was:

  cannot be loaded ... is not digitally signed

This is a PowerShell execution-policy block. The easiest fix is to use the
BAT runner included here:

  RUN_B5E_FIG4_NO_POLICY_BLOCK.bat

How to use:
-----------
1) Copy all files in this folder into your EntryGuidance-master directory:

   D:\savunma-makale-adımlar\savunma makale-2.adım\EntryGuidance-master

2) Double-click or run from terminal:

   RUN_B5E_FIG4_NO_POLICY_BLOCK.bat

Alternative PowerShell run:
---------------------------
If you want to use the fixed PS1:

  powershell -ExecutionPolicy Bypass -File ".\run_B5E_bounded_and_make_fig03_FIXED.ps1"

Important:
----------
The old run_B5E_bounded_and_make_fig03.ps1 had a hardcoded C:\Users\... path.
This fixed runner uses its own folder, so it works from your D:\... project path.
