import { lazy, Suspense, useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  ApiError,
  artifactUrl,
  createDesignStream,
  getHistory,
  getVersion,
  health,
  reviseDesign,
} from "./api/client";
import type {
  DesignResponse,
  DrawingGenerateResponse,
  HealthResponse,
  HistoryEntry,
  Photo3DResult,
} from "./api/client";
import { DrawingPanel } from "./components/DrawingPanel";
import { MultiviewPanel } from "./components/MultiviewPanel";
import { Photo3DPanel } from "./components/Photo3DPanel";
import { HistoryPanel } from "./components/HistoryPanel";

const Viewer = lazy(() => import("./components/Viewer").then((module) => ({ default: module.Viewer })));

type Stage = "idle" | "llm" | "geometry" | "done";
type InputMode = "text" | "drawing" | "multiview" | "photo3d";

const ERROR_GUIDE: Record<string, string> = {
  cuda_unavailable: "CUDA와 그래픽 드라이버 상태를 확인해 주세요.",
  oom: "GPU를 사용하는 다른 앱을 닫고 다시 시도해 주세요.",
  schema_invalid: "치수와 부품 수를 더 명확하게 적어 다시 시도해 주세요.",
  geometry_failed: "서로 겹치는 부품이나 지나치게 작은 치수가 없는지 확인해 주세요.",
  model_download_failed: "인터넷 연결과 모델 캐시 경로를 확인해 주세요.",
  image_too_large: "10MB 이하이며 4096×4096 픽셀 이하인 이미지를 사용해 주세요.",
  image_unsupported: "PNG, JPEG 또는 WebP 이미지를 선택해 주세요.",
  profile_detection_failed: "닫힌 외곽선이 선명한 영역을 다시 선택해 주세요.",
  profile_invalid: "겹치거나 외곽선 밖에 있는 구멍과 점 위치를 확인해 주세요.",
  photo_input_unsupported: "배경·글자·원근을 제거한 단일 정면 선 도면을 올려 주세요.",
  analysis_not_found: "분석 결과가 만료됐습니다. 이미지를 다시 분석해 주세요.",
  invalid_analysis_region: "폭과 높이가 있는 영역을 다시 선택해 주세요.",
  multiview_invalid: "정면·평면·우측면 역할과 공통 X/Y/Z 치수를 확인해 주세요.",
  photo3d_invalid: "사진 방향과 배경 대비를 확인해 주세요.",
  photo3d_unavailable: "8090 포트의 로컬 Hunyuan3D 서버를 먼저 실행해 주세요.",
  photo3d_generation_failed: "다른 GPU 모델과 GPU 앱을 종료한 뒤 다시 시도해 주세요.",
  network: "백엔드가 127.0.0.1:8000에서 실행 중인지 확인해 주세요.",
  unknown: "백엔드 로그에서 요청 ID와 상세 오류를 확인해 주세요.",
};

function formatSeconds(value: number) {
  return value < 1 ? `${Math.round(value * 1000)}ms` : `${value.toFixed(1)}s`;
}

export default function App() {
  const [server, setServer] = useState<HealthResponse | null>(null);
  const [prompt, setPrompt] = useState("가로 1200mm, 깊이 600mm, 높이 750mm인 책상을 만들어줘. 상판 두께는 25mm이고 다리는 4개야.");
  const [revision, setRevision] = useState("");
  const [result, setResult] = useState<DesignResponse | DrawingGenerateResponse | null>(null);
  const [photoResult, setPhotoResult] = useState<Photo3DResult | null>(null);
  const [historyEntries, setHistoryEntries] = useState<HistoryEntry[]>([]);
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState<ApiError | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [mode, setMode] = useState<InputMode>("text");

  useEffect(() => {
    health().then(setServer).catch(() => setServer(null));
  }, []);

  async function refreshHistory(designId: string) {
    setHistoryLoading(true);
    try {
      setHistoryEntries((await getHistory(designId)).versions.slice().reverse());
    } finally {
      setHistoryLoading(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!prompt.trim() || stage === "llm" || stage === "geometry") return;
    setError(null);
    setStage("llm");
    try {
      const created = await createDesignStream(prompt.trim(), (nextStage) => setStage(nextStage));
      setPhotoResult(null);
      setResult(created);
      await refreshHistory(created.design_id);
      setStage("done");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(String(caught), { errorType: "unknown", status: 0 }));
      setStage("idle");
    }
  }

  async function revise(event: FormEvent) {
    event.preventDefault();
    if (!result || !revision.trim()) return;
    setError(null);
    setStage("llm");
    try {
      const updated = await reviseDesign(result.design_id, revision.trim());
      setResult(updated);
      setRevision("");
      await refreshHistory(updated.design_id);
      setStage("done");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(String(caught), { errorType: "unknown", status: 0 }));
      setStage("done");
    }
  }

  async function selectVersion(version: number) {
    if (!result) return;
    setError(null);
    try {
      const selected = await getVersion(result.design_id, version);
      setResult({ ...result, ...selected, diff: [] });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(String(caught), { errorType: "unknown", status: 0 }));
    }
  }

  async function acceptDrawing(created: DrawingGenerateResponse) {
    setError(null);
    setPhotoResult(null);
    setResult(created);
    await refreshHistory(created.design_id);
    setStage("done");
  }

  function showError(caught: ApiError) {
    setError(caught);
  }

  function resetDrawing() {
    setResult(null);
    setHistoryEntries([]);
    setError(null);
    setPhotoResult(null);
    setStage("idle");
  }

  function acceptPhoto(created: Photo3DResult) {
    setError(null);
    setResult(null);
    setHistoryEntries([]);
    setPhotoResult(created);
    setStage("done");
  }

  const busy = stage === "llm" || stage === "geometry";

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Local AI CAD 홈">
          <span className="brand-mark">L</span>
          <span><strong>LOCAL AI</strong><small>CAD WORKBENCH</small></span>
        </a>
        <div className="server-state">
          <span className={server?.model_loaded ? "status-dot online" : "status-dot"} />
          <span>{server ? (server.model_loaded ? "모델 준비됨" : "모델 로딩 중") : "백엔드 연결 안 됨"}</span>
          {server?.device_name && <small>{server.device_name}</small>}
        </div>
      </header>

      <div id="top" className="workspace">
        <aside className="control-column">
          <nav className="input-tabs" aria-label="설계 입력 방식">
            <button type="button" className={mode === "text" ? "is-active" : ""} onClick={() => setMode("text")}>텍스트 설계</button>
            <button type="button" className={mode === "drawing" ? "is-active" : ""} onClick={() => setMode("drawing")}>2D 도면 가져오기</button>
            <button type="button" className={mode === "multiview" ? "is-active" : ""} onClick={() => setMode("multiview")}>3면 CAD 복원</button>
            <button type="button" className={mode === "photo3d" ? "is-active" : ""} onClick={() => setMode("photo3d")}>사진 3D · GPU</button>
          </nav>
          <section className="intro">
            <span className="eyebrow">PRIVATE · GPU LOCAL</span>
            <h1>말로 만드는<br /><em>실제 CAD.</em></h1>
            <p>설명은 로컬 LLM이 명세로 바꾸고, CadQuery가 바로 제작 가능한 STEP과 STL을 만듭니다.</p>
          </section>

          {mode === "text" ? (
            <>
              <form className="prompt-card" onSubmit={submit}>
                <label htmlFor="prompt">무엇을 설계할까요?</label>
                <textarea id="prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={6} maxLength={4000} />
                <div className="prompt-footer">
                  <span>{prompt.length} / 4000</span>
                  <button className="primary-button" disabled={busy || !prompt.trim()}>
                    {busy ? "생성 중…" : "설계 생성"}<span aria-hidden="true">→</span>
                  </button>
                </div>
              </form>

              {busy && (
                <div className="progress-card" role="status">
                  <span className="spinner" />
                  <div><strong>{stage === "llm" ? "설계 명세 생성 중" : "3D 형상 생성 중"}</strong><small>GPU에서 로컬로 처리하고 있습니다.</small></div>
                </div>
              )}

            </>
          ) : mode === "drawing" ? (
            <DrawingPanel onGenerated={acceptDrawing} onError={showError} onReset={resetDrawing} />
          ) : mode === "multiview" ? (
            <MultiviewPanel onGenerated={acceptDrawing} onError={showError} onReset={resetDrawing} />
          ) : (
            <Photo3DPanel onGenerated={acceptPhoto} onError={showError} onReset={resetDrawing} />
          )}
          {result && (
            <form className="revision-card" onSubmit={revise}>
              <label htmlFor="revision">이 설계를 말로 수정하기</label>
              <div className="inline-input">
                <input id="revision" value={revision} onChange={(event) => setRevision(event.target.value)} placeholder="예: 상판이 다리를 모두 덮도록 넓혀줘" />
                <button disabled={busy || !revision.trim()}>수정</button>
              </div>
            </form>
          )}

          {error && (
            <div className="error-card" role="alert">
              <strong>{error.message}</strong>
              <p>{ERROR_GUIDE[error.errorType] ?? ERROR_GUIDE.unknown}</p>
              {error.detail && <details><summary>상세 정보</summary><pre>{error.detail}</pre></details>}
            </div>
          )}
        </aside>

        <section className="result-column">
          <Suspense fallback={<div className="viewer viewer-loading">3D 뷰어 불러오는 중…</div>}>
            <Viewer
              url={result ? artifactUrl(result.artifacts.stl) : photoResult ? artifactUrl(photoResult.artifact) : null}
              label={result?.spec.name ?? (photoResult ? "로컬 GPU 사진 3D 메시" : "3D 미리보기")}
            />
          </Suspense>
          {result && (
            <div className="result-strip">
              <div><span className="eyebrow">DESIGN</span><strong>{result.spec.name}</strong><small>v{result.version} · {result.spec.parts.length}개 부품</small></div>
              {"metrics" in result && <div className="metric"><span>추론</span><strong>{formatSeconds(result.metrics.inference_seconds)}</strong></div>}
              <div className="metric"><span>부피</span><strong>{(result.geometry.volume_mm3 / 1_000_000).toFixed(1)} L</strong></div>
              <div className="downloads">
                <a href={artifactUrl(result.artifacts.stl)} download>STL</a>
                <a className="download-primary" href={artifactUrl(result.artifacts.step)} download>STEP ↓</a>
              </div>
            </div>
          )}
          {photoResult && (
            <div className="result-strip">
              <div><span className="eyebrow">LOCAL GPU MESH</span><strong>Hunyuan3D-2mv 결과</strong><small>{photoResult.input_views.join(" · ")} · {(photoResult.bytes / 1_000_000).toFixed(1)}MB</small></div>
              <div className="metric"><span>생성</span><strong>{formatSeconds(photoResult.generation_seconds)}</strong></div>
              <div className="downloads"><a className="download-primary" href={artifactUrl(photoResult.artifact)} download>GLB ↓</a></div>
            </div>
          )}

          {result && "diff" in result && result.diff.length > 0 && (
            <section className="diff-card">
              <span className="eyebrow">LATEST CHANGE</span>
              {result.diff.map((item) => <p key={item.path}><code>{item.path}</code><span>{String(item.before)} → {String(item.after)}</span></p>)}
            </section>
          )}

          <HistoryPanel entries={historyEntries} currentVersion={result?.version ?? null} loading={historyLoading} onSelect={selectVersion} />
        </section>
      </div>
    </main>
  );
}
