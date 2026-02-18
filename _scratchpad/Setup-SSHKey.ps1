param(
    [string]$TargetHost = "77.233.222.214",
    [string]$User = "root",
    [string]$Password = "u?GG8MJ1p9m?jN",
    [string]$PythonPath = "C:\Users\Евгений\AppData\Local\Programs\Python\Python313\python.exe"
)

$keyPath = "$env:USERPROFILE\.ssh\id_rsa.pub"

if (-not (Test-Path $keyPath)) {
    Write-Host "[INFO] SSH key not found. Generating new key pair..." -ForegroundColor Yellow
    $privatePath = "$env:USERPROFILE\.ssh\id_rsa"
    ssh-keygen -t rsa -b 4096 -N "" -f $privatePath | Out-Null
}

if (-not (Test-Path $PythonPath)) {
    Write-Host "[ERROR] Python executable not found at $PythonPath" -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Uploading public key to $User@$TargetHost" -ForegroundColor Cyan
& $PythonPath "_scratchpad\setup_ssh_key.py" --host $TargetHost --user $User --password $Password --key $keyPath

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to configure SSH key." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "[OK] SSH key added successfully." -ForegroundColor Green

