$conn = Get-NetTCPConnection -LocalPort 10808 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    Write-Host "Port 10808 is listening"
    $proc = $conn | Select-Object -ExpandProperty OwningProcess -First 1
    if ($proc) {
        $process = Get-Process -Id $proc -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "Process: $($process.Name)"
            Write-Host "Path: $($process.Path)"
        }
    }
} else {
    Write-Host "Port 10808 is not listening"
}








