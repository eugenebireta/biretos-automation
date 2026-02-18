<#
.SYNOPSIS
    Запускает Xray в фоновом режиме без блокировки терминала.
.DESCRIPTION
    Использует Start-Process с перенаправлением stdout/stderr в логи.
    Возвращает управление мгновенно, предотвращая deadlock Cursor-Agent.
#>

param(
    [string]$ConfigPath = "C:\Users\Eugene\xray\config.json",
    [string]$XrayExe = "C:\Users\Eugene\xray\xray.exe"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path $XrayExe)) {
    throw "Xray executable not found: $XrayExe"
}

if (-not (Test-Path $ConfigPath)) {
    throw "Xray config not found: $ConfigPath"
}

$logDir = "C:\logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$workDir = Split-Path -Parent $XrayExe

Write-Host "Starting Xray in background..."
Write-Host "  Executable: $XrayExe"
Write-Host "  Config:     $ConfigPath"
Write-Host "  Logs:       $logDir\xray_*.log"

Start-Process -FilePath $XrayExe `
    -ArgumentList "run", "-config", $ConfigPath `
    -WorkingDirectory $workDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$logDir\xray_out.log" `
    -RedirectStandardError "$logDir\xray_err.log"

Write-Host "Xray started successfully (background process)."









