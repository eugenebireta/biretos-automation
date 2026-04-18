# PowerShell script to setup Windows Task Scheduler for auto-fine-tune trigger
# Run as Administrator

$TaskName = "Biretos-AutoFinetune"
$ScriptPath = "D:\BIRETOS\projects\biretos-automation\scripts\pipeline_v2\auto_pipeline_hook.py"
$PythonPath = "C:\Users\eugene\AppData\Local\Programs\Python\Python311\python.exe"

# Delete existing task if exists
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Create new task: runs daily at 3 AM + on login
$Action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument "-X utf8 `"$ScriptPath`"" `
    -WorkingDirectory "D:\BIRETOS\projects\biretos-automation"

$Trigger1 = New-ScheduledTaskTrigger -Daily -At 3am
$Trigger2 = New-ScheduledTaskTrigger -AtLogOn

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger @($Trigger1, $Trigger2) `
    -Settings $Settings `
    -Description "Auto-rebuild training data + trigger fine-tune when thresholds hit" `
    -RunLevel Highest

Write-Host "Task registered: $TaskName"
Write-Host "Runs: daily 3 AM + on every login"
Write-Host "Script: $ScriptPath"
