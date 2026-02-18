param($target, $name)

Write-Host "Testing $name ($target)..." -ForegroundColor Cyan
try {
    $pingOutput = ping.exe -n 5 -w 1000 $target 2>&1
    $times = $pingOutput | Select-String "time=(\d+)ms" | ForEach-Object { 
        if ($_.Matches.Groups[1].Value) { [int]$_.Matches.Groups[1].Value }
    }
    
    if ($times.Count -gt 0) {
        $avg = ($times | Measure-Object -Average).Average
        $min = ($times | Measure-Object -Minimum).Minimum
        $max = ($times | Measure-Object -Maximum).Maximum
        Write-Host "  Avg: $([math]::Round($avg, 0))ms, Min: $min ms, Max: $max ms" -ForegroundColor Green
        return $avg
    } else {
        Write-Host "  No response" -ForegroundColor Red
        return $null
    }
} catch {
    Write-Host "  Error: $_" -ForegroundColor Red
    return $null
}








