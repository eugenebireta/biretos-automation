#!/bin/bash
# Part C: VPS USA - Disable WireGuard

set -e

echo "========================================"
echo "  PART C: VPS USA"
echo "========================================"
echo ""

results=()

# 1. Check WireGuard
echo "1. Checking WireGuard..."
if ip link show wg0 &>/dev/null 2>&1; then
    echo "   wg0 interface exists"
    
    # Stop via wg-quick
    if command -v wg-quick &>/dev/null; then
        echo "   Stopping wg0 via wg-quick..."
        wg-quick down wg0 2>/dev/null || true
        sleep 2
    fi
    
    # Stop systemd service
    if systemctl list-units --type=service wg-quick@wg0.service &>/dev/null 2>&1; then
        echo "   Stopping wg-quick@wg0 service..."
        systemctl stop wg-quick@wg0 2>/dev/null || true
        systemctl disable wg-quick@wg0 2>/dev/null || true
        echo "   ✅ WireGuard service stopped and disabled"
        results+=("WireGuard|wg-quick@wg0|Stopped|Service stopped and disabled")
    else
        echo "   ✅ WireGuard interface stopped"
        results+=("WireGuard|wg0|Stopped|Interface stopped")
    fi
else
    echo "   ✅ wg0 not active"
    results+=("WireGuard|wg0|Not Active|Interface not found")
fi

# 2. Verify direct internet
echo ""
echo "2. Verifying direct internet..."
external_ip=$(curl -s --max-time 5 https://api.ipify.org 2>/dev/null || echo "unknown")
echo "   External IP: $external_ip"
if [ "$external_ip" = "216.9.227.124" ]; then
    echo "   ✅ Direct internet confirmed"
    results+=("Internet|Direct|OK|IP matches VPS USA")
else
    echo "   ⚠️  IP: $external_ip (expected: 216.9.227.124)"
    results+=("Internet|Direct|Warning|IP mismatch: $external_ip")
fi

# 3. Test AI providers
echo ""
echo "3. Testing AI providers..."
for host in api.openai.com api.anthropic.com; do
    if timeout 3 curl -s -o /dev/null "https://$host" 2>/dev/null; then
        echo "   ✅ $host: accessible"
        results+=("AI Provider|$host|OK|Accessible")
    else
        echo "   ⚠️  $host: not accessible"
        results+=("AI Provider|$host|Warning|Not accessible")
    fi
done

# 4. Final verification
echo ""
echo "4. Final verification..."
if ip link show wg0 &>/dev/null 2>&1; then
    wg_status=$(ip link show wg0 2>/dev/null | grep -c "state UP" || echo "0")
    if [ "$wg_status" -gt 0 ]; then
        echo "   ⚠️  wg0 interface is still UP"
    else
        echo "   ✅ wg0 interface is DOWN"
    fi
else
    echo "   ✅ wg0 interface not found"
fi

echo ""
echo "=== PART C COMPLETE ==="
echo ""
echo "Results:"
printf "%-20s | %-20s | %-15s | %s\n" "Component" "Service" "Status" "Notes"
echo "--------------------------------------------------------------------------------"
for result in "${results[@]}"; do
    IFS='|' read -r component service status notes <<< "$result"
    printf "%-20s | %-20s | %-15s | %s\n" "$component" "$service" "$status" "$notes"
done








