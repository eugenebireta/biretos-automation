#!/usr/bin/env python3
"""
Extract Telegram bot token from n8n database
Run on server: python3 extract_telegram_token.py
"""
import subprocess
import json
import re

# Query n8n database for telegram credentials
cmd = [
    'docker', 'exec', 'biretos-postgres',
    'psql', '-U', 'n8n', '-d', 'n8n', '-t', '-c',
    "SELECT data::text FROM credentials WHERE type = 'telegramApi' LIMIT 1;"
]

try:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data_str = result.stdout.strip()
    
    if not data_str or data_str == '(0 rows)':
        print("No telegram credentials found")
        exit(1)
    
    # Parse JSON data
    data = json.loads(data_str)
    
    # Extract token (can be in different fields)
    token = None
    if isinstance(data, dict):
        token = data.get('accessToken') or data.get('access_token') or data.get('token')
    
    if token:
        print(token)
    else:
        print("Token not found in credentials data")
        print("Data keys:", list(data.keys()) if isinstance(data, dict) else "Not a dict")
        exit(1)
        
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    exit(1)






















