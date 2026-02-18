from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class StepState(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FALSE = "FALSE"
    ERROR = "ERROR"


STEP_ORDER = [
    "skeleton",
    "manufacturer",
    "categories",
    "media",
    "prices",
    "visibilities",
    "verify",
]


@dataclass
class ProductImportState:
    sku: str
    product_id: Optional[str] = None
    steps: Dict[str, StepState] = field(default_factory=lambda: {name: StepState.PENDING for name in STEP_ORDER})
    errors: List[str] = field(default_factory=list)
    diagnostics: Dict[str, str] = field(default_factory=dict)

    def set_step(self, step: str, status: StepState, message: Optional[str] = None) -> None:
        self.steps[step] = status
        if message:
            if status == StepState.ERROR:
                self.errors.append(f"{step}: {message}")
            else:
                self.diagnostics[step] = message

    def is_successful(self) -> bool:
        return all(self.steps[name] == StepState.SUCCESS for name in STEP_ORDER)
