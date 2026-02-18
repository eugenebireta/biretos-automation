#!/usr/bin/env python3
"""
TCP RTT диагностика через curl timing.
Измеряет connect и appconnect время без ICMP.
"""
import subprocess
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional
from . import test_result, TestStatus


def run_curl_timing(url: str, proxy: Optional[str] = None, timeout: int = 10) -> Dict[str, float]:
    """Запускает curl с timing и возвращает метрики."""
    cmd = [
        'curl',
        '-w', json.dumps({
            'time_namelookup': '%{time_namelookup}',
            'time_connect': '%{time_connect}',
            'time_appconnect': '%{time_appconnect}',
            'time_pretransfer': '%{time_pretransfer}',
            'time_starttransfer': '%{time_starttransfer}',
            'time_total': '%{time_total}',
            'http_code': '%{http_code}',
        }),
        '-s',
        '-o', '/dev/null',
        '--max-time', str(timeout),
        url
    ]
    
    if proxy:
        cmd.extend(['--proxy', f'socks5://{proxy}'])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 5
        )
        
        # Парсим JSON из stderr (curl пишет timing в stderr)
        output = result.stderr.strip()
        if not output:
            output = result.stdout.strip()
        
        # Ищем JSON в выводе
        json_match = re.search(r'\{[^}]+\}', output)
        if json_match:
            timing = json.loads(json_match.group())
            # Конвертируем секунды в миллисекунды
            return {
                'dns_ms': float(timing.get('time_namelookup', 0)) * 1000,
                'connect_ms': float(timing.get('time_connect', 0)) * 1000,
                'appconnect_ms': float(timing.get('time_appconnect', 0)) * 1000,
                'ttfb_ms': float(timing.get('time_starttransfer', 0)) * 1000,
                'total_ms': float(timing.get('time_total', 0)) * 1000,
                'http_code': int(timing.get('http_code', 0))
            }
        
        return {}
    except subprocess.TimeoutExpired:
        return {}
    except Exception as e:
        return {'error': str(e)}


def test_tcp_rtt(url: str = "https://chatgpt.com", proxy: Optional[str] = None, mode: str = "direct") -> Dict[str, Any]:
    """
    Тест TCP RTT.
    
    Args:
        url: URL для тестирования
        proxy: SOCKS5 proxy (например, "127.0.0.1:10808") или None
        mode: "direct" или "proxy"
    
    Returns:
        Результат теста в формате test_result
    """
    # Проверяем наличие curl
    try:
        subprocess.run(['curl', '--version'], capture_output=True, check=True, timeout=5)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return test_result(
            name="tcp_rtt",
            status=TestStatus.ERROR,
            details="curl not found or not accessible",
            mode=mode
        )
    
    # Запускаем несколько измерений
    results = []
    for i in range(3):
        timing = run_curl_timing(url, proxy, timeout=10)
        if timing and 'error' not in timing:
            results.append(timing)
    
    if not results:
        return test_result(
            name="tcp_rtt",
            status=TestStatus.ERROR,
            details="Failed to get timing results from curl",
            mode=mode
        )
    
    # Вычисляем средние значения
    avg_metrics = {
        'dns_ms': sum(r.get('dns_ms', 0) for r in results) / len(results),
        'connect_ms': sum(r.get('connect_ms', 0) for r in results) / len(results),
        'appconnect_ms': sum(r.get('appconnect_ms', 0) for r in results) / len(results),
        'ttfb_ms': sum(r.get('ttfb_ms', 0) for r in results) / len(results),
        'total_ms': sum(r.get('total_ms', 0) for r in results) / len(results),
    }
    
    # Проверяем HTTP код (403 от Cloudflare - это OK, мы измеряем timing)
    http_codes = [r.get('http_code', 0) for r in results]
    avg_metrics['http_code'] = http_codes[0] if http_codes else 0
    
    # Статус: SUCCESS если удалось измерить, даже при 403
    status = TestStatus.SUCCESS
    details = f"Measured {len(results)} samples. HTTP code: {avg_metrics['http_code']}"
    
    if avg_metrics['http_code'] == 0:
        status = TestStatus.ERROR
        details = "No HTTP response received"
    elif avg_metrics['connect_ms'] == 0:
        status = TestStatus.ERROR
        details = "Failed to measure connect time"
    
    return test_result(
        name="tcp_rtt",
        status=status,
        metrics=avg_metrics,
        details=details,
        mode=mode
    )


if __name__ == '__main__':
    import sys
    
    proxy = sys.argv[1] if len(sys.argv) > 1 else None
    mode = "proxy" if proxy else "direct"
    
    result = test_tcp_rtt(proxy=proxy, mode=mode)
    print(json.dumps(result, indent=2))
