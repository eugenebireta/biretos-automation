param(
    [string]$LogPattern = "*.log"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$workspaceRoot = Resolve-Path "$PSScriptRoot/../.."
$scratchpad = Join-Path $workspaceRoot '_scratchpad'

if (-not (Test-Path $scratchpad)) {
    throw "Scratchpad directory not found: $scratchpad"
}

$logFiles = Get-ChildItem -Path $scratchpad -Filter $LogPattern -File
if (-not $logFiles) {
    Write-Output "INFO: No log files found under $scratchpad."
    exit 0
}

$pattern = '(?i)\b(?:ssh|scp)\s+[^`n]*root@'
$violations = @()

foreach ($file in $logFiles) {
    $matches = Select-String -Path $file.FullName -Pattern $pattern
    foreach ($match in $matches) {
        $violations += [pscustomobject]@{
            File = $file.FullName
            LineNumber = $match.LineNumber
            Line = $match.Line.Trim()
        }
    }
}

if ($violations.Count -eq 0) {
    Write-Output "OK: Direct ssh/scp usage not detected in logs."
    exit 0
}

Write-Warning "Detected direct ssh/scp usage. Replace with Invoke-SafeSsh/Invoke-SafeScp."
$violations | Format-Table -AutoSize
exit 2

