"""요청/응답 모델.

모든 성공 응답은 Phase 1의 측정 필드를 그대로 들고 다닌다.
단계가 올라가도 성능 퇴행을 추적할 수 있어야 하기 때문이다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.design.schema import DesignSpec, SketchProfile


class Metrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model_id: str
    device: str
    dtype: str
    load_seconds: float
    inference_seconds: float
    input_tokens: int
    output_tokens: int
    peak_vram_mib: float


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_id: str
    device: str
    dtype: str
    cuda_available: bool
    device_name: str | None


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=4000)


class GenerateResponse(BaseModel):
    text: str
    metrics: Metrics
    request_id: str


class DesignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=4000)


class ReviseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(min_length=1, max_length=4000)


class Artifacts(BaseModel):
    stl: str
    step: str


class DiffEntry(BaseModel):
    path: str
    before: object | None = None
    after: object | None = None


class GeometryReport(BaseModel):
    is_valid: bool
    volume_mm3: float
    bounding_box_mm: list[float]
    expected_bounding_box_mm: list[float]
    within_tolerance: bool
    tolerance_mm: float


class DesignResponse(BaseModel):
    design_id: str
    version: int
    spec: DesignSpec
    artifacts: Artifacts
    geometry: GeometryReport
    metrics: Metrics
    spec_attempts: int
    diff: list[DiffEntry] = Field(default_factory=list)
    request_id: str



class DrawingAnalyzeResponse(BaseModel):
    analysis_id: str
    image_url: str
    overlay_url: str
    profile: dict[str, Any]


class DrawingGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    name: str = Field(min_length=1, max_length=120)
    profile: SketchProfile
    depth: float = Field(ge=0.1, le=10_000.0)


class DrawingGenerateResponse(BaseModel):
    design_id: str
    version: int
    spec: DesignSpec
    artifacts: Artifacts
    geometry: GeometryReport
    request_id: str

class HistoryEntry(BaseModel):
    version: int
    created_at: str
    name: str
    prompt: str | None = None
    instruction: str | None = None


class HistoryResponse(BaseModel):
    design_id: str
    versions: list[HistoryEntry]


class VersionResponse(BaseModel):
    design_id: str
    version: int
    spec: DesignSpec
    artifacts: Artifacts


class ErrorResponse(BaseModel):
    """오류는 원인별로 다른 `error_type` 을 쓴다. UI 가 이걸로 메시지를 가른다."""

    error_type: str
    message: str
    detail: dict[str, object] | None = None
    request_id: str | None = None
