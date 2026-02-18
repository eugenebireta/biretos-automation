# Comprehensive Architecture Diagnostic Script
# Проверка идеальной архитектуры передачи данных

$ErrorActionPreference = 'Continue'
$results = @()

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  ARCHITECTURE DIAGNOSTIC REPORT" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# A. ЛОКАЛЬНЫЙ ПК
Write-Host "=== A. LOCAL PC DIAGNOSTICS ===" -ForegroundColor Yellow

# 1. External IP
Write-Host "`n1. External Egress IP:" -ForegroundColor Cyan
try {
    $externalIP = (Invoke-RestMethod -Uri "https://api.ipify.org?format=json" -TimeoutSec 10).ip
    Write-Host "   External IP: $externalIP" -ForegroundColor Green
    
    $isVPN = $false
    $isVPS = $false
    $vpnRanges = @("185.", "188.", "195.")  # Switzerland VPN ranges
    $vps1Range = "216.9.227."
    $vps2Range = "77.233.222."
    
    if ($externalIP -match "^($($vpnRanges -join '|'))") {
        $isVPN = $true
        Write-Host "   ⚠️  WARNING: Traffic goes through VPN (Switzerland)" -ForegroundColor Red
    } elseif ($externalIP -match "^$vps1Range") {
        $isVPS = $true
        Write-Host "   ⚠️  WARNING: Traffic goes through VPS-1 (USA)" -ForegroundColor Yellow
    } elseif ($externalIP -match "^$vps2Range") {
        $isVPS = $true
        Write-Host "   ⚠️  WARNING: Traffic goes through VPS-2 (Moscow)" -ForegroundColor Yellow
    } else {
        Write-Host "   ✅ Direct connection (not VPN, not VPS)" -ForegroundColor Green
    }
    
    $results += [PSCustomObject]@{
        Segment = "Local PC → Internet"
        Expected = "Direct (not VPN, not VPS)"
        Actual = if ($isVPN) { "VPN (Switzerland)" } elseif ($isVPS) { "VPS Proxy" } else { "Direct" }
        Status = if ($isVPN -or $isVPS) { "❌" } else { "✅" }
    }
} catch {
    Write-Host "   ❌ Error: $_" -ForegroundColor Red
    $results += [PSCustomObject]@{
        Segment = "Local PC → Internet"
        Expected = "Direct"
        Actual = "ERROR"
        Status = "❌"
    }
}

# 2. Active Proxies Check
Write-Host "`n2. Active Proxies Check:" -ForegroundColor Cyan
$proxyVars = @("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY")
$hasProxy = $false
foreach ($var in $proxyVars) {
    $value = [Environment]::GetEnvironmentVariable($var, "User")
    if ($value) {
        Write-Host "   ⚠️  Found: $var = $value" -ForegroundColor Yellow
        $hasProxy = $true
    }
}
if (-not $hasProxy) {
    Write-Host "   ✅ No proxy environment variables set" -ForegroundColor Green
}

# Check Cursor settings
$cursorSettings = "$env:APPDATA\Cursor\User\settings.json"
if (Test-Path $cursorSettings) {
    $settings = Get-Content $cursorSettings -Raw | ConvertFrom-Json
    if ($settings.'http.proxy') {
        Write-Host "   ⚠️  Cursor proxy configured: $($settings.'http.proxy')" -ForegroundColor Yellow
        $hasProxy = $true
    } else {
        Write-Host "   ✅ Cursor proxy: Not configured" -ForegroundColor Green
    }
}

# Check listening ports (SOCKS/HTTP proxy)
Write-Host "`n3. Listening Proxy Ports:" -ForegroundColor Cyan
$proxyPorts = @(10808, 10800, 8080, 3128, 8888)
$activeProxies = @()
foreach ($port in $proxyPorts) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        Write-Host "   ⚠️  Port $port is listening (possible proxy)" -ForegroundColor Yellow
        $activeProxies += $port
        $hasProxy = $true
    }
}
if ($activeProxies.Count -eq 0) {
    Write-Host "   ✅ No proxy ports listening" -ForegroundColor Green
}

$results += [PSCustomObject]@{
    Segment = "Local PC → Proxies"
    Expected = "No active proxies"
    Actual = if ($hasProxy) { "Proxies detected" } else { "No proxies" }
    Status = if ($hasProxy) { "⚠️" } else { "✅" }
}

# B. МАРШРУТИЗАЦИЯ С ПК
Write-Host "`n=== B. ROUTING FROM LOCAL PC ===" -ForegroundColor Yellow

$testHosts = @(
    @{Name="VPS USA"; IP="216.9.227.124"},
    @{Name="VPS RU"; IP="77.233.222.214"},
    @{Name="api.openai.com"; IP="api.openai.com"},
    @{Name="api.anthropic.com"; IP="api.anthropic.com"},
    @{Name="github.com"; IP="github.com"}
)

foreach ($h in $testHosts) {
    Write-Host "`nTesting route to $($h.Name) ($($h.IP)):" -ForegroundColor Cyan
    
    try {
        # Ping test
        $ping = Test-Connection -ComputerName $h.IP -Count 4 -ErrorAction Stop
        $avgRTT = ($ping | Measure-Object -Property ResponseTime -Average).Average
        $minRTT = ($ping | Measure-Object -Property ResponseTime -Minimum).Minimum
        $maxRTT = ($ping | Measure-Object -Property ResponseTime -Maximum).Maximum
        
        Write-Host "   RTT: Avg=$([math]::Round($avgRTT, 2))ms, Min=$([math]::Round($minRTT, 2))ms, Max=$([math]::Round($maxRTT, 2))ms" -ForegroundColor Green
        
        # Traceroute (first 5 hops)
        Write-Host "   Traceroute (first 5 hops):" -ForegroundColor Cyan
        $tracert = tracert -h 5 -w 1000 $h.IP 2>&1 | Select-Object -Skip 1 -First 5
        foreach ($line in $tracert) {
            if ($line -match "^\s*\d+\s+") {
                Write-Host "     $line" -ForegroundColor Gray
            }
        }
        
        # Determine if direct or VPN
        $isDirect = $true
        $firstHop = ($tracert | Where-Object { $_ -match "^\s*1\s+" } | Select-Object -First 1)
        if ($firstHop -match "185\.|188\.|195\.") {
            $isDirect = $false
            Write-Host "   ⚠️  First hop suggests VPN routing" -ForegroundColor Yellow
        }
        
        $results += [PSCustomObject]@{
            Segment = "Local PC → $($h.Name)"
            Expected = "Direct"
            Actual = if ($isDirect) { "Direct (RTT: $([math]::Round($avgRTT, 2))ms)" } else { "VPN routing" }
            Status = if ($isDirect) { "✅" } else { "⚠️" }
        }
    } catch {
        Write-Host "   ❌ Error: $_" -ForegroundColor Red
        $results += [PSCustomObject]@{
            Segment = "Local PC → $($h.Name)"
            Expected = "Direct"
            Actual = "ERROR"
            Status = "❌"
        }
    }
}

# F. RTT & LATENCY TESTS
Write-Host "`n=== F. RTT & LATENCY TESTS ===" -ForegroundColor Yellow

$rttResults = @()

# 1. Local PC → VPS USA
Write-Host "`n1. Local PC → VPS USA:" -ForegroundColor Cyan
try {
    $ping = Test-Connection -ComputerName "216.9.227.124" -Count 5 -ErrorAction Stop
    $avg = ($ping | Measure-Object -Property ResponseTime -Average).Average
    $min = ($ping | Measure-Object -Property ResponseTime -Minimum).Minimum
    $max = ($ping | Measure-Object -Property ResponseTime -Maximum).Maximum
    Write-Host "   Avg: $([math]::Round($avg, 2))ms, Min: $([math]::Round($min, 2))ms, Max: $([math]::Round($max, 2))ms" -ForegroundColor Green
    $verdict = if ($avg -lt 150) { "Ideal" } elseif ($avg -lt 300) { "OK" } else { "Bad" }
    $rttResults += [PSCustomObject]@{
        Link = "Local PC → VPS USA"
        AvgRTT = "$([math]::Round($avg, 2))ms"
        Verdict = $verdict
    }
} catch {
    Write-Host "   ❌ Error: $_" -ForegroundColor Red
    $rttResults += [PSCustomObject]@{
        Link = "Local PC → VPS USA"
        AvgRTT = "ERROR"
        Verdict = "Bad"
    }
}

# 2. Local PC → VPS RU
Write-Host "`n2. Local PC → VPS RU:" -ForegroundColor Cyan
try {
    $ping = Test-Connection -ComputerName "77.233.222.214" -Count 5 -ErrorAction Stop
    $avg = ($ping | Measure-Object -Property ResponseTime -Average).Average
    $min = ($ping | Measure-Object -Property ResponseTime -Minimum).Minimum
    $max = ($ping | Measure-Object -Property ResponseTime -Maximum).Maximum
    Write-Host "   Avg: $([math]::Round($avg, 2))ms, Min: $([math]::Round($min, 2))ms, Max: $([math]::Round($max, 2))ms" -ForegroundColor Green
    $verdict = if ($avg -lt 50) { "Ideal" } elseif ($avg -lt 100) { "OK" } else { "Bad" }
    $rttResults += [PSCustomObject]@{
        Link = "Local PC → VPS RU"
        AvgRTT = "$([math]::Round($avg, 2))ms"
        Verdict = $verdict
    }
} catch {
    Write-Host "   ❌ Error: $_" -ForegroundColor Red
    $rttResults += [PSCustomObject]@{
        Link = "Local PC → VPS RU"
        AvgRTT = "ERROR"
        Verdict = "Bad"
    }
}

# Summary Tables
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  SUMMARY TABLES" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Architecture Status:" -ForegroundColor Yellow
$results | Format-Table -AutoSize

Write-Host "`nRTT & Latency:" -ForegroundColor Yellow
$rttResults | Format-Table -AutoSize

# Final Verdict
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  FINAL VERDICT" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$broken = ($results | Where-Object { $_.Status -eq "❌" }).Count
$warnings = ($results | Where-Object { $_.Status -eq "⚠️" }).Count
$ok = ($results | Where-Object { $_.Status -eq "✅" }).Count

if ($broken -gt 0) {
    Write-Host "❌ ARCHITECTURE BROKEN" -ForegroundColor Red
    Write-Host "   Found $broken critical issues" -ForegroundColor Red
} elseif ($warnings -gt 0) {
    Write-Host "⚠️  ACCEPTABLE BUT SUBOPTIMAL" -ForegroundColor Yellow
    Write-Host "   Found $warnings warnings" -ForegroundColor Yellow
} else {
    Write-Host "✅ ARCHITECTURE IDEAL" -ForegroundColor Green
    Write-Host "   All checks passed" -ForegroundColor Green
}

# Export results
$results | Export-Csv -Path "_scratchpad/architecture-diagnostic-results.csv" -NoTypeInformation -Encoding UTF8
$rttResults | Export-Csv -Path "_scratchpad/rtt-results.csv" -NoTypeInformation -Encoding UTF8

Write-Host "`nResults exported to:" -ForegroundColor Cyan
Write-Host "  - _scratchpad/architecture-diagnostic-results.csv" -ForegroundColor Gray
Write-Host "  - _scratchpad/rtt-results.csv" -ForegroundColor Gray

