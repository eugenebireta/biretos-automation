"""
Procurement Domain - Conversion Layer

Преобразует raw extraction results (Dict[str, Any]) в типизированные CDM модели.

Phase 1b: Converter only (no integration with ru_worker.py yet).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

try:
    from .rfq_models import (
        RFQRequest,
        RFQItem,
        ContactInfo,
        CompanyInfo,
        RFQSource,
        RFQStatus,
        PartNumberConfidence,
    )
except ImportError:
    from rfq_models import (
        RFQRequest,
        RFQItem,
        ContactInfo,
        CompanyInfo,
        RFQSource,
        RFQStatus,
        PartNumberConfidence,
    )


def _normalize_part_number(part_number: str) -> str:
    """
    Нормализует партномер.
    
    Правила:
    - strip() — удаляет пробелы
    - upper() — приводит к верхнему регистру
    """
    return part_number.strip().upper()


def _deduplicate_part_numbers(part_numbers: List[str]) -> List[str]:
    """
    Удаляет дубликаты партномеров, сохраняя порядок первого появления.
    """
    seen = set()
    result = []
    for pn in part_numbers:
        normalized = _normalize_part_number(pn)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _extract_inn_from_company_identifiers(company_identifiers: Any) -> Optional[str]:
    """
    Извлекает ИНН из company_identifiers.
    
    Обрабатывает inconsistent форматы:
    - dict: {"inn": "1234567890"} → "1234567890"
    - dict: {"inn": ["1234567890"]} → "1234567890"
    - list: ["1234567890"] → игнорируется (legacy format)
    - None → None
    """
    if not company_identifiers:
        return None
    
    # Если это dict
    if isinstance(company_identifiers, dict):
        inn_value = company_identifiers.get("inn")
        
        # Если inn — это list, берём первый элемент
        if isinstance(inn_value, list):
            return inn_value[0] if inn_value else None
        
        # Если inn — это строка
        if isinstance(inn_value, str):
            return inn_value
        
        return None
    
    # Если это list (legacy format) — игнорируем
    if isinstance(company_identifiers, list):
        return None
    
    return None


def _determine_confidence(llm_used: bool) -> PartNumberConfidence:
    """
    Определяет уровень уверенности в извлечённых партномерах.
    
    Правила:
    - llm_used=True → MEDIUM (LLM-based extraction)
    - llm_used=False → HIGH (deterministic extraction)
    """
    return PartNumberConfidence.MEDIUM if llm_used else PartNumberConfidence.HIGH


def convert_to_canonical(
    merged_dict: Dict[str, Any],
    raw_text: str,
    source: str,
    request_id: UUID,
    created_at: datetime,
) -> RFQRequest:
    """
    Преобразует raw extraction results в типизированный RFQRequest.
    
    Args:
        merged_dict: Результат parse_rfq_deterministic() + merge_llm_results()
                     Ожидаемая структура:
                     {
                         "candidate_part_numbers": [...],
                         "emails": [...],
                         "phones": [...],
                         "company_identifiers": {...} или [...],
                         "llm_used": bool,
                         "llm_confidence": float or None
                     }
        raw_text: Исходный текст RFQ запроса
        source: Источник запроса ("telegram", "email", "manual")
        request_id: UUID для RFQ запроса
        created_at: Timestamp создания
    
    Returns:
        RFQRequest: Типизированная каноническая модель
    
    Fail-safe behavior:
        - Не бросает исключения при неожиданных форматах
        - Возвращает пустые значения для отсутствующих полей
        - Нормализует и дедуплицирует партномера
    """
    # Extract and normalize part numbers
    raw_part_numbers = merged_dict.get("candidate_part_numbers", [])
    if not isinstance(raw_part_numbers, list):
        raw_part_numbers = []
    
    normalized_part_numbers = _deduplicate_part_numbers(raw_part_numbers)
    
    # Extract contact info
    emails = merged_dict.get("emails", [])
    if not isinstance(emails, list):
        emails = []
    
    phones = merged_dict.get("phones", [])
    if not isinstance(phones, list):
        phones = []
    
    contact = ContactInfo(emails=emails, phones=phones)
    
    # Extract company info
    company_identifiers = merged_dict.get("company_identifiers")
    inn = _extract_inn_from_company_identifiers(company_identifiers)
    company = CompanyInfo(inn=inn)
    
    # Determine confidence level
    llm_used = merged_dict.get("llm_used", False)
    confidence = _determine_confidence(llm_used)
    
    # Build parsing metadata
    parsing_metadata = {}
    if "llm_used" in merged_dict:
        parsing_metadata["llm_used"] = merged_dict["llm_used"]
    if "llm_confidence" in merged_dict:
        parsing_metadata["llm_confidence"] = merged_dict["llm_confidence"]
    if "llm_error" in merged_dict:
        parsing_metadata["llm_error"] = merged_dict["llm_error"]
    
    # Map source string to enum
    try:
        source_enum = RFQSource(source.lower())
    except (ValueError, AttributeError):
        source_enum = RFQSource.MANUAL  # Fallback
    
    # Create RFQ items
    items = []
    for idx, part_number in enumerate(normalized_part_numbers, start=1):
        item = RFQItem(
            id=uuid4(),
            rfq_id=request_id,
            line_no=idx,
            part_number=part_number,
            qty=None,  # Всегда None (как в текущей реализации)
            notes=None,
            confidence=confidence,
            created_at=created_at,
        )
        items.append(item)
    
    # Create RFQ request
    request = RFQRequest(
        id=request_id,
        source=source_enum,
        status=RFQStatus.PROCESSED,  # После парсинга всегда PROCESSED
        raw_text=raw_text,
        contact=contact,
        company=company,
        items=items,
        parsing_metadata=parsing_metadata,
        created_at=created_at,
    )
    
    return request
