# Отчёт по диагностике WireGuardTunnel$CursorVPN (Windows)

Дата: текущее выполнение (UTC локальное время системы)

## Резюме
- Служба существует, но в состоянии `Stopped`, ошибки SCM: `1066/0x42a` с `SERVICE_EXIT_CODE 2 (ERROR_FILE_NOT_FOUND)`.
- Event Log System (Service Control Manager 7024): "Не удается найти указанный файл" при запуске `WireGuard Tunnel: CursorVPN`.
- Двоичный путь службы: `"C:\Program Files\WireGuard\wireguard.exe" /tunnelservice C:\cursor_project\biretos-automation\CursorVPN.conf` (из `sc qc` и реестра).
- Файл `C:\cursor_project\biretos-automation\CursorVPN.conf` существует, ASCII/UTF-8 без BOM, права включают SYSTEM:(F), Администраторы:(F).
- Логи WireGuard в `C:\ProgramData\WireGuard\...` отсутствуют (папки нет) — сервис не пишет логи.
- Адаптер WireGuard отсутствует: `Get-NetAdapter -IncludeHidden` и `Get-PnpDevice -Class Net` не показывают WireGuard.
- Ручная команда `/installtunnelservice` не дала вывода, статус службы не изменился (по-прежнему 1066/2).
- Версия `wireguard.exe`: 0.5.3 (22.12.2021), подпись Entrust/ WireGuard LLC (валидная по Authenticode), возможна устаревшая сборка.

## Детали проверки
1) **Конфиг**
   - Путь: `C:\cursor_project\biretos-automation\CursorVPN.conf`
   - Первые байты: `91 73 110 116 101 114 102 97` (нет BOM).
   - Права (icacls): SYSTEM:(F), Администраторы:(F), Пользователи:(RX), Authenticated Users:(M).

2) **Служба и реестр**
   - `sc qc "WireGuardTunnel$CursorVPN"`: бинарник `"C:\Program Files\WireGuard\wireguard.exe" /tunnelservice C:\cursor_project\biretos-automation\CursorVPN.conf`, Start=Auto, Account=LocalSystem.
   - `sc query "WireGuardTunnel$CursorVPN"`: STATE=STOPPED, WIN32_EXIT_CODE=1066, SERVICE_EXIT_CODE=2.
   - Реестр `HKLM:\SYSTEM\CurrentControlSet\Services\WireGuardTunnel$CursorVPN`: тот же ImagePath, зависим. Nsi/TcpIp, ObjectName=LocalSystem.

3) **Логи**
   - `C:\ProgramData\WireGuard\log\` и `C:\ProgramData\WireGuard\tunnel\CursorVPN.log`: каталог отсутствует → логи не создавались.
   - Event Log System (SCM):
     - 7024 Ошибка: "WireGuard Tunnel: CursorVPN" завершена, "Не удается найти указанный файл" (несколько раз).
     - 7045 Инфо: служба установлена с указанным ImagePath (см. выше).
   - Application: релевантных событий WireGuard нет.

4) **Адаптер/драйвер**
   - `Get-NetAdapter -IncludeHidden`: нет записей WireGuard → адаптер не создаётся.
   - `Get-PnpDevice -Class Net` с фильтром WireGuard: пусто.

5) **Бинарник WireGuard**
   - Файл: `C:\Program Files\WireGuard\wireguard.exe`
   - Version: 0.5.3 (File/Product), дата 22.12.2021, размер ~8.2 MB.
   - Подпись: Valid (WireGuard LLC, Entrust EVC), NotAfter сертификата 22.12.2024 (есть timestamp TSA).

6) **Ручной запуск установки службы**
   - Команда: `"C:\Program Files\WireGuard\wireguard.exe" /installtunnelservice "C:\cursor_project\biretos-automation\CursorVPN.conf"`
   - Вывод: отсутствует, статус службы не изменился (остался 1066/2).

## Предварительный вердикт (вероятные причины)
- Ошибка `ERROR_FILE_NOT_FOUND (2)` при старте службы, хотя конфиг существует и доступен SYSTEM → вероятно, WireGuard не находит/не подгружает драйвер или не видит конфиг в момент старта.
- Отсутствие адаптера WireGuard указывает на проблему с драйвером/установкой (WireGuard 0.5.3 устаревший; драйвер мог не установиться/быть удалён/блокирован).
- Логи WireGuard не создаются → бинарник падает до инициализации туннеля.

## Что проверить дальше (без изменений конфигурации)
1) Запустить диагностику от администратора (сеанс Elevated) — подтвердить, что команды дают те же ошибки.  
2) Проверить наличие драйвера/INF:
   - `pnputil /enum-drivers | findstr /I wireguard`
   - `sc query wireguard` (драйвер).
3) Проверить целостность установки WireGuard (Repair/Reinstall 0.5.3 или обновить до актуальной версии 0.5.6+), затем повторить запуск службы.  
4) Если после переустановки драйвер появится, но ошибка сохранится — собрать свежие события SCM и логи в `C:\ProgramData\WireGuard\log\`.

## Артефакты диагностики
- Event Log System (фильтр WireGuard/SCM): `C:\cursor_project\biretos-automation\tmp_events_sys.txt`
- Список служб WireGuard: `C:\cursor_project\biretos-automation\tmp_services.txt`
- SC QC/Query: `C:\cursor_project\biretos-automation\tmp_sc_qc.txt`, `C:\cursor_project\biretos-automation\tmp_sc_query.txt`
- WireGuard версия/подпись: `C:\cursor_project\biretos-automation\tmp_wg_version.txt`, `C:\cursor_project\biretos-automation\tmp_wg_sig.txt`
- Диагностика адаптеров/PnP: `C:\cursor_project\biretos-automation\tmp_adapters.txt`, `C:\cursor_project\biretos-automation\tmp_pnp.txt`
- Конфиг (инспекция байтов/ACL): `C:\cursor_project\biretos-automation\tmp_bytes.txt`, `C:\cursor_project\biretos-automation\tmp_acl.txt`
- Ручной installtunnelservice: `C:\cursor_project\biretos-automation\tmp_install.txt`


