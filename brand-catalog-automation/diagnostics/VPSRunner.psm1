<#
.SYNOPSIS
    Reliable SSH/SCP execution on the VPS without freezes.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$script:VpsRunnerLogPath   = Join-Path $PSScriptRoot 'vps-runner.log'
$script:LastRunReportPath = Join-Path $PSScriptRoot 'LAST_RUN_REPORT.md'

function Invoke-VPSProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,
        [int]$TimeoutSeconds = 180,
        [string]$LogContext = 'external command'
    )

    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()
    $exitPath   = [System.IO.Path]::GetTempFileName()

    try {
        $cmdExe = $env:ComSpec
        if (-not $cmdExe) { $cmdExe = 'cmd.exe' }
        $commandLine = ConvertTo-VPSCommandLine -FilePath $FilePath -ArgumentList $ArgumentList
        $redirected  = "( $commandLine ) 1>`"$stdoutPath`" 2>`"$stderrPath`" & echo %ERRORLEVEL% > `"$exitPath`""

        $process = Start-Process -FilePath $cmdExe `
                                 -ArgumentList '/c', $redirected `
                                 -NoNewWindow `
                                 -PassThru

        $timeoutMs = [Math]::Max(1,$TimeoutSeconds) * 1000
        if (-not $process.WaitForExit($timeoutMs)) {
            Write-VPSLog "Process '$LogContext' timeout after ${TimeoutSeconds}s. Killing..." 'WARN'
            try {
                Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                Start-Sleep -Milliseconds 500
            } catch { }
            throw "Process '$LogContext' exceeded ${TimeoutSeconds}s timeout."
        }

        try { $process.WaitForExit(); $process.Refresh() } catch { }

        $stdout = Get-Content $stdoutPath -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content $stderrPath -Raw -ErrorAction SilentlyContinue
        $exitRaw = Get-Content $exitPath -Raw -ErrorAction SilentlyContinue

        $exitCode = -1
        if ($exitRaw -match '(-?\d+)') {
            $exitCode = [int]$Matches[1]
        }

        $stdoutLen = if ($null -ne $stdout) { $stdout.Length } else { 0 }
        $stderrLen = if ($null -ne $stderr) { $stderr.Length } else { 0 }
        Write-VPSLog "[Invoke-VPSProcess][$LogContext] exit=$exitCode stdoutLen=$stdoutLen stderrLen=$stderrLen"

        if ($exitCode -ne 0) {
            $errPreview = if ($stderr) { $stderr.Trim() } else { '<empty stderr>' }
            Write-VPSLog "Process '$LogContext' exited with $exitCode. stderr: $errPreview" 'ERROR'
        }

        return [pscustomobject]@{
            ExitCode = $exitCode
            StdOut   = $stdout
            StdErr   = $stderr
        }
    }
    finally {
        if ($process -and -not $process.HasExited) {
            try { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } catch { }
        }
        if ($process) { $process.Dispose() }
        Remove-Item $stdoutPath -ErrorAction SilentlyContinue
        Remove-Item $stderrPath -ErrorAction SilentlyContinue
        Remove-Item $exitPath -ErrorAction SilentlyContinue
    }
}

function Get-VPSBaseSshOptions {
    param(
        [int]$ConnectTimeout = 10
    )

    return @(
        '-o', 'BatchMode=yes',
        '-o', "ConnectTimeout=$ConnectTimeout",
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'ServerAliveInterval=5',
        '-o', 'ServerAliveCountMax=2'
    )
}

function ConvertTo-VPSCommandLine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList
    )

    function Quote-Part {
        param([string]$Text)
        if ($null -eq $Text -or $Text -eq '') {
            return '""'
        }
        if ($Text -match '[\s"&|<>^]') {
            return '"' + ($Text -replace '"','\"') + '"'
        }
        return $Text
    }

    $parts = @()
    $parts += Quote-Part $FilePath
    foreach ($arg in $ArgumentList) {
        $parts += Quote-Part $arg
    }
    return ($parts -join ' ')
}

function Write-VPSLog {
    param(
        [string]$Message,
        [string]$Level = 'INFO'
    )
    if (-not $Message) { return }
    $stamp = (Get-Date).ToString('u')
    $line = "[{0}] [{1}] {2}" -f $stamp, $Level.ToUpperInvariant(), $Message.Trim()
    Add-Content -Path $script:VpsRunnerLogPath -Value $line -Encoding UTF8
}

function Write-VPSReport {
    param(
        [string]$Status,
        [string[]]$Lines
    )
    $builder = [System.Text.StringBuilder]::new()
    $null = $builder.AppendLine("# VPS Command Execution Report")
    $null = $builder.AppendLine(("Date: {0}" -f (Get-Date -Format 'u')))
    $null = $builder.AppendLine(("Status: {0}" -f $Status))
    foreach ($line in $Lines) {
        $null = $builder.AppendLine($line)
    }
    Set-Content -Path $script:LastRunReportPath -Value $builder.ToString() -Encoding UTF8
}

function Invoke-VPSCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [string]$Server = 'root@216.9.227.124',
        [int]$ConnectTimeout = 10,
        [int]$Timeout = 180,
        [ValidateSet('Direct','File')]
        [string]$Method = 'Direct',
        [switch]$Quiet
    )

    $reportLines = @(
        ("Command: {0}" -f $Command),
        ("Server: {0}" -f $Server),
        ("Method: {0}" -f $Method),
        ("ConnectTimeout: {0}" -f $ConnectTimeout),
        ("Timeout: {0}" -f $Timeout)
    )

    try {
        $sshPath = (Get-Command ssh -ErrorAction Stop | Select-Object -First 1 -ExpandProperty Source)
        $scpPath = (Get-Command scp -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source)
        Write-VPSLog "Executing [$Method] on ${Server}: $Command"
        $sshBaseArgs = @(Get-VPSBaseSshOptions -ConnectTimeout $ConnectTimeout)

        switch ($Method) {
            'Direct' {
                $argList = $sshBaseArgs + @($Server, $Command)
                $result = Invoke-VPSProcess -FilePath $sshPath -ArgumentList $argList -TimeoutSeconds $Timeout -LogContext 'ssh-direct'
                if ($result.ExitCode -ne 0) {
                    throw "ssh exited with code $($result.ExitCode)`n$result.StdErr"
                }
                $combined = $result.StdOut + $result.StdErr
                if ($null -eq $combined) {
                    $output = ''
                }
                else {
                    $output = $combined.TrimEnd()
                }
            }
            'File' {
                if (-not $scpPath) { throw "scp not found in PATH" }
                $remoteOut = "/tmp/vps_out_$([System.Guid]::NewGuid().ToString('N')).txt"
                $execArgs = $sshBaseArgs + @($Server, "$Command > $remoteOut 2>&1")
                $execResult = Invoke-VPSProcess -FilePath $sshPath -ArgumentList $execArgs -TimeoutSeconds $Timeout -LogContext 'ssh-file-exec'
                if ($execResult.ExitCode -ne 0) {
                    throw "Remote execution failed (exit $($execResult.ExitCode))`n$($execResult.StdErr)"
                }
                $localOut = [System.IO.Path]::GetTempFileName()
                $scpArgs = @(Get-VPSBaseSshOptions -ConnectTimeout $ConnectTimeout) + @("$Server`:$remoteOut", $localOut)
                $scpResult = Invoke-VPSProcess -FilePath $scpPath -ArgumentList $scpArgs -TimeoutSeconds $Timeout -LogContext 'scp-download'
                if ($scpResult.ExitCode -ne 0) {
                    Remove-Item $localOut -ErrorAction SilentlyContinue
                    throw "SCP download failed (exit $($scpResult.ExitCode))`n$($scpResult.StdErr)"
                }
                $output = Get-Content $localOut -Raw -ErrorAction SilentlyContinue
                Remove-Item $localOut -ErrorAction SilentlyContinue
                $cleanupArgs = $sshBaseArgs + @($Server, "rm -f $remoteOut")
                Invoke-VPSProcess -FilePath $sshPath -ArgumentList $cleanupArgs -TimeoutSeconds 30 -LogContext 'ssh-cleanup' | Out-Null
            }
        }

        if (-not $Quiet -and $output) {
            Write-Host $output
        }

        $outputForPreview = $output
        if (-not $outputForPreview) { $outputForPreview = '(empty output)' }
        $preview = if ($outputForPreview.Length -gt 1000) { $outputForPreview.Substring(0,1000) + '...' } else { $outputForPreview }
        Write-VPSReport -Status 'SUCCESS' -Lines ($reportLines + @("Output preview:", $preview))
        Write-VPSLog "Command completed successfully."

        return [pscustomobject]@{
            ExitCode = 0
            Output   = $output
            Error    = ''
        }
    }
    catch {
        $message = $_.Exception.Message
        Write-VPSLog "Command failed: $message" 'ERROR'
        Write-VPSReport -Status 'FAILED' -Lines ($reportLines + @("Error: $message"))
        throw
    }
}

function Invoke-VPSScript {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$LocalScriptPath,
        [string]$Server = 'root@216.9.227.124',
        [string]$RemotePath = '/root/temp_vps_script.sh',
        [int]$ConnectTimeout = 10,
        [int]$Timeout = 300,
        [switch]$KeepRemoteScript,
        [ValidateSet('Direct','File','Job')]
        [string]$Method = 'Direct'
    )

    if (-not (Test-Path $LocalScriptPath)) {
        throw "Local script '$LocalScriptPath' not found."
    }

    $scpPath = (Get-Command scp -ErrorAction Stop | Select-Object -First 1 -ExpandProperty Source)
    Write-VPSLog "Uploading $LocalScriptPath to ${Server}:$RemotePath"
    $uploadArgs = @(Get-VPSBaseSshOptions -ConnectTimeout $ConnectTimeout) + @($LocalScriptPath, "$Server`:$RemotePath")
    $uploadResult = Invoke-VPSProcess -FilePath $scpPath -ArgumentList $uploadArgs -TimeoutSeconds $Timeout -LogContext 'scp-upload'
    if ($uploadResult.ExitCode -ne 0) {
        throw "SCP upload failed (exit $($uploadResult.ExitCode))`n$($uploadResult.StdErr)"
    }

    Invoke-VPSCommand -Command "chmod +x $RemotePath" -Server $Server -ConnectTimeout $ConnectTimeout -Timeout 30 -Method 'Direct' -Quiet
    $result = Invoke-VPSCommand -Command "bash $RemotePath" -Server $Server -ConnectTimeout $ConnectTimeout -Timeout $Timeout -Method $Method

    if (-not $KeepRemoteScript) {
        Invoke-VPSCommand -Command "rm -f $RemotePath" -Server $Server -ConnectTimeout $ConnectTimeout -Timeout 30 -Method 'Direct' -Quiet
    }

    return $result
}

Export-ModuleMember -Function Invoke-VPSCommand, Invoke-VPSScript

