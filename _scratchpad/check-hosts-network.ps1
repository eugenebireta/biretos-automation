# Network connectivity check

Write-Host "`n=== External IP ===" -ForegroundColor Cyan
try {
    $ip = Invoke-RestMethod -Uri "https://api.ipify.org?format=json" -TimeoutSec 10
    Write-Host "External IP: $($ip.ip)" -ForegroundColor Green
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
}

Write-Host "`n=== Hosts Check ===" -ForegroundColor Cyan

$hosts = @(
    "cursor.sh",
    "api.openai.com",
    "api.anthropic.com",
    "api.groq.com",
    "deepmind.googleapis.com",
    "openrouter.ai",
    "huggingface.co",
    "github.com",
    "githubusercontent.com",
    "216.9.227.124",
    "77.233.222.214"
)

$results = @()

foreach ($h in $hosts) {
    Write-Host "`n--- $h ---" -ForegroundColor Yellow
    try {
        $result = Test-NetConnection -ComputerName $h -Port 443 -InformationLevel Detailed -WarningAction SilentlyContinue -ErrorAction Stop
        $status = "OK"
        $sourceIP = $result.SourceAddress
        $remoteIP = $result.RemoteAddress
        $tcpSuccess = $result.TcpTestSucceeded
        
        Write-Host "  Source IP: $sourceIP" -ForegroundColor Cyan
        Write-Host "  Remote IP: $remoteIP" -ForegroundColor Cyan
        Write-Host "  TCP Test: $tcpSuccess" -ForegroundColor $(if ($tcpSuccess) { "Green" } else { "Red" })
        
        $results += [PSCustomObject]@{
            Host = $h
            Status = $status
            SourceIP = $sourceIP
            RemoteIP = $remoteIP
            TcpSuccess = $tcpSuccess
        }
    } catch {
        Write-Host "  Error: $_" -ForegroundColor Red
        $results += [PSCustomObject]@{
            Host = $h
            Status = "ERROR"
            SourceIP = "N/A"
            RemoteIP = "N/A"
            TcpSuccess = $false
        }
    }
}

Write-Host "`n=== Summary ===" -ForegroundColor Cyan
$results | Format-Table -AutoSize

# Connection type analysis
Write-Host "`n=== Analysis ===" -ForegroundColor Cyan
try {
    $externalIP = (Invoke-RestMethod -Uri "https://api.ipify.org?format=json" -TimeoutSec 10).ip
    Write-Host "System External IP: $externalIP" -ForegroundColor Yellow
    
    if ($externalIP -match "^(185\.|188\.|195\.)") {
        Write-Host "Traffic likely goes through VPN (Switzerland)" -ForegroundColor Red
    } elseif ($externalIP -match "^(216\.9\.227\.)") {
        Write-Host "Traffic goes through VPS-1 (USA)" -ForegroundColor Green
    } elseif ($externalIP -match "^(77\.233\.222\.)") {
        Write-Host "Traffic goes through VPS-2 (Moscow)" -ForegroundColor Yellow
    } else {
        Write-Host "Traffic goes directly (possibly your real IP)" -ForegroundColor Green
    }
} catch {
    Write-Host "Error determining connection type: $_" -ForegroundColor Red
}
