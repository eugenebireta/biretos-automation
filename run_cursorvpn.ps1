[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-WireGuardPath {
    $candidates = @(
        (Join-Path $env:ProgramFiles 'WireGuard\wireguard.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'WireGuard\wireguard.exe'),
        'wireguard.exe'
    ) | Where-Object { $_ }

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }

    throw "WireGuard не найден. Установите WireGuard для Windows."
}

$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$configPath = Join-Path $scriptDir 'CursorVPN.conf'

if (-not (Test-Path $configPath)) {
    throw "Config not found: $configPath"
}

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run PowerShell as Administrator to install WireGuard service."
}

$wgPath      = Get-WireGuardPath
$tunnelName  = [IO.Path]::GetFileNameWithoutExtension($configPath)
$serviceName = "WireGuardTunnel$" + $tunnelName

Write-Host "WireGuard: $wgPath"
Write-Host "Config:   $configPath"
Write-Host "Tunnel:   $tunnelName"

try {
    & $wgPath /uninstalltunnelservice $tunnelName *> $null
} catch {
    Write-Warning "Could not remove previous service (safe to ignore): $_"
}

& $wgPath /installtunnelservice "$configPath"
Start-Sleep -Seconds 5

$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($service -and $service.Status -ne 'Running') {
    Start-Service -InputObject $service
    Start-Sleep -Seconds 2
}

$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if (-not $service -or $service.Status -ne 'Running') {
    throw "Service $serviceName failed to start."
}

Write-Host "WireGuard status:"
& $wgPath /status $tunnelName

Write-Host "Tunnel $tunnelName installed and running."

