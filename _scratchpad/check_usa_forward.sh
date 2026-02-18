#!/bin/bash
set -euo pipefail

echo "=== Forwarding status $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
sysctl net.ipv4.ip_forward
sysctl net.ipv4.conf.all.forwarding
sysctl net.ipv4.conf.wg0.forwarding
sysctl net.ipv4.conf.eth0.forwarding
sysctl net.ipv6.conf.all.forwarding
sysctl net.ipv4.conf.all.rp_filter
sysctl net.ipv4.conf.wg0.rp_filter
sysctl net.ipv4.conf.eth0.rp_filter
echo
iptables -S FORWARD

