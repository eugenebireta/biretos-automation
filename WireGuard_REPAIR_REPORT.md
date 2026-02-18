# WireGuard Repair Report (Windows)

Дата: текущая сессия (локальное время Windows)

## Итог
- Полное удаление старых служб/папок выполнено (WireGuardTunnel$CursorVPN, wireguard manager/driver).
- Установлен WireGuard через тихий инсталлятор (link: download.wireguard.com). Файл `C:\Program Files\WireGuard\wireguard.exe` версии 0.5.3 (датой 22.12.2021) остался тем же — вероятно, это актуальная стабильная сборка инсталлятора.
- Драйвер Wintun присутствует: `sc query wintun` → STATE=STOPPED (0x0 exit code). Служба `wireguard` не создается (как и в новых версиях, используется wintun).
- Туннель установлен командой `/installtunnelservice`, но запуск службы завершается: `WIN32_EXIT_CODE=1066`, `SERVICE_EXIT_CODE=2 (ERROR_FILE_NOT_FOUND)`. Состояние: STOPPED.
- Сетевой адаптер WireGuard не появляется (Get-NetAdapter пустой). Внешний IP не проверялся из-за нестарта туннеля.

## Что делалось
1) Удаление старой инсталляции
   - `wireguard.exe /uninstallmanagerservice`
   - `wireguard.exe /uninstalltunnelservice CursorVPN`
   - `sc stop/delete WireGuardTunnel$CursorVPN`, `sc stop/delete wireguard`
   - Удалены каталоги `C:\Program Files\WireGuard`, `C:\ProgramData\WireGuard`
   - Проверка `pnputil /enum-drivers` — упоминаний wireguard не осталось

2) Установка новой версии
   - Скачан `C:\cursor_project\biretos-automation\wireguard-installer.exe`
   - Установка: `Start-Process ... /S` (и повтор с `-Verb RunAs`)
   - После установки: службы `WireGuardManager` (Running) и `WireGuardTunnel$CursorVPN` (Stopped) появились; драйвер `wintun` присутствует

3) Пересоздание туннеля
   - `/uninstalltunnelservice CursorVPN` → `/installtunnelservice C:\cursor_project\biretos-automation\CursorVPN.conf`
   - Запуск: `Start-Service 'WireGuardTunnel$CursorVPN'` → ошибка
   - `sc query "WireGuardTunnel$CursorVPN"` → WIN32_EXIT_CODE=1066, SERVICE_EXIT_CODE=2

4) Проверка после установки
   - Драйвер: `sc query wintun` → OK (статус STOPPED, exit 0)
   - Адаптер: нет записей в `Get-NetAdapter` с WireGuard
   - Версия файла: 0.5.3 (как до удаления)

## Артефакты (логи/выводы)
- Службы: `Get-Service *WireGuard*` (в сессии; менеджер Running, туннель Stopped)
- SC статус: `sc query "WireGuardTunnel$CursorVPN"` → 1066/2
- Файл версии: `C:\cursor_project\biretos-automation\tmp_wg_ver.txt`
- Драйвер: `sc query wintun`
- Драйверы pnputil: `C:\cursor_project\biretos-automation\tmp_drivers.txt`

## Предварительные выводы
- Wintun установлен, но служба туннеля не стартует с `ERROR_FILE_NOT_FOUND`. Так как конфиг существует и доступен, ошибка, вероятнее всего, не о файле .conf, а о внутреннем ресурсе, необходимом для старта (например, не создается/находится адаптер).
- Версия 0.5.3 могла остаться из-за того, что официальный инсталлятор действительно содержит 0.5.3 как текущую стабильную; это не признак сбоя.
- Отсутствие адаптера указывает, что служба падает до инициализации интерфейса. Возможные причины: блокировка драйвера/службы политикой, антивирусом, или некорректный путь/права при запуске службы.

## Что ещё можно сделать вручную (без правок конфигурации)
1) Запустить `wireguard.exe` GUI от имени администратора и попробовать импорт/активацию конфига вручную — посмотреть точный текст ошибки GUI.
2) Проверить Event Log (System/Application) сразу после попытки запуска службы — могут появиться новые события с более детальным кодом.
3) Проверить, не блокируется ли драйвер/служба антивирусом или политиками (WDAC/SmartScreen/AV).
4) Переподтвердить доступность конфига для LocalSystem (уже OK по ACL, но можно проверить `icacls`/`Get-Acl` и открытие файла от имени SYSTEM через psexec/schtasks).
5) Альтернативно — создать туннель как пользовательский (не сервис) через GUI и проверить, поднимается ли адаптер и интерфейс; если да — проблема именно в сервисном режиме `/installtunnelservice`.

## Статус
Проблема запуска службы `WireGuardTunnel$CursorVPN` не устранена: ошибка 1066/2 сохраняется после переустановки. Требуется дополнительная проверка причин падения службы (см. пункты выше).


