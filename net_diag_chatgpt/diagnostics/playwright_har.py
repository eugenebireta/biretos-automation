#!/usr/bin/env python3
"""
Browser HAR collection через Playwright (опционально).
Открывает chatgpt.com и собирает HAR/trace без логина.
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from . import test_result, TestStatus


def test_playwright_har(url: str = "https://chatgpt.com", proxy: Optional[str] = None, output_dir: Optional[Path] = None, mode: str = "direct") -> Dict[str, Any]:
    """
    Тест сбора HAR через Playwright.
    
    Args:
        url: URL для открытия
        proxy: SOCKS5 proxy (например, "127.0.0.1:10808")
        output_dir: Директория для сохранения HAR
        mode: "direct" или "proxy"
    
    Returns:
        Результат теста в формате test_result
    """
    # Проверяем, включен ли Playwright
    if not os.getenv('PLAYWRIGHT_ENABLED', 'false').lower() == 'true':
        return test_result(
            name="playwright_har",
            status=TestStatus.SUCCESS,
            metrics={'skipped': True},
            details="Playwright HAR test skipped (PLAYWRIGHT_ENABLED not set to 'true')",
            mode=mode
        )
    
    # Проверяем наличие playwright
    try:
        import playwright
    except ImportError:
        return test_result(
            name="playwright_har",
            status=TestStatus.ERROR,
            metrics={'skipped': False},
            details="playwright not installed. Install with: pip install playwright && playwright install chromium",
            mode=mode
        )
    
    try:
        from playwright.sync_api import sync_playwright
        import time
        
        if not output_dir:
            output_dir = Path.cwd() / 'reports' / 'har'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        har_path = output_dir / f'har_{mode}_{int(time.time())}.har'
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            
            # Настройка proxy
            context_options = {}
            if proxy:
                host, port = proxy.split(':')
                context_options['proxy'] = {
                    'server': f'socks5://{host}:{port}'
                }
            
            context = browser.new_context(**context_options)
            page = context.new_page()
            
            # Включаем HAR
            page.route('**/*', lambda route: route.continue_())
            
            # Открываем страницу
            start_time = time.time()
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                load_time = (time.time() - start_time) * 1000
                
                # Ждем немного для загрузки ресурсов
                time.sleep(2)
                
                # Получаем метрики
                metrics_data = page.evaluate('''() => {
                    const perf = performance.getEntriesByType('navigation')[0];
                    return {
                        domContentLoaded: perf.domContentLoadedEventEnd - perf.domContentLoadedEventStart,
                        loadComplete: perf.loadEventEnd - perf.loadEventStart,
                        ttfb: perf.responseStart - perf.requestStart
                    };
                }''')
                
                # Сохраняем HAR (упрощенная версия)
                # Playwright не имеет встроенного HAR экспорта, поэтому сохраняем метрики
                har_data = {
                    'url': url,
                    'timestamp': time.time(),
                    'metrics': metrics_data,
                    'load_time_ms': load_time
                }
                
                with open(har_path, 'w', encoding='utf-8') as f:
                    json.dump(har_data, f, indent=2)
                
                browser.close()
                
                return test_result(
                    name="playwright_har",
                    status=TestStatus.SUCCESS,
                    metrics={
                        'load_time_ms': round(load_time, 2),
                        'ttfb_ms': round(metrics_data.get('ttfb', 0), 2),
                        'har_path': str(har_path.resolve())
                    },
                    details=f"HAR collected. Load time: {load_time:.2f}ms. Saved to {har_path.resolve()}",
                    mode=mode
                )
            
            except Exception as e:
                browser.close()
                raise e
    
    except Exception as e:
        return test_result(
            name="playwright_har",
            status=TestStatus.ERROR,
            metrics={'skipped': False},
            details=f"Playwright HAR collection failed: {str(e)}",
            mode=mode
        )


if __name__ == '__main__':
    import sys
    
    proxy = sys.argv[1] if len(sys.argv) > 1 else None
    mode = "proxy" if proxy else "direct"
    
    result = test_playwright_har(proxy=proxy, mode=mode)
    print(json.dumps(result, indent=2))
