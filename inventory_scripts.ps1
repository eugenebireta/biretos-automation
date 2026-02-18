<#
.SYNOPSIS
    Генерирует каталог всех скриптов (.py, .ps1, .sh) в проекте.
.DESCRIPTION
    Рекурсивно сканирует дерево, игнорируя системные директории, и создает
    Markdown-отчет SCRIPTS_CATALOG.md с кратким описанием каждого скрипта.
#>

param(
    [string]$OutputFile = "SCRIPTS_CATALOG.md",
    [string[]]$IncludeExtensions = @(".py", ".ps1", ".sh"),
    [string[]]$IgnoreDirs = @(
        ".git",
        ".cursor",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "build",
        "dist",
        ".idea",
        ".vscode",
        "migrations",
        ".pytest_cache"
    )
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$rootPath = Get-Location
$outputPath = Join-Path $rootPath $OutputFile

Write-Host "Scanning project ($rootPath)..." -ForegroundColor Cyan

function Test-IsIgnoredPath {
    param(
        [string]$Path,
        [string[]]$Ignored
    )
    foreach ($dir in $Ignored) {
        if ($Path -like "*\${dir}\*") {
            return $true
        }
    }
    return $false
}

function Get-CategoryFromPath {
    param([string]$RelativePath, [string]$FileName)

    switch -regex ($RelativePath) {
        "infrastructure" { return "Infrastructure" }
        "insales_to_shopware_migration" { return "Migration" }
        "perplexity" { return "Data Enrichment" }
        "_scratchpad" { return "Scratchpad" }
    }

    switch -regex ($FileName) {
        "^analy[sz]e_" { return "Analytics" }
        "^compare_" { return "Analytics" }
        "^check_" { return "Diagnostics" }
        "^test_" { return "Diagnostics" }
        "^verify_" { return "Diagnostics" }
        "^fix_" { return "Maintenance" }
        "^update_" { return "Maintenance" }
    }

    return "Utilities"
}

function Get-DescriptionSample {
    param([System.IO.FileInfo]$File)

    try {
        $lines = Get-Content -Path $File.FullName -First 8 -ErrorAction Stop
    } catch {
        return ""
    }

    $meaningful = $lines |
        Where-Object { $_ -match "\S" } |
        Select-Object -First 3

    if (-not $meaningful) {
        return ""
    }

    $joined = ($meaningful -join " ").Trim()
    if ($joined.Length -gt 160) {
        $joined = $joined.Substring(0, 157) + "..."
    }

    return ($joined -replace "\|", "\|")
}

$files = Get-ChildItem -Path $rootPath -Recurse -File |
    Where-Object {
        $IncludeExtensions -contains $_.Extension.ToLower() -and
        -not (Test-IsIgnoredPath -Path $_.FullName -Ignored $IgnoreDirs)
    } |
    Sort-Object FullName

Write-Host ("Files found: {0}" -f $files.Count) -ForegroundColor Green

$report = @()
$report += '# Script Catalog'
$report += ""
$report += ("Generated at: {0:yyyy-MM-dd HH:mm}" -f (Get-Date))
$report += ""
$report += '| File | Path (from root) | Category | Description |'
$report += '|------|-------------------|----------|-------------|'

foreach ($file in $files) {
    $relPath = $file.FullName.Substring($rootPath.Path.Length + 1)
    $category = Get-CategoryFromPath -RelativePath $relPath -FileName $file.Name
    $description = Get-DescriptionSample -File $file
    $escapedPath = $relPath.Replace("\", "/")
    $report += "| **$($file.Name)** | `$escapedPath` | $category | $description |"
}

$report | Out-File -FilePath $outputPath -Encoding UTF8

Write-Host "Done: $outputPath" -ForegroundColor Green

