from __future__ import annotations

from dataclasses import dataclass

from scripts.lot_scoring.pipeline.helpers import clamp, to_float, to_str

_VOLUME_WEIGHTS: dict[str, float] = {
    "SMALL": 1.0,
    "MEDIUM": 0.65,
    "LARGE": 0.25,
    "UNKNOWN": 0.50,
}

_VOLUME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "SMALL": (
        "sensor",
        "detector",
        "module",
        "board",
        "relay",
        "card",
        "indicator",
        "head",
        "probe",
        "element",
        "plug",
        "connector",
        "датчик",
        "извещ",
        "модул",
        "плат",
        "реле",
        "карт",
        "элемент",
        "разъем",
        "разъём",
        "зонд",
        "головк",
    ),
    "MEDIUM": (
        "valve",
        "actuator",
        "controller",
        "analyzer",
        "transmitter",
        "pump",
        "motor",
        "blower",
        "supply",
        "клапан",
        "привод",
        "контроллер",
        "анализатор",
        "преобразов",
        "насос",
        "двигател",
        "блок питан",
    ),
    "LARGE": (
        "cabinet",
        "rack",
        "enclosure",
        "pipe",
        "cable",
        "drum",
        "duct",
        "frame",
        "housing",
        "panel",
        "шкаф",
        "стойк",
        "труб",
        "кабел",
        "барабан",
        "воздуховод",
        "корпус",
        "рам",
        "короб",
    ),
}


@dataclass(frozen=True)
class VolumeProfileResult:
    vci: float
    distribution: dict[str, float]
    flags: list[str]
    classified_count: int
    total_count: int
    confidence: str


def classify_volume_class(raw_text: str) -> str:
    text = to_str(raw_text).lower()
    if not text:
        return "UNKNOWN"

    # LARGE has highest priority for risk-sensitive logistics classification.
    if any(token in text for token in _VOLUME_KEYWORDS["LARGE"]):
        return "LARGE"
    if any(token in text for token in _VOLUME_KEYWORDS["SMALL"]):
        return "SMALL"
    if any(token in text for token in _VOLUME_KEYWORDS["MEDIUM"]):
        return "MEDIUM"
    return "UNKNOWN"


def compute_volume_profile(
    core_skus: list[dict],
    large_threshold: float = 0.40,
    unknown_threshold: float = 0.50,
) -> VolumeProfileResult:
    total_count = len(core_skus)
    classified_count = 0
    value_by_class = {key: 0.0 for key in _VOLUME_WEIGHTS}

    for sku in core_skus:
        volume_class = classify_volume_class(to_str(sku.get("raw_text")))
        if volume_class != "UNKNOWN":
            classified_count += 1

        line_value = max(0.0, to_float(sku.get("effective_line_usd"), 0.0))
        if line_value <= 0.0:
            continue
        value_by_class[volume_class] += line_value

    total_value = sum(value_by_class.values())
    if total_value > 0.0:
        distribution = {key: value_by_class[key] / total_value for key in _VOLUME_WEIGHTS}
        vci = sum(_VOLUME_WEIGHTS[key] * distribution[key] for key in _VOLUME_WEIGHTS)
    else:
        distribution = {key: 0.0 for key in _VOLUME_WEIGHTS}
        vci = _VOLUME_WEIGHTS["UNKNOWN"]

    flags: list[str] = []
    if distribution["LARGE"] > large_threshold:
        flags.append("VOLUME_RISK:LARGE_HEAVY")
    if distribution["UNKNOWN"] > unknown_threshold:
        flags.append("VOLUME_PROFILE:LOW_CONFIDENCE")

    if "VOLUME_PROFILE:LOW_CONFIDENCE" in flags:
        confidence = "LOW"
    elif total_count > 0 and (classified_count / float(total_count)) < 0.6:
        confidence = "MEDIUM"
    else:
        confidence = "HIGH"

    return VolumeProfileResult(
        vci=clamp(vci, 0.0, 1.0),
        distribution=distribution,
        flags=flags,
        classified_count=classified_count,
        total_count=total_count,
        confidence=confidence,
    )
