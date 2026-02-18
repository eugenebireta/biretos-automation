$ErrorActionPreference = 'Stop'
. 'C:\cursor_project\biretos-automation\brand-catalog-automation\diagnostics\VPSRunner.psm1'
Get-Command Invoke-VPSProcess -ErrorAction Stop | Out-Null
$scp = (Get-Command scp -ErrorAction Stop).Source
$args = @(
    '-o','BatchMode=yes',
    '-o','ConnectTimeout=5',
    '-o','StrictHostKeyChecking=no',
    'C:\cursor_project\biretos-automation\brand-catalog-automation\diagnostics\test_tbank_api.sh',
    'root@216.9.227.124:/root/test_tbank_api.sh'
)
$res = Invoke-VPSProcess -FilePath $scp -ArgumentList $args -TimeoutSeconds 30 -LogContext 'manual'
$res | Format-List *

