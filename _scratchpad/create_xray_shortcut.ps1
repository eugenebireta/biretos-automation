$shell = New-Object -ComObject WScript.Shell
$shortcutPath = 'C:\Users\Eugene\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\Xray.lnk'
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = 'C:\Users\Eugene\xray\xray_no_window.vbs'
$shortcut.WorkingDirectory = 'C:\Users\Eugene\xray'
$shortcut.IconLocation = 'C:\Users\Eugene\xray\xray.exe,0'
$shortcut.Save()









