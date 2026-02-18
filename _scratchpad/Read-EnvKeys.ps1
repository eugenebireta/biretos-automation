param(
    [string]$EnvPath = "C:\cursor_project\biretos-automation\.env"
)

Write-Host "[INFO] Read-EnvKeys started" -ForegroundColor Cyan

if (-not (Test-Path -Path $EnvPath)) {
    Write-Host "[ERROR] .env file not found at $EnvPath" -ForegroundColor Red
    exit 1
}

function Get-KeyValue {
    param(
        [string]$Content,
        [string]$Key
    )

    $pattern = "^\s*$Key\s*=\s*(.+)$"
    foreach ($line in $Content.Split("`n")) {
        $trimmed = $line.Trim()
        if ($trimmed -match $pattern) {
            return $Matches[1].Trim()
        }
    }

    return "<not set>"
}

$envContent = Get-Content -Path $EnvPath -Raw
$keysToExtract = @(
    "OPENROUTER_API_KEY",
    "INSALES_SHOP",
    "INSALES_API_KEY",
    "INSALES_API_PASSWORD",
    "SHOPWARE_URL",
    "SHOPWARE_CLIENT_ID",
    "SHOPWARE_CLIENT_SECRET",
    "SHOPWARE_USERNAME",
    "SHOPWARE_PASSWORD"
)

Write-Host "[INFO] Extracting keys..." -ForegroundColor Cyan
$results = @{}
foreach ($key in $keysToExtract) {
    $results[$key] = Get-KeyValue -Content $envContent -Key $key
}

Write-Host ""
Write-Host "=== Key Summary ===" -ForegroundColor Green
foreach ($entry in $results.GetEnumerator()) {
    $value = if ($entry.Value -eq "<not set>") { "<not set>" } else { $entry.Value }
    Write-Host ("{0} = {1}" -f $entry.Key, $value)
}

Write-Host ""
Write-Host "[INFO] Read-EnvKeys completed" -ForegroundColor Cyan

