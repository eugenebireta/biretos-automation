"""Проверка всех thumbnail sizes"""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('77.233.222.214', username='root', password='HuPtNj39', timeout=30)

command = 'docker exec shopware mysql -h 127.0.0.1 -u root -proot shopware -e "SELECT width, height, HEX(id) as id_hex FROM thumbnail_size ORDER BY width, height;" 2>&1 | grep -v Warning'
stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
output = stdout.read().decode()
errors = stderr.read().decode()

print("Все thumbnail sizes:")
print(output)
if errors:
    print("Ошибки:")
    print(errors)

ssh.close()








