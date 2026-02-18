param(
    [string]$BaseUrl
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir  # brand-catalog-automation
$repoRoot = Split-Path -Parent $repoRoot   # project root

$envPath = Join-Path $repoRoot ".env"
if (-not (Test-Path $envPath)) {
    throw ".env file not found at $envPath"
}

$envLines = Get-Content -Path $envPath
function Get-EnvValue {
    param (
        [string]$Key
    )
    foreach ($line in $envLines) {
        if ($line -match "^$Key=") {
            return $line.Split("=",2)[1].Trim('"')
        }
    }
    return $null
}

$token = Get-EnvValue -Key "TBANK_TOKEN"
if (-not $token) {
    throw "TBANK_TOKEN not found in .env"
}

$base = if ($BaseUrl) { $BaseUrl } else { Get-EnvValue -Key "TBANK_API_URL" }
if (-not $base) {
    $base = "https://api.tbank.ru"
}
$base = $base.TrimEnd("/")

$endpoint = "/v1/consignments?limit=3&status=paid"
$url = "$base$endpoint"
Write-Host "[probe] GET $url"

$outputPath = Join-Path $scriptDir "tbank_invoices_test.json"

try {
    $resp = Invoke-WebRequest -Uri $url -Headers @{
        Authorization = "Bearer $token"
        Accept        = "application/json"
    } -TimeoutSec 30

    $body = $resp.Content
    $jsonBody = $null
    try {
        $jsonBody = $body | ConvertFrom-Json
    } catch {
        $jsonBody = $null
    }

    $payload = [pscustomobject]@{
        generated_at = (Get-Date).ToString("o")
        base_url     = $base
        endpoint     = $endpoint
        status       = $resp.StatusCode
        body_raw     = $body
        body_json    = $jsonBody
    }
}
catch {
    if ($_.Exception.Response) {
        $resp = $_.Exception.Response
        $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $bodyText = $reader.ReadToEnd()
        $jsonBody = $null
        try {
            $jsonBody = $bodyText | ConvertFrom-Json
        } catch {
            $jsonBody = $null
        }
        $payload = [pscustomobject]@{
            generated_at = (Get-Date).ToString("o")
            base_url     = $base
            endpoint     = $endpoint
            status       = [int]$resp.StatusCode
            error        = $_.Exception.Message
            body_raw     = $bodyText
            body_json    = $jsonBody
        }
    }
    else {
        throw
    }
}

$payload | ConvertTo-Json -Depth 12 | Set-Content -Path $outputPath -Encoding UTF8
Write-Host "[probe] Saved diagnostics to $outputPath"

