#!/usr/bin/env python3
"""
TLS handshake диагностика через openssl s_client.
"""
import subprocess
import re
import time
from typing import Dict, Any, Optional
from . import test_result, TestStatus


def test_tls_handshake(host: str = "chatgpt.com", port: int = 443, proxy: Optional[str] = None, mode: str = "direct") -> Dict[str, Any]:
    """
    Тест TLS handshake времени.
    
    Args:
        host: Хост для тестирования
        port: Порт (по умолчанию 443)
        proxy: SOCKS5 proxy (не поддерживается openssl напрямую, будет ERROR)
        mode: "direct" или "proxy"
    
    Returns:
        Результат теста в формате test_result
    """
    # openssl не поддерживает SOCKS5 proxy напрямую
    if proxy:
        return test_result(
            name="tls_handshake",
            status=TestStatus.ERROR,
            details="openssl s_client does not support SOCKS5 proxy. Use proxy-aware tool or test direct connection.",
            mode=mode
        )
    
    # Проверяем наличие openssl
    try:
        subprocess.run(['openssl', 'version'], capture_output=True, check=True, timeout=5)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return test_result(
            name="tls_handshake",
            status=TestStatus.ERROR,
            details="openssl not found or not accessible. Install OpenSSL to enable TLS handshake testing.",
            mode=mode
        )
    
    # Запускаем openssl s_client с замером времени
    cmd = [
        'openssl', 's_client',
        '-connect', f'{host}:{port}',
        '-servername', host,
        '-no_ticket',
        '-no_tls1_3'  # Для совместимости
    ]
    
    try:
        start_time = time.time()
        result = subprocess.run(
            cmd,
            input='\n',  # Отправляем пустую строку для завершения
            capture_output=True,
            text=True,
            timeout=10
        )
        elapsed = (time.time() - start_time) * 1000  # в миллисекундах
        
        # Парсим вывод openssl
        output = result.stdout + result.stderr
        
        # Ищем информацию о handshake
        verify_match = re.search(r'Verify return code: (\d+)', output)
        cipher_match = re.search(r'Cipher\s*:\s*(\S+)', output)
        
        metrics = {
            'handshake_ms': round(elapsed, 2),
            'verify_code': int(verify_match.group(1)) if verify_match else -1,
            'cipher': cipher_match.group(1) if cipher_match else "unknown"
        }
        
        # Статус: SUCCESS если handshake прошел
        status = TestStatus.SUCCESS
        details = f"TLS handshake completed in {metrics['handshake_ms']:.2f}ms"
        
        if result.returncode != 0:
            status = TestStatus.ERROR
            details = f"openssl s_client failed with return code {result.returncode}"
        elif metrics['verify_code'] != 0:
            details += f" (verify code: {metrics['verify_code']})"
        
        return test_result(
            name="tls_handshake",
            status=status,
            metrics=metrics,
            details=details,
            mode=mode
        )
    
    except subprocess.TimeoutExpired:
        return test_result(
            name="tls_handshake",
            status=TestStatus.ERROR,
            details="TLS handshake timeout (>10s)",
            mode=mode
        )
    except Exception as e:
        return test_result(
            name="tls_handshake",
            status=TestStatus.ERROR,
            details=f"Unexpected error: {str(e)}",
            mode=mode
        )


if __name__ == '__main__':
    import sys
    import json
    
    host = sys.argv[1] if len(sys.argv) > 1 else "chatgpt.com"
    result = test_tls_handshake(host=host)
    print(json.dumps(result, indent=2))
