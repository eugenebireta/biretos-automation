param(
    [string]$Url = "https://shopware.biretos.ae"
)

Write-Host "[INFO] Checking Shopware endpoint $Url" -ForegroundColor Cyan

try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -Method Head -ErrorAction Stop
    Write-Host "[OK] StatusCode: $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        Write-Host "[DETAIL] HTTP Status: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Yellow
    }
    exit 1
}

Write-Host "[INFO] Shopware endpoint check finished" -ForegroundColor Cyan












