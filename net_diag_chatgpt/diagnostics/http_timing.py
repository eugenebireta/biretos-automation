#!/usr/bin/env python3
"""
HTTP timing диагностика через curl -w.
Измеряет DNS lookup, connect, SSL, TTFB, total time.
"""
import subprocess
import json
import re
from typing import Dict, Any, Optional
from . import test_result, TestStatus


def test_http_timing(url: str = "https://chatgpt.com", proxy: Optional[str] = None, mode: str = "direct") -> Dict[str, Any]:
    """
    Тест HTTP timing.
    
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
            name="http_timing",
            status=TestStatus.ERROR,
            details="curl not found or not accessible",
            mode=mode
        )
    
    # Формат вывода curl -w
    format_str = (
        '{"dns":%{time_namelookup},'
        '"connect":%{time_connect},'
        '"ssl":%{time_appconnect},'
        '"ttfb":%{time_starttransfer},'
        '"total":%{time_total},'
        '"http_code":%{http_code},'
        '"size_download":%{size_download}}'
    )
    
    cmd = [
        'curl',
        '-w', format_str,
        '-s',
        '-o', '/dev/null',
        '--max-time', '10',
        url
    ]
    
    if proxy:
        cmd.extend(['--proxy', f'socks5://{proxy}'])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15
        )
        
        # Парсим JSON из stderr
        output = result.stderr.strip()
        if not output:
            output = result.stdout.strip()
        
        # Ищем JSON в выводе
        json_match = re.search(r'\{[^}]+\}', output)
        if json_match:
            timing = json.loads(json_match.group())
            # Конвертируем секунды в миллисекунды
            metrics = {
                'dns_ms': round(float(timing.get('dns', 0)) * 1000, 2),
                'connect_ms': round(float(timing.get('connect', 0)) * 1000, 2),
                'ssl_ms': round(float(timing.get('ssl', 0)) * 1000, 2),
                'ttfb_ms': round(float(timing.get('ttfb', 0)) * 1000, 2),
                'total_ms': round(float(timing.get('total', 0)) * 1000, 2),
                'http_code': int(timing.get('http_code', 0)),
                'size_bytes': int(timing.get('size_download', 0))
            }
            
            status = TestStatus.SUCCESS
            details = f"HTTP {metrics['http_code']}. TTFB: {metrics['ttfb_ms']:.2f}ms, Total: {metrics['total_ms']:.2f}ms"
            
            if metrics['http_code'] == 0:
                status = TestStatus.ERROR
                details = "No HTTP response received"
            elif metrics['connect_ms'] == 0:
                status = TestStatus.ERROR
                details = "Failed to measure connect time"
            
            return test_result(
                name="http_timing",
                status=status,
                metrics=metrics,
                details=details,
                mode=mode
            )
        
        return test_result(
            name="http_timing",
            status=TestStatus.ERROR,
            details="Failed to parse curl timing output",
            mode=mode
        )
    
    except subprocess.TimeoutExpired:
        return test_result(
            name="http_timing",
            status=TestStatus.ERROR,
            details="HTTP request timeout (>15s)",
            mode=mode
        )
    except Exception as e:
        return test_result(
            name="http_timing",
            status=TestStatus.ERROR,
            details=f"Unexpected error: {str(e)}",
            mode=mode
        )


if __name__ == '__main__':
    import sys
    import json
    
    proxy = sys.argv[1] if len(sys.argv) > 1 else None
    mode = "proxy" if proxy else "direct"
    
    result = test_http_timing(proxy=proxy, mode=mode)
    print(json.dumps(result, indent=2))
