"""Проверка созданных thumbnail sizes"""
import paramiko

host = "77.233.222.214"
ssh_username = "root"
ssh_password = "HuPtNj39"
container_name = "shopware"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=ssh_username, password=ssh_password, timeout=30)

print("=" * 60)
print("ПРОВЕРКА THUMBNAIL SIZES")
print("=" * 60)

# Проверяем все размеры
command = f"docker exec {container_name} mysql -h 127.0.0.1 -u root -proot shopware -e 'SELECT width, height FROM thumbnail_size ORDER BY width, height;' 2>&1 | grep -v Warning"
stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
output = stdout.read().decode()

if output:
    sizes = [line for line in output.strip().split('\n') if line and not line.startswith('width')]
    print(f"\nНайдено размеров: {len(sizes)}")
    print("\nСозданные thumbnail sizes:")
    for line in sizes:
        parts = line.split('\t')
        if len(parts) >= 2:
            print(f"  - {parts[0]}x{parts[1]}")
else:
    print("\n⚠️ Размеры не найдены")

ssh.close()

print("\n" + "=" * 60)








