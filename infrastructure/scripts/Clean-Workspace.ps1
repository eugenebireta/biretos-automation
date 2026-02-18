param(
    [int]$DaysToKeep = 7
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$workspaceRoot = Resolve-Path "$PSScriptRoot/../.."
$scratchpad = Join-Path $workspaceRoot '_scratchpad'
$archiveDir = Join-Path $scratchpad 'archive'

if (-not (Test-Path $scratchpad)) {
    throw "Scratchpad directory not found: $scratchpad"
}

New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null

$threshold = (Get-Date).AddDays(-$DaysToKeep)
$protectedPatterns = @('ssh_activity.log', '*-msk.log', '*-usa.log')

function Test-ProtectedFile {
    param($FileInfo)
    foreach ($pattern in $protectedPatterns) {
        if ($FileInfo.Name -like $pattern) {
            return $true
        }
    }
    return $false
}

$oldFiles = Get-ChildItem -Path $scratchpad -File | Where-Object {
    $_.LastWriteTime -lt $threshold -and -not (Test-ProtectedFile -FileInfo $_)
}

if ($oldFiles) {
    $archiveName = "archive-{0}.zip" -f (Get-Date -Format 'yyyyMMdd-HHmmss')
    $archivePath = Join-Path $archiveDir $archiveName
    Compress-Archive -Path $oldFiles.FullName -DestinationPath $archivePath -CompressionLevel Optimal
    $oldFiles | Remove-Item -Force
    Write-Output "Archived $($oldFiles.Count) files to $archivePath"
} else {
    Write-Output "No files older than $DaysToKeep days to archive."
}

$tmpItems = Get-ChildItem -Path $scratchpad -Filter 'tmp*'
foreach ($item in $tmpItems) {
    if (-not (Test-ProtectedFile -FileInfo $item)) {
        if ($item.PSIsContainer) {
            Remove-Item -Path $item.FullName -Recurse -Force
        } else {
            Remove-Item -Path $item.FullName -Force
        }
    }
}

Write-Output "Temporary items cleanup completed."

