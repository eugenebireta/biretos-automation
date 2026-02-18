#!/usr/bin/env bash
set -euo pipefail

report_section() {
    echo ""
    echo "===== $1 ====="
}

report_section "System"
hostname
if command -v lsb_release >/dev/null 2>&1; then
    lsb_release -ds
else
    head -n 1 /etc/os-release
fi
uptime

report_section "CPU"
lscpu | egrep 'Model name|CPU\(s\)|Thread|Core|Socket' || true

report_section "Memory"
free -m

report_section "Swap"
swapon --show || echo "No swap configured"

report_section "Disk usage (root, var, home)"
df -h / /var /home 2>/dev/null || df -h

report_section "Largest web directories (/var/www)"
if [ -d /var/www ]; then
    du -sh /var/www/* 2>/dev/null | sort -h | tail -n 10
else
    echo "/var/www not found"
fi

report_section "Docker status"
if command -v docker >/dev/null 2>&1; then
    docker ps --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
else
    echo "docker not installed"
fi

report_section "Shopware hint"
if [ -d /var/www/html ]; then
    du -sh /var/www/html 2>/dev/null
fi
if [ -d /var/www/shopware ]; then
    du -sh /var/www/shopware 2>/dev/null
fi

report_section "Recent memory usage (top 5)"
ps -eo pid,ppid,%mem,%cpu,cmd --sort=-%mem | head -n 6

report_section "Network"
ip -brief addr












