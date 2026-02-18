#!/bin/bash
# Part B: VPS RU (Moscow) - Disable WireGuard and Xray

set -e

echo "========================================"
echo "  PART B: VPS RU (Moscow)"
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

# 2. Check Xray
echo ""
echo "2. Checking Xray..."
if systemctl list-units --type=service xray.service &>/dev/null 2>&1; then
    if systemctl is-active --quiet xray 2>/dev/null; then
        echo "   Xray is active"
        systemctl stop xray 2>/dev/null || true
        systemctl disable xray 2>/dev/null || true
        sleep 2
        if systemctl is-active --quiet xray 2>/dev/null; then
            echo "   ⚠️  Xray may still be active"
            results+=("Xray|xray.service|Warning|May still be active")
        else
            echo "   ✅ Xray stopped and disabled"
            results+=("Xray|xray.service|Stopped|Service stopped and disabled")
        fi
    else
        echo "   ✅ Xray already stopped"
        systemctl disable xray 2>/dev/null || true
        results+=("Xray|xray.service|Not Running|Already stopped, autostart disabled")
    fi
else
    echo "   ✅ Xray service not found"
    results+=("Xray|N/A|Not Found|Service not installed")
fi

# 3. Verify direct internet
echo ""
echo "3. Verifying direct internet..."
external_ip=$(curl -s --max-time 5 https://api.ipify.org 2>/dev/null || echo "unknown")
echo "   External IP: $external_ip"
if [ "$external_ip" = "77.233.222.214" ]; then
    echo "   ✅ Direct internet confirmed"
    results+=("Internet|Direct|OK|IP matches VPS RU")
else
    echo "   ⚠️  IP: $external_ip (expected: 77.233.222.214)"
    results+=("Internet|Direct|Warning|IP mismatch: $external_ip")
fi

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

if systemctl is-active --quiet xray 2>/dev/null; then
    echo "   ⚠️  Xray service is still active"
else
    echo "   ✅ Xray service is stopped"
fi

echo ""
echo "=== PART B COMPLETE ==="
echo ""
echo "Results:"
printf "%-20s | %-20s | %-15s | %s\n" "Component" "Service" "Status" "Notes"
echo "--------------------------------------------------------------------------------"
for result in "${results[@]}"; do
    IFS='|' read -r component service status notes <<< "$result"
    printf "%-20s | %-20s | %-15s | %s\n" "$component" "$service" "$status" "$notes"
done








