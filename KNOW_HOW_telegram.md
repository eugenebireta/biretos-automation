# Know-How: Telegram Pipeline

<!-- Sub-file of KNOW_HOW.md. Same format: YYYY-MM-DD | #тег | scope: Суть -->
<!-- Records here are DUPLICATED from KNOW_HOW.md (not moved) per CLAUDE.md rule. -->

## Architecture

Key scripts:
- `orchestrator/telegram_bot.py` — core bot, receives commands, routes to handlers
- `orchestrator/telegram_gateway.py` — webhook gateway, receives updates via HTTP
- `orchestrator/telegram_notifier.py` — sends alerts/status to owner
- `routers/telegram/export_command.py` — /export command handler
- `scripts/supervisor/telegram_reader.py` — supervisor reads Telegram during autopilot

Docs: `docs/howto/COMMANDS.md`

## Known issues (from MAX bot project)

2026-04-12 | #platform | telegram-dedup: дублирование сообщений (9x одно сообщение за 92мс) = несколько одновременных экземпляров gateway. Fix: PID lockfile. In-memory dedup не спасает — у каждого процесса своя память.
2026-04-12 | #platform | telegram-marker: marker (курсор пагинации GET /updates) не персистировался. На рестарте — повторная доставка. Fix: файл-маркер, сохранять после каждого poll.
2026-04-12 | #platform | telegram-claude: claude --print через SSH открывает новый IDE-чат каждый вызов (не продолжает контекст). Не годится для conversational bot. Вместо этого: Anthropic API с system prompt + история в файле.
