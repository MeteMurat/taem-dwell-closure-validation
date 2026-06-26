$ErrorActionPreference = "Stop"

$Root = (Get-Location).Path
$Out = ".\outputs\exact_figure_source_blocks.txt"
New-Item -ItemType Directory -Force -Path ".\outputs" | Out-Null

function Write-Block {
    param(
        [string]$File,
        [int]$Start,
        [int]$End
    )

    if (-not (Test-Path -LiteralPath $File)) {
        "============================================================" | Out-File $Out -Append -Encoding UTF8
        "MISSING FILE: $File" | Out-File $Out -Append -Encoding UTF8
        return
    }

    "============================================================" | Out-File $Out -Append -Encoding UTF8
    "FILE: $File" | Out-File $Out -Append -Encoding UTF8
    "LINES: $Start - $End" | Out-File $Out -Append -Encoding UTF8
    "============================================================" | Out-File $Out -Append -Encoding UTF8

    $i = 0
    Get-Content -LiteralPath $File | ForEach-Object {
        $i++
        if ($i -ge $Start -and $i -le $End) {
            "{0,5}: {1}" -f $i, $_ | Out-File $Out -Append -Encoding UTF8
        }
    }

    "" | Out-File $Out -Append -Encoding UTF8
}

if (Test-Path -LiteralPath $Out) {
    Remove-Item -LiteralPath $Out -Force
}

"Exact figure source block extraction" | Out-File $Out -Encoding UTF8
"Root: $Root" | Out-File $Out -Append -Encoding UTF8
"Time: $(Get-Date)" | Out-File $Out -Append -Encoding UTF8
"" | Out-File $Out -Append -Encoding UTF8

# Figure 2 source candidate
Write-Block ".\make_fig01_b5d_success_rates.py" 1 140

# Figure 4 source candidates
Write-Block ".\make_fig03_B5E_normalized_residual.py" 140 220
Write-Block ".\make_fig03_B5E_normalized_residual_from_runs.py" 340 410

# B6 sources where Figure 3 / Figure 5 likely live
Write-Block ".\phase2_B6_figure_polish_package.py" 160 260
Write-Block ".\phase2_B6_make_publication_figures.py" 170 285

# Also search exact set_title/savefig/include strings
"============================================================" | Out-File $Out -Append -Encoding UTF8
"STRING SEARCH RESULTS" | Out-File $Out -Append -Encoding UTF8
"============================================================" | Out-File $Out -Append -Encoding UTF8

$SearchFiles = @(
    ".\make_fig01_b5d_success_rates.py",
    ".\make_fig03_B5E_normalized_residual.py",
    ".\make_fig03_B5E_normalized_residual_from_runs.py",
    ".\phase2_B6_figure_polish_package.py",
    ".\phase2_B6_make_publication_figures.py"
)

$Patterns = @(
    "set_title",
    "suptitle",
    "savefig",
    "fig01_phase2_success_rates_professional",
    "fig02_failure_boundary_summary_professional",
    "fig03_B5E_terminal_error_diagnostic_professional",
    "fig04_B5F_range_closure_audit_professional",
    "B5D",
    "B5E",
    "B5F",
    "Failure-boundary",
    "Observed range-to-go reduction",
    "No strict TAEM closure",
    "No terminal output"
)

foreach ($f in $SearchFiles) {
    if (-not (Test-Path -LiteralPath $f)) { continue }

    "-------------------- $f --------------------" | Out-File $Out -Append -Encoding UTF8

    foreach ($p in $Patterns) {
        $hits = Select-String -LiteralPath $f -Pattern $p -SimpleMatch -ErrorAction SilentlyContinue
        foreach ($h in $hits) {
            "line $($h.LineNumber): $($h.Line.Trim())" | Out-File $Out -Append -Encoding UTF8
        }
    }

    "" | Out-File $Out -Append -Encoding UTF8
}

Write-Host "[OK] Extracted source blocks to:" $Out -ForegroundColor Green
Get-Content $Out -Raw