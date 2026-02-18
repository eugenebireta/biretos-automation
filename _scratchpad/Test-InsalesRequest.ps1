param(
    [string]$Url,
    [string]$ApiKey,
    [string]$ApiPassword
)

if (-not $Url) { throw "Url is required" }

$secure = ConvertTo-SecureString $ApiPassword -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential($ApiKey, $secure)

try {
    $response = Invoke-WebRequest -Uri $Url -Credential $cred -UseBasicParsing -TimeoutSec 60
    Write-Host "[OK] Status: $($response.StatusCode)" -ForegroundColor Green
    Write-Host $response.Content
} catch {
    if ($_.Exception.Response) {
        $status = $_.Exception.Response.StatusCode.value__
        Write-Host "[ERROR] HTTP $status" -ForegroundColor Red
        $reader = New-Object System.IO.StreamReader $_.Exception.Response.GetResponseStream()
        $body = $reader.ReadToEnd()
        Write-Host $body
    } else {
        Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    }
    exit 1
}












