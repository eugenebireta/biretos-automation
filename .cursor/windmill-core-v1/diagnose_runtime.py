"""
Runtime РґРёР°РіРЅРѕСЃС‚РёРєР° Telegram /start РєРѕРјР°РЅРґС‹
"""

import json
import sys
import urllib.request
import urllib.error

from config import get_config

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

_CONFIG = get_config()
POSTGRES_HOST = _CONFIG.postgres_host or "localhost"
POSTGRES_PORT = _CONFIG.postgres_port or 5432
POSTGRES_DB = _CONFIG.postgres_db or "biretos_automation"
POSTGRES_USER = _CONFIG.postgres_user or "biretos_user"
POSTGRES_PASSWORD = _CONFIG.postgres_password
TELEGRAM_BOT_TOKEN = _CONFIG.telegram_bot_token
WEBHOOK_SERVICE_URL = _CONFIG.webhook_service_url or "http://localhost:8001"

results = {}

# 1. РџСЂРѕРІРµСЂРєР° webhook_service
print("[1] РџСЂРѕРІРµСЂРєР° webhook_service...")
try:
    req = urllib.request.Request(f"{WEBHOOK_SERVICE_URL}/health")
    with urllib.request.urlopen(req, timeout=5.0) as response:
        if response.getcode() == 200:
            data = json.loads(response.read().decode())
            results["webhook_service"] = "OK"
            print(f"    [OK] /health РґРѕСЃС‚СѓРїРµРЅ: {data}")
        else:
            results["webhook_service"] = "FAIL"
            print(f"    [FAIL] /health РІРµСЂРЅСѓР»: {response.getcode()}")
except urllib.error.URLError:
    results["webhook_service"] = "FAIL"
    print(f"    [FAIL] webhook_service РЅРµ РґРѕСЃС‚СѓРїРµРЅ (РїРѕСЂС‚ 8001 РЅРµ СЃР»СѓС€Р°РµС‚)")
except Exception as e:
    results["webhook_service"] = "FAIL"
    print(f"    вќЊ РћС€РёР±РєР°: {e}")

# 2. РџСЂРѕРІРµСЂРєР° Telegram webhook
print("\n[2] РџСЂРѕРІРµСЂРєР° Telegram webhook...")
if not TELEGRAM_BOT_TOKEN:
    results["telegram_webhook"] = "NO_TOKEN"
    print(f"    [WARN] TELEGRAM_BOT_TOKEN РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ")
else:
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo"
        )
        with urllib.request.urlopen(req, timeout=10.0) as response:
            data = json.loads(response.read().decode())
        if data.get("ok"):
            webhook_url = data["result"].get("url", "")
            if webhook_url and "/webhook/telegram" in webhook_url:
                results["telegram_webhook"] = "OK"
                print(f"    [OK] Webhook РЅР°СЃС‚СЂРѕРµРЅ: {webhook_url}")
            elif webhook_url:
                results["telegram_webhook"] = "WRONG_URL"
                print(f"    [FAIL] Webhook URL РЅРµРїСЂР°РІРёР»СЊРЅС‹Р№: {webhook_url}")
            else:
                results["telegram_webhook"] = "NOT_SET"
                print(f"    [FAIL] Webhook РЅРµ РЅР°СЃС‚СЂРѕРµРЅ (РїСѓСЃС‚РѕР№ URL)")
        else:
            results["telegram_webhook"] = "API_ERROR"
            print(f"    [FAIL] Telegram API РѕС€РёР±РєР°: {data.get('description')}")
    except Exception as e:
        results["telegram_webhook"] = "ERROR"
        print(f"    [FAIL] РћС€РёР±РєР°: {e}")

# 3. РџСЂРѕРІРµСЂРєР° job_queue
print("\n[3] РџСЂРѕРІРµСЂРєР° job_queue...")
if not PSYCOPG2_AVAILABLE:
    results["job_queue"] = "NO_MODULE"
    print(f"    [WARN] psycopg2 РЅРµ РґРѕСЃС‚СѓРїРµРЅ, РїСЂРѕРІРµСЂРєР° РїСЂРѕРїСѓС‰РµРЅР°")
else:
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            """
            SELECT id, job_type, status, created_at
            FROM job_queue
            WHERE job_type = 'telegram_update'
            ORDER BY created_at DESC
            LIMIT 5
            """
        )
        jobs = cursor.fetchall()
        
        cursor.execute(
            """
            SELECT status, COUNT(*) as cnt
            FROM job_queue
            WHERE job_type = 'telegram_update'
            GROUP BY status
            """
        )
        statuses = dict(cursor.fetchall())
        
        if len(jobs) > 0:
            results["job_queue"] = "YES"
            print(f"    [OK] РќР°Р№РґРµРЅРѕ jobs: {len(jobs)}")
            print(f"    РЎС‚Р°С‚СѓСЃС‹: {statuses}")
            for job in jobs[:3]:
                print(f"      - {job['id']} | {job['status']} | {job['created_at']}")
        else:
            results["job_queue"] = "NO"
            print(f"    [FAIL] Jobs РЅРµ РЅР°Р№РґРµРЅС‹")
        
        cursor.close()
        conn.close()
    except psycopg2.OperationalError as e:
        results["job_queue"] = "DB_ERROR"
        print(f"    [FAIL] РћС€РёР±РєР° РїРѕРґРєР»СЋС‡РµРЅРёСЏ Рє Р‘Р”: {e}")
    except Exception as e:
        results["job_queue"] = "ERROR"
        print(f"    [FAIL] РћС€РёР±РєР°: {e}")

# 4. РџСЂРѕРІРµСЂРєР° ru_worker (РєРѕСЃРІРµРЅРЅР°СЏ С‡РµСЂРµР· job_queue СЃС‚Р°С‚СѓСЃС‹)
print("\n[4] РџСЂРѕРІРµСЂРєР° ru_worker...")
if not PSYCOPG2_AVAILABLE:
    results["ru_worker"] = "NO_MODULE"
    print(f"    [WARN] psycopg2 РЅРµ РґРѕСЃС‚СѓРїРµРЅ, РїСЂРѕРІРµСЂРєР° РїСЂРѕРїСѓС‰РµРЅР°")
elif results.get("job_queue") == "YES":
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            """
            SELECT job_type, status, COUNT(*) as cnt
            FROM job_queue
            WHERE job_type IN ('telegram_update', 'telegram_command')
            GROUP BY job_type, status
            """
        )
        all_statuses = cursor.fetchall()
        
        pending = sum(r["cnt"] for r in all_statuses if r["status"] == "pending")
        completed = sum(r["cnt"] for r in all_statuses if r["status"] == "completed")
        
        if pending > 0:
            results["ru_worker"] = "NOT_PROCESSING"
            print(f"    [FAIL] Р•СЃС‚СЊ {pending} pending jobs (ru_worker РЅРµ РѕР±СЂР°Р±Р°С‚С‹РІР°РµС‚)")
        elif completed > 0:
            results["ru_worker"] = "PROCESSING"
            print(f"    [OK] Р•СЃС‚СЊ {completed} completed jobs (ru_worker СЂР°Р±РѕС‚Р°РµС‚)")
        else:
            results["ru_worker"] = "NO_DATA"
            print(f"    [WARN] РќРµС‚ РґР°РЅРЅС‹С… РґР»СЏ РїСЂРѕРІРµСЂРєРё")
        
        cursor.close()
        conn.close()
    except Exception as e:
        results["ru_worker"] = "ERROR"
        print(f"    вќЊ РћС€РёР±РєР°: {e}")
else:
    results["ru_worker"] = "NO_JOBS"
    print(f"    [WARN] РќРµС‚ jobs РґР»СЏ РїСЂРѕРІРµСЂРєРё")

# РћРїСЂРµРґРµР»РµРЅРёРµ С‚РѕС‡РєРё РѕР±СЂС‹РІР°
print("\n" + "=" * 60)
print("ANALIZ:")
print("=" * 60)

if results.get("webhook_service") != "OK":
    point = "Telegram -> webhook"
elif results.get("telegram_webhook") not in ["OK", "NO_TOKEN"]:
    point = "Telegram -> webhook"
elif results.get("job_queue") == "NO":
    point = "webhook -> job_queue"
elif results.get("ru_worker") == "NOT_PROCESSING":
    point = "job_queue -> ru_worker"
elif results.get("ru_worker") == "PROCESSING":
    point = "ru_worker -> Telegram API"
else:
    point = "vse rabotaet, problema vne sistemy"

print(f"\nTOCHKA_OBRYVA = {point}")

