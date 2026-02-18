param(
    [string]$Server = 'root@216.9.227.124',
    [string]$RemotePath = '/root/test_tbank_api.sh',
    [int]$Timeout = 300
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$modulePath  = Join-Path $scriptDir 'VPSRunner.psm1'
$localScript = Join-Path $scriptDir 'test_tbank_api.sh'
$resultPath  = Join-Path $scriptDir 'tbank_api_test_result.txt'

if (-not (Test-Path $modulePath)) { throw "VPSRunner module not found at $modulePath" }
if (-not (Test-Path $localScript)) { throw "Local script not found at $localScript" }

Import-Module $modulePath -Force

$methods = @('Direct','File')
$success = $false
$lastError = $null

foreach ($method in $methods) {
    Write-Host "[tbank-test] Trying method: $method" -ForegroundColor Cyan
    try {
        $result = Invoke-VPSScript -LocalScriptPath $localScript `
                                   -Server $Server `
                                   -RemotePath $RemotePath `
                                   -Timeout $Timeout `
                                   -Method $method `
                                   -KeepRemoteScript:$false
        $success = $true
        Write-Host "[tbank-test] Success via $method" -ForegroundColor Green
        if ($result.Output) {
            Set-Content -Path $resultPath -Value $result.Output -Encoding UTF8
            Write-Host "[tbank-test] Saved output to $resultPath"
        }
        break
    }
    catch {
        $lastError = $_.Exception.Message
        Write-Warning "[tbank-test] Method $method failed: $lastError"
    }
}

if (-not $success) {
    Write-Error "[tbank-test] All methods failed. Last error: $lastError"
    exit 1
}

Write-Host "[tbank-test] Done."


