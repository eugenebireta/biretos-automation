#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка доступности InSales API и получение тестовых товаров.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict

# Добавляем путь к модулям
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from clients import InsalesClient, InsalesClientError, InsalesConfig


def check_insales_api(config_path: Path, limit: int = 5) -> Dict[str, Any]:
    """
    Проверяет доступность InSales API и получает тестовые товары.
    
    Returns:
        dict: Результат проверки с детальной информацией
    """
    result = {
        "api_available": False,
        "status_code": None,
        "error": None,
        "products_count": 0,
        "products": [],
        "rate_limit_info": None,
        "auth_status": "unknown",
        "total_products": None
    }
    
    try:
        # Загрузка конфигурации
        if not config_path.exists():
            result["error"] = f"Конфигурация не найдена: {config_path}"
            return result
        
        with config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)
        
        insales_config = config.get("insales", {})
        if not insales_config:
            result["error"] = "Секция 'insales' не найдена в конфигурации"
            return result
        
        # Создание клиента
        client_config = InsalesConfig(
            host=insales_config["host"],
            api_key=insales_config["api_key"],
            api_password=insales_config["api_password"],
        )
        
        client = InsalesClient(client_config, timeout=30)
        
        # Попытка получить товары
        try:
            products = client.get_products(page=1, per_page=limit)
            
            # Проверка структуры ответа
            if isinstance(products, list):
                result["products"] = products[:limit]
                result["products_count"] = len(products)
            elif isinstance(products, dict):
                # API может вернуть {"products": [...]}
                products_list = products.get("products", [])
                result["products"] = products_list[:limit]
                result["products_count"] = len(products_list)
            else:
                result["products"] = []
                result["products_count"] = 0
            
            # Если получили хотя бы один товар - API доступен
            result["api_available"] = True
            result["auth_status"] = "success"
            result["status_code"] = 200
            
            # Попытка получить общее количество товаров для проверки лимитов
            try:
                total_count = client.get_products_count()
                if total_count is not None:
                    result["total_products"] = total_count
            except Exception:
                pass  # Игнорируем ошибку получения количества
            
        except InsalesClientError as e:
            error_msg = str(e)
            result["error"] = error_msg
            
            # Определение типа ошибки
            if "401" in error_msg or "Unauthorized" in error_msg:
                result["auth_status"] = "unauthorized"
                result["status_code"] = 401
            elif "403" in error_msg or "Forbidden" in error_msg:
                result["auth_status"] = "forbidden"
                result["status_code"] = 403
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                result["auth_status"] = "rate_limited"
                result["status_code"] = 429
                result["rate_limit_info"] = "Превышен лимит запросов"
            elif "404" in error_msg:
                result["status_code"] = 404
                result["error"] = "Эндпоинт не найден"
            else:
                result["status_code"] = "unknown"
            
            result["api_available"] = False
            
        except Exception as e:
            result["error"] = f"Неожиданная ошибка: {str(e)}"
            result["api_available"] = False
    
    except Exception as e:
        result["error"] = f"Ошибка при проверке: {str(e)}"
        result["api_available"] = False
    
    return result


def print_result(result: Dict[str, Any]) -> None:
    """Выводит результат проверки в читаемом виде."""
    print("=" * 60)
    print("ПРОВЕРКА InSales API")
    print("=" * 60)
    
    if result["api_available"]:
        print("✅ InSales API: ДОСТУПЕН")
        print(f"   Статус авторизации: {result['auth_status']}")
        print(f"   HTTP статус: {result['status_code']}")
        print(f"   Получено товаров: {result['products_count']}")
        
        if result.get("total_products") is not None:
            print(f"   Всего товаров в магазине: {result['total_products']}")
        
        if result["products"]:
            print("\n   Примеры товаров:")
            for i, product in enumerate(result["products"][:3], 1):
                title = product.get("title", "Без названия")
                product_id = product.get("id", "N/A")
                variants_count = len(product.get("variants", []))
                print(f"   {i}. ID: {product_id}, Название: {title[:50]}, Вариантов: {variants_count}")
    else:
        print("❌ InSales API: НЕДОСТУПЕН")
        print(f"   Причина: {result['error']}")
        print(f"   Статус авторизации: {result['auth_status']}")
        if result["status_code"]:
            print(f"   HTTP статус: {result['status_code']}")
        
        if result["status_code"] == 401:
            print("\n   ⚠️  Ошибка авторизации (401):")
            print("      - Проверьте правильность API ключа и пароля")
            print("      - Убедитесь, что ключи не истекли")
        elif result["status_code"] == 403:
            print("\n   ⚠️  Доступ запрещён (403):")
            print("      - Проверьте права доступа API ключа")
        elif result["status_code"] == 429:
            print("\n   ⚠️  Превышен лимит запросов (429):")
            print("      - Подождите несколько минут перед повторной попыткой")
    
    print("=" * 60)


def main():
    """Главная функция."""
    # Путь к конфигурации
    config_path = ROOT / "config.json"
    
    if not config_path.exists():
        print(f"❌ Ошибка: Конфигурация не найдена: {config_path}")
        return 1
    
    # Выполнение проверки
    result = check_insales_api(config_path, limit=5)
    
    # Вывод результата
    print_result(result)
    
    # Возврат кода выхода
    return 0 if result["api_available"] else 1


if __name__ == "__main__":
    sys.exit(main())







