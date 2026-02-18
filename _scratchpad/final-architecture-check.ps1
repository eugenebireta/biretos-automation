# Final Architecture Check After VPN Disable
# Comprehensive verification of DIRECT architecture

$ErrorActionPreference = 'Continue'
$results = @()
$rttResults = @()

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  FINAL ARCHITECTURE CHECK" -ForegroundColor Cyan
Write-Host "  (After VPN Components Disable)" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# A. LOCAL PC
Write-Host "=== A. LOCAL PC ===" -ForegroundColor Yellow

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
        Write-Host "   ❌ WARNING: Traffic goes through VPN (Switzerland)" -ForegroundColor Red
    } elseif ($externalIP -match "^$vps1Range") {
        $isVPS = $true
        Write-Host "   ❌ WARNING: Traffic goes through VPS-1 (USA)" -ForegroundColor Red
    } elseif ($externalIP -match "^$vps2Range") {
        $isVPS = $true
        Write-Host "   ❌ WARNING: Traffic goes through VPS-2 (Moscow)" -ForegroundColor Red
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

# 2. Active Proxies
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
    Write-Host "   ✅ No proxy environment variables" -ForegroundColor Green
}

# Check Cursor settings
$cursorSettings = "$env:APPDATA\Cursor\User\settings.json"
if (Test-Path $cursorSettings) {
    $settings = Get-Content $cursorSettings -Raw | ConvertFrom-Json
    if ($settings.'http.proxy') {
        Write-Host "   ⚠️  Cursor proxy: $($settings.'http.proxy')" -ForegroundColor Yellow
        $hasProxy = $true
    } else {
        Write-Host "   ✅ Cursor proxy: Not configured" -ForegroundColor Green
    }
}

# Check listening ports
Write-Host "`n3. Listening Proxy Ports:" -ForegroundColor Cyan
$proxyPorts = @(10808, 10800, 8080, 3128, 8888)
$activeProxies = @()
foreach ($port in $proxyPorts) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        Write-Host "   ⚠️  Port $port is listening" -ForegroundColor Yellow
        $activeProxies += $port
        $hasProxy = $true
    }
}
if ($activeProxies.Count -eq 0) {
    Write-Host "   ✅ No proxy ports listening" -ForegroundColor Green
}

# Check processes
Write-Host "`n4. VPN/Proxy Processes:" -ForegroundColor Cyan
$xrayProcess = Get-Process -Name "xray" -ErrorAction SilentlyContinue
$wgProcess = Get-Process -Name "wireguard" -ErrorAction SilentlyContinue
$wgService = Get-Service -Name "WireGuardTunnel*" -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Running' }

if ($xrayProcess) {
    Write-Host "   ❌ Xray process is running" -ForegroundColor Red
} else {
    Write-Host "   ✅ Xray process: Stopped" -ForegroundColor Green
}

if ($wgProcess -or $wgService) {
    Write-Host "   ❌ WireGuard is running" -ForegroundColor Red
} else {
    Write-Host "   ✅ WireGuard: Stopped" -ForegroundColor Green
}

$results += [PSCustomObject]@{
    Segment = "Local PC → Proxies"
    Expected = "No active proxies"
    Actual = if ($hasProxy) { "Proxies detected" } else { "No proxies" }
    Status = if ($hasProxy) { "❌" } else { "✅" }
}

# B. ROUTING FROM PC
Write-Host "`n=== B. ROUTING FROM LOCAL PC ===" -ForegroundColor Yellow

$testHosts = @(
    @{Name="VPS USA"; IP="216.9.227.124"},
    @{Name="VPS RU"; IP="77.233.222.214"},
    @{Name="github.com"; IP="github.com"},
    @{Name="api.openai.com"; IP="api.openai.com"}
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
        $hopCount = 0
        $hasVPNHop = $false
        foreach ($line in $tracert) {
            if ($line -match "^\s*(\d+)\s+") {
                $hopCount++
                $ipMatch = [regex]::Match($line, "\d+\.\d+\.\d+\.\d+")
                if ($ipMatch.Success) {
                    $hopIP = $ipMatch.Value
                    Write-Host "     Hop ${hopCount}: $hopIP" -ForegroundColor Gray
                    if ($hopIP -match "^(185\.|188\.|195\.)") {
                        $hasVPNHop = $true
                        Write-Host "       ⚠️  VPN hop detected" -ForegroundColor Yellow
                    }
                }
            }
        }
        
        $isDirect = -not $hasVPNHop
        $verdict = if ($avgRTT -lt 50) { "Ideal" } elseif ($avgRTT -lt 150) { "OK" } else { "Bad" }
        
        $results += [PSCustomObject]@{
            Segment = "Local PC → $($h.Name)"
            Expected = "Direct"
            Actual = if ($isDirect) { "Direct (RTT: $([math]::Round($avgRTT, 2))ms, Hops: $hopCount)" } else { "VPN routing" }
            Status = if ($isDirect) { "✅" } else { "❌" }
        }
        
        $rttResults += [PSCustomObject]@{
            Link = "Local PC → $($h.Name)"
            AvgRTT = "$([math]::Round($avgRTT, 2))ms"
            Verdict = $verdict
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
    Write-Host "   Found $broken critical issues:" -ForegroundColor Red
    $results | Where-Object { $_.Status -eq "❌" } | ForEach-Object {
        Write-Host "     - $($_.Segment): $($_.Actual)" -ForegroundColor Red
    }
} elseif ($warnings -gt 0) {
    Write-Host "⚠️  ACCEPTABLE BUT SUBOPTIMAL" -ForegroundColor Yellow
    Write-Host "   Found $warnings warnings" -ForegroundColor Yellow
} else {
    Write-Host "✅ ARCHITECTURE IDEAL" -ForegroundColor Green
    Write-Host "   All checks passed - System is in DIRECT mode" -ForegroundColor Green
}

# Export results
$results | Export-Csv -Path "_scratchpad/final-architecture-results.csv" -NoTypeInformation -Encoding UTF8
$rttResults | Export-Csv -Path "_scratchpad/final-rtt-results.csv" -NoTypeInformation -Encoding UTF8

Write-Host "`nResults exported to:" -ForegroundColor Cyan
Write-Host "  - _scratchpad/final-architecture-results.csv" -ForegroundColor Gray
Write-Host "  - _scratchpad/final-rtt-results.csv" -ForegroundColor Gray

