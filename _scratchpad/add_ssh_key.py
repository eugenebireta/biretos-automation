#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Добавление SSH ключа на сервер"""
import subprocess
import sys
import os

def add_ssh_key(host, user, password, public_key_path):
    """Добавляет публичный SSH ключ на сервер"""
    if not os.path.exists(public_key_path):
        print(f"[ERROR] Файл ключа не найден: {public_key_path}")
        return False
    
    with open(public_key_path, 'r', encoding='utf-8') as f:
        public_key = f.read().strip()
    
    # Команда для добавления ключа
    cmd = f"""mkdir -p ~/.ssh && chmod 700 ~/.ssh && 
              if ! grep -q "{public_key.split()[1]}" ~/.ssh/authorized_keys 2>/dev/null; then
                  echo "{public_key}" >> ~/.ssh/authorized_keys && 
                  chmod 600 ~/.ssh/authorized_keys && 
                  echo "OK"
              else
                  echo "ALREADY_EXISTS"
              fi"""
    
    # Используем sshpass если доступен, иначе paramiko
    try:
        # Попробуем через sshpass (если установлен)
        result = subprocess.run(
            ["sshpass", "-p", password, "ssh", "-o", "StrictHostKeyChecking=no", 
             "-o", "UserKnownHostsFile=/dev/null", f"{user}@{host}", cmd],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print(f"[OK] SSH ключ добавлен на {user}@{host}")
            return True
    except FileNotFoundError:
        pass
    
    # Если sshpass недоступен, используем paramiko
    try:
        import paramiko
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=user, password=password, timeout=10)
        
        # Проверяем, есть ли уже ключ
        stdin, stdout, stderr = ssh.exec_command(
            f"grep -q '{public_key.split()[1]}' ~/.ssh/authorized_keys 2>/dev/null && echo EXISTS || echo NOT_EXISTS"
        )
        exists = stdout.read().decode().strip()
        
        if "EXISTS" in exists:
            print(f"[INFO] SSH ключ уже существует на {user}@{host}")
            ssh.close()
            return True
        
        # Добавляем ключ
        stdin, stdout, stderr = ssh.exec_command(
            "mkdir -p ~/.ssh && chmod 700 ~/.ssh"
        )
        stdout.read()
        
        stdin, stdout, stderr = ssh.exec_command(
            f'echo "{public_key}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
        )
        stdout.read()
        
        ssh.close()
        print(f"[OK] SSH ключ добавлен на {user}@{host}")
        return True
        
    except ImportError:
        print("[ERROR] Требуется paramiko. Установите: pip install paramiko")
        return False
    except Exception as e:
        print(f"[ERROR] Ошибка при добавлении ключа: {e}")
        return False

if __name__ == "__main__":
    host = "216.9.227.124"
    user = "root"
    password = "HuPtNj39"  # Из памяти
    key_path = os.path.expanduser("~/.ssh/id_ed25519.pub")
    
    if len(sys.argv) > 1:
        key_path = sys.argv[1]
    
    success = add_ssh_key(host, user, password, key_path)
    sys.exit(0 if success else 1)



