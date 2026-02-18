#!/usr/bin/env python3
"""Check logs for Telegram updates"""
import psycopg2
from datetime import datetime, timedelta

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    dbname='biretos_automation',
    user='biretos_user',
    password='biretos_pass'
)
cur = conn.cursor()

# Check recent telegram jobs
print("[1] Checking job_queue for telegram jobs...")
cur.execute("""
    SELECT id, job_type, status, created_at, updated_at, error
    FROM job_queue 
    WHERE job_type IN ('telegram_update', 'telegram_command')
    ORDER BY created_at DESC 
    LIMIT 10
""")
rows = cur.fetchall()

if rows:
    print(f"    Found {len(rows)} recent telegram jobs:")
    for r in rows:
        print(f"      - {r[1]} | {r[2]} | Created: {r[3]} | Error: {r[5][:50] if r[5] else 'None'}")
else:
    print("    No telegram jobs found")

# Check for pending telegram_update
print("\n[2] Checking for pending telegram_update jobs...")
cur.execute("""
    SELECT COUNT(*) FROM job_queue 
    WHERE job_type = 'telegram_update' AND status = 'pending'
""")
pending = cur.fetchone()[0]
print(f"    Pending telegram_update jobs: {pending}")

# Check for completed telegram_command
print("\n[3] Checking for completed telegram_command jobs...")
cur.execute("""
    SELECT COUNT(*) FROM job_queue 
    WHERE job_type = 'telegram_command' AND status = 'completed'
""")
completed = cur.fetchone()[0]
print(f"    Completed telegram_command jobs: {completed}")

conn.close()






















