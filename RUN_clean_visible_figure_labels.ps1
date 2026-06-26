$ErrorActionPreference = "Stop"

# ============================================================
# RUN_clean_visible_figure_labels.ps1
# Purpose:
#   Search Python figure-generation scripts, remove visible
#   B5D/B5E/B5F labels from figure titles, bar labels, and x-axis labels,
#   then rerun modified scripts when possible.
# ============================================================

$Root = $PSScriptRoot
Set-Location -LiteralPath $Root

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$AuditDir = Join-Path $Root "outputs\figure_label_cleanup_$Stamp"
New-Item -ItemType Directory -Force -Path $AuditDir | Out-Null

$ScanReport = Join-Path $AuditDir "scan_report.txt"
$PatchReport = Join-Path $AuditDir "patch_report.txt"
$RunLog = Join-Path $AuditDir "run_log.txt"

"Figure label cleanup started: $(Get-Date)" | Out-File -FilePath $ScanReport -Encoding UTF8
"Root: $Root" | Out-File -FilePath $ScanReport -Encoding UTF8 -Append
"" | Out-File -FilePath $ScanReport -Encoding UTF8 -Append

Write-Host ""
Write-Host "=== Visible figure-label cleanup ===" -ForegroundColor Cyan
Write-Host "Root: $Root"
Write-Host "Audit dir: $AuditDir"
Write-Host ""

# ------------------------------------------------------------
# 1) Candidate Python files
# ------------------------------------------------------------
$ExcludeRegex = "\\(\.git|__pycache__|venv|env|\.venv|site-packages|outputs\\figure_label_cleanup_|outputs\\terminal_angular_diagnostics)\\"

$PyFiles = Get-ChildItem -Path $Root -Recurse -Filter "*.py" -File |
    Where-Object { $_.FullName -notmatch $ExcludeRegex }

$Needles = @(
    "B5D",
    "B5E",
    "B5F",
    "tight local-envelope validation statistics",
    "tight local envelope validation statistics",
    "Failure-boundary diagnostic summary",
    "failure-boundary diagnostic summary",
    "normalized terminal-residual diagnostic",
    "long-propagation range-closure audit",
    "case-level`nstrict closure",
    "vehicle-level`nstrict closure",
    "case-level strict closure",
    "vehicle-level strict closure"
)

$CandidateFiles = New-Object System.Collections.Generic.List[System.IO.FileInfo]

foreach ($f in $PyFiles) {
    $txt = Get-Content -LiteralPath $f.FullName -Raw -ErrorAction SilentlyContinue
    if ($null -eq $txt) { continue }

    $hit = $false
    foreach ($n in $Needles) {
        if ($txt.Contains($n)) {
            $hit = $true
            break
        }
    }

    if ($hit) {
        $CandidateFiles.Add($f)
    }
}

Write-Host "Candidate Python files found: $($CandidateFiles.Count)" -ForegroundColor Yellow
"Candidate Python files found: $($CandidateFiles.Count)" | Out-File -FilePath $ScanReport -Encoding UTF8 -Append

foreach ($f in $CandidateFiles) {
    Write-Host "  $($f.FullName)"
    "FILE: $($f.FullName)" | Out-File -FilePath $ScanReport -Encoding UTF8 -Append

    foreach ($n in $Needles) {
        $matches = Select-String -Path $f.FullName -Pattern ([regex]::Escape($n)) -SimpleMatch -ErrorAction SilentlyContinue
        if ($matches) {
            foreach ($m in $matches) {
                "  line $($m.LineNumber): $($m.Line.Trim())" | Out-File -FilePath $ScanReport -Encoding UTF8 -Append
            }
        }
    }

    "" | Out-File -FilePath $ScanReport -Encoding UTF8 -Append
}

if ($CandidateFiles.Count -eq 0) {
    Write-Host ""
    Write-Host "No candidate Python files found. Search report:" -ForegroundColor Red
    Write-Host $ScanReport
    exit 1
}

# ------------------------------------------------------------
# 2) Text patch function
# ------------------------------------------------------------
function Patch-VisibleFigureText {
    param(
        [string]$Text
    )

    $Original = $Text

    # --------------------------------------------------------
    # Figure 2: title and bar labels
    # --------------------------------------------------------
    $Text = $Text.Replace("B5D tight local-envelope validation statistics", "Final sampled validation statistics")
    $Text = $Text.Replace("B5D tight local envelope validation statistics", "Final sampled validation statistics")
    $Text = $Text.Replace("B5D tight sampled-local validation statistics", "Final sampled validation statistics")
    $Text = $Text.Replace("B5D sampled local validation statistics", "Final sampled validation statistics")
    $Text = $Text.Replace("B5D validation statistics", "Final sampled validation statistics")

    $Text = $Text.Replace("B5D case-level`nstrict closure", "Case-level`nstrict closure")
    $Text = $Text.Replace("B5D vehicle-level`nstrict closure", "Vehicle-level`nstrict closure")
    $Text = $Text.Replace("B5D case-level\nstrict closure", "Case-level\nstrict closure")
    $Text = $Text.Replace("B5D vehicle-level\nstrict closure", "Vehicle-level\nstrict closure")
    $Text = $Text.Replace("B5D case-level strict closure", "Case-level strict closure")
    $Text = $Text.Replace("B5D vehicle-level strict closure", "Vehicle-level strict closure")

    # Python source often stores literal backslash-n inside strings.
    $Text = $Text.Replace("B5D case-level\\nstrict closure", "Case-level\\nstrict closure")
    $Text = $Text.Replace("B5D vehicle-level\\nstrict closure", "Vehicle-level\\nstrict closure")

    # --------------------------------------------------------
    # Figure 3: title and x-axis tick labels
    # --------------------------------------------------------
    $Text = $Text.Replace("Failure-boundary diagnostic summary", "Boundary-diagnostic summary")
    $Text = $Text.Replace("failure-boundary diagnostic summary", "Boundary-diagnostic summary")
    $Text = $Text.Replace("B5E/B5F failure-boundary diagnostic summary", "Boundary-diagnostic summary")
    $Text = $Text.Replace("B5E-B5F failure-boundary diagnostic summary", "Boundary-diagnostic summary")

    # Replace common exact tick-label list forms only.
    # This avoids breaking file paths or stage-folder names.
    $Text = $Text.Replace("['B5E', 'B5F']", "['Residual-boundary audit', 'Long-propagation audit']")
    $Text = $Text.Replace('["B5E", "B5F"]', '["Residual-boundary audit", "Long-propagation audit"]')
    $Text = $Text.Replace("('B5E', 'B5F')", "('Residual-boundary audit', 'Long-propagation audit')")
    $Text = $Text.Replace('("B5E", "B5F")', '("Residual-boundary audit", "Long-propagation audit")')

    # Matplotlib set_xticklabels variants.
    $Text = [regex]::Replace(
        $Text,
        "set_xticklabels\(\s*\[\s*['""]B5E['""]\s*,\s*['""]B5F['""]\s*\]\s*\)",
        "set_xticklabels(['Residual-boundary audit', 'Long-propagation audit'], rotation=0)"
    )

    # --------------------------------------------------------
    # Figure 4: title
    # --------------------------------------------------------
    $Text = $Text.Replace("B5E normalized terminal-residual diagnostic", "Normalized terminal-residual diagnostic")
    $Text = $Text.Replace("B5E normalized terminal residual diagnostic", "Normalized terminal-residual diagnostic")

    # --------------------------------------------------------
    # Figure 5: title
    # --------------------------------------------------------
    $Text = $Text.Replace("B5F long-propagation range-closure audit", "Long-propagation range-closure audit")
    $Text = $Text.Replace("B5F long propagation range closure audit", "Long-propagation range-closure audit")

    # --------------------------------------------------------
    # Conservative regex cleanup only inside title-like calls.
    # This removes B5D/B5E/B5F prefix from set_title/title/suptitle strings.
    # --------------------------------------------------------
    $Text = [regex]::Replace(
        $Text,
        "(set_title|suptitle|title)\(\s*(['""])\s*B5D\s+([^'""]+)\2",
        '$1($2$3$2'
    )

    $Text = [regex]::Replace(
        $Text,
        "(set_title|suptitle|title)\(\s*(['""])\s*B5E\s+([^'""]+)\2",
        '$1($2$3$2'
    )

    $Text = [regex]::Replace(
        $Text,
        "(set_title|suptitle|title)\(\s*(['""])\s*B5F\s+([^'""]+)\2",
        '$1($2$3$2'
    )

    return @{
        Text = $Text
        Changed = ($Text -ne $Original)
    }
}

# ------------------------------------------------------------
# 3) Patch candidates
# ------------------------------------------------------------
$ChangedFiles = New-Object System.Collections.Generic.List[string]

"Patch started: $(Get-Date)" | Out-File -FilePath $PatchReport -Encoding UTF8

foreach ($f in $CandidateFiles) {
    $path = $f.FullName
    $txt = Get-Content -LiteralPath $path -Raw

    $result = Patch-VisibleFigureText -Text $txt

    if ($result.Changed) {
        $Backup = "$path.bak_figurelabels_$Stamp"
        Copy-Item -LiteralPath $path -Destination $Backup -Force

        Set-Content -LiteralPath $path -Value $result.Text -Encoding UTF8

        $ChangedFiles.Add($path)

        Write-Host "[PATCHED] $path" -ForegroundColor Green
        "[PATCHED] $path" | Out-File -FilePath $PatchReport -Encoding UTF8 -Append
        "  Backup: $Backup" | Out-File -FilePath $PatchReport -Encoding UTF8 -Append
    }
    else {
        Write-Host "[NO CHANGE] $path"
        "[NO CHANGE] $path" | Out-File -FilePath $PatchReport -Encoding UTF8 -Append
    }
}

Write-Host ""
Write-Host "Changed Python files: $($ChangedFiles.Count)" -ForegroundColor Yellow
"" | Out-File -FilePath $PatchReport -Encoding UTF8 -Append
"Changed Python files: $($ChangedFiles.Count)" | Out-File -FilePath $PatchReport -Encoding UTF8 -Append

foreach ($p in $ChangedFiles) {
    "  $p" | Out-File -FilePath $PatchReport -Encoding UTF8 -Append
}

# ------------------------------------------------------------
# 4) Re-run modified scripts when possible
# ------------------------------------------------------------
"Run started: $(Get-Date)" | Out-File -FilePath $RunLog -Encoding UTF8

foreach ($p in $ChangedFiles) {
    Write-Host ""
    Write-Host "[RUN TRY] $p" -ForegroundColor Cyan
    "============================================================" | Out-File -FilePath $RunLog -Encoding UTF8 -Append
    "[RUN TRY] $p" | Out-File -FilePath $RunLog -Encoding UTF8 -Append

    $content = Get-Content -LiteralPath $p -Raw

    # Do not run obvious library/module-only files.
    if ($content -notmatch "__main__" -and $content -notmatch "argparse" -and $content -notmatch "savefig") {
        Write-Host "  skipped: no obvious script entry point / savefig"
        "  skipped: no obvious script entry point / savefig" | Out-File -FilePath $RunLog -Encoding UTF8 -Append
        continue
    }

    $ScriptDir = Split-Path -Parent $p
    $ScriptName = Split-Path -Leaf $p

    Push-Location -LiteralPath $ScriptDir

    try {
        # If script has argparse and --outdir, pass a clean output dir.
        if ($content -match "--outdir") {
            $CleanFigOut = Join-Path $Root "outputs\cleaned_visible_figures_$Stamp"
            New-Item -ItemType Directory -Force -Path $CleanFigOut | Out-Null

            Write-Host "  command: python $ScriptName --outdir $CleanFigOut"
            "  command: python $ScriptName --outdir $CleanFigOut" | Out-File -FilePath $RunLog -Encoding UTF8 -Append

            python $ScriptName --outdir "$CleanFigOut" 2>&1 | Tee-Object -FilePath $RunLog -Append
        }
        else {
            Write-Host "  command: python $ScriptName"
            "  command: python $ScriptName" | Out-File -FilePath $RunLog -Encoding UTF8 -Append

            python $ScriptName 2>&1 | Tee-Object -FilePath $RunLog -Append
        }
    }
    catch {
        Write-Host "  run failed: $($_.Exception.Message)" -ForegroundColor Red
        "  run failed: $($_.Exception.Message)" | Out-File -FilePath $RunLog -Encoding UTF8 -Append
    }
    finally {
        Pop-Location
    }
}

# ------------------------------------------------------------
# 5) Post-patch verification search
# ------------------------------------------------------------
$PostReport = Join-Path $AuditDir "post_patch_visible_label_search.txt"

"Post-patch visible-label search: $(Get-Date)" | Out-File -FilePath $PostReport -Encoding UTF8
"" | Out-File -FilePath $PostReport -Encoding UTF8 -Append

$CheckPatterns = @(
    "B5D tight local-envelope validation statistics",
    "B5D case-level",
    "B5D vehicle-level",
    "B5E normalized terminal-residual diagnostic",
    "B5F long-propagation range-closure audit",
    "Failure-boundary diagnostic summary"
)

foreach ($pat in $CheckPatterns) {
    "PATTERN: $pat" | Out-File -FilePath $PostReport -Encoding UTF8 -Append
    $hits = Select-String -Path ($PyFiles.FullName) -Pattern $pat -SimpleMatch -ErrorAction SilentlyContinue
    if ($hits) {
        foreach ($h in $hits) {
            "  $($h.Path):$($h.LineNumber): $($h.Line.Trim())" | Out-File -FilePath $PostReport -Encoding UTF8 -Append
        }
    }
    else {
        "  no hits" | Out-File -FilePath $PostReport -Encoding UTF8 -Append
    }
    "" | Out-File -FilePath $PostReport -Encoding UTF8 -Append
}

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Green
Write-Host "Scan report:  $ScanReport"
Write-Host "Patch report: $PatchReport"
Write-Host "Run log:      $RunLog"
Write-Host "Post report:  $PostReport"
Write-Host ""

Write-Host "Changed files:"
foreach ($p in $ChangedFiles) {
    Write-Host "  $p"
}

Write-Host ""
Write-Host "Now check generated figures. If a modified script required custom arguments,"
Write-Host "open run_log.txt and rerun that script manually with its original command."
