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

function Test-Endpoint {
    param(
        [Parameter(Mandatory = $true)] [string] $Host,
        [int] $Port = 443
    )

    try {
        $probe = Test-NetConnection -ComputerName $Host -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
        if ($probe) { Write-Host \"${Host}:${Port} reachable\" }
        else { Write-Warning \"${Host}:${Port} not reachable\" }
    } catch {
        Write-Warning \"${Host}:${Port} probe error: $_\"
    }
}

$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$runScript  = Join-Path $scriptDir 'run_cursorvpn.ps1'
$configPath = Join-Path $scriptDir 'CursorVPN.conf'

if (-not (Test-Path $runScript)) {
    throw "run_cursorvpn.ps1 not found: $runScript"
}

if (-not (Test-Path $configPath)) {
    throw "Config not found: $configPath"
}

$tunnelName  = [IO.Path]::GetFileNameWithoutExtension($configPath)
$serviceName = "WireGuardTunnel$" + $tunnelName
$expectedIp  = '216.9.227.124'

Write-Host "=== Starting main script ==="
& $runScript

Write-Host "=== Checking WireGuard service ==="
$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($service) {
    Write-Host "$serviceName : $($service.Status)"
} else {
    Write-Warning "Service $serviceName not found"
}

$wgPath = Get-WireGuardPath
Write-Host "=== Tunnel status ==="
& $wgPath /status $tunnelName

Write-Host "=== External IP check ==="
try {
    $currentIp = (Invoke-RestMethod -Uri 'https://ipinfo.io/ip' -TimeoutSec 5).Trim()
    Write-Host "Current IP: $currentIp (expected $expectedIp)"
} catch {
    Write-Warning "Failed to fetch IP: $_"
    exit 1
}

if ($currentIp -ne $expectedIp) {
    Write-Warning "IP mismatch, running diagnostics"
    Test-Endpoint -Host '216.9.227.124' -Port 51820
    Test-Endpoint -Host 'api.openai.com' -Port 443
    Test-Endpoint -Host 'anthropic.com' -Port 443
    Test-Endpoint -Host 'openrouter.ai' -Port 443
    exit 1
}

Write-Host "IP matches, VPS routing confirmed."
Write-Host "=== AI endpoint probes ==="
Test-Endpoint -Host 'api.openai.com' -Port 443
Test-Endpoint -Host 'anthropic.com' -Port 443
Test-Endpoint -Host 'openrouter.ai' -Port 443

Write-Host "Done."

