<#
.SYNOPSIS
    Включает ChatGPT USA Route: подготавливает конфиги X-Ray и выводит инструкции.
.DESCRIPTION
    Скрипт создает backup текущих конфигов, рендерит новые конфиги из шаблонов,
    но НЕ запускает X-Ray автоматически (только подготовка).
    Для запуска X-Ray используйте infrastructure/safe-run/Start-Xray.ps1 вручную.
#>

param(
    [switch]$AutoStartXray = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$baseDir = Resolve-Path $scriptDir

# Пути
$runtimeDir = Join-Path $baseDir ".runtime"
$backupDir = Join-Path $baseDir "backup"
$envFile = Join-Path $baseDir ".env"

# Проверяем наличие .env
if (-not (Test-Path $envFile)) {
    Write-Host "ERROR: .env file not found at $envFile" -ForegroundColor Red
    Write-Host "Please copy .env.example to .env and fill in the values." -ForegroundColor Yellow
    exit 1
}

# Создаем директории
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

# Делаем backup существующих конфигов (если есть)
$existingConfigs = Get-ChildItem -Path $runtimeDir -Filter "xray-*.json" -ErrorAction SilentlyContinue
if ($existingConfigs) {
    $backupTimestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $timestampBackupDir = Join-Path $backupDir $backupTimestamp
    New-Item -ItemType Directory -Path $timestampBackupDir -Force | Out-Null
    
    foreach ($config in $existingConfigs) {
        Copy-Item $config.FullName -Destination (Join-Path $timestampBackupDir $config.Name)
        Write-Host "Backed up: $($config.Name)" -ForegroundColor Gray
    }
    
    Write-Host "Backup created at: $timestampBackupDir" -ForegroundColor Green
}

# Рендерим конфиги
Write-Host "Rendering X-Ray configs..." -ForegroundColor Cyan

$pythonCmd = "python"
try {
    $pythonVersion = & $pythonCmd --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python not found"
    }
} catch {
    # Пробуем python3
    try {
        $pythonCmd = "python3"
        $pythonVersion = & $pythonCmd --version 2>&1
    } catch {
        Write-Host "ERROR: Python not found. Please install Python 3.7+" -ForegroundColor Red
        exit 1
    }
}

$renderScript = Join-Path $baseDir "utils\xray_render.py"
$renderResult = & $pythonCmd $renderScript 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to render X-Ray configs:" -ForegroundColor Red
    Write-Host $renderResult -ForegroundColor Red
    exit 1
}

Write-Host $renderResult

# Проверяем наличие сгенерированных конфигов
$clientConfig = Join-Path $runtimeDir "xray-client-usa.json"
if (-not (Test-Path $clientConfig)) {
    Write-Host "ERROR: Generated config not found: $clientConfig" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Configuration Ready ===" -ForegroundColor Green
Write-Host "X-Ray client config: $clientConfig" -ForegroundColor Cyan
Write-Host "X-Ray server config template: $(Join-Path $runtimeDir 'xray-server-usa.json')" -ForegroundColor Cyan

# Опциональный запуск X-Ray
if ($AutoStartXray) {
    $xrayStartScript = Join-Path (Split-Path -Parent $baseDir) "infrastructure\safe-run\Start-Xray.ps1"
    
    if (Test-Path $xrayStartScript) {
        Write-Host "`nStarting X-Ray..." -ForegroundColor Cyan
        
        # Создаем marker файл
        $markerFile = Join-Path $runtimeDir "started_by_enable.txt"
        Set-Content -Path $markerFile -Value (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        
        # Запускаем X-Ray
        & $xrayStartScript -ConfigPath $clientConfig
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "X-Ray started successfully." -ForegroundColor Green
        } else {
            Write-Host "WARNING: X-Ray start may have failed. Check logs." -ForegroundColor Yellow
        }
    } else {
        Write-Host "WARNING: Start-Xray.ps1 not found at $xrayStartScript" -ForegroundColor Yellow
        Write-Host "Please start X-Ray manually with:" -ForegroundColor Yellow
        Write-Host "  xray.exe run -config `"$clientConfig`"" -ForegroundColor Gray
    }
} else {
    Write-Host "`n=== Next Steps ===" -ForegroundColor Yellow
    Write-Host "1. Start X-Ray manually:" -ForegroundColor Cyan
    Write-Host "   xray.exe run -config `"$clientConfig`"" -ForegroundColor Gray
    Write-Host "   OR use: infrastructure\safe-run\Start-Xray.ps1 -ConfigPath `"$clientConfig`"" -ForegroundColor Gray
    Write-Host "`n2. Configure browser to use SOCKS5 proxy: 127.0.0.1:10808" -ForegroundColor Cyan
    Write-Host "`n3. Run diagnostics:" -ForegroundColor Cyan
    Write-Host "   python net_diag_chatgpt\run_all.py --mode both" -ForegroundColor Gray
}

Write-Host "`n=== Status: SUCCESS ===" -ForegroundColor Green
Write-Host "Configs ready at: $runtimeDir" -ForegroundColor Gray
