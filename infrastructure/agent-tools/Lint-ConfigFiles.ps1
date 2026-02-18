Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$workspaceRoot = Resolve-Path "$PSScriptRoot/../.."
$infraDir = Join-Path $workspaceRoot 'infrastructure'

if (-not (Test-Path $infraDir)) {
    throw "Infrastructure directory not found: $infraDir"
}

$errors = @()

$pythonExe = 'python'
$envConfigPath = Join-Path $workspaceRoot 'infrastructure/config/env_config.json'
if (Test-Path $envConfigPath) {
    try {
        $envConfig = Get-Content $envConfigPath -Raw | ConvertFrom-Json
        if ($envConfig.python.system_path) {
            $pythonExe = $envConfig.python.system_path
        }
    } catch {
        $errors += [pscustomobject]@{
            File = $envConfigPath
            Issue = "Failed to parse env_config.json: $($_.Exception.Message)"
        }
    }
}

# Validate JSON files
$jsonFiles = Get-ChildItem -Path $infraDir -Filter *.json -File -Recurse
foreach ($file in $jsonFiles) {
    try {
        & $pythonExe -m json.tool $file.FullName | Out-Null
    } catch {
        $errors += [pscustomobject]@{
            File = $file.FullName
            Issue = "Invalid JSON structure: $($_.Exception.Message)"
        }
    }
}

# Validate WireGuard/CONF files
$confFiles = Get-ChildItem -Path $infraDir -Filter *.conf -File -Recurse
foreach ($file in $confFiles) {
    $bytes = Get-Content -Path $file.FullName -Encoding Byte
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $errors += [pscustomobject]@{
            File = $file.FullName
            Issue = "Contains UTF-8 BOM"
        }
    }

    for ($i = 0; $i -lt $bytes.Length - 1; $i++) {
        if ($bytes[$i] -eq 13 -and $bytes[$i + 1] -eq 10) {
            $errors += [pscustomobject]@{
                File = $file.FullName
                Issue = "Contains CRLF line endings (must be LF)."
            }
            break
        }
    }
}

if ($errors.Count -eq 0) {
    Write-Output "OK: All configuration files passed validation."
    exit 0
}

Write-Warning "Configuration validation failed:"
$errors | Sort-Object File -Unique | Format-Table -AutoSize
exit 1

