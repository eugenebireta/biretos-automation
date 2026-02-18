param(
    [string]$Endpoint,
    [string]$ApiKey,
    [string]$ApiPassword
)

if (-not $Endpoint) { throw "Endpoint is required" }

$secure = ConvertTo-SecureString $ApiPassword -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential($ApiKey, $secure)

$url = "https://myshop-bsu266.myinsales.ru/admin/$Endpoint"
$response = Invoke-WebRequest -Uri $url -Credential $cred -UseBasicParsing -TimeoutSec 60
Write-Output $response.Content












