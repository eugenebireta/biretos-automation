$ErrorActionPreference = 'Stop'
$stdoutPath = [System.IO.Path]::GetTempFileName()
$stderrPath = [System.IO.Path]::GetTempFileName()
$scp = (Get-Command scp -ErrorAction Stop).Source
$args = @(
    '-o','BatchMode=yes',
    '-o','ConnectTimeout=5',
    '-o','StrictHostKeyChecking=no',
    'C:\cursor_project\biretos-automation\brand-catalog-automation\diagnostics\test_tbank_api.sh',
    'root@216.9.227.124:/root/test_tbank_api.sh'
)
$process = Start-Process -FilePath $scp -ArgumentList $args -NoNewWindow -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
try {
    Wait-Process -InputObject $process -Timeout 10 -ErrorAction Stop
}
catch {
    try { $process.Kill() } catch { }
    throw "Timeout"
}
$exitCode = $process.ExitCode
$stdout = Get-Content $stdoutPath -Raw -ErrorAction SilentlyContinue
$stderr = Get-Content $stderrPath -Raw -ErrorAction SilentlyContinue
Write-Host "Exit=$exitCode"
Write-Host "StdOut=[$stdout]"
Write-Host "StdErr=[$stderr]"
Remove-Item $stdoutPath,$stderrPath -ErrorAction SilentlyContinue

