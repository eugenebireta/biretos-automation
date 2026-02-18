"""
Модули диагностики для ChatGPT USA Route.
"""
from typing import Dict, Any, Optional
from enum import Enum


class TestStatus(str, Enum):
    """Статусы тестов."""
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"
    ERROR = "ERROR"


def test_result(
    name: str,
    status: TestStatus,
    metrics: Optional[Dict[str, Any]] = None,
    details: str = "",
    mode: str = "direct"
) -> Dict[str, Any]:
    """Создает структуру результата теста."""
    from datetime import datetime
    
    return {
        "name": name,
        "status": status.value,
        "metrics": metrics or {},
        "details": details,
        "ts": datetime.utcnow().isoformat() + "Z",
        "mode": mode
    }
