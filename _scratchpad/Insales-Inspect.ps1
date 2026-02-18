param(
    [string]$Shop = "biretos.insales.ru",
    [string]$ApiKey = "changeme",
    [string]$ApiPassword = "changeme",
    [switch]$UseHttp
)

function Invoke-InsalesRequest {
    param(
        [string]$Endpoint
    )

    if ($UseHttp.IsPresent) {
        $scheme = "http"
    } else {
        $scheme = "https"
    }
    $baseUrl = "{0}://{1}:{2}@{3}/admin" -f $scheme, $ApiKey, $ApiPassword, $Shop
    $url = "$baseUrl/$Endpoint"
    $authPair = "{0}:{1}" -f $ApiKey, $ApiPassword
    $authHeader = [System.Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes($authPair))
    $headers = @{
        "Accept"        = "application/json"
        "Authorization" = "Basic $authHeader"
    }

    try {
        Write-Host "[INFO] GET $url" -ForegroundColor Cyan
        $response = Invoke-WebRequest -Uri $url -Headers $headers -UseBasicParsing -TimeoutSec 60
        $json = $response.Content | ConvertFrom-Json
        return [pscustomobject]@{
            Success = $true
            Data    = $json
            Status  = $response.StatusCode
        }
    } catch {
        Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
        return [pscustomobject]@{
            Success = $false
            Data    = $null
            Status  = $null
        }
    }
}

$results = [ordered]@{}
$endpoints = @(
    "products/count.json",
    "collections/count.json",
    "orders/count.json",
    "clients/count.json"
)

foreach ($endpoint in $endpoints) {
    $res = Invoke-InsalesRequest -Endpoint $endpoint
    $results[$endpoint] = $res
}

$productSample = Invoke-InsalesRequest -Endpoint "products.json?per_page=1&fields=id,title,variants,images,updated_at,created_at"
$results["products_sample"] = $productSample

$outputPath = "C:\cursor_project\biretos-automation\_scratchpad\insales_inspect_result.json"
$export = @{}
foreach ($key in $results.Keys) {
    if ($results[$key].Success -and $results[$key].Data) {
        $export[$key] = $results[$key].Data
    } else {
        $export[$key] = @{ error = "request_failed" }
    }
}

$export | ConvertTo-Json -Depth 6 | Set-Content -Path $outputPath -Encoding UTF8
Write-Host "[INFO] Results saved to $outputPath" -ForegroundColor Green


