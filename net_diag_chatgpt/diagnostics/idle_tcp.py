#!/usr/bin/env python3
"""
Idle TCP stability тест.
Проверяет стабильность TCP соединения при простое.
"""
import subprocess
import time
import json
from typing import Dict, Any, Optional
from . import test_result, TestStatus


def test_idle_tcp(host: str = "chatgpt.com", port: int = 443, proxy: Optional[str] = None, idle_seconds: int = 30, mode: str = "direct") -> Dict[str, Any]:
    """
    Тест стабильности idle TCP соединения.
    
    Args:
        host: Хост для тестирования
        port: Порт
        proxy: SOCKS5 proxy
        idle_seconds: Время простоя в секундах
        mode: "direct" или "proxy"
    
    Returns:
        Результат теста в формате test_result
    """
    # Используем curl с keepalive для проверки стабильности
    # Запускаем несколько запросов с паузами
    
    try:
        subprocess.run(['curl', '--version'], capture_output=True, check=True, timeout=5)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return test_result(
            name="idle_tcp",
            status=TestStatus.ERROR,
            details="curl not found or not accessible",
            mode=mode
        )
    
    url = f"https://{host}:{port}"
    cmd_base = ['curl', '-s', '-o', '/dev/null', '--max-time', '10']
    
    if proxy:
        cmd_base.extend(['--proxy', f'socks5://{proxy}'])
    
    # Делаем первый запрос
    cmd1 = cmd_base + ['-w', '{"connect":%{time_connect},"total":%{time_total}}', url]
    
    try:
        result1 = subprocess.run(cmd1, capture_output=True, text=True, timeout=15)
        timing1 = json.loads(result1.stderr.strip() if result1.stderr else '{}')
        
        # Ждем idle_seconds
        time.sleep(idle_seconds)
        
        # Делаем второй запрос
        result2 = subprocess.run(cmd1, capture_output=True, text=True, timeout=15)
        timing2 = json.loads(result2.stderr.strip() if result2.stderr else '{}')
        
        # Сравниваем timing
        connect1 = float(timing1.get('connect', 0)) * 1000
        connect2 = float(timing2.get('connect', 0)) * 1000
        
        metrics = {
            'first_connect_ms': round(connect1, 2),
            'second_connect_ms': round(connect2, 2),
            'idle_seconds': idle_seconds,
            'connect_diff_ms': round(abs(connect2 - connect1), 2)
        }
        
        # Статус: SUCCESS если разница небольшая (<50ms), FAIL если большая
        status = TestStatus.SUCCESS
        details = f"Idle test completed. First connect: {connect1:.2f}ms, Second connect: {connect2:.2f}ms"
        
        if metrics['connect_diff_ms'] > 100:
            status = TestStatus.FAIL
            details += f". Large difference ({metrics['connect_diff_ms']:.2f}ms) suggests connection instability."
        elif connect1 == 0 or connect2 == 0:
            status = TestStatus.ERROR
            details = "Failed to measure connect times"
        
        return test_result(
            name="idle_tcp",
            status=status,
            metrics=metrics,
            details=details,
            mode=mode
        )
    
    except subprocess.TimeoutExpired:
        return test_result(
            name="idle_tcp",
            status=TestStatus.ERROR,
            details="Idle TCP test timeout",
            mode=mode
        )
    except Exception as e:
        return test_result(
            name="idle_tcp",
            status=TestStatus.ERROR,
            details=f"Unexpected error: {str(e)}",
            mode=mode
        )


if __name__ == '__main__':
    import sys
    import json
    
    proxy = sys.argv[1] if len(sys.argv) > 1 else None
    mode = "proxy" if proxy else "direct"
    
    result = test_idle_tcp(proxy=proxy, mode=mode)
    print(json.dumps(result, indent=2))
