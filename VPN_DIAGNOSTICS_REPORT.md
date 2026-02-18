# VPN Diagnostics Report (Cursor VPN → WireGuard → VPS 216.9.227.124)

Дата: текущий запуск диагностики

## Итог
- Служба установлена, но не стартует: `WireGuardTunnel$CursorVPN` в состоянии `Stopped`.
- При запуске `C:\cursor_project\biretos-automation\run_cursorvpn.ps1` / `auto_setup_cursor_vpn.ps1` происходит ошибка `Start-Service ... failed to start` (вероятная причина — отсутствие прав администратора или блокировка сервиса).
- Интерфейс WireGuard не поднят: адаптеров/адресов `10.66.66.x` нет, маршруты по умолчанию остаются через `Ethernet`.
- MTU/трафик-тесты не выполнены, так как туннель не поднялся.

## Что уже проверено
- Логи запусков: `C:\cursor_project\biretos-automation\tmp_auto_setup.log`.
- Службы: `WireGuardManager` (Running), `WireGuardTunnel$CursorVPN` (Stopped).
- Маршруты: единственный `0.0.0.0/0` → `192.168.38.1` (Ethernet).
- Конфиг: `C:\cursor_project\biretos-automation\CursorVPN.conf` (MTU=1380, AllowedIPs=0.0.0.0/0, PersistentKeepalive=25).
- Диагностический вывод: `C:\cursor_project\biretos-automation\tmp_diag_report_raw.txt`.

## Что нужно сделать, чтобы завершить план
1) Открыть PowerShell **от имени администратора** в `C:\cursor_project\biretos-automation`.
2) Повторно запустить авто-скрипт с логированием:
   ```powershell
   PowerShell -ExecutionPolicy Bypass -File .\auto_setup_cursor_vpn.ps1 *>&1 |
     Tee-Object -FilePath .\tmp_auto_setup.log
   ```
   Если ошибка сохраняется — собрать Event Log по сервису WireGuardTunnel$CursorVPN.
3) Повторить диагностику:
   ```powershell
   PowerShell -ExecutionPolicy Bypass -File .\tmp_vpn_diag.ps1
   Get-Content .\tmp_diag_report_raw.txt
   ```
4) Если сервис стартовал — выполнить MTU-тесты и трафик-проверку:
   ```powershell
   ping -f -l 1352 216.9.227.124
   ping -f -l 1300 216.9.227.124
   ping -f -l 1252 216.9.227.124
   Invoke-RestMethod -Uri "https://ipinfo.io/ip"
   curl -I https://api.openai.com
   curl -I https://anthropic.com
   ```
5) По результатам:
   - Если пинги на 1352 фрагментируются — снизить MTU (рекомендую 1280 как safe-mode).
   - Если соединение рвётся в простое — уменьшить `PersistentKeepalive` до 15–20.
   - `AllowedIPs` оставить `0.0.0.0/0` (Full tunnel) для Cursor Stabilizer; при необходимости split-tunnel — указать CIDR целевых AI-ендпоинтов.

## Оставшиеся риски/наблюдения
- Главная проблема сейчас — сервис WireGuard не стартует (нужна проверка в режиме администратора и/или журнал WireGuard).
- Пока туннель не поднят, проверить реальный трафик Cursor/AI невозможно.
- MTU не проверен; возможны потери производительности при текущем 1380.

## Артефакты
- Лог автозапуска: `C:\cursor_project\biretos-automation\tmp_auto_setup.log`
- Диагностика: `C:\cursor_project\biretos-automation\tmp_diag_report_raw.txt`
- План: `C:\Users\Eugene\.cursor\plans\vpn_validation_&_optimization_b72ec331.plan.md`


