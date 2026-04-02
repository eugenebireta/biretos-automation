"""
hard_shell/model_selector.py — автовыбор модели и effort на основе surface.

Три триггера Opus (SPEC §11.3):
  A. Surface-based: ContextAssembler нашёл OPUS_SURFACES → Opus high
  B. Quality Gate Escalation: Sonnet не прошёл Gate → Opus high (1 попытка)
  C. Owner Override: явно указан model=opus

Модели берутся из config/models.yaml, не hardcoded.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .contracts import EffortLevel, ModelName, RiskLevel
from .context_assembler import OPUS_SURFACES

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = {
    "builder": {"default": "sonnet", "escalation": "opus"},
}


def _load_models_config(config_path: str | Path | None = None) -> dict[str, Any]:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "models.yaml"
    config_path = Path(config_path)
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    logger.warning("model_selector: models.yaml not found at %s, using defaults", config_path)
    return _DEFAULT_CONFIG


class ModelSelector:
    """
    Выбирает модель + effort для Builder.

    Принцип:
    - ~70% задач → Sonnet medium (подписка, экономия лимитов)
    - ~20% задач → Opus high сразу (surface-based)
    - ~10% задач → Opus high через escalation (safety net)
    - 0% → ручной выбор / 1M context по умолчанию
    """

    def __init__(self, config_path: str | Path | None = None):
        cfg = _load_models_config(config_path)
        builder_cfg = cfg.get("builder", {})
        self._default_model = builder_cfg.get("default", "sonnet")
        self._escalation_model = builder_cfg.get("escalation", "opus")

    def select(
        self,
        risk: RiskLevel,
        surfaces: set[str],
        owner_model_override: str | None = None,
    ) -> tuple[ModelName, EffortLevel]:
        """
        Trigger A: surface-based (до начала).
        Trigger C: owner override (escape hatch).
        """
        # Trigger C — owner override
        if owner_model_override:
            model = ModelName(owner_model_override.lower())
            effort = EffortLevel.HIGH if model == ModelName.OPUS else EffortLevel.MEDIUM
            logger.info("model_selector: owner override model=%s effort=%s", model, effort)
            return model, effort

        # Trigger A — surface-based
        if surfaces & OPUS_SURFACES:
            logger.info(
                "model_selector: opus selected (surface hit) surfaces=%s",
                sorted(surfaces & OPUS_SURFACES),
            )
            return ModelName.OPUS, EffortLevel.HIGH

        # Risk-based default
        if risk == RiskLevel.LOW:
            return ModelName.SONNET, EffortLevel.LOW
        return ModelName.SONNET, EffortLevel.MEDIUM

    def escalate(self, current_model: ModelName) -> tuple[ModelName, EffortLevel] | None:
        """
        Trigger B — Quality Gate escalation.
        Максимум 1 escalation. Opus не вытянул → owner.
        """
        if current_model == ModelName.SONNET:
            logger.info("model_selector: escalating sonnet → opus (quality gate failed)")
            return ModelName.OPUS, EffortLevel.HIGH
        # Opus тоже failed → owner review, не escalate дальше
        logger.warning("model_selector: opus also failed quality gate → owner review")
        return None
