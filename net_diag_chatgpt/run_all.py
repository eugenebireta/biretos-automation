#!/usr/bin/env python3
"""
Главный runner диагностики ChatGPT USA Route.
Запускает все тесты в режимах direct и/или proxy, сохраняет результаты.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from diagnostics import tcp_rtt, tls_handshake, dns_leak, http_timing, ws_echo, playwright_har, idle_tcp
from utils.xray_render import render_xray_configs


def load_env(base_dir: Path) -> Dict[str, str]:
    """Загружает переменные окружения."""
    env = {}
    env_file = base_dir / '.env'
    
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    env[key.strip()] = value.strip()
    
    # Переопределяем системными переменными
    for key in list(env.keys()):
        sys_value = os.getenv(key)
        if sys_value:
            env[key] = sys_value
    
    return env


def run_tests(mode: str, proxy: Optional[str], base_dir: Path, output_dir: Path, env: Dict[str, str]) -> List[Dict[str, Any]]:
    """Запускает все тесты в указанном режиме."""
    results = []
    
    url = "https://chatgpt.com"
    host = "chatgpt.com"
    
    # TCP RTT
    print(f"[{mode}] Running TCP RTT test...")
    results.append(tcp_rtt.test_tcp_rtt(url=url, proxy=proxy, mode=mode))
    
    # TLS Handshake
    print(f"[{mode}] Running TLS handshake test...")
    results.append(tls_handshake.test_tls_handshake(host=host, proxy=proxy, mode=mode))
    
    # DNS Leak
    print(f"[{mode}] Running DNS leak test...")
    results.append(dns_leak.test_dns_leak(domain=host, proxy=proxy, mode=mode))
    
    # HTTP Timing
    print(f"[{mode}] Running HTTP timing test...")
    results.append(http_timing.test_http_timing(url=url, proxy=proxy, mode=mode))
    
    # WebSocket Echo (опционально)
    ws_url = env.get('WS_ECHO_URL')
    print(f"[{mode}] Running WebSocket echo test...")
    results.append(ws_echo.test_ws_echo(ws_url=ws_url, proxy=proxy, mode=mode))
    
    # Playwright HAR (опционально)
    print(f"[{mode}] Running Playwright HAR test...")
    results.append(playwright_har.test_playwright_har(url=url, proxy=proxy, output_dir=output_dir, mode=mode))
    
    # Idle TCP
    print(f"[{mode}] Running Idle TCP test...")
    results.append(idle_tcp.test_idle_tcp(host=host, proxy=proxy, mode=mode))
    
    return results


def generate_report(results: List[Dict[str, Any]], output_dir: Path) -> None:
    """Генерирует отчеты в JSON и Markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Сохраняем JSON
    json_path = output_dir / 'report.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'results': results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"JSON report saved to: {json_path.resolve()}")
    
    # Генерируем Markdown отчет
    md_path = output_dir / 'report.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("# ChatGPT USA Route Diagnostic Report\n\n")
        f.write(f"**Generated:** {datetime.utcnow().isoformat()}\n\n")
        
        # Группируем по режимам
        direct_results = [r for r in results if r.get('mode') == 'direct']
        proxy_results = [r for r in results if r.get('mode') == 'proxy']
        
        if direct_results and proxy_results:
            f.write("## Comparison: Direct vs Proxy\n\n")
            f.write("| Test | Direct Status | Proxy Status | Improvement |\n")
            f.write("|------|---------------|--------------|-------------|\n")
            
            # Создаем словарь для быстрого поиска
            direct_dict = {r['name']: r for r in direct_results}
            proxy_dict = {r['name']: r for r in proxy_results}
            
            all_tests = set(direct_dict.keys()) | set(proxy_dict.keys())
            
            for test_name in sorted(all_tests):
                direct = direct_dict.get(test_name, {})
                proxy = proxy_dict.get(test_name, {})
                
                direct_status = direct.get('status', 'N/A')
                proxy_status = proxy.get('status', 'N/A')
                
                # Вычисляем улучшение (если есть метрики)
                improvement = "N/A"
                if direct.get('metrics') and proxy.get('metrics'):
                    # Пытаемся найти ключевые метрики для сравнения
                    for key in ['connect_ms', 'ttfb_ms', 'total_ms', 'handshake_ms']:
                        if key in direct['metrics'] and key in proxy['metrics']:
                            direct_val = direct['metrics'][key]
                            proxy_val = proxy['metrics'][key]
                            if direct_val > 0:
                                pct = ((direct_val - proxy_val) / direct_val) * 100
                                improvement = f"{pct:+.1f}%"
                                break
                
                f.write(f"| {test_name} | {direct_status} | {proxy_status} | {improvement} |\n")
        
        f.write("\n## Detailed Results\n\n")
        
        for result in results:
            f.write(f"### {result['name']} ({result.get('mode', 'unknown')})\n\n")
            f.write(f"**Status:** {result['status']}\n\n")
            f.write(f"**Details:** {result.get('details', 'N/A')}\n\n")
            
            if result.get('metrics'):
                f.write("**Metrics:**\n\n")
                f.write("```json\n")
                f.write(json.dumps(result['metrics'], indent=2))
                f.write("\n```\n\n")
    
    print(f"Markdown report saved to: {md_path.resolve()}")


def main():
    parser = argparse.ArgumentParser(description='ChatGPT USA Route Diagnostic Runner')
    parser.add_argument('--mode', choices=['direct', 'proxy', 'both'], default='both',
                        help='Test mode: direct, proxy, or both (default: both)')
    parser.add_argument('--render-only', action='store_true',
                        help='Only render X-Ray configs, do not run tests')
    parser.add_argument('--out', type=str, default=None,
                        help='Output directory (default: reports/<timestamp>)')
    parser.add_argument('--proxy-socks5', type=str, default=None,
                        help='SOCKS5 proxy address (default: from env PROXY_SOCKS5_HOST:PORT)')
    
    args = parser.parse_args()
    
    base_dir = Path(__file__).parent.resolve()
    env = load_env(base_dir)
    
    # Определяем proxy
    if args.proxy_socks5:
        proxy = args.proxy_socks5
    else:
        proxy_host = env.get('PROXY_SOCKS5_HOST', '127.0.0.1')
        proxy_port = env.get('PROXY_SOCKS5_PORT', '10808')
        proxy = f"{proxy_host}:{proxy_port}" if proxy_host and proxy_port else None
    
    # Рендерим конфиги
    runtime_dir = base_dir / '.runtime'
    runtime_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        rendered = render_xray_configs(base_dir, runtime_dir)
        print(f"Rendered {len(rendered)} X-Ray configs to {runtime_dir.resolve()}")
    except Exception as e:
        print(f"WARNING: Failed to render X-Ray configs: {e}", file=sys.stderr)
        if args.render_only:
            sys.exit(1)
    
    if args.render_only:
        print("Config rendering complete. Exiting.")
        sys.exit(0)
    
    # Определяем output директорию
    if args.out:
        output_dir = Path(args.out).resolve()
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = base_dir / 'reports' / timestamp
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Запускаем тесты
    all_results = []
    
    if args.mode in ['direct', 'both']:
        print("\n=== Running tests in DIRECT mode ===\n")
        direct_results = run_tests('direct', None, base_dir, output_dir, env)
        all_results.extend(direct_results)
    
    if args.mode in ['proxy', 'both']:
        if not proxy:
            # Создаем FAIL результаты для всех тестов в proxy режиме
            print(f"\n=== Running tests in PROXY mode (proxy unavailable) ===\n")
            from diagnostics import test_result, TestStatus
            url = "https://chatgpt.com"
            host = "chatgpt.com"
            
            proxy_fail_results = [
                test_result("tcp_rtt", TestStatus.FAIL, {"proxy_available": False}, "Proxy not configured or unavailable", "proxy"),
                test_result("tls_handshake", TestStatus.FAIL, {"proxy_available": False}, "Proxy not configured or unavailable", "proxy"),
                test_result("dns_leak", TestStatus.FAIL, {"proxy_available": False}, "Proxy not configured or unavailable", "proxy"),
                test_result("http_timing", TestStatus.FAIL, {"proxy_available": False}, "Proxy not configured or unavailable", "proxy"),
                test_result("ws_echo", TestStatus.FAIL, {"proxy_available": False, "skipped": True}, "Proxy not configured or unavailable", "proxy"),
                test_result("playwright_har", TestStatus.FAIL, {"proxy_available": False, "skipped": True}, "Proxy not configured or unavailable", "proxy"),
                test_result("idle_tcp", TestStatus.FAIL, {"proxy_available": False}, "Proxy not configured or unavailable", "proxy"),
            ]
            all_results.extend(proxy_fail_results)
        else:
            print(f"\n=== Running tests in PROXY mode (via {proxy}) ===\n")
            proxy_results = run_tests('proxy', proxy, base_dir, output_dir, env)
            all_results.extend(proxy_results)
    
    # Генерируем отчеты
    print("\n=== Generating reports ===\n")
    generate_report(all_results, output_dir)
    
    # Выводим сводку
    print("\n=== Summary ===\n")
    success_count = sum(1 for r in all_results if r['status'] == 'SUCCESS')
    fail_count = sum(1 for r in all_results if r['status'] == 'FAIL')
    error_count = sum(1 for r in all_results if r['status'] == 'ERROR')
    
    print(f"SUCCESS: {success_count}")
    print(f"FAIL: {fail_count}")
    print(f"ERROR: {error_count}")
    print(f"\nReports saved to: {output_dir.resolve()}")


if __name__ == '__main__':
    main()
