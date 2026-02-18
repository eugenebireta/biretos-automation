param($target, $name)

Write-Host "Testing $name ($target)..." -ForegroundColor Cyan
try {
    $result = Test-Connection -ComputerName $target -Count 3 -ErrorAction Stop
    $avg = ($result | Measure-Object -Property ResponseTime -Average).Average
    $min = ($result | Measure-Object -Property ResponseTime -Minimum).Minimum
    $max = ($result | Measure-Object -Property ResponseTime -Maximum).Maximum
    Write-Host "  Avg: $([math]::Round($avg, 2))ms, Min: $([math]::Round($min, 2))ms, Max: $([math]::Round($max, 2))ms" -ForegroundColor Green
    return $avg
} catch {
    Write-Host "  Error: $_" -ForegroundColor Red
    return $null
}








