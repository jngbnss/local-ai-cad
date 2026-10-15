"""HTTP 오류 매핑.

원인별로 다른 `error_type` 을 내보낸다. UI 는 이 값으로 메시지를 가른다.
전부 500 "오류가 발생했습니다" 로 뭉치면 사용자는 GPU 문제인지 모델 문제인지
설계 문제인지 알 수 없다.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.ai.errors import (
    CudaUnavailableError,
    GpuOutOfMemoryError,
    ModelDownloadError,
    ProviderError,
    TorchNotInstalledError,
)
from app.cad.errors import BooleanFailedError, ExportError, GeometryError, SolidInvalidError
from app.config import ConfigError
from app.design.history import DesignNotFoundError, HistoryError, VersionNotFoundError
from app.design.validator import SpecGenerationError
from app.drawing.errors import (
    DrawingError,
    ImageTooLargeError,
    ProfileDetectionError,
    ProfileInvalidError,
    UnsupportedImageError,
)

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, error_type: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.status = status


# 예외 타입 → (error_type, HTTP 상태)
_MAPPING: tuple[tuple[type[Exception], str, int], ...] = (
    (CudaUnavailableError, "cuda_unavailable", 503),
    (TorchNotInstalledError, "torch_missing", 503),
    (GpuOutOfMemoryError, "oom", 507),
    (ModelDownloadError, "model_download_failed", 502),
    (ImageTooLargeError, "image_too_large", 413),
    (UnsupportedImageError, "image_unsupported", 415),
    (ProfileDetectionError, "profile_detection_failed", 422),
    (ProfileInvalidError, "profile_invalid", 422),
    (SpecGenerationError, "schema_invalid", 422),
    (SolidInvalidError, "geometry_invalid", 422),
    (BooleanFailedError, "geometry_failed", 422),
    (ExportError, "export_failed", 500),
    (DesignNotFoundError, "design_not_found", 404),
    (VersionNotFoundError, "version_not_found", 404),
    (ConfigError, "config_invalid", 500),
)


def _classify(exc: Exception) -> tuple[str, int]:
    for exc_type, error_type, status in _MAPPING:
        if isinstance(exc, exc_type):
            return error_type, status
    if isinstance(exc, GeometryError):
        return "geometry_failed", 422
    if isinstance(exc, HistoryError):
        return "history_failed", 500
    if isinstance(exc, ProviderError):
        return "inference_failed", 500
    return "internal_error", 500


def _detail(exc: Exception) -> dict[str, object] | None:
    if isinstance(exc, GpuOutOfMemoryError):
        return {"peak_vram_mib": exc.peak_vram_mib, "max_new_tokens": exc.max_new_tokens}
    if isinstance(exc, SpecGenerationError):
        return {
            "attempts": [
                {"index": attempt.index, "failure": attempt.failure}
                for attempt in exc.attempts
            ]
        }
    return None


def error_payload(exc: Exception) -> tuple[dict[str, object], int]:
    """일반 응답과 SSE가 공유하는 구조화 오류 본문."""
    error_type, status = _classify(exc)
    return (
        {
            "error_type": error_type,
            "message": str(exc),
            "detail": _detail(exc),
        },
        status,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"error_type": exc.error_type, "message": exc.message, "detail": None},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        drawing_request = request.url.path.startswith("/api/v1/drawing/")
        return JSONResponse(
            status_code=422,
            content={
                "error_type": "profile_invalid" if drawing_request else "schema_invalid",
                "message": (
                    "도면 프로파일의 점 또는 구멍이 유효하지 않습니다."
                    if drawing_request
                    else "요청 형식이 유효하지 않습니다."
                ),
                "detail": {
                    "errors": jsonable_encoder(
                        exc.errors(), custom_encoder={ValueError: str}
                    )
                },
            },
        )

    @app.exception_handler(DrawingError)
    async def _drawing_error(_request: Request, exc: DrawingError) -> JSONResponse:
        content, status = error_payload(exc)
        logger.warning("%s: %s", content["error_type"], exc)
        return JSONResponse(status_code=status, content=content)

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        content, status = error_payload(exc)
        error_type = str(content["error_type"])
        if error_type == "internal_error":
            logger.exception("처리되지 않은 오류")
        else:
            logger.warning("%s: %s", error_type, exc)
        return JSONResponse(
            status_code=status,
            content=content,
        )
