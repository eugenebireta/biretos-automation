#!/bin/bash
# verify_bot_log.sh - live Day 1 bot verification from the server.
# Run on server: bash /root/windmill-core-v1/tests/verify_bot_log.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WEBHOOK="http://127.0.0.1:8001/webhook/telegram"
CHAT_ID="${CHAT_ID:-186497598}"
WORKER_LOG="/root/windmill-core-v1/ru_worker/ru_worker.log"
BASE_UID=$((998000 + RANDOM % 1000))

resolve_secret() {
  if [ -n "${TELEGRAM_WEBHOOK_SECRET:-}" ]; then
    printf "%s" "$TELEGRAM_WEBHOOK_SECRET"
    return
  fi
  if [ -n "${TELEGRAM_SECRET_TOKEN:-}" ]; then
    printf "%s" "$TELEGRAM_SECRET_TOKEN"
    return
  fi

  local from_config=""
  from_config="$(
    {
      cd "$REPO_ROOT" && PYTHONPATH="$REPO_ROOT" python3 - <<'PY' 2>/dev/null
from config import get_config
cfg = get_config()
print((getattr(cfg, "telegram_webhook_secret", "") or getattr(cfg, "telegram_secret_token", "") or "").strip())
PY
    } || true
  )"
  if [ -n "$from_config" ]; then
    printf "%s" "$from_config"
    return
  fi

  printf "%s" "demo_secret_key"
}

SECRET_TOKEN="$(resolve_secret)"
HMAC_HEADER="X-Telegram-Bot-Api-Secret-Token: $SECRET_TOKEN"

if [ -f "$WORKER_LOG" ]; then
  USE_JOURNALCTL=0
else
  USE_JOURNALCTL=1
fi

mark_log() {
  if [ "$USE_JOURNALCTL" = "0" ]; then
    wc -l < "$WORKER_LOG"
  else
    date +%s
  fi
}

log_since_mark() {
  local mark="$1"
  if [ "$USE_JOURNALCTL" = "0" ]; then
    tail -n "+$((mark + 1))" "$WORKER_LOG" 2>/dev/null || true
  else
    journalctl -u biretos-worker.service --since="@$mark" --no-pager 2>/dev/null || true
  fi
}

wait_for_pattern() {
  local mark="$1"
  local pattern="$2"
  local timeout="${3:-30}"
  local waited=0

  while [ "$waited" -lt "$timeout" ]; do
    local log_text
    log_text="$(log_since_mark "$mark")"
    if printf "%s\n" "$log_text" | grep -Eq "$pattern"; then
      printf "%s" "$log_text"
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done

  return 1
}

wait_for_all_patterns() {
  local mark="$1"
  local timeout="$2"
  shift 2
  local waited=0

  while [ "$waited" -lt "$timeout" ]; do
    local log_text
    local pattern
    local has_all=1
    log_text="$(log_since_mark "$mark")"

    for pattern in "$@"; do
      if ! printf "%s\n" "$log_text" | grep -Eq "$pattern"; then
        has_all=0
        break
      fi
    done

    if [ "$has_all" -eq 1 ]; then
      printf "%s" "$log_text"
      return 0
    fi

    sleep 1
    waited=$((waited + 1))
  done

  return 1
}

extract_confirmation_id() {
  local intent="$1"
  local log_text="$2"
  printf "%s\n" "$log_text" \
    | grep '"event": "nlu_confirmation_ready"' \
    | grep "\"intent_type\": \"$intent\"" \
    | tail -n 1 \
    | sed -n 's/.*"confirmation_id": "\([^"]*\)".*/\1/p'
}

post_message_update() {
  local update_id="$1"
  local text="$2"
  curl -s -o /dev/null -w "%{http_code}" -X POST "$WEBHOOK" \
    -H "Content-Type: application/json" \
    -H "$HMAC_HEADER" \
    -d "{\"update_id\":$update_id,\"message\":{\"message_id\":$update_id,\"from\":{\"id\":$CHAT_ID,\"is_bot\":false,\"first_name\":\"Verify\"},\"chat\":{\"id\":$CHAT_ID,\"type\":\"private\"},\"text\":\"$text\",\"date\":$(date +%s)}}"
}

post_confirm_callback() {
  local update_id="$1"
  local confirmation_id="$2"
  curl -s -o /dev/null -w "%{http_code}" -X POST "$WEBHOOK" \
    -H "Content-Type: application/json" \
    -H "$HMAC_HEADER" \
    -d "{\"update_id\":$update_id,\"callback_query\":{\"id\":\"verify-cb-$update_id\",\"from\":{\"id\":$CHAT_ID,\"is_bot\":false,\"first_name\":\"Verify\"},\"message\":{\"message_id\":$update_id,\"chat\":{\"id\":$CHAT_ID,\"type\":\"private\"}},\"data\":\"nlu_confirm:$confirmation_id\"}}"
}

echo "========================================"
echo "Day 1 Bot Verification"
echo "  Base update_id: $BASE_UID"
echo "  Chat ID: $CHAT_ID"
echo "  Secret source: $( [ "$SECRET_TOKEN" = "demo_secret_key" ] && echo fallback || echo config )"
echo "========================================"
echo ""

PASS=0
FAIL=0

echo "[1/5] Slash /ping"
MARK="$(mark_log)"
HTTP_CODE="$(post_message_update "$BASE_UID" "/ping")"
if [ "$HTTP_CODE" != "200" ]; then
  echo "[FAIL] /ping webhook HTTP $HTTP_CODE"
  FAIL=$((FAIL + 1))
else
  if LOG_SLICE="$(wait_for_pattern "$MARK" 'telegram_message_sent' 20)"; then
    echo "[PASS] /ping -> message sent"
    PASS=$((PASS + 1))
  else
    echo "[FAIL] /ping -> no telegram_message_sent in worker log"
    FAIL=$((FAIL + 1))
  fi
fi

echo "[2/5] NLU check_payment -> confirmation buttons"
MARK="$(mark_log)"
HTTP_CODE="$(post_message_update "$((BASE_UID + 1))" "проверить оплату INV-VERIFY-001")"
if [ "$HTTP_CODE" != "200" ]; then
  echo "[FAIL] check_payment webhook HTTP $HTTP_CODE"
  FAIL=$((FAIL + 1))
else
  if LOG_SLICE="$(wait_for_all_patterns "$MARK" 20 '"event": "nlu_confirmation_ready"' '"intent_type": "check_payment"' '"has_reply_markup": true' 'telegram_message_sent')"; then
    if printf "%s\n" "$LOG_SLICE" | grep -q '"intent_type": "check_payment"' \
      && printf "%s\n" "$LOG_SLICE" | grep -q '"has_reply_markup": true' \
      && printf "%s\n" "$LOG_SLICE" | grep -q 'telegram_message_sent'; then
      echo "[PASS] check_payment -> confirmation created"
      PASS=$((PASS + 1))
    else
      echo "[FAIL] check_payment -> confirmation path not observed"
      FAIL=$((FAIL + 1))
    fi
  else
    echo "[FAIL] check_payment -> no confirmation log event"
    FAIL=$((FAIL + 1))
  fi
fi

echo "[3/5] NLU get_tracking -> confirm path"
MARK="$(mark_log)"
HTTP_CODE="$(post_message_update "$((BASE_UID + 2))" "где посылка 10248510566")"
if [ "$HTTP_CODE" != "200" ]; then
  echo "[FAIL] get_tracking webhook HTTP $HTTP_CODE"
  FAIL=$((FAIL + 1))
else
  if LOG_SLICE="$(wait_for_all_patterns "$MARK" 20 '"event": "nlu_confirmation_ready"' '"intent_type": "get_tracking"' 'telegram_message_sent')"; then
    CONFIRM_ID="$(extract_confirmation_id "get_tracking" "$LOG_SLICE")"
    if [ -z "$CONFIRM_ID" ]; then
      echo "[FAIL] get_tracking -> confirmation_id not found"
      FAIL=$((FAIL + 1))
    else
      CALLBACK_MARK="$(mark_log)"
      HTTP_CODE="$(post_confirm_callback "$((BASE_UID + 102))" "$CONFIRM_ID")"
      if [ "$HTTP_CODE" != "200" ]; then
        echo "[FAIL] get_tracking confirm webhook HTTP $HTTP_CODE"
        FAIL=$((FAIL + 1))
      elif CALLBACK_LOG="$(wait_for_all_patterns "$CALLBACK_MARK" 35 '"event": "nlu_confirm_result"' '"intent_type": "get_tracking"' '"status": "success"' 'telegram_message_sent')"; then
        if printf "%s\n" "$CALLBACK_LOG" | grep -q '"intent_type": "get_tracking"' \
          && printf "%s\n" "$CALLBACK_LOG" | grep -q '"status": "success"' \
          && printf "%s\n" "$CALLBACK_LOG" | grep -q 'telegram_message_sent'; then
          echo "[PASS] get_tracking -> confirmed and replied"
          PASS=$((PASS + 1))
        else
          echo "[FAIL] get_tracking -> confirm path incomplete"
          FAIL=$((FAIL + 1))
        fi
      else
        echo "[FAIL] get_tracking -> no confirm result in log"
        FAIL=$((FAIL + 1))
      fi
    fi
  else
    echo "[FAIL] get_tracking -> no confirmation created"
    FAIL=$((FAIL + 1))
  fi
fi

echo "[4/5] NLU get_waybill -> confirm path"
MARK="$(mark_log)"
HTTP_CODE="$(post_message_update "$((BASE_UID + 3))" "накладная 10248510566")"
if [ "$HTTP_CODE" != "200" ]; then
  echo "[FAIL] get_waybill webhook HTTP $HTTP_CODE"
  FAIL=$((FAIL + 1))
else
  if LOG_SLICE="$(wait_for_all_patterns "$MARK" 20 '"event": "nlu_confirmation_ready"' '"intent_type": "get_waybill"' 'telegram_message_sent')"; then
    CONFIRM_ID="$(extract_confirmation_id "get_waybill" "$LOG_SLICE")"
    if [ -z "$CONFIRM_ID" ]; then
      echo "[FAIL] get_waybill -> confirmation_id not found"
      FAIL=$((FAIL + 1))
    else
      CALLBACK_MARK="$(mark_log)"
      HTTP_CODE="$(post_confirm_callback "$((BASE_UID + 103))" "$CONFIRM_ID")"
      if [ "$HTTP_CODE" != "200" ]; then
        echo "[FAIL] get_waybill confirm webhook HTTP $HTTP_CODE"
        FAIL=$((FAIL + 1))
      elif CALLBACK_LOG="$(wait_for_all_patterns "$CALLBACK_MARK" 40 '"event": "nlu_confirm_result"' '"intent_type": "get_waybill"' 'telegram_message_sent')"; then
        if printf "%s\n" "$CALLBACK_LOG" | grep -q '"intent_type": "get_waybill"' \
          && printf "%s\n" "$CALLBACK_LOG" | grep -q '"status": "success"' \
          && printf "%s\n" "$CALLBACK_LOG" | grep -q 'telegram_message_sent'; then
          echo "[PASS] get_waybill -> confirmed and replied with success"
          PASS=$((PASS + 1))
        elif printf "%s\n" "$CALLBACK_LOG" | grep -q '"intent_type": "get_waybill"' \
          && printf "%s\n" "$CALLBACK_LOG" | grep -q '"status": "error"' \
          && printf "%s\n" "$CALLBACK_LOG" | grep -q 'telegram_message_sent'; then
          echo "[PASS] get_waybill -> confirmed and replied with graceful transient handling"
          PASS=$((PASS + 1))
        else
          echo "[FAIL] get_waybill -> confirm path incomplete"
          FAIL=$((FAIL + 1))
        fi
      else
        echo "[FAIL] get_waybill -> no confirm result in log"
        FAIL=$((FAIL + 1))
      fi
    fi
  else
    echo "[FAIL] get_waybill -> no confirmation created"
    FAIL=$((FAIL + 1))
  fi
fi

echo "[5/5] Garbage fallback"
MARK="$(mark_log)"
HTTP_CODE="$(post_message_update "$((BASE_UID + 4))" "qwerty asdfgh lorem ipsum xyz")"
if [ "$HTTP_CODE" != "200" ]; then
  echo "[FAIL] garbage webhook HTTP $HTTP_CODE"
  FAIL=$((FAIL + 1))
else
  if LOG_SLICE="$(wait_for_pattern "$MARK" 'telegram_message_sent' 20)"; then
    if printf "%s\n" "$LOG_SLICE" | grep -q 'telegram_message_sent'; then
      echo "[PASS] garbage -> fallback reply sent"
      PASS=$((PASS + 1))
    else
      echo "[FAIL] garbage -> fallback reply missing"
      FAIL=$((FAIL + 1))
    fi
  else
    echo "[FAIL] garbage -> no telegram_message_sent in worker log"
    FAIL=$((FAIL + 1))
  fi
fi

echo ""
echo "========================================"
echo "Total: $PASS passed, $FAIL failed out of 5"
echo "========================================"

exit "$FAIL"
