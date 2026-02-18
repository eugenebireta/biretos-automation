#!/bin/bash
# Deploy webhook_service on server

WEBHOOK_DIR="/root/windmill-core-v1/webhook_service"

# Check if directory exists
if [ ! -d "$WEBHOOK_DIR" ]; then
    echo "ERROR: $WEBHOOK_DIR not found"
    exit 1
fi

cd "$WEBHOOK_DIR"

# Check if already running
if pgrep -f "python.*main.py" > /dev/null; then
    echo "webhook_service already running"
    exit 0
fi

# Start webhook_service
nohup python3 main.py > /var/log/webhook_service.log 2>&1 &
echo $! > /var/run/webhook_service.pid
echo "webhook_service started, PID: $(cat /var/run/webhook_service.pid)"

# Wait a bit and check
sleep 2
if curl -s http://localhost:8001/health > /dev/null; then
    echo "OK: webhook_service is responding"
else
    echo "WARN: webhook_service may not be running properly"
fi






















