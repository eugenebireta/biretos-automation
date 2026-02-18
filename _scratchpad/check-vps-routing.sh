#!/bin/bash
# VPS Routing Check Script

echo "=== VPS Routing Diagnostics ==="
echo ""

# Check external IP
echo "1. External IP:"
curl -s https://api.ipify.org
echo ""
echo ""

# Check default route
echo "2. Default Route:"
ip route show default
echo ""

# Check WireGuard interface
echo "3. WireGuard Interface (wg0):"
if ip link show wg0 &>/dev/null; then
    ip addr show wg0
    echo ""
    echo "WireGuard routes:"
    ip route show | grep wg0
else
    echo "  wg0 not found"
fi
echo ""

# Check Xray service (if exists)
echo "4. Xray Service:"
if systemctl is-active --quiet xray 2>/dev/null; then
    echo "  Xray is running"
    systemctl status xray --no-pager -l | head -10
else
    echo "  Xray is not running"
fi
echo ""

# Test connectivity to AI providers
echo "5. Connectivity to AI Providers:"
for host in api.openai.com api.anthropic.com deepmind.googleapis.com; do
    echo -n "  $host: "
    if timeout 3 curl -s -o /dev/null -w "%{http_code}" "https://$host" > /dev/null 2>&1; then
        echo "OK"
    else
        echo "FAILED"
    fi
done
echo ""

# Test connectivity to other VPS
echo "6. Connectivity to other VPS:"
if [ "$HOSTNAME" = "biretos" ] || [ "$(hostname)" = "biretos" ]; then
    # We are on VPS-1 (USA), test VPS-2 (Moscow)
    echo -n "  VPS-2 (77.233.222.214): "
    if timeout 3 ping -c 1 77.233.222.214 > /dev/null 2>&1; then
        echo "OK"
    else
        echo "FAILED"
    fi
else
    # We are on VPS-2 (Moscow), test VPS-1 (USA)
    echo -n "  VPS-1 (216.9.227.124): "
    if timeout 3 ping -c 1 216.9.227.124 > /dev/null 2>&1; then
        echo "OK"
    else
        echo "FAILED"
    fi
fi
echo ""

# Check iptables rules (if any)
echo "7. IPTables Rules (policy routing):"
iptables -t nat -L -n 2>/dev/null | head -20
echo ""








