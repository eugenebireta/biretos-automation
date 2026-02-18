# Измерение RTT до chatgpt.com
$results = @()
$count = 10

Write-Host "Измерение RTT до chatgpt.com ($count запросов)..." -ForegroundColor Cyan

1..$count | ForEach-Object {
    $num = $_
    $start = Get-Date
    try {
        $response = Invoke-WebRequest -Uri "https://chatgpt.com" -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
        $end = Get-Date
        $rtt = ($end - $start).TotalMilliseconds
        $results += [PSCustomObject]@{
            Request = $num
            RTT_ms = [math]::Round($rtt, 2)
            Status = "Success"
            StatusCode = $response.StatusCode
        }
        Write-Host "Request $num : $([math]::Round($rtt, 2)) ms" -ForegroundColor Green
    } catch {
        $results += [PSCustomObject]@{
            Request = $num
            RTT_ms = 0
            Status = "Failed"
            StatusCode = "N/A"
        }
        Write-Host "Request $num : Failed - $($_.Exception.Message)" -ForegroundColor Red
    }
    Start-Sleep -Milliseconds 1000
}

Write-Host "`n=== Результаты ===" -ForegroundColor Cyan
$results | Format-Table -AutoSize

if ($results | Where-Object { $_.Status -eq "Success" }) {
    $successful = $results | Where-Object { $_.Status -eq "Success" }
    $avgRTT = ($successful | Measure-Object -Property RTT_ms -Average).Average
    $minRTT = ($successful | Measure-Object -Property RTT_ms -Minimum).Minimum
    $maxRTT = ($successful | Measure-Object -Property RTT_ms -Maximum).Maximum
    $jitter = $maxRTT - $minRTT
    $successRate = ($successful.Count / $count) * 100
    
    Write-Host "`n=== Статистика ===" -ForegroundColor Cyan
    Write-Host "Min RTT: $([math]::Round($minRTT, 2)) ms" -ForegroundColor Yellow
    Write-Host "Avg RTT: $([math]::Round($avgRTT, 2)) ms" -ForegroundColor Yellow
    Write-Host "Max RTT: $([math]::Round($maxRTT, 2)) ms" -ForegroundColor Yellow
    Write-Host "Jitter: $([math]::Round($jitter, 2)) ms" -ForegroundColor Yellow
    Write-Host "Success Rate: $([math]::Round($successRate, 2))%" -ForegroundColor Yellow
}

# Экспорт результатов
$results | Export-Csv -Path "rtt_results.csv" -NoTypeInformation -Encoding UTF8
Write-Host "`nРезультаты сохранены в rtt_results.csv" -ForegroundColor Green



