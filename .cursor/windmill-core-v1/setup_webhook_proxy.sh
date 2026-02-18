#!/bin/bash
# Setup reverse proxy for webhook_service on VPS

# Check if webhook_service is running on port 8001
if ! curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo "ERROR: webhook_service is not running on port 8001"
    exit 1
fi

# Check for Caddy
if command -v caddy > /dev/null 2>&1; then
    echo "Using Caddy for reverse proxy"
    
    # Create Caddyfile entry
    cat >> /tmp/caddy_webhook.conf << 'EOF'
webhook.biretos.ae {
    reverse_proxy localhost:8001
}
EOF
    
    # Add to Caddyfile or create new
    if [ -f /etc/caddy/Caddyfile ]; then
        cat /tmp/caddy_webhook.conf >> /etc/caddy/Caddyfile
        systemctl reload caddy
    else
        echo "Caddyfile not found at /etc/caddy/Caddyfile"
        echo "Create Caddyfile with content:"
        cat /tmp/caddy_webhook.conf
    fi
    
elif command -v nginx > /dev/null 2>&1; then
    echo "Using nginx for reverse proxy"
    
    # Create nginx config
    cat > /etc/nginx/sites-available/webhook-service << 'EOF'
server {
    listen 80;
    server_name webhook.biretos.ae;
    
    location /webhook/telegram {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
EOF
    
    ln -sf /etc/nginx/sites-available/webhook-service /etc/nginx/sites-enabled/
    nginx -t && systemctl reload nginx
    
else
    echo "ERROR: Neither Caddy nor nginx found"
    exit 1
fi

echo "Reverse proxy configured. Use URL: http://webhook.biretos.ae/webhook/telegram"






















