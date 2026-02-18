"""
Procurement Domain - Canonical Domain Model (CDM)

Типизированные модели для RFQ (Request for Quotation) pipeline.
Эти модели описывают нормализованную структуру данных после extraction и validation.

Phase 1a: Models only (no business logic, no DB access, no conversion).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID


class RFQSource(str, Enum):
    """Источник RFQ запроса."""
    TELEGRAM = "telegram"
    EMAIL = "email"
    MANUAL = "manual"


class RFQStatus(str, Enum):
    """Статус обработки RFQ запроса."""
    NEW = "new"
    PROCESSED = "processed"
    FAILED = "failed"


class PartNumberConfidence(str, Enum):
    """Уровень уверенности в извлечённом партномере."""
    HIGH = "high"        # Deterministic extraction
    MEDIUM = "medium"    # LLM-only extraction
    LOW = "low"          # Ambiguous or low-quality extraction


@dataclass(frozen=True)
class ContactInfo:
    """
    Контактная информация из RFQ запроса.
    Value object (не entity).
    """
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "emails": self.emails,
            "phones": self.phones
        }


@dataclass(frozen=True)
class CompanyInfo:
    """
    Информация о компании из RFQ запроса.
    Value object (не entity).
    """
    inn: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "inn": self.inn
        }


@dataclass
class RFQItem:
    """
    Элемент RFQ запроса (строка с партномером).
    
    Maps to rfq_items table in PostgreSQL.
    """
    id: UUID
    rfq_id: UUID
    line_no: int
    part_number: str
    qty: Optional[int] = None
    notes: Optional[str] = None
    confidence: PartNumberConfidence = PartNumberConfidence.HIGH
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "id": str(self.id),
            "rfq_id": str(self.rfq_id),
            "line_no": self.line_no,
            "part_number": self.part_number,
            "qty": self.qty,
            "notes": self.notes,
            "confidence": self.confidence.value,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


@dataclass
class RFQRequest:
    """
    RFQ запрос (Request for Quotation).
    
    Canonical model для Procurement domain.
    Maps to rfq_requests table in PostgreSQL.
    """
    id: UUID
    source: RFQSource
    status: RFQStatus
    raw_text: str
    contact: ContactInfo
    company: CompanyInfo
    items: List[RFQItem] = field(default_factory=list)
    parsing_metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize to dict.
        
        Format matches current parsed_json structure in rfq_requests.parsed_json.
        """
        return {
            "id": str(self.id),
            "source": self.source.value,
            "status": self.status.value,
            "raw_text": self.raw_text,
            "contact": self.contact.to_dict(),
            "company": self.company.to_dict(),
            "items": [item.to_dict() for item in self.items],
            "parsing_metadata": self.parsing_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    def to_db_params(self) -> Dict[str, Any]:
        """
        Convert to database parameters for INSERT.
        
        Returns dict matching current INSERT structure in ru_worker.py:
        - id, source, raw_text, parsed_json, status
        """
        # parsed_json contains: contact, company, candidate_part_numbers, parsing_metadata
        parsed_json = {
            "candidate_part_numbers": [item.part_number for item in self.items],
            "emails": self.contact.emails,
            "phones": self.contact.phones,
            "company_identifiers": self.company.to_dict(),
            **self.parsing_metadata  # llm_used, llm_confidence, etc.
        }
        
        return {
            "id": self.id,
            "source": self.source.value,
            "raw_text": self.raw_text,
            "parsed_json": parsed_json,
            "status": self.status.value
        }
    
    def get_items_db_params(self) -> List[Dict[str, Any]]:
        """
        Convert items to database parameters for INSERT.
        
        Returns list of dicts for rfq_items table.
        """
        return [
            {
                "id": item.id,
                "rfq_id": item.rfq_id,
                "line_no": item.line_no,
                "part_number": item.part_number,
                "qty": item.qty,
                "notes": item.notes
            }
            for item in self.items
        ]
