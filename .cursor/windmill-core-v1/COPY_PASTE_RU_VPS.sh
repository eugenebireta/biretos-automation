#!/bin/bash
# ==========================================
# РЎРљРћРџРР РЈР™ Р Р’Р«РџРћР›РќР Р­РўРћ РќРђ RU VPS (77.233.222.214)
# ==========================================

set -e

echo "=== РќРђРЎРўР РћР™РљРђ TELEGRAM WEBHOOK ==="
echo ""

# РџРµСЂРµРјРµРЅРЅС‹Рµ
TOKEN="<REDACTED_TELEGRAM_TOKEN>"
RU_VPS_IP="77.233.222.214"

# 1. Р—Р°РїСѓСЃРє webhook_service
echo "[1] Р—Р°РїСѓСЃРє webhook_service..."
cd /path/to/windmill-core-v1/webhook_service  # РР—РњР•РќР РџРЈРўР¬!
if pgrep -f "main.py" > /dev/null; then
    echo "   [OK] РЈР¶Рµ Р·Р°РїСѓС‰РµРЅ"
else
    nohup python3 main.py > webhook_service.log 2>&1 &
    sleep 2
    if curl -s http://localhost:8001/health > /dev/null; then
        echo "   [OK] Р—Р°РїСѓС‰РµРЅ"
    else
        echo "   [ERROR] РќРµ Р·Р°РїСѓСЃС‚РёР»СЃСЏ, РїСЂРѕРІРµСЂСЊ Р»РѕРіРё"
        exit 1
    fi
fi

# 2. РћС‚РєСЂС‹С‚РёРµ РїРѕСЂС‚Р°
echo ""
echo "[2] РћС‚РєСЂС‹С‚РёРµ РїРѕСЂС‚Р° 8001..."
if command -v ufw > /dev/null; then
    sudo ufw allow 8001/tcp 2>/dev/null || true
    echo "   [OK] РџРѕСЂС‚ РѕС‚РєСЂС‹С‚ (ufw)"
elif command -v iptables > /dev/null; then
    sudo iptables -A INPUT -p tcp --dport 8001 -j ACCEPT 2>/dev/null || true
    echo "   [OK] РџРѕСЂС‚ РѕС‚РєСЂС‹С‚ (iptables)"
fi

# 3. РџСЂРѕРІРµСЂРєР° РґРѕСЃС‚СѓРїРЅРѕСЃС‚Рё
echo ""
echo "[3] РџСЂРѕРІРµСЂРєР° РґРѕСЃС‚СѓРїРЅРѕСЃС‚Рё..."
if curl -s --max-time 5 "http://${RU_VPS_IP}:8001/health" > /dev/null; then
    echo "   [OK] Р”РѕСЃС‚СѓРїРµРЅ СЃРЅР°СЂСѓР¶Рё"
else
    echo "   [WARNING] РќРµРґРѕСЃС‚СѓРїРµРЅ СЃРЅР°СЂСѓР¶Рё, РїСЂРѕРІРµСЂСЊ firewall"
fi

# 4. РЈСЃС‚Р°РЅРѕРІРєР° webhook (HTTP - РјРѕР¶РµС‚ РЅРµ СЂР°Р±РѕС‚Р°С‚СЊ)
echo ""
echo "[4] РЈСЃС‚Р°РЅРѕРІРєР° webhook..."
WEBHOOK_URL="http://${RU_VPS_IP}:8001/webhook/telegram"
RESPONSE=$(curl -s "https://api.telegram.org/bot${TOKEN}/setWebhook?url=${WEBHOOK_URL}")

if echo "$RESPONSE" | grep -q '"ok":true'; then
    echo "   [OK] Webhook СѓСЃС‚Р°РЅРѕРІР»РµРЅ!"
    echo "   URL: ${WEBHOOK_URL}"
else
    ERROR=$(echo "$RESPONSE" | grep -o '"description":"[^"]*"' | cut -d'"' -f4)
    echo "   [ERROR] РќРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ: ${ERROR}"
    echo ""
    echo "   Р Р•РЁР•РќРР•: Telegram С‚СЂРµР±СѓРµС‚ HTTPS!"
    echo "   1. РќР°СЃС‚СЂРѕР№ nginx СЃ SSL"
    echo "   2. РР»Рё РёСЃРїРѕР»СЊР·СѓР№ РґРѕРјРµРЅ СЃ SSL"
    echo "   3. РЎРј. DEPLOY_WEBHOOK_RU_VPS.md"
    exit 1
fi

# 5. РџСЂРѕРІРµСЂРєР°
echo ""
echo "[5] РџСЂРѕРІРµСЂРєР° webhook..."
curl -s "https://api.telegram.org/bot${TOKEN}/getWebhookInfo" | python3 -m json.tool

echo ""
echo "=== Р“РћРўРћР’Рћ ==="
echo "РћС‚РїСЂР°РІСЊ /start Р±РѕС‚Сѓ РґР»СЏ РїСЂРѕРІРµСЂРєРё"
















