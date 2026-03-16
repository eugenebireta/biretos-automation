# РЎС‚Р°С‚СѓСЃ РґРµРїР»РѕСЏ Telegram Р±РѕС‚Р°

**Р”Р°С‚Р°:** 2026-01-06  
**РЎРµСЂРІРµСЂ:** 216.9.227.124 (biretos.ae)

## Р’С‹РїРѕР»РЅРµРЅРЅС‹Рµ Р·Р°РґР°С‡Рё

### вњ… 1. Р”РµРїР»РѕР№ ru_worker
- Р¤Р°Р№Р»С‹ СЃРєРѕРїРёСЂРѕРІР°РЅС‹ РЅР° СЃРµСЂРІРµСЂ: `/opt/biretos/windmill-core-v1/ru_worker/`
- Р’СЃРµ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё СѓСЃС‚Р°РЅРѕРІР»РµРЅС‹
- РџСЂРѕС†РµСЃСЃ Р·Р°РїСѓС‰РµРЅ Рё СЂР°Р±РѕС‚Р°РµС‚
- **РЎС‚Р°С‚СѓСЃ:** COMPLETED

### вњ… 2. Р”РµРїР»РѕР№ webhook_service
- Р¤Р°Р№Р»С‹ СЃРєРѕРїРёСЂРѕРІР°РЅС‹ РЅР° СЃРµСЂРІРµСЂ: `/opt/biretos/windmill-core-v1/webhook_service/`
- РЎРµСЂРІРёСЃ Р·Р°РїСѓС‰РµРЅ РЅР° РїРѕСЂС‚Сѓ 8001
- Health endpoint РѕС‚РІРµС‡Р°РµС‚: `{"status":"healthy","service":"webhook-queue"}`
- **РЎС‚Р°С‚СѓСЃ:** COMPLETED

### вњ… 3. РќР°СЃС‚СЂРѕР№РєР° РїРµСЂРµРјРµРЅРЅС‹С… РѕРєСЂСѓР¶РµРЅРёСЏ
- Р¤Р°Р№Р» `.env` СЃРѕР·РґР°РЅ: `/opt/biretos/windmill-core-v1/.env`
- Р”РѕР±Р°РІР»РµРЅС‹ РІСЃРµ РЅРµРѕР±С…РѕРґРёРјС‹Рµ РїРµСЂРµРјРµРЅРЅС‹Рµ (С€Р°Р±Р»РѕРЅС‹)
- **РЎС‚Р°С‚СѓСЃ:** COMPLETED

### вњ… 4. РќР°СЃС‚СЂРѕР№РєР° Telegram webhook
- nginx РЅР°СЃС‚СЂРѕРµРЅ: `location /webhook/telegram` в†’ `proxy_pass http://localhost:8001/webhook/telegram`
- SSL СЃРµСЂС‚РёС„РёРєР°С‚ СЂР°Р±РѕС‚Р°РµС‚ (biretos.ae)
- Webhook endpoint РїСЂРёРЅРёРјР°РµС‚ Р·Р°РїСЂРѕСЃС‹: `{"ok":true,"message":"Update received"}`
- **РџСЂРёРјРµС‡Р°РЅРёРµ:** РўРѕРєРµРЅ Р±РѕС‚Р° С‚СЂРµР±СѓРµС‚ РѕР±РЅРѕРІР»РµРЅРёСЏ (С‚РµРєСѓС‰РёР№ С‚РѕРєРµРЅ РґР°РµС‚ 401 Unauthorized)
- **РЎС‚Р°С‚СѓСЃ:** COMPLETED (РёРЅС„СЂР°СЃС‚СЂСѓРєС‚СѓСЂР° РіРѕС‚РѕРІР°)

## РўРµРєСѓС‰РµРµ СЃРѕСЃС‚РѕСЏРЅРёРµ СЃРёСЃС‚РµРјС‹

### Р—Р°РїСѓС‰РµРЅРЅС‹Рµ РїСЂРѕС†РµСЃСЃС‹
- вњ… `ru_worker.py` - Р·Р°РїСѓС‰РµРЅ (PID: РїСЂРѕРІРµСЂСЏРµС‚СЃСЏ)
- вњ… `webhook_service` (main.py) - Р·Р°РїСѓС‰РµРЅ РЅР° РїРѕСЂС‚Сѓ 8001

### РРЅС„СЂР°СЃС‚СЂСѓРєС‚СѓСЂР°
- вњ… PostgreSQL РїРѕРґРєР»СЋС‡РµРЅРёРµ РЅР°СЃС‚СЂРѕРµРЅРѕ
- вњ… nginx reverse proxy РЅР°СЃС‚СЂРѕРµРЅ
- вњ… SSL СЃРµСЂС‚РёС„РёРєР°С‚ РІР°Р»РёРґРµРЅ
- вњ… Webhook endpoint РґРѕСЃС‚СѓРїРµРЅ: `https://biretos.ae/webhook/telegram`

## systemd (рекомендуется для стабильности)

При установке systemd-сервисов `biretos-ru-worker` и `biretos-webhook`:
- Автоперезапуск при падении (`Restart=always`)
- `deploy.sh` автоматически использует `systemctl restart` при наличии systemd
- Однократная установка: скопировать `infrastructure/systemd/*.service` и `infrastructure/scripts/install-biretos-services.sh` на сервер, затем `sudo bash install-biretos-services.sh`
- Проверка: `systemctl status biretos-ru-worker` и `systemctl status biretos-webhook`

## Р§С‚Рѕ РЅСѓР¶РЅРѕ РґР»СЏ РїРѕР»РЅРѕР№ СЂР°Р±РѕС‚С‹

### 1. РћР±РЅРѕРІРёС‚СЊ TELEGRAM_BOT_TOKEN
РўРµРєСѓС‰РёР№ С‚РѕРєРµРЅ РЅРµРІРµСЂРЅС‹Р№ (401 Unauthorized). РќСѓР¶РЅРѕ:
- РџРѕР»СѓС‡РёС‚СЊ Р°РєС‚СѓР°Р»СЊРЅС‹Р№ С‚РѕРєРµРЅ РѕС‚ @BotFather
- РћР±РЅРѕРІРёС‚СЊ РІ `.env`: `TELEGRAM_BOT_TOKEN=<РЅРѕРІС‹Р№_С‚РѕРєРµРЅ>`
- РџРµСЂРµР·Р°РїСѓСЃС‚РёС‚СЊ СЃРµСЂРІРёСЃС‹

### 2. РќР°СЃС‚СЂРѕРёС‚СЊ T-Bank API РїРµСЂРµРјРµРЅРЅС‹Рµ
Р’ `.env` РЅСѓР¶РЅРѕ Р·Р°РїРѕР»РЅРёС‚СЊ:
```
TBANK_API_BASE=<Р±Р°Р·РѕРІС‹Р№_URL>
TBANK_INVOICE_STATUS_PATH=<РїСѓС‚СЊ_СЃ_{invoice_id}>
TBANK_INVOICES_LIST_PATH=<РїСѓС‚СЊ_СЃРїРёСЃРєР°>
```

### 3. РќР°СЃС‚СЂРѕРёС‚СЊ CDEK API РїРµСЂРµРјРµРЅРЅС‹Рµ
Р’ `.env` РЅСѓР¶РЅРѕ Р·Р°РїРѕР»РЅРёС‚СЊ:
```
CDEK_API_BASE=<Р±Р°Р·РѕРІС‹Р№_URL>
CDEK_CLIENT_ID=<REDACTED>
CDEK_CLIENT_SECRET=<REDACTED>
CDEK_SENDER_COMPANY=<РєРѕРјРїР°РЅРёСЏ>
CDEK_SENDER_PHONE=<С‚РµР»РµС„РѕРЅ>
CDEK_SENDER_ADDRESS=<Р°РґСЂРµСЃ>
```

### 4. РЈСЃС‚Р°РЅРѕРІРёС‚СЊ Telegram webhook
РџРѕСЃР»Рµ РѕР±РЅРѕРІР»РµРЅРёСЏ С‚РѕРєРµРЅР°:
```bash
curl "https://api.telegram.org/bot<РќРћР’Р«Р™_РўРћРљР•Рќ>/setWebhook?url=https://biretos.ae/webhook/telegram"
```

## РўРµСЃС‚РёСЂРѕРІР°РЅРёРµ

### Р“РѕС‚РѕРІРѕ Рє С‚РµСЃС‚РёСЂРѕРІР°РЅРёСЋ
- вњ… Webhook endpoint РїСЂРёРЅРёРјР°РµС‚ Р·Р°РїСЂРѕСЃС‹
- вњ… РРЅС„СЂР°СЃС‚СЂСѓРєС‚СѓСЂР° РЅР°СЃС‚СЂРѕРµРЅР°
- вљ пёЏ РўСЂРµР±СѓРµС‚СЃСЏ РІР°Р»РёРґРЅС‹Р№ С‚РѕРєРµРЅ Р±РѕС‚Р° РґР»СЏ СЂРµР°Р»СЊРЅРѕРіРѕ С‚РµСЃС‚РёСЂРѕРІР°РЅРёСЏ

### РљРѕРјР°РЅРґС‹ РґР»СЏ С‚РµСЃС‚РёСЂРѕРІР°РЅРёСЏ (РїРѕСЃР»Рµ РѕР±РЅРѕРІР»РµРЅРёСЏ С‚РѕРєРµРЅР°)
1. `/start` - Р±Р°Р·РѕРІР°СЏ РєРѕРјР°РЅРґР°
2. `/invoices` - РїРѕР»СѓС‡РµРЅРёРµ СЃРїРёСЃРєР° СЃС‡РµС‚РѕРІ (С‚СЂРµР±СѓРµС‚ T-Bank API)
3. РќР°Р¶Р°С‚РёРµ РєРЅРѕРїРєРё "рџ“¦ РЎРѕР·РґР°С‚СЊ РЅР°РєР»Р°РґРЅСѓСЋ" - СЃРѕР·РґР°РЅРёРµ РЅР°РєР»Р°РґРЅРѕР№ CDEK (С‚СЂРµР±СѓРµС‚ CDEK API)

## РЎР»РµРґСѓСЋС‰РёРµ С€Р°РіРё

1. **РџРѕР»СѓС‡РёС‚СЊ Р°РєС‚СѓР°Р»СЊРЅС‹Р№ TELEGRAM_BOT_TOKEN** РѕС‚ @BotFather
2. **РћР±РЅРѕРІРёС‚СЊ .env С„Р°Р№Р»** СЃ СЂРµР°Р»СЊРЅС‹РјРё Р·РЅР°С‡РµРЅРёСЏРјРё РґР»СЏ T-Bank Рё CDEK API
3. **РџРµСЂРµР·Р°РїСѓСЃС‚РёС‚СЊ СЃРµСЂРІРёСЃС‹** РґР»СЏ Р·Р°РіСЂСѓР·РєРё РЅРѕРІС‹С… РїРµСЂРµРјРµРЅРЅС‹С…
4. **РЈСЃС‚Р°РЅРѕРІРёС‚СЊ webhook** С‡РµСЂРµР· Telegram API
5. **РџСЂРѕС‚РµСЃС‚РёСЂРѕРІР°С‚СЊ** РєРѕРјР°РЅРґС‹ РІ СЂРµР°Р»СЊРЅРѕРј Telegram Р±РѕС‚Рµ

## РљРѕРјР°РЅРґС‹ РґР»СЏ РїРµСЂРµР·Р°РїСѓСЃРєР° (РїРѕСЃР»Рµ РѕР±РЅРѕРІР»РµРЅРёСЏ .env)

```bash
# РќР° СЃРµСЂРІРµСЂРµ (deploy.sh сам выберет systemctl или nohup)
cd /opt/biretos/windmill-core-v1/ru_worker && bash deploy.sh start
cd /opt/biretos/windmill-core-v1/webhook_service && bash deploy.sh start

# Либо при установленном systemd:
systemctl restart biretos-ru-worker biretos-webhook
```

## Р”РёР°РіРЅРѕСЃС‚РёРєР°

### РџСЂРѕРІРµСЂРєР° РїСЂРѕС†РµСЃСЃРѕРІ
```bash
ps aux | grep '[r]u_worker.py'
ps aux | grep '[m]ain.py.*webhook'
```

### РџСЂРѕРІРµСЂРєР° Р»РѕРіРѕРІ
```bash
tail -n 50 /opt/biretos/windmill-core-v1/ru_worker/ru_worker.log
tail -n 50 /opt/biretos/windmill-core-v1/webhook_service/webhook_service.log
```

### РџСЂРѕРІРµСЂРєР° webhook
```bash
curl http://localhost:8001/health
curl https://biretos.ae/webhook/telegram -X POST -H 'Content-Type: application/json' -d '{"update_id":1}'
```







