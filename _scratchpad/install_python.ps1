Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$pythonVersion = '3.12.8'
$installerName = "python-$pythonVersion-amd64.exe"
$installerUrl = "https://www.python.org/ftp/python/$pythonVersion/$installerName"
$workspaceRoot = Resolve-Path "$PSScriptRoot/.."
$scratchpad = Join-Path $workspaceRoot '_scratchpad'
$installerPath = Join-Path $scratchpad $installerName
$logPath = Join-Path $scratchpad 'install_python.log'

"[$(Get-Date -Format o)] Starting Python $pythonVersion installation" | Out-File -FilePath $logPath -Encoding UTF8

if (-not (Test-Path $installerPath)) {
    "[$(Get-Date -Format o)] Downloading installer..." | Add-Content $logPath
    Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath
} else {
    "[$(Get-Date -Format o)] Installer already downloaded, skipping download." | Add-Content $logPath
}

$installArgs = @(
    '/quiet',
    'InstallAllUsers=0',
    'PrependPath=1',
    'Include_test=0',
    'Include_pip=1',
    'Shortcuts=0'
)

"[$(Get-Date -Format o)] Running installer..." | Add-Content $logPath
Start-Process -FilePath $installerPath -ArgumentList $installArgs -Wait

$pythonBase = Join-Path $env:LOCALAPPDATA 'Programs\Python'
if (-not (Test-Path $pythonBase)) {
    throw "Python base directory not found at $pythonBase after installation."
}

$pythonDir = Get-ChildItem $pythonBase -Directory | Where-Object { $_.Name -like 'Python312*' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $pythonDir) {
    throw "Python 3.12 installation directory not found under $pythonBase."
}

$pythonExe = Join-Path $pythonDir.FullName 'python.exe'
if (-not (Test-Path $pythonExe)) {
    throw "python.exe not found at $pythonExe."
}

"[$(Get-Date -Format o)] Upgrading pip..." | Add-Content $logPath
& $pythonExe -m pip install --upgrade pip

"[$(Get-Date -Format o)] Installing required libraries..." | Add-Content $logPath
& $pythonExe -m pip install --upgrade paramiko requests

"[$(Get-Date -Format o)] Installation finished successfully." | Add-Content $logPath
Write-Output "Python installed at $pythonExe"









