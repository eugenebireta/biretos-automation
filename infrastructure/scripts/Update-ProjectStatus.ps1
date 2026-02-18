<#
Update-ProjectStatus.ps1
Обновляет PROJECT_STATUS.md на основе текущей инфраструктуры и AI-логов.
#>

$root = Resolve-Path "$PSScriptRoot/../.."
$statusFile = Join-Path $root "PROJECT_STATUS.md"
$issuesFile = Join-Path $root "ai_engineering/AI_ISSUES_LOG.md"
$archFile = Join-Path $root "ai_engineering/ARCHITECTURE_GUIDE.md"

# --- 1. Проверка инфраструктуры ---

# Проверка VPS (пример: 216.9.227.124)
$VpsStatus = if (Test-Connection -Count 1 -Quiet 216.9.227.124) { "Online" } else { "Offline" }

# Проверка n8n
try {
    $n8n = Invoke-WebRequest -Uri "http://localhost:5678" -TimeoutSec 2 -UseBasicParsing
    $N8nStatus = "Online"
}
catch {
    $N8nStatus = "Offline"
}

# Shopware stub (развернется позже)
$ShopwareStatus = "Unknown"

# T-Bank API stub (проверка добавится после фикса проблемы токенов)
$TBankStatus = "Unknown"

# --- 2. Последние ошибки AI ---
$recentIssues = ""
if (Test-Path $issuesFile) {
    $recentIssues = (Get-Content $issuesFile | Select-Object -Last 12) -join "`n"
}

# --- 3. Архитектурный фокус ---
$archFocus = ""
if (Test-Path $archFile) {
    $archFocus = (Get-Content $archFile | Select-Object -First 10) -join "`n"
}

# --- 4. Сбор статуса ---

$content = @"
# 🧭 Project Status Dashboard

(Обновлено: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss"))

## 🔌 1. Инфраструктура
- VPS: $VpsStatus
- n8n: $N8nStatus
- Shopware: $ShopwareStatus
- T-Bank API: $TBankStatus

---

## 🧠 2. Последние архитектурные события
См. файл ARCHITECTURE_GUIDE.md

---

## 🐛 3. Последние ошибки AI (summary)
$recentIssues

---

## 🎯 4. Архитектурный фокус дня
$archFocus

---

## 🔧 5. Примечания
Этот файл обновляется автоматически скриптом Update-ProjectStatus.ps1.
"@

# --- 5. Запись в PROJECT_STATUS.md ---
Set-Content -Path $statusFile -Value $content -Encoding UTF8
Write-Host "PROJECT_STATUS.md обновлён."
<#
Update-ProjectStatus.ps1
Обновляет PROJECT_STATUS.md на основе текущей инфраструктуры и AI-логов.
#>

$root = Resolve-Path "$PSScriptRoot/../.."
$statusFile = Join-Path $root "PROJECT_STATUS.md"
$issuesFile = Join-Path $root "ai_engineering/AI_ISSUES_LOG.md"
$archFile = Join-Path $root "ai_engineering/ARCHITECTURE_GUIDE.md"

# --- 1. Проверка инфраструктуры ---

# Проверка VPS (пример: 216.9.227.124)
$VpsStatus = if (Test-Connection -Count 1 -Quiet 216.9.227.124) { "Online" } else { "Offline" }

# Проверка n8n
try {
    $n8n = Invoke-WebRequest -Uri "http://localhost:5678" -TimeoutSec 2 -UseBasicParsing
    $N8nStatus = "Online"
}
catch {
    $N8nStatus = "Offline"
}

# Shopware stub (развернется позже)
$ShopwareStatus = "Unknown"

# T-Bank API stub (проверка добавится после фикса проблемы токенов)
$TBankStatus = "Unknown"

# --- 2. Последние ошибки AI ---
$recentIssues = ""
if (Test-Path $issuesFile) {
    $recentIssues = (Get-Content $issuesFile | Select-Object -Last 12) -join "`n"
}

# --- 3. Архитектурный фокус ---
$archFocus = ""
if (Test-Path $archFile) {
    $archFocus = (Get-Content $archFile | Select-Object -First 10) -join "`n"
}

# --- 4. Сбор статуса ---

$content = @"
# 🧭 Project Status Dashboard

(Обновлено: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss"))

## 🔌 1. Инфраструктура
- VPS: $VpsStatus
- n8n: $N8nStatus
- Shopware: $ShopwareStatus
- T-Bank API: $TBankStatus

---

## 🧠 2. Последние архитектурные события
См. файл ARCHITECTURE_GUIDE.md

---

## 🐛 3. Последние ошибки AI (summary)
$recentIssues

---

## 🎯 4. Архитектурный фокус дня
$archFocus

---

## 🔧 5. Примечания
Этот файл обновляется автоматически скриптом Update-ProjectStatus.ps1.
"@

# --- 5. Запись в PROJECT_STATUS.md ---
Set-Content -Path $statusFile -Value $content -Encoding UTF8
Write-Host "PROJECT_STATUS.md обновлён."


