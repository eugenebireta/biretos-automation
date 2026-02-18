<# 
    Safe-PythonExec.ps1
    --------------------
    Безопасная обёртка для запуска Python-скриптов через PowerShell.
    Цели:
      * автоматически сохранять многострочный код в C:\cursor_project\biretos-automation\_scratchpad;
      * избегать inline-вызовов `python -c`;
      * логировать каждую попытку и результат;
      * обеспечивать таймаут и аккуратное завершение процесса;
      * повторно воспроизводить stdout/stderr в консоль для удобства отладки.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false, Position = 0)]
    [string]$Code,

    [Parameter(Mandatory = $false)]
    [string]$ScriptPath,

    [Parameter()]
    [string[]]$Arguments = @(),

[Parameter()]
[string]$PythonExecutable,

    [Parameter()]
    [int]$TimeoutSeconds = 600,

    [Parameter()]
    [string]$ScratchpadDirectory = (Join-Path -Path (Get-Location).Path -ChildPath "_scratchpad"),

    [Parameter()]
    [string]$LogFile = (Join-Path -Path (Get-Location).Path -ChildPath "_scratchpad\\safe_python_exec.log"),

    [switch]$AutoCleanup,
    [switch]$Silent
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-LogLine {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fffK"
    $line = "[${timestamp}] $Message"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Ensure-Directory {
    param([string]$PathValue)
    if (-not (Test-Path -LiteralPath $PathValue)) {
        New-Item -ItemType Directory -Path $PathValue -Force | Out-Null
    }
}

function Resolve-AbsolutePath {
    param([string]$InputPath)
    if (-not $InputPath) {
        return $null
    }
    if ([System.IO.Path]::IsPathRooted($InputPath)) {
        return (Resolve-Path -LiteralPath $InputPath).Path
    }
    return (Resolve-Path -LiteralPath (Join-Path -Path (Get-Location).Path -ChildPath $InputPath)).Path
}

if ([string]::IsNullOrWhiteSpace($Code) -and [string]::IsNullOrWhiteSpace($ScriptPath)) {
    throw "Нужно передать либо -Code, либо -ScriptPath."
}

if (-not [string]::IsNullOrWhiteSpace($Code) -and -not [string]::IsNullOrWhiteSpace($ScriptPath)) {
    throw "Нельзя одновременно указывать -Code и -ScriptPath."
}

Ensure-Directory -PathValue $ScratchpadDirectory
Ensure-Directory -PathValue (Split-Path -Path $LogFile -Parent)

function Find-InPath {
    param([string]$Name)
    try {
        $cmd = Get-Command -Name $Name -ErrorAction Stop
        return $cmd.Path
    } catch {
        return $null
    }
}

function Resolve-PythonExecutable {
    param([string]$Requested)

    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($Requested)) {
        if (Test-Path -LiteralPath $Requested) {
            return (Resolve-AbsolutePath -InputPath $Requested)
        }
        $candidates += $Requested
    }

    $candidates += @("python", "python3", "python.exe", "python3.exe", "py", "py.exe")

    foreach ($candidate in $candidates) {
        $found = Find-InPath -Name $candidate
        if ($found) {
            return $found
        }
    }

    $searchRoots = @(
        "$env:LOCALAPPDATA\\Programs\\Python",
        "$env:LOCALAPPDATA\\Microsoft\\WindowsApps",
        "$env:ProgramFiles\\Python",
        "$env:ProgramFiles\\Python312",
        "$env:ProgramFiles\\Python311",
        "$env:ProgramFiles\\Python310",
        "$env:ProgramFiles(x86)\\Python",
        "C:\\Python312",
        "C:\\Python311",
        "C:\\Python310"
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    foreach ($root in $searchRoots) {
        $exe = Get-ChildItem -LiteralPath $root -Filter python.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($exe) {
            return $exe.FullName
        }
    }

    throw "Не удалось найти python. Укажите путь явно через -PythonExecutable."
}

$scriptToRun = $null
$generated = $false

if (-not [string]::IsNullOrWhiteSpace($Code)) {
    $fileName = "safe_pyexec_{0:yyyyMMdd_HHmmssfff}_{1}.py" -f (Get-Date), (Get-Random -Maximum 1000000)
    $scriptToRun = Join-Path -Path $ScratchpadDirectory -ChildPath $fileName
    Set-Content -Path $scriptToRun -Value $Code -Encoding UTF8
    $generated = $true
} else {
    $resolvedSource = Resolve-AbsolutePath -InputPath $ScriptPath
    if (-not (Test-Path -LiteralPath $resolvedSource)) {
        throw "Скрипт $resolvedSource не найден."
    }

    $scratchpadRoot = (Resolve-AbsolutePath -InputPath $ScratchpadDirectory)
    if (-not $resolvedSource.StartsWith($scratchpadRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        $fileName = "safe_pyexec_copy_{0:yyyyMMdd_HHmmssfff}_{1}.py" -f (Get-Date), (Get-Random -Maximum 1000000)
        $scriptToRun = Join-Path -Path $scratchpadRoot -ChildPath $fileName
        Copy-Item -LiteralPath $resolvedSource -Destination $scriptToRun -Force
    } else {
        $scriptToRun = $resolvedSource
    }
}

function Build-ArgumentString {
    param(
        [string]$Script,
        [string[]]$Args
    )

    function Quote-Arg {
        param([string]$Value)
        if ($null -eq $Value) { return '""' }
        if ($Value -notmatch '[\s"`]') {
            return $Value
        }
        '"' + ($Value -replace '"', '""') + '"'
    }

    $argString = Quote-Arg -Value $Script
    foreach ($item in $Args) {
        $argString += " " + (Quote-Arg -Value $item)
    }
    return $argString
}

$resolvedPython = Resolve-PythonExecutable -Requested $PythonExecutable

$processInfo = New-Object System.Diagnostics.ProcessStartInfo
$processInfo.FileName = $resolvedPython
$processInfo.Arguments = Build-ArgumentString -Script $scriptToRun -Args $Arguments
$processInfo.RedirectStandardOutput = $true
$processInfo.RedirectStandardError = $true
$processInfo.UseShellExecute = $false
$processInfo.CreateNoWindow = $true

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $processInfo

$logHeader = @(
    "=== Safe-PythonExec ===",
    "Script   : $scriptToRun",
    "Python   : $resolvedPython",
    "Arguments: $($Arguments -join ', ')",
    "Timeout  : $TimeoutSeconds s",
    "Started  : $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss.fffK')"
)
foreach ($entry in $logHeader) {
    Write-LogLine -Message $entry
}

$startTime = Get-Date
$process.Start() | Out-Null

if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    try { $process.Kill() | Out-Null } catch {}
    Write-LogLine -Message "Status   : TIMEOUT"
    if (-not $Silent) {
        Write-Error "Safe-PythonExec: превышен таймаут $TimeoutSeconds секунд."
    }
    if ($generated -and $AutoCleanup) {
        Remove-Item -LiteralPath $scriptToRun -Force -ErrorAction SilentlyContinue
    }
    throw "Выполнение Python превысило лимит $TimeoutSeconds секунд."
}

$stdout = $process.StandardOutput.ReadToEnd()
$stderr = $process.StandardError.ReadToEnd()
$exitCode = $process.ExitCode
$duration = (Get-Date) - $startTime

Write-LogLine -Message ("Finished : {0:yyyy-MM-ddTHH:mm:ss.fffK}" -f (Get-Date))
Write-LogLine -Message ("Duration : {0} ms" -f [int]$duration.TotalMilliseconds)
Write-LogLine -Message ("ExitCode : $exitCode")

function Truncate-ForLog {
    param([string]$Text, [int]$MaxLength = 4000)
    if (-not $Text) { return "" }
    if ($Text.Length -le $MaxLength) { return $Text }
    return $Text.Substring(0, $MaxLength) + "...(truncated)"
}

Write-LogLine -Message "STDOUT >>>"
if ($stdout) {
    foreach ($line in (Truncate-ForLog -Text $stdout).Split([Environment]::NewLine)) {
        Write-LogLine -Message $line
    }
}
Write-LogLine -Message "STDERR >>>"
if ($stderr) {
    foreach ($line in (Truncate-ForLog -Text $stderr).Split([Environment]::NewLine)) {
        Write-LogLine -Message $line
    }
}
Write-LogLine -Message "=== End Safe-PythonExec ===`n"

if (-not $Silent) {
    if ($stdout) {
        Write-Output $stdout
    }
    if ($stderr) {
        Write-Error $stderr
    }
}

if ($generated -and $AutoCleanup) {
    Remove-Item -LiteralPath $scriptToRun -Force -ErrorAction SilentlyContinue
}

if ($exitCode -ne 0) {
    throw "Python завершился с кодом $exitCode. См. лог $LogFile."
}

