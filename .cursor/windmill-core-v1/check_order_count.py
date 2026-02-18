import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    dbname='biretos_automation',
    user='biretos_user',
    password='biretos_pass'
)
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM order_ledger')
count = cur.fetchone()[0]
print(f'order_ledger records: {count}')

if count > 0:
    cur.execute('SELECT order_id, insales_order_id FROM order_ledger LIMIT 1')
    row = cur.fetchone()
    print(f'Sample order_id: {row[0]}')
    print(f'Sample insales_order_id: {row[1]}')

conn.close()






















