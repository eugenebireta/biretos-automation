<#
Initialize-Session.ps1
Загружает краткий контекст проекта Biretos Automation при старте сессии.
Этот файл не должен требовать прав администратора.
#>

Write-Host "=== Biretos Automation — Session Initialize ===" -ForegroundColor Cyan
Write-Host "Project Path: $PSScriptRoot" -ForegroundColor DarkCyan
Write-Host ""

# 1. Последние три записи из AI_ISSUES_LOG.md
$issuesPath = Join-Path $PSScriptRoot "..\..\ai_engineering\AI_ISSUES_LOG.md"
if (Test-Path $issuesPath) {
    Write-Host "Recent AI Issues:" -ForegroundColor Yellow
    Get-Content $issuesPath | Select-Object -Last 12
    Write-Host ""
}

# 2. Архитектурный фокус
$archPath = Join-Path $PSScriptRoot "..\..\ai_engineering\ARCHITECTURE_GUIDE.md"
if (Test-Path $archPath) {
    Write-Host "Architecture Focus:" -ForegroundColor Yellow
    Get-Content $archPath | Select-Object -First 10
    Write-Host ""
}

# 3. Инфраструктурные проверки (базовые)
Write-Host "Infrastructure Status:" -ForegroundColor Yellow

# Проверка VPS доступности (пинг 216.9.227.124 как пример)
$ping = Test-Connection -Count 1 -Quiet 216.9.227.124
Write-Host ("- VPS: " + ($(if ($ping) { "Online" } else { "Offline" })))

# Проверка доступности n8n
try {
    $n8n = Invoke-WebRequest -Uri "http://localhost:5678" -TimeoutSec 2 -UseBasicParsing
    Write-Host "- n8n: Online"
}
catch {
    Write-Host "- n8n: Offline"
}

Write-Host ""

# 4. Статус проекта
$statusPath = Join-Path $PSScriptRoot "..\..\PROJECT_STATUS.md"
if (Test-Path $statusPath) {
    Write-Host "Project Status Summary:" -ForegroundColor Yellow
    Get-Content $statusPath | Select-Object -First 15
}

Write-Host ""
Write-Host "=== Session Ready ===" -ForegroundColor Green













