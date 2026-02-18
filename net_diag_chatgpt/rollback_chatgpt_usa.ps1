<#
.SYNOPSIS
    Откатывает ChatGPT USA Route: восстанавливает backup конфигов и останавливает X-Ray (если был запущен через enable).
.DESCRIPTION
    Скрипт восстанавливает backup конфигов из директории backup/,
    останавливает X-Ray процесс (если был запущен через enable_chatgpt_usa.ps1),
    и очищает временные файлы.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$baseDir = Resolve-Path $scriptDir

# Пути
$runtimeDir = Join-Path $baseDir ".runtime"
$backupDir = Join-Path $baseDir "backup"
$markerFile = Join-Path $runtimeDir "started_by_enable.txt"

Write-Host "=== Rolling back ChatGPT USA Route ===" -ForegroundColor Cyan

# Проверяем, был ли X-Ray запущен через enable
$xrayWasStarted = $false
if (Test-Path $markerFile) {
    $xrayWasStarted = $true
    $startTime = Get-Content $markerFile
    Write-Host "X-Ray was started by enable script at: $startTime" -ForegroundColor Gray
}

# Останавливаем X-Ray (если был запущен)
if ($xrayWasStarted) {
    Write-Host "`nStopping X-Ray..." -ForegroundColor Cyan
    
    $xrayProcesses = Get-Process -Name "xray" -ErrorAction SilentlyContinue
    if ($xrayProcesses) {
        foreach ($proc in $xrayProcesses) {
            Write-Host "Stopping X-Ray process (PID: $($proc.Id))..." -ForegroundColor Gray
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 2
        
        # Проверяем, что процесс остановлен
        $stillRunning = Get-Process -Name "xray" -ErrorAction SilentlyContinue
        if ($stillRunning) {
            Write-Host "WARNING: Some X-Ray processes may still be running." -ForegroundColor Yellow
        } else {
            Write-Host "X-Ray stopped successfully." -ForegroundColor Green
        }
    } else {
        Write-Host "X-Ray process not found (may have been stopped already)." -ForegroundColor Gray
    }
    
    # Удаляем marker файл
    Remove-Item $markerFile -Force -ErrorAction SilentlyContinue
}

# Восстанавливаем backup конфигов
if (Test-Path $backupDir) {
    $backupDirs = Get-ChildItem -Path $backupDir -Directory | Sort-Object LastWriteTime -Descending
    
    if ($backupDirs) {
        $latestBackup = $backupDirs[0]
        Write-Host "`nRestoring configs from backup: $($latestBackup.Name)" -ForegroundColor Cyan
        
        $backupConfigs = Get-ChildItem -Path $latestBackup.FullName -Filter "xray-*.json"
        
        if ($backupConfigs) {
            foreach ($config in $backupConfigs) {
                $targetPath = Join-Path $runtimeDir $config.Name
                Copy-Item $config.FullName -Destination $targetPath -Force
                Write-Host "Restored: $($config.Name)" -ForegroundColor Green
            }
        } else {
            Write-Host "No configs found in backup directory." -ForegroundColor Yellow
        }
    } else {
        Write-Host "No backup directories found." -ForegroundColor Yellow
    }
} else {
    Write-Host "Backup directory not found. Nothing to restore." -ForegroundColor Yellow
}

# Очищаем временные файлы (опционально, можно закомментировать для сохранения логов)
Write-Host "`nCleaning up temporary files..." -ForegroundColor Cyan

# Удаляем только marker файл, конфиги оставляем (могут быть нужны)
# Если нужно полностью очистить .runtime, раскомментируйте:
# if (Test-Path $runtimeDir) {
#     Remove-Item $runtimeDir -Recurse -Force -ErrorAction SilentlyContinue
#     Write-Host "Cleaned .runtime directory." -ForegroundColor Green
# }

Write-Host "`n=== Rollback Complete ===" -ForegroundColor Green
Write-Host "Status: SUCCESS" -ForegroundColor Green
