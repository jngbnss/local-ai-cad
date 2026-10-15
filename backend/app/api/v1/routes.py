"""v1 엔드포인트.

생성은 blocking 이므로 전부 스레드 풀에 위임한다. 이벤트 루프에서 직접 돌리면
생성 20초 동안 health 체크조차 막힌다.

추론 직렬화는 provider 의 lock 이 담당한다 (Phase 1 불변식). 여기서 중복으로
막지 않는다. 대신 기하 생성은 CPU 작업이라 병렬로 둔다.
"""

from __future__ import annotations

import logging
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse

from app.api.deps import AppState
from app.api.errors import ApiError, error_payload
from app.api.schemas import (
    Artifacts,
    DesignRequest,
    DrawingAnalyzeResponse,
    DrawingGenerateRequest,
    DrawingGenerateResponse,
    DesignResponse,
    DiffEntry,
    GenerateRequest,
    GenerateResponse,
    GeometryReport,
    HealthResponse,
    HistoryEntry,
    HistoryResponse,
    Metrics,
    ReviseRequest,
    VersionResponse,
)
from app.cad.builder import build_solid
from app.cad.exporter import export_artifacts
from app.cad.validate import validate_solid
from app.design.history import DesignVersion
from app.design.schema import DesignSpec
from app.design.validator import generate_spec, revise_spec
from app.drawing.analyzer import (
    MAX_FILE_BYTES,
    AnalysisRegion,
    analyze_image,
    overlay_svg,
)
from app.drawing.store import cleanup_analyses, create_analysis, get_analysis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


def _state(request: Request) -> AppState:
    return request.app.state.app_state


def _request_id() -> str:
    return uuid.uuid4().hex[:12]


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    state = _state(request)
    cuda_available = False
    device_name = None
    try:
        import torch

        cuda_available = torch.cuda.is_available()
        if cuda_available:
            device_name = torch.cuda.get_device_properties(0).name
    except ImportError:
        pass

    return HealthResponse(
        status="ok",
        model_loaded=state.provider.is_loaded,
        model_id=state.settings.model_id,
        device=state.settings.device,
        dtype=state.settings.dtype,
        cuda_available=cuda_available,
        device_name=device_name,
    )


@router.post("/generate", response_model=GenerateResponse)
async def generate(request: Request, body: GenerateRequest) -> GenerateResponse:
    state = _state(request)
    request_id = _request_id()
    logger.info("generate 시작 request_id=%s", request_id)

    result = await run_in_threadpool(state.provider.generate, body.prompt)

    logger.info(
        "generate 완료 request_id=%s inference=%.3fs tokens=%d",
        request_id,
        result.metrics.inference_seconds,
        result.metrics.output_tokens,
    )
    return GenerateResponse(
        text=result.text,
        metrics=Metrics(**result.metrics.as_dict()),
        request_id=request_id,
    )


@router.post("/design", response_model=DesignResponse)
async def create_design(request: Request, body: DesignRequest) -> DesignResponse:
    state = _state(request)
    request_id = _request_id()

    spec_result = await run_in_threadpool(generate_spec, state.provider, body.prompt)
    record = await run_in_threadpool(state.history.create, spec_result.spec, body.prompt)
    geometry, artifacts = await run_in_threadpool(_materialise, state, record)

    return DesignResponse(
        design_id=record.design_id,
        version=record.version,
        spec=record.spec,
        artifacts=artifacts,
        geometry=geometry,
        metrics=Metrics(**spec_result.metrics.as_dict()),
        spec_attempts=spec_result.attempt_count,
        diff=[],
        request_id=request_id,
    )


def _sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/design/stream")
async def create_design_stream(request: Request, body: DesignRequest) -> StreamingResponse:
    """Phase 5용 진행 스트림. 최종 complete 데이터는 DesignResponse와 동일하다."""
    state = _state(request)
    request_id = _request_id()

    async def events():
        yield _sse("progress", {"stage": "llm", "message": "설계 명세 생성 중", "request_id": request_id})
        try:
            spec_result = await run_in_threadpool(generate_spec, state.provider, body.prompt)
            yield _sse("progress", {"stage": "geometry", "message": "3D 형상 생성 중", "request_id": request_id})
            record = await run_in_threadpool(state.history.create, spec_result.spec, body.prompt)
            geometry, artifacts = await run_in_threadpool(_materialise, state, record)
            response = DesignResponse(
                design_id=record.design_id,
                version=record.version,
                spec=record.spec,
                artifacts=artifacts,
                geometry=geometry,
                metrics=Metrics(**spec_result.metrics.as_dict()),
                spec_attempts=spec_result.attempt_count,
                diff=[],
                request_id=request_id,
            )
            yield _sse("complete", response.model_dump(mode="json"))
        except Exception as exc:  # 스트림이 시작된 뒤에는 HTTP 상태를 바꿀 수 없다.
            content, status = error_payload(exc)
            content["status"] = status
            content["request_id"] = request_id
            yield _sse("error", content)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/design/{design_id}/revise", response_model=DesignResponse)
async def revise_design(
    request: Request, design_id: str, body: ReviseRequest
) -> DesignResponse:
    state = _state(request)
    request_id = _request_id()

    current = await run_in_threadpool(state.history.get, design_id)
    spec_result = await run_in_threadpool(
        revise_spec, state.provider, current.spec, body.instruction
    )
    record = await run_in_threadpool(
        state.history.add_revision, design_id, spec_result.spec, body.instruction
    )
    geometry, artifacts = await run_in_threadpool(_materialise, state, record)

    return DesignResponse(
        design_id=record.design_id,
        version=record.version,
        spec=record.spec,
        artifacts=artifacts,
        geometry=geometry,
        metrics=Metrics(**spec_result.metrics.as_dict()),
        spec_attempts=spec_result.attempt_count,
        diff=[
            DiffEntry(path=change.path, before=change.before, after=change.after)
            for change in record.diff
        ],
        request_id=request_id,
    )


@router.get("/design/{design_id}/history", response_model=HistoryResponse)
async def design_history(request: Request, design_id: str) -> HistoryResponse:
    state = _state(request)
    versions = await run_in_threadpool(state.history.list_versions, design_id)
    return HistoryResponse(
        design_id=design_id,
        versions=[
            HistoryEntry(
                version=item.version,
                created_at=item.created_at,
                name=item.spec.name,
                prompt=item.prompt,
                instruction=item.instruction,
            )
            for item in versions
        ],
    )


@router.get("/design/{design_id}/versions/{version}", response_model=VersionResponse)
async def design_version(request: Request, design_id: str, version: int) -> VersionResponse:
    state = _state(request)
    record = await run_in_threadpool(state.history.get, design_id, version)
    geometry, artifacts = await run_in_threadpool(_materialise, state, record)
    del geometry
    return VersionResponse(
        design_id=record.design_id,
        version=record.version,
        spec=record.spec,
        artifacts=artifacts,
    )


@router.post("/drawing/analyze", response_model=DrawingAnalyzeResponse)
async def analyze_drawing(
    request: Request,
    image: UploadFile = File(...),
    x: int | None = Form(default=None),
    y: int | None = Form(default=None),
    width: int | None = Form(default=None),
    height: int | None = Form(default=None),
) -> DrawingAnalyzeResponse:
    values = (x, y, width, height)
    if any(value is not None for value in values) and not all(
        value is not None for value in values
    ):
        raise ApiError(
            "invalid_analysis_region",
            "analysis region은 x, y, width, height를 모두 보내야 합니다.",
            status=422,
        )
    data = await image.read(MAX_FILE_BYTES + 1)
    region = (
        AnalysisRegion(x=x, y=y, width=width, height=height)
        if all(value is not None for value in values)
        else None
    )
    state = _state(request)
    root = state.artifact_dir / "drawing-analyses"

    def analyze_and_store():
        cleanup_analyses(root)
        detected = analyze_image(data, region=region)
        profile = detected.as_dict()
        stored = create_analysis(
            root,
            normalized_png=detected.normalized_png,
            overlay=overlay_svg(detected),
            profile=profile,
        )
        return stored, profile

    stored, profile = await run_in_threadpool(analyze_and_store)
    base = f"/api/v1/drawing/analyses/{stored.analysis_id}"
    return DrawingAnalyzeResponse(
        analysis_id=stored.analysis_id,
        image_url=f"{base}/image",
        overlay_url=f"{base}/overlay",
        profile=profile,
    )


@router.get("/drawing/analyses/{analysis_id}/{asset}")
async def drawing_analysis_asset(
    request: Request, analysis_id: str, asset: str
) -> FileResponse:
    stored = get_analysis(_state(request).artifact_dir / "drawing-analyses", analysis_id)
    if stored is None:
        raise ApiError("analysis_not_found", "도면 분석 결과가 없습니다.", status=404)
    if asset == "image":
        return FileResponse(stored.image_path, media_type="image/png")
    if asset == "overlay":
        return FileResponse(stored.overlay_path, media_type="image/svg+xml")
    raise ApiError("analysis_asset_not_found", "지원하지 않는 분석 파일입니다.", status=404)


@router.post("/drawing/generate", response_model=DrawingGenerateResponse)
async def generate_drawing(
    request: Request, body: DrawingGenerateRequest
) -> DrawingGenerateResponse:
    state = _state(request)
    stored = get_analysis(
        state.artifact_dir / "drawing-analyses", body.analysis_id
    )
    if stored is None:
        raise ApiError("analysis_not_found", "도면 분석 결과가 없습니다.", status=404)
    analysis_profile = json.loads(stored.profile_path.read_text(encoding="utf-8"))
    if "detail_heavy_input" in analysis_profile.get("warnings", []):
        raise ApiError(
            "photo_input_unsupported",
            "문자·무늬·배경이 많은 사진은 정확한 CAD로 변환할 수 없습니다.",
            status=422,
        )
    spec = DesignSpec.model_validate(
        {
            "schema_version": "2.0",
            "name": body.name,
            "source": {
                "kind": "drawing_import",
                "analysis_id": body.analysis_id,
            },
            "parts": [
                {
                    "id": "drawing-body",
                    "primitive": "sketch_extrusion",
                    "profile": body.profile.model_dump(mode="json"),
                    "depth": body.depth,
                    "position": {},
                }
            ],
            "operations": [],
        }
    )
    record = await run_in_threadpool(
        state.history.create, spec, f"drawing:{body.analysis_id}"
    )
    geometry, artifacts = await run_in_threadpool(_materialise, state, record)
    return DrawingGenerateResponse(
        design_id=record.design_id,
        version=record.version,
        spec=record.spec,
        artifacts=artifacts,
        geometry=geometry,
        request_id=_request_id(),
    )


@router.get("/artifacts/{filename}")
async def artifact(request: Request, filename: str) -> FileResponse:
    state = _state(request)
    # 경로 조작 차단: 파일명만 받고 디렉터리 성분은 버린다.
    safe_name = Path(filename).name
    if safe_name != filename:
        raise ApiError("invalid_artifact", "아티팩트 이름에 경로를 쓸 수 없습니다.", status=400)

    path = state.artifact_dir / safe_name
    if not path.is_file():
        raise ApiError(
            "artifact_not_found", f"아티팩트가 없습니다: {safe_name}", status=404
        )
    return FileResponse(path, filename=safe_name)


def artifact_id_for(record: DesignVersion) -> str:
    return f"{record.design_id}-v{record.version}"


def _materialise(state: AppState, record: DesignVersion) -> tuple[GeometryReport, Artifacts]:
    """DesignSpec → 솔리드 → 검증 → STL/STEP.

    아티팩트는 캐시로 취급한다. 이미 있으면 다시 만들지 않는다 (디스크 절약).
    """
    artifact_id = artifact_id_for(record)
    stl_path = state.artifact_dir / f"{artifact_id}.stl"
    step_path = state.artifact_dir / f"{artifact_id}.step"

    solid = build_solid(record.spec)
    report = validate_solid(solid, record.spec)

    if not (stl_path.is_file() and step_path.is_file()):
        export_artifacts(solid, state.artifact_dir, artifact_id)

    return (
        GeometryReport(**report),
        Artifacts(
            stl=f"/api/v1/artifacts/{artifact_id}.stl",
            step=f"/api/v1/artifacts/{artifact_id}.step",
        ),
    )


def spec_from_json(payload: dict) -> DesignSpec:
    return DesignSpec.model_validate(payload)
