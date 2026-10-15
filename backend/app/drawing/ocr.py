"""CPU-only OCR dimension candidates; candidates never calibrate geometry automatically."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any

import numpy as np

_DIMENSION = re.compile(r"(?<![\d.])(\d+(?:[.,]\d+)?)\s*(mm|cm)\b", re.IGNORECASE)
_ENGINE: Any | None = None
_ENGINE_LOCK = threading.RLock()


class OcrUnavailableError(RuntimeError):
    """The optional OCR pass failed; manual calibration remains available."""


@dataclass(frozen=True, slots=True)
class DimensionCandidate:
    text: str
    value: float
    unit: str
    value_mm: float
    confidence: float
    box_px: tuple[tuple[float, float], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "value": self.value,
            "unit": self.unit,
            "value_mm": self.value_mm,
            "confidence": self.confidence,
            "box_px": [list(point) for point in self.box_px],
        }


def _engine() -> Any:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            try:
                from rapidocr import RapidOCR

                _ENGINE = RapidOCR(params={"EngineConfig.onnxruntime.use_cuda": False})
            except Exception as exc:
                raise OcrUnavailableError(f"로컬 CPU OCR을 초기화하지 못했습니다: {exc}") from exc
        return _ENGINE


def extract_dimensions(image: np.ndarray) -> list[DimensionCandidate]:
    """Return numeric mm/cm text only, preserving OCR confidence and location."""
    try:
        with _ENGINE_LOCK:
            result = _engine()(image)
    except OcrUnavailableError:
        raise
    except Exception as exc:
        raise OcrUnavailableError(f"로컬 CPU OCR 실행에 실패했습니다: {exc}") from exc

    candidates: list[DimensionCandidate] = []
    boxes = result.boxes if result.boxes is not None else ()
    texts = result.txts if result.txts is not None else ()
    scores = result.scores if result.scores is not None else ()
    for box, text, score in zip(boxes, texts, scores, strict=True):
        for match in _DIMENSION.finditer(str(text)):
            value = float(match.group(1).replace(",", "."))
            unit = match.group(2).lower()
            candidates.append(
                DimensionCandidate(
                    text=str(text),
                    value=value,
                    unit=unit,
                    value_mm=value if unit == "mm" else value * 10.0,
                    confidence=float(score),
                    box_px=tuple((float(point[0]), float(point[1])) for point in box),
                )
            )
    return candidates
