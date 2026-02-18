<#
.SYNOPSIS
    Проверяет доступность сети через активный туннель.
.DESCRIPTION
    Тестирует ключевые хосты и выводит внешний IP.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

$targets = @(
    @{ Host = "github.com"; Port = 443 },
    @{ Host = "ipinfo.io"; Port = 443 },
    @{ Host = "api.openai.com"; Port = 443 }
)

Write-Host "=== Tunnel Connectivity Check ===" -ForegroundColor Cyan

foreach ($target in $targets) {
    $result = Test-NetConnection -ComputerName $target.Host -Port $target.Port -InformationLevel Quiet -WarningAction SilentlyContinue
    $status = if ($result) { "OK" } else { "FAIL" }
    $color = if ($result) { "Green" } else { "Red" }

    Write-Host ("{0,-22} : {1}" -f "$($target.Host):$($target.Port)", $status) -ForegroundColor $color
}

Write-Host ""
Write-Host "External IP:" -NoNewline
try {
    $ip = (Invoke-RestMethod -Uri 'https://ipinfo.io/ip' -TimeoutSec 5).Trim()
    Write-Host " $ip" -ForegroundColor Green
} catch {
    Write-Host " Unable to fetch" -ForegroundColor Red
}









