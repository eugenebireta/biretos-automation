"""
RFQ Execution Core Business v1 - Deterministic RFQ Parser
Извлекает структурированные данные из RFQ текста через regex и эвристики
"""

import re
from typing import Dict, Any, List, Optional


def _to_e164(phone: str) -> Optional[str]:
    """Converts a Russian phone to simplified E.164 (+7XXXXXXXXXX)."""
    digits_only = ''.join(c for c in phone if c.isdigit())
    if len(digits_only) != 11:
        return None
    if digits_only[0] == '8':
        digits_only = '7' + digits_only[1:]
    if digits_only[0] != '7':
        return None
    return f"+{digits_only}"


def calculate_confidence(
    part_numbers: List[str],
    phones: List[str],
    emails: List[str],
    inns: List[str],
) -> Dict[str, Any]:
    """
    Lightweight deterministic confidence layer.

    Returns:
    {
      "confidence_overall": float,
      "confidence_breakdown": {
        "part_numbers": float,
        "phones": float,
        "emails": float,
        "inn": float
      }
    }
    """
    # part_numbers confidence
    part_count = len(part_numbers)
    if part_count >= 3:
        part_conf = 0.95
    elif part_count >= 1:
        part_conf = 0.9
    else:
        part_conf = 0.0

    # phones confidence (via E.164 validation)
    valid_phones = {p for p in (_to_e164(phone) for phone in phones) if p}
    if len(valid_phones) > 1:
        phones_conf = 0.95
    elif len(valid_phones) == 1:
        phones_conf = 0.9
    else:
        phones_conf = 0.2

    # emails confidence
    valid_emails = {
        email for email in emails
        if re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', email)
    }
    if len(valid_emails) > 1:
        emails_conf = 0.95
    elif len(valid_emails) == 1:
        emails_conf = 0.9
    else:
        emails_conf = 0.2

    # inn confidence
    valid_inn = any(isinstance(inn, str) and inn.isdigit() and len(inn) in (10, 12) for inn in inns)
    inn_conf = 0.9 if valid_inn else 0.2

    overall = (part_conf + phones_conf + emails_conf + inn_conf) / 4.0

    return {
        "confidence_overall": overall,
        "confidence_breakdown": {
            "part_numbers": part_conf,
            "phones": phones_conf,
            "emails": emails_conf,
            "inn": inn_conf,
        },
    }


def extract_part_numbers(text: str) -> List[str]:
    """
    Извлекает candidate part numbers из текста
    
    Паттерны:
    - Буквенно-цифровые последовательности (3+ символов)
    - Типичные форматы: ABC123, ABC-123, ABC_123, 12345-ABC
    
    Строгие правила фильтрации:
    - Должен содержать минимум 1 цифру
    - Должен содержать минимум 3 символа
    - Не должен быть только буквами
    - Не должен содержать кириллицу
    - Не должен содержать "@"
    - Не должен быть длиннее 30 символов
    - Не должен быть ИНН (10 или 12 цифр)
    - Не должен быть частью телефона
    """
    # Паттерны для part numbers (с дефисами и подчёркиваниями)
    patterns = [
        r'\b[A-Z0-9]+(?:[-_][A-Z0-9]+)+\b',  # С разделителями: ABC-123, ABC_123
        r'\b[A-Z]{2,}\d{2,}\b',  # 2+ буквы + 2+ цифры: ABC12
        r'\b\d{2,}[A-Z]{2,}\b',  # 2+ цифры + 2+ буквы: 12ABC
        r'\b[A-Z]+\d+[A-Z]+\b',  # Буквы-цифры-буквы: ABC123XYZ
    ]
    
    # Стоп-слова (исключаем очевидный мусор)
    stopwords = {
        'EMAIL', 'EXAMPLE', 'IVAN', 'PETROV', 'COM', 'RU', 'HTTP', 'HTTPS', 'WWW',
        'GMAIL', 'YANDEX', 'MAIL', 'INFO', 'ADMIN', 'SUPPORT'
    }
    
    part_numbers = set()
    
    for pattern in patterns:
        matches = re.findall(pattern, text.upper())
        for match in matches:
            cleaned = match.strip('-_').strip()
            
            # Фильтр 1: Длина (3-30 символов)
            if len(cleaned) < 3 or len(cleaned) > 30:
                continue
            
            # Фильтр 2: Должен содержать хотя бы одну цифру
            if not any(c.isdigit() for c in cleaned):
                continue
            
            # Фильтр 3: Не должен быть только буквами
            if cleaned.isalpha():
                continue
            
            # Фильтр 4: Не должен быть только цифрами
            if cleaned.isdigit():
                continue
            
            # Фильтр 5: Не должен быть ИНН (10 или 12 цифр)
            if cleaned.isdigit() and len(cleaned) in (10, 12):
                continue
            
            # Фильтр 6: Не должен содержать "@"
            if '@' in cleaned:
                continue
            
            # Фильтр 7: Не должен быть в стоп-словах
            if cleaned in stopwords:
                continue
            
            # Фильтр 8: Не должен содержать кириллицу
            if any('\u0400' <= c <= '\u04FF' for c in cleaned):
                continue
            
            # Фильтр 9: Не должен быть частью телефона (только цифры и дефисы)
            if all(c.isdigit() or c == '-' for c in cleaned):
                # Если это только цифры с дефисами, проверяем длину
                digits_only = cleaned.replace('-', '')
                if len(digits_only) >= 7:  # Телефонные номера обычно 7+ цифр
                    continue
            
            part_numbers.add(cleaned)
    
    # Фильтр 10: Удаляем подстроки (если "ABC123" и "ABC123-XYZ" оба есть, оставляем только "ABC123-XYZ")
    final_parts = []
    sorted_parts = sorted(part_numbers, key=len, reverse=True)  # Сортируем по длине (длинные первыми)
    
    for part in sorted_parts:
        # Проверяем, не является ли этот part подстрокой уже добавленного
        is_substring = False
        for existing in final_parts:
            if part in existing and part != existing:
                is_substring = True
                break
        
        if not is_substring:
            final_parts.append(part)
    
    return sorted(final_parts)


def extract_emails(text: str) -> List[str]:
    """Извлекает email адреса"""
    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(pattern, text, re.IGNORECASE)
    return list(set(emails))  # Удаляем дубликаты


def extract_phones(text: str) -> List[str]:
    """
    Извлекает телефоны (российские и международные форматы)
    
    Строгие правила фильтрации:
    - Минимум 10 цифр после удаления нецифровых символов
    - Не должен быть ИНН (ровно 10 или 12 цифр)
    - Дедупликация и нормализация
    """
    # Российские форматы (более строгие)
    ru_patterns = [
        r'\+7\s?\(?\d{3}\)?\s?\d{3}[\-\s]?\d{2}[\-\s]?\d{2}',  # +7 (XXX) XXX-XX-XX
        r'8\s?\(?\d{3}\)?\s?\d{3}[\-\s]?\d{2}[\-\s]?\d{2}',    # 8 (XXX) XXX-XX-XX
        r'\+7[\-\s]?\d{3}[\-\s]?\d{3}[\-\s]?\d{2}[\-\s]?\d{2}', # +7-XXX-XXX-XX-XX
    ]
    
    phones = set()
    
    for pattern in ru_patterns:
        matches = re.findall(pattern, text)
        phones.update(matches)
    
    # Фильтрация и нормализация
    filtered_phones = []
    
    for phone in phones:
        # Извлекаем только цифры для проверки
        digits_only = ''.join(c for c in phone if c.isdigit())
        
        # Фильтр 1: Минимум 10 цифр (российский номер)
        if len(digits_only) < 10:
            continue
        
        # Фильтр 2: Не должен быть ИНН (ровно 10 или 12 цифр без префикса)
        # Если это начинается с 7 или 8, то это телефон
        if digits_only[0] not in ('7', '8') and len(digits_only) in (10, 12):
            continue
        
        # Фильтр 3: Максимум 11 цифр (российский формат)
        if len(digits_only) > 11:
            continue
        
        filtered_phones.append(phone)
    
    # Дедупликация: нормализуем и удаляем дубликаты
    normalized = set()
    for phone in filtered_phones:
        # Нормализуем: оставляем +7, скобки, пробелы, дефисы
        normalized.add(phone.strip())
    
    return sorted(list(normalized))


def extract_inn(text: str) -> List[str]:
    """
    Извлекает ИНН (10 или 12 цифр)
    Эвристика: ищем последовательности цифр с маркерами "ИНН" или контекстом
    """
    # Паттерн: ИНН + 10 или 12 цифр
    inn_pattern = r'(?:ИНН|INN|inn)[\s:]*(\d{10}|\d{12})'
    matches = re.findall(inn_pattern, text, re.IGNORECASE)
    
    inns = list(set(matches))
    
    # Дополнительная эвристика: ищем изолированные 10-12 цифр с контекстом
    isolated_pattern = r'\b(\d{10}|\d{12})\b'
    isolated = re.findall(isolated_pattern, text)
    
    # Фильтруем: если рядом есть ключевые слова (компания, организация и т.д.)
    for candidate in isolated:
        # Простая проверка: если в радиусе 50 символов есть ключевые слова
        idx = text.find(candidate)
        if idx >= 0:
            context = text[max(0, idx-50):min(len(text), idx+50)].lower()
            keywords = ['инн', 'inn', 'компания', 'организация', 'юр', 'юридическ']
            if any(keyword in context for keyword in keywords):
                if candidate not in inns:
                    inns.append(candidate)
    
    return inns


def parse_rfq_deterministic(raw_text: str) -> Dict[str, Any]:
    """
    Детерминированный парсер RFQ текста
    
    Извлекает:
    - candidate_part_numbers
    - emails
    - phones
    - company_identifiers (ИНН)
    """
    if not raw_text:
        confidence = calculate_confidence([], [], [], [])
        return {
            "candidate_part_numbers": [],
            "emails": [],
            "phones": [],
            "company_identifiers": [],
            "confidence_overall": confidence["confidence_overall"],
            "confidence_breakdown": confidence["confidence_breakdown"],
        }
    
    # Извлекаем данные
    part_numbers = extract_part_numbers(raw_text)
    emails = extract_emails(raw_text)
    phones = extract_phones(raw_text)
    inns = extract_inn(raw_text)
    confidence = calculate_confidence(part_numbers, phones, emails, inns)
    
    return {
        "candidate_part_numbers": part_numbers,
        "emails": emails,
        "phones": phones,
        "company_identifiers": {
            "inn": inns
        },
        "confidence_overall": confidence["confidence_overall"],
        "confidence_breakdown": confidence["confidence_breakdown"],
    }


def merge_llm_results(deterministic_result: Dict[str, Any], llm_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Объединяет результаты deterministic parser и LLM
    
    LLM результат имеет приоритет, но дополняется deterministic данными
    """
    if not llm_result:
        return deterministic_result
    
    merged = deterministic_result.copy()
    
    # Merge part numbers (объединяем и удаляем дубликаты)
    llm_parts = llm_result.get("part_numbers", [])
    all_parts = list(set(merged.get("candidate_part_numbers", []) + llm_parts))
    merged["candidate_part_numbers"] = sorted(all_parts)
    
    # Merge emails
    llm_emails = llm_result.get("emails", [])
    all_emails = list(set(merged.get("emails", []) + llm_emails))
    merged["emails"] = all_emails
    
    # Merge phones
    llm_phones = llm_result.get("phones", [])
    all_phones = list(set(merged.get("phones", []) + llm_phones))
    merged["phones"] = all_phones
    
    # Merge company identifiers
    if "company_identifiers" in llm_result:
        merged["company_identifiers"] = {
            **merged.get("company_identifiers", {}),
            **llm_result["company_identifiers"]
        }
    
    # Добавляем метаданные о LLM
    merged["llm_used"] = True
    merged["llm_confidence"] = llm_result.get("confidence", None)
    
    return merged








