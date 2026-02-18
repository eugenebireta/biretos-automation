"""Тестовый скрипт для проверки SQL запроса"""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('77.233.222.214', username='root', password='HuPtNj39', timeout=10)

query = """
SELECT
  HEX(p.id) as product_id,
  HEX(p.cover) as current_cover,
  'WRONG_MEDIA_ID' as problem_type
FROM product p
LEFT JOIN product_media pm ON pm.id = p.cover
INNER JOIN media m ON m.id = p.cover
WHERE p.cover IS NOT NULL
  AND pm.id IS NULL
  AND m.id IS NOT NULL
ORDER BY HEX(p.id);
"""

escaped_query = query.replace('"', '\\"').replace('\n', ' ')
cmd = f'docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e "{escaped_query}" 2>&1 | grep -v Warning'

stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
output = stdout.read().decode('utf-8', errors='ignore').strip()
error = stderr.read().decode('utf-8', errors='ignore').strip()

print("Результат запроса:")
print(output)
if error:
    print("\nОшибки:")
    print(error)

ssh.close()

