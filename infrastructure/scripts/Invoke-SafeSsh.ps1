<#
.SYNOPSIS
    Safe SSH wrapper with centralized config, logging, and timeouts.
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$ServerName,

    [Parameter(Mandatory = $true)]
    [string]$Command,

    [int]$TimeoutSeconds = 30
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

$serverHost = $server.host
$user = $server.user
$sshKey = $server.ssh_key_path

if (-not $serverHost -or -not $user) {
    throw "Server '$ServerName' is missing host or user."
}

function Write-SshLog($message) {
    $timestamp = (Get-Date).ToString('u')
    $entry = "[{0}] [Server:{1}] {2}" -f $timestamp, $ServerName, $message
    Add-Content -Path $logPath -Value $entry -Encoding UTF8
}

Write-SshLog "START Command: $Command"

$sshArgs = @(
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'ConnectTimeout=10',
    '-o', 'ServerAliveInterval=5',
    '-o', 'ServerAliveCountMax=3'
)

if ($sshKey) {
    $sshArgs += @('-i', $sshKey)
}

$sshArgs += @("$user@$serverHost", $Command)

function Convert-ToQuotedArgument {
    param([string]$Value)
    if ($Value -match '[\s"]') {
        '"' + ($Value -replace '"', '\"') + '"'
    } else {
        $Value
    }
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'ssh'
$psi.Arguments = ($sshArgs | ForEach-Object { Convert-ToQuotedArgument $_ }) -join ' '
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $psi
$null = $process.Start()

if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    Write-SshLog "TIMEOUT after ${TimeoutSeconds}s. Killing process."
    try { $process.Kill() } catch {}
    throw "SSH command timed out after ${TimeoutSeconds}s."
}

$stdout = $process.StandardOutput.ReadToEnd()
$stderr = $process.StandardError.ReadToEnd()
$exitCode = $process.ExitCode

Write-SshLog ("FINISH exit={0}" -f $exitCode)

if ($exitCode -ne 0) {
    throw "SSH exited with code $exitCode`n$stderr"
}

return $stdout



