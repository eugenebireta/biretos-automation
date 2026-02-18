#!/usr/bin/env python3
"""
DNS leak диагностика через nslookup.
Проверяет, какой DNS resolver используется для chatgpt.com.
"""
import subprocess
import re
from typing import Dict, Any, Optional
from . import test_result, TestStatus


def get_dns_resolver(domain: str = "chatgpt.com", proxy: Optional[str] = None) -> Dict[str, Any]:
    """
    Определяет DNS resolver через nslookup.
    
    Args:
        domain: Домен для резолва
        proxy: SOCKS5 proxy (не поддерживается nslookup напрямую)
    
    Returns:
        Информация о DNS resolver
    """
    if proxy:
        # nslookup не поддерживает SOCKS5 proxy
        return {
            'resolver': None,
            'ip': None,
            'error': 'nslookup does not support SOCKS5 proxy. Cannot verify DNS leak through proxy.'
        }
    
    try:
        # Запускаем nslookup
        result = subprocess.run(
            ['nslookup', domain],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        output = result.stdout + result.stderr
        
        # Парсим resolver из вывода
        # nslookup показывает "Server: <resolver>" в первой строке
        resolver_match = re.search(r'Server:\s*(\S+)', output)
        resolver = resolver_match.group(1) if resolver_match else None
        
        # Парсим IP адреса
        ip_matches = re.findall(r'\d+\.\d+\.\d+\.\d+', output)
        ips = list(set(ip_matches)) if ip_matches else []
        
        return {
            'resolver': resolver,
            'ips': ips,
            'output': output
        }
    
    except subprocess.TimeoutExpired:
        return {'error': 'nslookup timeout'}
    except FileNotFoundError:
        return {'error': 'nslookup not found'}
    except Exception as e:
        return {'error': str(e)}


def test_dns_leak(domain: str = "chatgpt.com", proxy: Optional[str] = None, mode: str = "direct") -> Dict[str, Any]:
    """
    Тест DNS leak.
    
    Args:
        domain: Домен для тестирования
        proxy: SOCKS5 proxy
        mode: "direct" или "proxy"
    
    Returns:
        Результат теста в формате test_result
    """
    dns_info = get_dns_resolver(domain, proxy)
    
    if 'error' in dns_info:
        if proxy:
            # В proxy режиме невозможно проверить DNS leak через nslookup
            return test_result(
                name="dns_leak",
                status=TestStatus.FAIL,
                metrics={'resolver': None, 'ips': []},
                details=f"Cannot verify DNS leak through proxy: {dns_info['error']}. DNS should be resolved through X-Ray (1.1.1.1) when proxy is active.",
                mode=mode
            )
        else:
            return test_result(
                name="dns_leak",
                status=TestStatus.ERROR,
                metrics={},
                details=dns_info['error'],
                mode=mode
            )
    
    resolver = dns_info.get('resolver')
    ips = dns_info.get('ips', [])
    
    # Проверяем, является ли resolver системным (не через X-Ray)
    # В proxy режиме resolver должен быть через X-Ray (1.1.1.1), но мы не можем это проверить через nslookup
    # Поэтому в proxy режиме всегда FAIL с объяснением
    
    if proxy:
        return test_result(
            name="dns_leak",
            status=TestStatus.FAIL,
            metrics={'resolver': resolver, 'ips': ips},
            details="Cannot confirm DNS resolution through proxy via nslookup. Verify manually that X-Ray DNS (1.1.1.1) is used for chatgpt.com when proxy is active.",
            mode=mode
        )
    
    # В direct режиме просто фиксируем resolver
    return test_result(
        name="dns_leak",
        status=TestStatus.SUCCESS,
        metrics={'resolver': resolver, 'ips': ips},
        details=f"DNS resolved via {resolver or 'system default'}. IPs: {', '.join(ips) if ips else 'none'}",
        mode=mode
    )


if __name__ == '__main__':
    import sys
    import json
    
    proxy = sys.argv[1] if len(sys.argv) > 1 else None
    mode = "proxy" if proxy else "direct"
    
    result = test_dns_leak(proxy=proxy, mode=mode)
    print(json.dumps(result, indent=2))
