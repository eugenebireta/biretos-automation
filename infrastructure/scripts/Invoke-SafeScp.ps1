<#
.SYNOPSIS
    Safe SCP wrapper with centralized config, logging, and timeouts.
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$ServerName,

    [Parameter(Mandatory = $true)]
    [string]$LocalPath,

    [Parameter(Mandatory = $true)]
    [string]$RemotePath,

    [int]$TimeoutSeconds = 60
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Resolve-Path "$PSScriptRoot/../.."
$configPath = Join-Path $root 'infrastructure/config/servers.json'
$logPath = Join-Path $root '_scratchpad/ssh_activity.log'

if (-not (Test-Path $configPath)) {
    throw "Config file not found: $configPath"
}

$configRaw = Get-Content $configPath -Raw | ConvertFrom-Json
$server = $configRaw.servers.$ServerName
if (-not $server) {
    throw "Server '$ServerName' not found in config."
}

$host = $server.host
$user = $server.user
$sshKey = $server.ssh_key_path

if (-not $host -or -not $user) {
    throw "Server '$ServerName' is missing host or user."
}

if (-not (Test-Path $LocalPath)) {
    throw "Local path not found: $LocalPath"
}

function Write-ScpLog($message) {
    $timestamp = (Get-Date).ToString('u')
    $entry = "[{0}] [Server:{1}] {2}" -f $timestamp, $ServerName, $message
    Add-Content -Path $logPath -Value $entry -Encoding UTF8
}

Write-ScpLog "SCP START Local: $LocalPath -> Remote: $RemotePath"

$scpArgs = @(
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'ConnectTimeout=10',
    '-o', 'ServerAliveInterval=5',
    '-o', 'ServerAliveCountMax=3'
)

if ($sshKey) {
    $scpArgs += @('-i', $sshKey)
}

$scpArgs += @($LocalPath, "$user@$host`:$RemotePath")

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'scp'
$psi.ArgumentList.AddRange($scpArgs)
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $psi
$null = $process.Start()

if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    Write-ScpLog "SCP TIMEOUT after ${TimeoutSeconds}s. Killing process."
    try { $process.Kill() } catch {}
    throw "SCP command timed out after ${TimeoutSeconds}s."
}

$stdout = $process.StandardOutput.ReadToEnd()
$stderr = $process.StandardError.ReadToEnd()
$exitCode = $process.ExitCode

Write-ScpLog ("SCP FINISH exit={0}" -f $exitCode)

if ($exitCode -ne 0) {
    throw "SCP exited with code $exitCode`n$stderr"
}

return $stdout











