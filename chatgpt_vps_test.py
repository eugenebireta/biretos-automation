#!/usr/bin/env python3
"""
Автоматический тест стабильности ChatGPT на VPS
"""
import time
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# Результаты теста
results = {
    "start_time": datetime.now().isoformat(),
    "page_load": {"status": "unknown", "time": None},
    "idle_test": {"status": "unknown", "duration": 600, "reconnections": 0, "errors": []},
    "after_idle": {"status": "unknown", "response_time": None, "success": False},
    "load_test": {"messages_sent": 0, "messages_received": 0, "response_times": [], "errors": []},
    "symptoms": {
        "connection_drops": 0,
        "page_reloads": 0,
        "load_errors": 0,
        "freezes": 0
    },
    "final_status": "UNKNOWN"
}

def log_event(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def setup_driver():
    """Настройка headless Chrome"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
    
    # Логирование для отслеживания сетевых событий
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        log_event(f"Ошибка настройки драйвера: {e}")
        # Попробовать без webdriver-manager
        try:
            driver = webdriver.Chrome(options=chrome_options)
            return driver
        except Exception as e2:
            log_event(f"Критическая ошибка: {e2}")
            return None

def check_network_events(driver):
    """Проверка сетевых событий из логов браузера"""
    events = []
    try:
        logs = driver.get_log('performance')
        for log in logs:
            message = json.loads(log['message'])
            if message['message']['method'] in ['Network.responseReceived', 'Network.requestFailed', 'Network.loadingFinished']:
                events.append(message['message'])
    except:
        pass
    return events

def test_chatgpt():
    driver = None
    try:
        log_event("=== НАЧАЛО ТЕСТА CHATGPT ===")
        
        # Настройка драйвера
        log_event("Настройка браузера...")
        driver = setup_driver()
        if not driver:
            results["final_status"] = "FAIL"
            results["symptoms"]["load_errors"] += 1
            return results
        
        # Этап 1: Загрузка страницы
        log_event("Загрузка chatgpt.com...")
        start_load = time.time()
        try:
            driver.get("https://chatgpt.com")
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            load_time = time.time() - start_load
            results["page_load"]["status"] = "success"
            results["page_load"]["time"] = round(load_time, 2)
            log_event(f"Страница загружена за {load_time:.2f} секунд")
        except TimeoutException:
            results["page_load"]["status"] = "timeout"
            results["symptoms"]["load_errors"] += 1
            log_event("Таймаут загрузки страницы")
        except Exception as e:
            results["page_load"]["status"] = "error"
            results["symptoms"]["load_errors"] += 1
            log_event(f"Ошибка загрузки: {e}")
        
        # Проверка наличия элементов ChatGPT
        time.sleep(5)  # Дополнительное время на загрузку
        
        # Этап 2: Idle тест (10 минут)
        log_event("Начало idle теста (10 минут)...")
        idle_start = time.time()
        initial_url = driver.current_url
        initial_title = driver.title
        
        # Мониторинг во время idle
        check_interval = 60  # Проверка каждую минуту
        idle_duration = 600  # 10 минут
        
        for i in range(0, idle_duration, check_interval):
            time.sleep(check_interval)
            elapsed = time.time() - idle_start
            
            # Проверка на перезагрузку страницы
            if driver.current_url != initial_url:
                results["symptoms"]["page_reloads"] += 1
                log_event(f"Обнаружена перезагрузка страницы на {elapsed:.0f} секунде")
            
            # Проверка сетевых событий
            events = check_network_events(driver)
            error_events = [e for e in events if 'error' in str(e).lower() or 'failed' in str(e).lower()]
            if error_events:
                results["idle_test"]["errors"].extend(error_events)
                results["symptoms"]["connection_drops"] += len(error_events)
                log_event(f"Обнаружены сетевые ошибки на {elapsed:.0f} секунде")
            
            log_event(f"Idle: {elapsed:.0f}/{idle_duration} секунд")
        
        results["idle_test"]["status"] = "completed"
        log_event("Idle тест завершен")
        
        # Этап 3: Тест после idle
        log_event("Отправка сообщения после idle...")
        try:
            # Попытка найти поле ввода (селекторы могут отличаться)
            start_response = time.time()
            
            # Ждем появления интерфейса ChatGPT
            time.sleep(3)
            
            # Проверяем, доступна ли страница
            current_url = driver.current_url
            if "chatgpt.com" not in current_url:
                results["after_idle"]["status"] = "redirected"
                results["after_idle"]["success"] = False
                log_event(f"Страница перенаправлена: {current_url}")
            else:
                # Пытаемся найти поле ввода
                try:
                    # Различные возможные селекторы
                    selectors = [
                        "textarea[placeholder*='Message']",
                        "textarea[data-id='root']",
                        "#prompt-textarea",
                        "textarea",
                        "[contenteditable='true']"
                    ]
                    
                    input_found = False
                    for selector in selectors:
                        try:
                            input_element = WebDriverWait(driver, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                            )
                            input_found = True
                            log_event(f"Найдено поле ввода: {selector}")
                            break
                        except:
                            continue
                    
                    if input_found:
                        # Отправка тестового сообщения
                        input_element.send_keys("Test message after idle")
                        time.sleep(1)
                        
                        # Поиск кнопки отправки
                        send_selectors = [
                            "button[data-testid='send-button']",
                            "button[aria-label*='Send']",
                            "button:has(svg)",
                            "button[type='submit']"
                        ]
                        
                        for selector in send_selectors:
                            try:
                                send_button = driver.find_element(By.CSS_SELECTOR, selector)
                                send_button.click()
                                break
                            except:
                                continue
                        
                        # Ждем ответа (максимум 30 секунд)
                        response_timeout = 30
                        response_received = False
                        start_wait = time.time()
                        
                        while time.time() - start_wait < response_timeout:
                            time.sleep(2)
                            # Проверяем наличие ответа (появление новых элементов)
                            try:
                                # Ищем индикаторы ответа
                                responses = driver.find_elements(By.CSS_SELECTOR, "[data-message-author-role='assistant']")
                                if responses:
                                    response_time = time.time() - start_response
                                    results["after_idle"]["status"] = "success"
                                    results["after_idle"]["response_time"] = round(response_time, 2)
                                    results["after_idle"]["success"] = True
                                    response_received = True
                                    log_event(f"Ответ получен за {response_time:.2f} секунд")
                                    break
                            except:
                                pass
                        
                        if not response_received:
                            results["after_idle"]["status"] = "timeout"
                            results["after_idle"]["success"] = False
                            results["symptoms"]["freezes"] += 1
                            log_event("Таймаут ожидания ответа после idle")
                    else:
                        results["after_idle"]["status"] = "input_not_found"
                        results["after_idle"]["success"] = False
                        log_event("Не найдено поле ввода")
                        
                except Exception as e:
                    results["after_idle"]["status"] = "error"
                    results["after_idle"]["success"] = False
                    log_event(f"Ошибка отправки сообщения: {e}")
        except Exception as e:
            results["after_idle"]["status"] = "error"
            results["after_idle"]["success"] = False
            log_event(f"Критическая ошибка после idle: {e}")
        
        # Этап 4: Нагрузочный тест (10 сообщений)
        log_event("Начало нагрузочного теста (10 сообщений)...")
        
        for i in range(1, 11):
            try:
                log_event(f"Отправка сообщения {i}/10...")
                msg_start = time.time()
                
                # Поиск поля ввода
                input_found = False
                for selector in selectors:
                    try:
                        input_element = driver.find_element(By.CSS_SELECTOR, selector)
                        input_found = True
                        break
                    except:
                        continue
                
                if not input_found:
                    results["load_test"]["errors"].append(f"Message {i}: Input not found")
                    log_event(f"Сообщение {i}: поле ввода не найдено")
                    continue
                
                # Очистка и ввод сообщения
                input_element.clear()
                input_element.send_keys(f"Test message {i}")
                time.sleep(0.5)
                
                # Отправка
                for selector in send_selectors:
                    try:
                        send_button = driver.find_element(By.CSS_SELECTOR, selector)
                        send_button.click()
                        break
                    except:
                        continue
                
                results["load_test"]["messages_sent"] += 1
                
                # Ожидание ответа
                response_received = False
                wait_start = time.time()
                while time.time() - wait_start < 30:
                    time.sleep(2)
                    try:
                        responses = driver.find_elements(By.CSS_SELECTOR, "[data-message-author-role='assistant']")
                        if len(responses) >= i:
                            response_time = time.time() - msg_start
                            results["load_test"]["messages_received"] += 1
                            results["load_test"]["response_times"].append(round(response_time, 2))
                            response_received = True
                            log_event(f"Сообщение {i}: ответ за {response_time:.2f} сек")
                            break
                    except:
                        pass
                
                if not response_received:
                    results["load_test"]["errors"].append(f"Message {i}: Timeout")
                    results["symptoms"]["freezes"] += 1
                    log_event(f"Сообщение {i}: таймаут ответа")
                
                time.sleep(2)  # Пауза между сообщениями
                
            except Exception as e:
                results["load_test"]["errors"].append(f"Message {i}: {str(e)}")
                log_event(f"Ошибка при отправке сообщения {i}: {e}")
        
        log_event("Нагрузочный тест завершен")
        
        # Определение итогового статуса
        if (results["page_load"]["status"] == "success" and
            results["after_idle"]["success"] and
            results["load_test"]["messages_received"] >= 8 and
            results["symptoms"]["connection_drops"] == 0 and
            results["symptoms"]["page_reloads"] == 0):
            results["final_status"] = "SUCCESS"
        elif (results["page_load"]["status"] == "success" and
              results["load_test"]["messages_received"] >= 5):
            results["final_status"] = "PARTIAL"
        else:
            results["final_status"] = "FAIL"
        
        results["end_time"] = datetime.now().isoformat()
        log_event(f"=== ТЕСТ ЗАВЕРШЕН: {results['final_status']} ===")
        
    except Exception as e:
        log_event(f"Критическая ошибка теста: {e}")
        results["final_status"] = "FAIL"
        results["symptoms"]["load_errors"] += 1
    finally:
        if driver:
            driver.quit()
    
    return results

if __name__ == "__main__":
    results = test_chatgpt()
    
    # Сохранение результатов
    output_file = "/tmp/chatgpt_test_results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n=== РЕЗУЛЬТАТЫ ТЕСТА ===")
    print(json.dumps(results, indent=2))
    print(f"\nРезультаты сохранены в {output_file}")



