<#
active_context_loader.ps1
Собирает минимальный, безопасный и контролируемый контекст проекта
для использования AI (Cursor Ask/Plan).
#>

$root = Resolve-Path "$PSScriptRoot/../.."

function Read-FileSafe($path, $lines = $null) {
    if (Test-Path $path) {
        if ($lines -ne $null) {
            return (Get-Content $path | Select-Object -First $lines) -join "`n"
        } else {
            return (Get-Content $path -Raw)
        }
    }
    return "<not found>"
}

Write-Output "=== ACTIVE PROJECT CONTEXT ==="

Write-Output "`n--- AUTO CONTEXT TEMPLATE ---"
Write-Output (Read-FileSafe (Join-Path $root "ai_engineering/auto_context_template.txt"))

Write-Output "`n--- PROJECT STATUS (SUMMARY) ---"
Write-Output (Read-FileSafe (Join-Path $root "PROJECT_STATUS.md") 20)

Write-Output "`n--- RECENT AI ISSUES ---"
Write-Output (Read-FileSafe (Join-Path $root "ai_engineering/AI_ISSUES_LOG.md") 20)

Write-Output "`n--- ARCHITECTURE GUIDE (INTRO) ---"
Write-Output (Read-FileSafe (Join-Path $root "ai_engineering/ARCHITECTURE_GUIDE.md") 25)

Write-Output "`n--- CONTEXT RULES ---"
Write-Output (Read-FileSafe (Join-Path $root "ai_engineering/CONTEXT_RULES.md"))

Write-Output "`n=== END OF CONTEXT ==="












