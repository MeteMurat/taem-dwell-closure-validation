$ErrorActionPreference = "Continue"

$Root = (Get-Location).Path
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$OutDir = ".\outputs\real_figure_source_scan_$Stamp"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$Report = Join-Path $OutDir "real_figure_source_candidates.txt"

$Patterns = @(
    "fig01_phase2_success_rates_professional.pdf",
    "fig02_failure_boundary_summary_professional.pdf",
    "fig03_B5E_terminal_error_diagnostic_professional.pdf",
    "fig04_B5F_range_closure_audit_professional.pdf",

    "B5D tight local-envelope validation statistics",
    "B5D case-level",
    "B5D vehicle-level",
    "B5D",

    "Failure-boundary diagnostic summary",
    "B5E normalized terminal-residual diagnostic",
    "B5F long-propagation range-closure audit",

    "Observed range-to-go reduction",
    "Normalized terminal residual",
    "Strict TAEM tolerance boundary",
    "No strict TAEM closure",
    "No terminal output",
    "Timeout or missing terminal output"
)

"Real manuscript figure source scan" | Out-File $Report -Encoding UTF8
"Root: $Root" | Out-File $Report -Append -Encoding UTF8
"Time: $(Get-Date)" | Out-File $Report -Append -Encoding UTF8
"" | Out-File $Report -Append -Encoding UTF8

# Critical: do NOT scan huge/generated output folders.
$ExcludeRegex = "\\(\.git|__pycache__|venv|env|\.venv|site-packages|outputs|store\\data_saved|FIGURE_BACKUP|figure_label_cleanup)\\"

# Search only likely source files, not old generated case reports.
$Files = Get-ChildItem -LiteralPath $Root -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.FullName -notmatch $ExcludeRegex -and
        $_.Extension.ToLower() -in @(".py", ".ipynb", ".ps1", ".txt", ".md")
    }

"Files scanned: $($Files.Count)" | Out-File $Report -Append -Encoding UTF8
"" | Out-File $Report -Append -Encoding UTF8

foreach ($f in $Files) {
    $hits = @()

    foreach ($p in $Patterns) {
        $m = Select-String -LiteralPath $f.FullName -Pattern $p -SimpleMatch -ErrorAction SilentlyContinue
        if ($m) {
            foreach ($x in $m) {
                $hits += "  line $($x.LineNumber): $($x.Line.Trim())"
            }
        }
    }

    if ($hits.Count -gt 0) {
        "============================================================" | Out-File $Report -Append -Encoding UTF8
        "FILE: $($f.FullName)" | Out-File $Report -Append -Encoding UTF8
        $hits | Out-File $Report -Append -Encoding UTF8
        "" | Out-File $Report -Append -Encoding UTF8
    }
}

Write-Host "[OK] Scan finished." -ForegroundColor Green
Write-Host "Report: $Report" -ForegroundColor Cyan
Write-Host ""
Get-Content $Report -Raw