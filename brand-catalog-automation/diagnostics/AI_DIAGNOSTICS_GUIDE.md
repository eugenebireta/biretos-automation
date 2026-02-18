# AI Diagnostics Guide: PowerShell SSH/SCP Deadlock

## Проблема

PowerShell зависает при запуске `ssh`/`scp`, когда вывод перенаправляется через стандартные pipe-буферы.

### Почему так происходит

1. `Start-Process -RedirectStandardOutput/-RedirectStandardError` создаёт pipe-буфер всего ~4 КБ.
2. SSH/SCP пишут много текста (статусы, JSON, ошибки). Буфер быстро заполняется.
3. Когда буфер заполнен, процесс блокируется, ожидая пока кто-то прочитает данные.
4. PowerShell в это время вызвал `Wait-Process` или `WaitForExit` и ждёт завершения процесса.
5. Получается deadlock: **процесс ждёт PowerShell, PowerShell ждёт процесс**.

### Симптомы

- Команда висит без вывода.
- Даже таймауты PowerShell не помогают.
- В диспетчере задач остаются `ssh.exe`/`scp.exe`.

## Решение

### Файловый вывод вместо pipe

```
Процесс → временный файл → чтение файла после завершения
```

Файл на диске не имеет ограничения на размер буфера, поэтому процессы никогда не блокируются при выводе.

### Реализация (модуль `VPSRunner.psm1`)

1. `Invoke-VPSProcess`
   - Запускает процесс через `Start-Process` с `-PassThru`.
   - Перенаправляет stdout/stderr в файлы (`[IO.Path]::GetTempFileName()`).
   - Ждёт процесс через `Wait-Process -Timeout`.
   - Если сработал таймаут — пишет в лог и делает `Stop-Process -Force`.
   - После завершения читает файлы и возвращает вывод.
   - Всегда очищает временные файлы в `finally`.

2. `Invoke-VPSCommand`
   - Оставлены только методы `Direct` и `File`.
   - Метод `Job` удалён как ненадёжный (он снова использовал pipe и WaitForExit).

3. `Invoke-VPSScript`
   - Загружает скрипт на VPS через SCP, запускает через SSH, удаляет после выполнения.

## Как пользоваться

```powershell
Import-Module .\brand-catalog-automation\diagnostics\VPSRunner.psm1

# Выполнить команду
Invoke-VPSCommand -Command "echo hello" -Server "root@216.9.227.124" -Timeout 30

# Запустить скрипт
Invoke-VPSScript -LocalScriptPath ".\diagnostics\test_tbank_api.sh" -Timeout 180
```

## Что НЕ делать

- ❌ `BeginOutputReadLine` / `OutputDataReceived`
- ❌ `2>&1 | Out-String` для нативных процессов
- ❌ `WaitForExit()` без таймаута
- ❌ PowerShell Jobs для длительных SSH команд

## Как тестировать

1. `.\brand-catalog-automation\diagnostics\Test-TBankAPI.ps1`
2. Проверить `brand-catalog-automation/diagnostics/vps-runner.log`
3. Убедиться, что `Get-Process ssh`/`scp` ничего не возвращают после завершения
4. Проверить таймаут: `Invoke-VPSCommand -Command "sleep 20" -Timeout 5`

## История

- 2025‑12‑08: Полностью переписан `Invoke-VPSProcess` (файлы + таймаут + Kill).
- 2025‑12‑08: Удалён метод `Job`, добавлена документация для AI.














