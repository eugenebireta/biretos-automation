Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$pythonHome = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312'
$scriptsPath = Join-Path $pythonHome 'Scripts'

if (-not (Test-Path $pythonHome)) {
    throw "Python directory not found: $pythonHome"
}

$pathsToEnsure = @($pythonHome, $scriptsPath)

$currentUserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$currentMachinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')

$updatedUserPath = $currentUserPath
foreach ($path in $pathsToEnsure) {
    if (-not [string]::IsNullOrWhiteSpace($path) -and ($updatedUserPath -notmatch [regex]::Escape($path))) {
        if ([string]::IsNullOrWhiteSpace($updatedUserPath)) {
            $updatedUserPath = $path
        } else {
            $updatedUserPath = "$path;$updatedUserPath"
        }
    }
}

if ($updatedUserPath -ne $currentUserPath) {
    [Environment]::SetEnvironmentVariable('Path', $updatedUserPath, 'User')
    Write-Output "User PATH updated."
} else {
    Write-Output "User PATH already contains required entries."
}

# Update current session as well
$env:Path = "$pythonHome;$scriptsPath;" + $env:Path
Write-Output "Current session PATH updated."









