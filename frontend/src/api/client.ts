/**
 * 백엔드 REST 계약의 TypeScript 미러.
 *
 * 설계 의도
 * - 백엔드 `backend/app/design/schema.py` 의 DesignSpec 과 1:1 로 대응하는 타입을 둔다.
 *   스키마가 바뀌면 여기도 바뀌어야 하고, 바뀌지 않으면 빌드가 깨지는 편이 낫다.
 * - 실패를 뭉개지 않는다. 모든 비정상 응답은 `ApiError` 로 올라오며 `errorType` 으로
 *   원인(환경/모델/스키마/기하/네트워크)이 구분된다. UI 는 이 구분으로 다른 문구를 낸다.
 * - 조용한 폴백 금지: 응답을 못 읽었다고 빈 객체를 만들어 넘기지 않는다.
 */

/** DesignSpec 좌표. `Part.position` 은 **바닥면 중심**(x·y 중심, z 바닥 높이)이다. */
export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface BoxDimensions {
  x: number;
  y: number;
  z: number;
}

export interface CylinderDimensions {
  radius: number;
  height: number;
}

export interface PartBase {
  id: string;
  position: Vec3;
}

export interface BoxPart extends PartBase {
  primitive: "box";
  dimensions: BoxDimensions;
}

export interface CylinderPart extends PartBase {
  primitive: "cylinder";
  dimensions: CylinderDimensions;
}

export type ProfileHole =
  | { kind: "circle"; center: [number, number]; radius: number }
  | { kind: "polygon"; points: [number, number][] };

export interface SketchExtrusionPart extends PartBase {
  primitive: "sketch_extrusion";
  profile: {
    outer: [number, number][];
    holes: ProfileHole[];
  };
  depth: number;
}

export type Part = BoxPart | CylinderPart | SketchExtrusionPart;
export type BooleanOp = "union" | "cut";

export interface Operation {
  type: BooleanOp;
  targets: string[];
}

export interface DesignSpec {
  schema_version: "2.0";
  unit: "mm";
  name: string;
  parts: Part[];
  operations: Operation[];
  source: {
    kind: "text" | "drawing_import";
    analysis_id: string | null;
  };
}

export interface Metrics {
  provider: string;
  model_id: string;
  device: string;
  dtype: string;
  load_seconds: number;
  inference_seconds: number;
  input_tokens: number;
  output_tokens: number;
  peak_vram_mib: number | null;
}

/** 아티팩트 경로. 보통 `/api/v1/artifacts/{design_id}-v{version}.stl` 형태다. */
export interface Artifacts {
  stl: string;
  step: string;
}

export interface HealthResponse {
  status: string;
  model_loaded: boolean;
  device: string;
  dtype: string;
  model_id: string;
  cuda_available: boolean;
  device_name: string | null;
}

export interface GenerateResponse {
  text: string;
  metrics: Metrics;
  request_id: string;
}

export interface DesignResponse {
  design_id: string;
  version: number;
  spec: DesignSpec;
  artifacts: Artifacts;
  geometry: GeometryReport;
  metrics: Metrics;
  spec_attempts: number;
  diff: DiffEntry[];
  request_id: string;
}

export interface GeometryReport {
  is_valid: boolean;
  volume_mm3: number;
  bounding_box_mm: number[];
  expected_bounding_box_mm: number[];
  within_tolerance: boolean;
  tolerance_mm: number;
}

/** 수정 전/후가 달라진 지점 하나. `path` 는 `parts[1].dimensions.x` 같은 점 표기다. */
export interface DiffEntry {
  path: string;
  before: unknown;
  after: unknown;
}

export interface ReviseResponse extends DesignResponse {
  diff: DiffEntry[];
}

export interface HistoryEntry {
  version: number;
  created_at: string;
  instruction: string | null;
  prompt: string | null;
  name: string;
}

export interface HistoryResponse {
  design_id: string;
  versions: HistoryEntry[];
}

export interface VersionResponse {
  design_id: string;
  version: number;
  spec: DesignSpec;
  artifacts: Artifacts;
}

export type DrawingHoleCandidate =
  | {
      kind: "circle";
      center_px: [number, number];
      radius_px: number;
      area_px2: number;
      confidence: number;
    }
  | {
      kind: "polygon";
      points_px: [number, number][];
      area_px2: number;
      confidence: number;
    };

export interface DrawingPolygonCandidate {
  kind: "polygon";
  points_px: [number, number][];
  area_px2: number;
  confidence: number;
}

export interface DimensionCandidate {
  text: string;
  value: number;
  unit: "mm" | "cm";
  value_mm: number;
  confidence: number;
  box_px: [number, number][];
}


export interface DrawingAnalysis {
  analysis_id: string;
  image_url: string;
  overlay_url: string;
  profile: {
    schema_version: string;
    image: { width_px: number; height_px: number };
    outer: DrawingPolygonCandidate;
    outer_candidates: DrawingPolygonCandidate[];
    holes: DrawingHoleCandidate[];
    dimensions: DimensionCandidate[];
    warnings: string[];
    analysis_seconds: number;
  };
}

export interface AnalysisRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface DrawingGenerateResponse {
  design_id: string;
  version: number;
  spec: DesignSpec;
  artifacts: Artifacts;
  geometry: GeometryReport;
  request_id: string;
}

/**
 * 오류 분류.
 *
 * 앞의 다섯 개는 백엔드가 응답 body 의 `error_type` 으로 내려주는 값이고,
 * `network` 는 응답 자체가 오지 않은 경우(백엔드 미기동 등),
 * `unknown` 은 백엔드가 분류하지 않은 나머지다. 이 셋을 합치면 디버깅이 불가능해진다.
 */
export type ApiErrorType =
  | "cuda_unavailable"
  | "oom"
  | "schema_invalid"
  | "geometry_failed"
  | "geometry_invalid"
  | "export_failed"
  | "model_download_failed"
  | "design_not_found"
  | "version_not_found"
  | "inference_failed"
  | "config_invalid"
  | "image_too_large"
  | "image_unsupported"
  | "profile_detection_failed"
  | "profile_invalid"
  | "analysis_not_found"
  | "invalid_analysis_region"
  | "network"
  | "unknown";

const KNOWN_ERROR_TYPES: readonly ApiErrorType[] = [
  "cuda_unavailable",
  "oom",
  "schema_invalid",
  "geometry_failed",
  "geometry_invalid",
  "export_failed",
  "model_download_failed",
  "design_not_found",
  "version_not_found",
  "inference_failed",
  "config_invalid",
  "image_too_large",
  "image_unsupported",
  "profile_detection_failed",
  "profile_invalid",
  "analysis_not_found",
  "invalid_analysis_region",
];

export class ApiError extends Error {
  readonly errorType: ApiErrorType;
  /** HTTP 상태. 응답이 오지 않았으면 0. */
  readonly status: number;
  /** 백엔드가 준 원문 메시지/상세. 화면 하단에 접어서 보여준다. */
  readonly detail: string | null;

  constructor(
    message: string,
    options: { errorType: ApiErrorType; status: number; detail?: string | null },
  ) {
    super(message);
    this.name = "ApiError";
    this.errorType = options.errorType;
    this.status = options.status;
    this.detail = options.detail ?? null;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

/**
 * 오류 body 에서 `error_type` 을 꺼낸다.
 *
 * FastAPI 는 `HTTPException(detail=...)` 을 `{"detail": ...}` 로 감싸므로
 * 최상위와 `detail` 안쪽을 모두 본다. 둘 다 없으면 `unknown` 이다.
 * 여기서 상태 코드로 추측해 분류를 지어내지 않는다 — 모르면 모른다고 한다.
 */
function readErrorBody(body: unknown): { errorType: ApiErrorType; message: string | null } {
  const root = asRecord(body);
  if (root === null) {
    return { errorType: "unknown", message: typeof body === "string" ? body : null };
  }

  const inner = asRecord(root["detail"]);
  const source = inner ?? root;

  const rawType = source["error_type"];
  const errorType = KNOWN_ERROR_TYPES.find((known) => known === rawType) ?? "unknown";

  const rawMessage = source["message"] ?? source["detail"] ?? root["detail"];
  const message = typeof rawMessage === "string" ? rawMessage : null;

  return { errorType, message };
}

const FALLBACK_MESSAGE: Record<ApiErrorType, string> = {
  cuda_unavailable: "GPU(CUDA)를 사용할 수 없습니다.",
  oom: "GPU 메모리가 부족합니다.",
  schema_invalid: "모델이 만든 설계 명세가 스키마를 만족하지 않습니다.",
  geometry_failed: "기하 생성에 실패했습니다.",
  geometry_invalid: "생성된 3D 형상이 유효하지 않습니다.",
  export_failed: "CAD 파일을 저장하지 못했습니다.",
  model_download_failed: "모델 가중치를 받지 못했습니다.",
  design_not_found: "요청한 설계를 찾지 못했습니다.",
  version_not_found: "요청한 설계 버전을 찾지 못했습니다.",
  inference_failed: "로컬 모델 추론에 실패했습니다.",
  config_invalid: "백엔드 설정이 올바르지 않습니다.",
  image_too_large: "이미지가 파일 또는 픽셀 상한을 넘었습니다.",
  image_unsupported: "PNG, JPEG, WebP 이미지만 사용할 수 있습니다.",
  profile_detection_failed: "닫힌 외곽선을 찾지 못했습니다.",
  profile_invalid: "확정한 외곽선 또는 구멍이 유효하지 않습니다.",
  analysis_not_found: "도면 분석 결과가 만료됐습니다. 이미지를 다시 분석해 주세요.",
  invalid_analysis_region: "분석 영역 좌표가 올바르지 않습니다.",
  network: "백엔드에 연결할 수 없습니다.",
  unknown: "백엔드가 요청을 처리하지 못했습니다.",
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (cause) {
    // fetch 가 던지는 경우는 사실상 "응답이 없다" 하나뿐이다. 백엔드 미기동이 대부분.
    throw new ApiError(FALLBACK_MESSAGE.network, {
      errorType: "network",
      status: 0,
      detail: cause instanceof Error ? cause.message : String(cause),
    });
  }

  const rawBody = await response.text();
  let parsed: unknown = null;
  if (rawBody.length > 0) {
    try {
      parsed = JSON.parse(rawBody);
    } catch {
      parsed = rawBody;
    }
  }

  if (!response.ok) {
    const { errorType, message } = readErrorBody(parsed);
    throw new ApiError(message ?? FALLBACK_MESSAGE[errorType], {
      errorType,
      status: response.status,
      detail: rawBody.length > 0 ? rawBody.slice(0, 2000) : null,
    });
  }

  if (parsed === null) {
    throw new ApiError("백엔드가 빈 응답을 보냈습니다.", {
      errorType: "unknown",
      status: response.status,
    });
  }

  return parsed as T;
}

function postJson<T>(path: string, payload: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

const BASE = "/api/v1";

export function health(): Promise<HealthResponse> {
  return request<HealthResponse>(`${BASE}/health`);
}

export function generate(prompt: string): Promise<GenerateResponse> {
  return postJson<GenerateResponse>(`${BASE}/generate`, { prompt });
}

export function analyzeDrawing(
  image: File,
  region: AnalysisRegion | null,
): Promise<DrawingAnalysis> {
  const body = new FormData();
  body.append("image", image);
  if (region !== null) {
    body.append("x", String(region.x));
    body.append("y", String(region.y));
    body.append("width", String(region.width));
    body.append("height", String(region.height));
  }
  return request<DrawingAnalysis>(`${BASE}/drawing/analyze`, {
    method: "POST",
    body,
  });
}

export function generateDrawing(payload: {
  analysis_id: string;
  name: string;
  profile: { outer: [number, number][]; holes: ProfileHole[] };
  depth: number;
}): Promise<DrawingGenerateResponse> {
  return postJson<DrawingGenerateResponse>(`${BASE}/drawing/generate`, payload);
}

export function createDesign(prompt: string): Promise<DesignResponse> {
  return postJson<DesignResponse>(`${BASE}/design`, { prompt });
}

export type DesignStage = "llm" | "geometry";

export async function createDesignStream(
  prompt: string,
  onProgress: (stage: DesignStage, message: string) => void,
): Promise<DesignResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE}/design/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ prompt }),
    });
  } catch (cause) {
    throw new ApiError(FALLBACK_MESSAGE.network, {
      errorType: "network",
      status: 0,
      detail: cause instanceof Error ? cause.message : String(cause),
    });
  }
  if (!response.ok || !response.body) {
    const body = await response.text();
    const parsed = readErrorBody(body);
    throw new ApiError(parsed.message ?? FALLBACK_MESSAGE[parsed.errorType], {
      errorType: parsed.errorType,
      status: response.status,
      detail: body,
    });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: DesignResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = frame.match(/^event:\s*(.+)$/m)?.[1];
      const rawData = frame.match(/^data:\s*(.+)$/m)?.[1];
      if (!event || !rawData) continue;
      const data = JSON.parse(rawData) as Record<string, unknown>;
      if (event === "progress") {
        const stage = data["stage"];
        if (stage === "llm" || stage === "geometry") {
          onProgress(stage, String(data["message"] ?? ""));
        }
      } else if (event === "complete") {
        finalResult = data as unknown as DesignResponse;
      } else if (event === "error") {
        const rawType = data["error_type"];
        const errorType = KNOWN_ERROR_TYPES.find((known) => known === rawType) ?? "unknown";
        throw new ApiError(String(data["message"] ?? FALLBACK_MESSAGE[errorType]), {
          errorType,
          status: typeof data["status"] === "number" ? data["status"] : 500,
          detail: rawData,
        });
      }
    }
    if (done) break;
  }
  if (!finalResult) {
    throw new ApiError("설계 스트림이 완료 데이터 없이 종료됐습니다.", { errorType: "unknown", status: 0 });
  }
  return finalResult;
}

export function reviseDesign(designId: string, instruction: string): Promise<ReviseResponse> {
  return postJson<ReviseResponse>(`${BASE}/design/${encodeURIComponent(designId)}/revise`, {
    instruction,
  });
}

export function getHistory(designId: string): Promise<HistoryResponse> {
  return request<HistoryResponse>(`${BASE}/design/${encodeURIComponent(designId)}/history`);
}

export function getVersion(designId: string, version: number): Promise<VersionResponse> {
  return request<VersionResponse>(
    `${BASE}/design/${encodeURIComponent(designId)}/versions/${version}`,
  );
}

/**
 * `artifacts.stl` / `artifacts.step` 값을 브라우저가 바로 요청할 수 있는 URL 로 바꾼다.
 *
 * 백엔드가 절대 URL 을 주면 그대로, `/api/...` 경로를 주면 그대로 쓴다.
 * `a1b2c3d4-v1.stl` 같은 아티팩트 파일명만 오는 경우만 `/api/v1/artifacts/` 를 붙인다.
 * 세 형태 모두 같은 파일을 가리키므로 이건 폴백이 아니라 표기 정규화다.
 */
export function artifactUrl(value: string): string {
  if (/^https?:\/\//i.test(value)) {
    return value;
  }
  if (value.startsWith("/")) {
    return value;
  }
  return `${BASE}/artifacts/${value.replace(/^artifacts\//, "")}`;
}
