$ErrorActionPreference = 'Stop'
Import-Module C:\cursor_project\biretos-automation\brand-catalog-automation\diagnostics\VPSRunner.psm1 -Force
try {
    Invoke-VPSCommand -Command 'echo test' -Server 'root@216.9.227.124' -Timeout 10 -Method Direct -Quiet
    Write-Host "Command succeeded"
}
catch {
    Write-Host "ERROR >>>"
    $_ | Format-List * | Out-String | Write-Host
}



