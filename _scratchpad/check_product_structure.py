"""Временный скрипт для проверки структуры таблицы product"""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('77.233.222.214', username='root', password='HuPtNj39', timeout=10)

# Проверяем все колонки с cover
cmd = 'docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e "SHOW COLUMNS FROM product;" 2>&1 | grep -v Warning'
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
output = stdout.read().decode()
print("Структура таблицы product:")
print(output)

# Проверяем, есть ли поле cover в других таблицах
cmd2 = "docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e \"SHOW TABLES LIKE '%product%';\" 2>&1 | grep -v Warning"
stdin2, stdout2, stderr2 = ssh.exec_command(cmd2, timeout=30)
output2 = stdout2.read().decode()
print("\nТаблицы с product:")
print(output2)

ssh.close()

