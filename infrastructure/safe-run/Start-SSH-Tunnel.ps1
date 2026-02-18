<#
.SYNOPSIS
    Запускает SSH SOCKS5 туннель в фоновом режиме.
.DESCRIPTION
    Создаёт динамический туннель (-D) на порт 10808 через dev-сервер.
    Использует Start-Process, чтобы Cursor-Agent не ждал завершения ssh.
#>

param(
    [string]$ServerHost = "77.233.222.214",
    [string]$User = "root",
    [int]$SocksPort = 10808
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$logDir = "C:\logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

Write-Host "Starting SSH tunnel in background..."
Write-Host "  Server:  $User@$ServerHost"
Write-Host "  SOCKS5:  127.0.0.1:$SocksPort"
Write-Host "  Logs:    $logDir\ssh_*.log"

$arguments = @(
    "-D", $SocksPort,
    "-N",
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=no",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
    "$User@$ServerHost"
)

Start-Process -FilePath "ssh.exe" `
    -ArgumentList $arguments `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$logDir\ssh_out.log" `
    -RedirectStandardError "$logDir\ssh_err.log"

Write-Host "SSH tunnel started successfully (background process)."
Write-Host "Test with: curl --socks5 127.0.0.1:$SocksPort https://ipinfo.io/ip"









