#!/bin/bash
# РЎРєСЂРёРїС‚ РґР»СЏ РЅР°СЃС‚СЂРѕР№РєРё Telegram webhook РЅР° RU VPS
# Р—Р°РїСѓСЃРєР°С‚СЊ РЅР° RU VPS (77.233.222.214)

set -e

RU_VPS_IP="77.233.222.214"
TOKEN="<REDACTED_TELEGRAM_TOKEN>"
WEBHOOK_PORT=8001

echo "=== РќРђРЎРўР РћР™РљРђ TELEGRAM WEBHOOK РќРђ RU VPS ==="
echo ""

# 1. РџСЂРѕРІРµСЂРєР°, С‡С‚Рѕ webhook_service Р·Р°РїСѓС‰РµРЅ
echo "[1] РџСЂРѕРІРµСЂРєР° webhook_service..."
if pgrep -f "webhook_service.*main.py" > /dev/null; then
    echo "   [OK] webhook_service Р·Р°РїСѓС‰РµРЅ"
else
    echo "   [WARNING] webhook_service РЅРµ Р·Р°РїСѓС‰РµРЅ"
    echo "   Р—Р°РїСѓСЃС‚РёС‚Рµ: cd windmill-core-v1/webhook_service && python3 main.py &"
    exit 1
fi

# 2. РџСЂРѕРІРµСЂРєР° health endpoint
echo ""
echo "[2] РџСЂРѕРІРµСЂРєР° health endpoint..."
if curl -s -f "http://localhost:${WEBHOOK_PORT}/health" > /dev/null; then
    echo "   [OK] webhook_service РѕС‚РІРµС‡Р°РµС‚ РЅР° localhost:${WEBHOOK_PORT}"
else
    echo "   [ERROR] webhook_service РЅРµ РѕС‚РІРµС‡Р°РµС‚ РЅР° localhost:${WEBHOOK_PORT}"
    exit 1
fi

# 3. РџСЂРѕРІРµСЂРєР° firewall
echo ""
echo "[3] РџСЂРѕРІРµСЂРєР° firewall..."
if command -v ufw > /dev/null; then
    if ufw status | grep -q "${WEBHOOK_PORT}"; then
        echo "   [OK] РџРѕСЂС‚ ${WEBHOOK_PORT} РѕС‚РєСЂС‹С‚ РІ ufw"
    else
        echo "   [INFO] РћС‚РєСЂС‹РІР°РµРј РїРѕСЂС‚ ${WEBHOOK_PORT} РІ ufw..."
        sudo ufw allow ${WEBHOOK_PORT}/tcp
    fi
elif command -v iptables > /dev/null; then
    if iptables -L -n | grep -q "${WEBHOOK_PORT}"; then
        echo "   [OK] РџРѕСЂС‚ ${WEBHOOK_PORT} РѕС‚РєСЂС‹С‚ РІ iptables"
    else
        echo "   [INFO] РћС‚РєСЂС‹РІР°РµРј РїРѕСЂС‚ ${WEBHOOK_PORT} РІ iptables..."
        sudo iptables -A INPUT -p tcp --dport ${WEBHOOK_PORT} -j ACCEPT
    fi
else
    echo "   [WARNING] РќРµ РЅР°Р№РґРµРЅ ufw РёР»Рё iptables, РїСЂРѕРІРµСЂСЊС‚Рµ firewall РІСЂСѓС‡РЅСѓСЋ"
fi

# 4. РџСЂРѕРІРµСЂРєР° РґРѕСЃС‚СѓРїРЅРѕСЃС‚Рё СЃРЅР°СЂСѓР¶Рё
echo ""
echo "[4] РџСЂРѕРІРµСЂРєР° РґРѕСЃС‚СѓРїРЅРѕСЃС‚Рё СЃРЅР°СЂСѓР¶Рё..."
if curl -s -f --max-time 5 "http://${RU_VPS_IP}:${WEBHOOK_PORT}/health" > /dev/null; then
    echo "   [OK] webhook_service РґРѕСЃС‚СѓРїРµРЅ СЃРЅР°СЂСѓР¶Рё"
else
    echo "   [WARNING] webhook_service РЅРµРґРѕСЃС‚СѓРїРµРЅ СЃРЅР°СЂСѓР¶Рё"
    echo "   РџСЂРѕРІРµСЂСЊС‚Рµ firewall Рё СЃРµС‚РµРІС‹Рµ РЅР°СЃС‚СЂРѕР№РєРё"
fi

# 5. РЈСЃС‚Р°РЅРѕРІРєР° webhook
echo ""
echo "[5] РЈСЃС‚Р°РЅРѕРІРєР° Telegram webhook..."
WEBHOOK_URL="http://${RU_VPS_IP}:${WEBHOOK_PORT}/webhook/telegram"
RESPONSE=$(curl -s "https://api.telegram.org/bot${TOKEN}/setWebhook?url=${WEBHOOK_URL}")

if echo "$RESPONSE" | grep -q '"ok":true'; then
    echo "   [OK] Webhook СѓСЃС‚Р°РЅРѕРІР»РµРЅ СѓСЃРїРµС€РЅРѕ!"
    echo "   URL: ${WEBHOOK_URL}"
else
    echo "   [ERROR] РќРµ СѓРґР°Р»РѕСЃСЊ СѓСЃС‚Р°РЅРѕРІРёС‚СЊ webhook"
    echo "   Response: ${RESPONSE}"
    exit 1
fi

# 6. РџСЂРѕРІРµСЂРєР° СѓСЃС‚Р°РЅРѕРІР»РµРЅРЅРѕРіРѕ webhook
echo ""
echo "[6] РџСЂРѕРІРµСЂРєР° СѓСЃС‚Р°РЅРѕРІР»РµРЅРЅРѕРіРѕ webhook..."
WEBHOOK_INFO=$(curl -s "https://api.telegram.org/bot${TOKEN}/getWebhookInfo")
echo "$WEBHOOK_INFO" | python3 -m json.tool

echo ""
echo "=== Р“РћРўРћР’Рћ ==="
echo "Webhook РЅР°СЃС‚СЂРѕРµРЅ РЅР°: ${WEBHOOK_URL}"
echo "РћС‚РїСЂР°РІСЊС‚Рµ /start Р±РѕС‚Сѓ РґР»СЏ РїСЂРѕРІРµСЂРєРё"
















