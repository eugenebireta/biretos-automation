# Part A: Local PC (Windows) - Disable WireGuard and Xray

$ErrorActionPreference = 'Continue'
$results = @()

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  PART A: LOCAL PC (Windows)" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 1. Check Xray
Write-Host "1. Checking Xray..." -ForegroundColor Yellow
$xrayProcess = Get-Process -Name "xray" -ErrorAction SilentlyContinue
$port10808 = Get-NetTCPConnection -LocalPort 10808 -State Listen -ErrorAction SilentlyContinue

if ($xrayProcess -or $port10808) {
    Write-Host "   Xray is running" -ForegroundColor Yellow
    try {
        if ($xrayProcess) {
            Write-Host "   Stopping Xray process..." -ForegroundColor Gray
            Stop-Process -Name "xray" -Force -ErrorAction Stop
            Start-Sleep -Seconds 2
        }
        $final = Get-Process -Name "xray" -ErrorAction SilentlyContinue
        $finalPort = Get-NetTCPConnection -LocalPort 10808 -State Listen -ErrorAction SilentlyContinue
        if (-not $final -and -not $finalPort) {
            Write-Host "   ✅ Xray stopped" -ForegroundColor Green
            $results += [PSCustomObject]@{Component="Xray"; Location="Local PC"; Status="Stopped"; Notes="Process terminated"}
        } else {
            Write-Host "   ⚠️  Xray may still be running" -ForegroundColor Yellow
            $results += [PSCustomObject]@{Component="Xray"; Location="Local PC"; Status="Warning"; Notes="May still be active"}
        }
    } catch {
        Write-Host "   ❌ Error: $_" -ForegroundColor Red
        $results += [PSCustomObject]@{Component="Xray"; Location="Local PC"; Status="Error"; Notes="Failed: $_"}
    }
} else {
    Write-Host "   ✅ Xray not running" -ForegroundColor Green
    $results += [PSCustomObject]@{Component="Xray"; Location="Local PC"; Status="Not Running"; Notes="Already stopped"}
}

# 2. Check WireGuard service
Write-Host "`n2. Checking WireGuard service..." -ForegroundColor Yellow
$wgService = Get-Service -Name "WireGuardTunnel*" -ErrorAction SilentlyContinue
if ($wgService) {
    foreach ($svc in $wgService) {
        Write-Host "   Found: $($svc.Name) (Status: $($svc.Status))" -ForegroundColor Gray
        if ($svc.Status -eq 'Running') {
            try {
                Stop-Service -Name $svc.Name -Force -ErrorAction Stop
                Start-Sleep -Seconds 2
                Write-Host "   ✅ Stopped" -ForegroundColor Green
                $results += [PSCustomObject]@{Component="WireGuard"; Location="Local PC"; Status="Stopped"; Notes="Service: $($svc.Name)"}
            } catch {
                Write-Host "   ❌ Error stopping: $_" -ForegroundColor Red
            }
        } else {
            Write-Host "   ✅ Already stopped" -ForegroundColor Green
        }
        # Disable autostart
        try {
            Set-Service -Name $svc.Name -StartupType Disabled -ErrorAction Stop
            Write-Host "   ✅ Autostart disabled" -ForegroundColor Green
        } catch {
            Write-Host "   ⚠️  Could not disable autostart: $_" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "   ✅ No WireGuard service found" -ForegroundColor Green
    $results += [PSCustomObject]@{Component="WireGuard"; Location="Local PC"; Status="Not Found"; Notes="No service installed"}
}

# 3. Check autostart
Write-Host "`n3. Checking autostart..." -ForegroundColor Yellow
$startupPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
if (Test-Path $startupPath) {
    $startupItems = Get-ChildItem -Path $startupPath -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*xray*" -or $_.Name -like "*wireguard*" }
    if ($startupItems) {
        foreach ($item in $startupItems) {
            $disabled = $item.FullName + ".disabled"
            if (-not (Test-Path $disabled)) {
                try {
                    Rename-Item -Path $item.FullName -NewName ($item.Name + ".disabled") -ErrorAction Stop
                    Write-Host "   ✅ Disabled: $($item.Name)" -ForegroundColor Green
                    $results += [PSCustomObject]@{Component="Autostart: $($item.Name)"; Location="Local PC"; Status="Disabled"; Notes="Renamed to .disabled"}
                } catch {
                    Write-Host "   ⚠️  Could not disable: $_" -ForegroundColor Yellow
                }
            } else {
                Write-Host "   Already disabled: $($item.Name)" -ForegroundColor Gray
            }
        }
    } else {
        Write-Host "   ✅ No autostart items found" -ForegroundColor Green
    }
} else {
    Write-Host "   Startup folder not found" -ForegroundColor Gray
}

# 4. Check scheduled tasks
Write-Host "`n4. Checking scheduled tasks..." -ForegroundColor Yellow
$tasks = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { 
    $_.TaskName -like "*xray*" -or $_.TaskName -like "*wireguard*" 
}
if ($tasks) {
    foreach ($task in $tasks) {
        Write-Host "   Found: $($task.TaskName)" -ForegroundColor Gray
        try {
            Disable-ScheduledTask -TaskName $task.TaskName -ErrorAction Stop
            Write-Host "   ✅ Disabled" -ForegroundColor Green
            $results += [PSCustomObject]@{Component="Scheduled Task: $($task.TaskName)"; Location="Local PC"; Status="Disabled"; Notes="Task disabled"}
        } catch {
            Write-Host "   ⚠️  Could not disable: $_" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "   ✅ No scheduled tasks found" -ForegroundColor Green
}

# 5. Final verification
Write-Host "`n5. Final verification..." -ForegroundColor Yellow
$finalXray = Get-Process -Name "xray" -ErrorAction SilentlyContinue
$finalPort = Get-NetTCPConnection -LocalPort 10808 -State Listen -ErrorAction SilentlyContinue
$finalWG = Get-Service -Name "WireGuardTunnel*" -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Running' }

Write-Host "   Xray process: $(if ($finalXray) { '❌ Running' } else { '✅ Stopped' })" -ForegroundColor $(if ($finalXray) { 'Red' } else { 'Green' })
Write-Host "   Port 10808: $(if ($finalPort) { '❌ Listening' } else { '✅ Free' })" -ForegroundColor $(if ($finalPort) { 'Red' } else { 'Green' })
Write-Host "   WireGuard service: $(if ($finalWG) { '❌ Running' } else { '✅ Stopped' })" -ForegroundColor $(if ($finalWG) { 'Red' } else { 'Green' })

if (-not $finalXray -and -not $finalPort -and -not $finalWG) {
    Write-Host "`n   ✅ All components stopped" -ForegroundColor Green
} else {
    Write-Host "`n   ⚠️  Some components may still be active" -ForegroundColor Yellow
}

Write-Host "`n=== PART A COMPLETE ===" -ForegroundColor Cyan

# Export results
$results | Export-Csv -Path "_scratchpad/local-pc-disable-results.csv" -NoTypeInformation -Encoding UTF8
$results | Format-Table -AutoSize

return $results








