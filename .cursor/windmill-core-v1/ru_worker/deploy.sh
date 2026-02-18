#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATUS_FILE="${SCRIPT_DIR}/deploy.status.json"
LOG_FILE="${SCRIPT_DIR}/deploy.log"
STARTED_AT_FILE="${SCRIPT_DIR}/.deploy_started_at"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"

now() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

load_started_at() {
    if [[ -n "${DEPLOY_STARTED_AT:-}" ]]; then
        printf '%s' "${DEPLOY_STARTED_AT}"
    elif [[ -f "$STARTED_AT_FILE" ]]; then
        cat "$STARTED_AT_FILE"
    else
        now
    fi
}

write_status() {
    local status="$1"
    local step="$2"
    local error="${3:-null}"
    local pid="${4:-null}"
    local started_at
    local updated_at
    local completed_at="null"

    started_at="$(load_started_at)"
    updated_at="$(now)"
    if [[ "$status" == "completed" || "$status" == "failed" ]]; then
        completed_at="\"$updated_at\""
    fi

    cat >"$STATUS_FILE" <<EOF
{
  "status": "$status",
  "step": "$step",
  "started_at": "$started_at",
  "updated_at": "$updated_at",
  "completed_at": $completed_at,
  "pid": $pid,
  "log_file": "$LOG_FILE",
  "error": $error
}
EOF
}

log() {
    echo "[$(now)] $*"
}

on_error() {
    local exit_code=$1
    local line_no=$2
    local message="\"Ошибка на шаге ${CURRENT_STEP:-unknown} (exit ${exit_code}, line ${line_no})\""
    write_status "failed" "${CURRENT_STEP:-unknown}" "$message" "$$"
    exit "$exit_code"
}

do_backup() {
    CURRENT_STEP="backup"
    write_status "running" "$CURRENT_STEP" "null" "$$"
    log "[1/5] Создание бэкапа…"
    cp -r "$SCRIPT_DIR" "${SCRIPT_DIR}_backup_${TIMESTAMP}"
}

do_deploy_step() {
    CURRENT_STEP="deploy"
    write_status "running" "$CURRENT_STEP" "null" "$$"
    log "[2/5] Файлы уже доставлены Cursor (deploy step noop)"
}

do_install() {
    CURRENT_STEP="install"
    write_status "running" "$CURRENT_STEP" "null" "$$"
    log "[3/5] Установка зависимостей…"
    cd "$SCRIPT_DIR"
    pip3 install -q -r requirements.txt
}

do_restart() {
    CURRENT_STEP="restart"
    write_status "running" "$CURRENT_STEP" "null" "$$"
    log "[4/5] Перезапуск ru_worker…"
    pkill -f 'python.*ru_worker.py' || true
    (nohup python3 ru_worker.py > ru_worker.log 2>&1 &) >/dev/null 2>&1
    sleep 3
}

do_verify() {
    CURRENT_STEP="verify"
    write_status "running" "$CURRENT_STEP" "null" "$$"
    log "[5/5] Проверка процесса…"
    if pgrep -f 'ru_worker.py' >/dev/null; then
        write_status "completed" "$CURRENT_STEP" "null" "$$"
        rm -f "$STARTED_AT_FILE"
        log "✅ Деплой ru_worker завершён успешно"
    else
        write_status "failed" "$CURRENT_STEP" "\"Процесс не запустился\"" "$$"
        exit 1
    fi
}

do_deploy() {
    set -euo pipefail
    trap 'on_error $? $LINENO' ERR
    exec >>"$LOG_FILE" 2>&1

    do_backup
    do_deploy_step
    do_install
    do_restart
    do_verify
}

check_running() {
    if [[ -f "$STATUS_FILE" ]] && grep -q '"status": "running"' "$STATUS_FILE"; then
        echo "Деплой уже запущен. Используйте 'bash deploy.sh poll'." >&2
        exit 2
    fi
}

cmd_start() {
    check_running
    DEPLOY_STARTED_AT="$(now)"
    printf '%s' "$DEPLOY_STARTED_AT" >"$STARTED_AT_FILE"
    : >"$LOG_FILE"
    write_status "running" "init" "null" "null"
    
    # Запуск полностью независимого процесса
    nohup "$0" _run </dev/null >/dev/null 2>&1 &
    pid=$!
    disown "$pid" 2>/dev/null || true
    
    write_status "running" "init" "null" "$pid"
    echo "{\"ok\": true, \"status\": \"running\", \"pid\": $pid}"
}

cmd_poll() {
    if [[ -f "$STATUS_FILE" ]]; then
        cat "$STATUS_FILE"
    else
        echo "{\"status\": \"unknown\"}"
    fi
    echo "---- tail deploy.log ----"
    if [[ -f "$LOG_FILE" ]]; then
        tail -n 5 "$LOG_FILE"
    else
        echo "(лог отсутствует)"
    fi
}

cmd_resume() {
    cmd_poll
}

usage() {
    echo "usage: $0 start|poll|resume"
    exit 1
}

case "${1:-}" in
    _run)
        # Эта команда вызывается только из nohup (фоновый процесс)
        export DEPLOY_STARTED_AT="$(cat "$STARTED_AT_FILE" 2>/dev/null || now)"
        do_deploy
        ;;
    start) cmd_start ;;
    poll) cmd_poll ;;
    resume) cmd_resume ;;
    *) usage ;;
esac
