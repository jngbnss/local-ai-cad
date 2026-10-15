import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  analyzeMultiview,
  generateMultiview,
} from "../api/client";
import type {
  DrawingGenerateResponse,
  MultiviewAnalysis,
  MultiviewName,
  ProjectionMethod,
} from "../api/client";

interface MultiviewPanelProps {
  onGenerated: (result: DrawingGenerateResponse) => void;
  onError: (error: ApiError) => void;
  onReset: () => void;
}

const VIEWS: readonly MultiviewName[] = ["front", "top", "right"];
const VIEW_LABEL: Record<MultiviewName, string> = {
  front: "정면도 · X×Z",
  top: "평면도 · X×Y",
  right: "우측면도 · Y×Z",
};

function asApiError(caught: unknown): ApiError {
  return caught instanceof ApiError
    ? caught
    : new ApiError(String(caught), { errorType: "unknown", status: 0 });
}

function points(values: [number, number][]) {
  return values.map(([x, y]) => `${x},${y}`).join(" ");
}

export function MultiviewPanel({ onGenerated, onError, onReset }: MultiviewPanelProps) {
  const previewUrls = useRef(new Set<string>());
  const [files, setFiles] = useState<Partial<Record<MultiviewName, File>>>({});
  const [previews, setPreviews] = useState<Partial<Record<MultiviewName, string>>>({});
  const [projection, setProjection] = useState<ProjectionMethod>("third_angle");
  const [analysis, setAnalysis] = useState<MultiviewAnalysis | null>(null);
  const [width, setWidth] = useState(120);
  const [depth, setDepth] = useState(80);
  const [height, setHeight] = useState(60);
  const [name, setName] = useState("3면도 복원");
  const [busy, setBusy] = useState(false);
  useEffect(() => () => {
    previewUrls.current.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  function choose(view: MultiviewName, file: File | null) {
    const previous = previews[view];
    if (previous) previewUrls.current.delete(previous);
    if (previous) URL.revokeObjectURL(previous);
    setFiles((current) => ({ ...current, [view]: file ?? undefined }));
    const nextPreview = file ? URL.createObjectURL(file) : undefined;
    if (nextPreview) previewUrls.current.add(nextPreview);
    setPreviews((current) => ({ ...current, [view]: nextPreview }));
    setAnalysis(null);
    onReset();
  }

  async function analyze() {
    if (!files.front || !files.top || !files.right) return;
    onReset();
    setBusy(true);
    try {
      setAnalysis(await analyzeMultiview(
        { front: files.front, top: files.top, right: files.right },
        projection,
      ));
    } catch (caught) {
      onError(asApiError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function generate() {
    if (!analysis) return;
    if (width <= 0 || depth <= 0 || height <= 0) {
      onError(new ApiError("가로·깊이·높이는 양수여야 합니다.", { errorType: "multiview_invalid", status: 422 }));
      return;
    }
    setBusy(true);
    try {
      onGenerated(await generateMultiview({
        analysis_id: analysis.analysis_id,
        name: name.trim() || "3면도 복원",
        width,
        depth,
        height,
      }));
    } catch (caught) {
      onError(asApiError(caught));
    } finally {
      setBusy(false);
    }
  }

  const allFiles = VIEWS.every((view) => files[view]);
  const blocked = analysis !== null && VIEWS.some((view) =>
    analysis.views[view].warnings.includes("detail_heavy_input"),
  );

  return (
    <section className="drawing-card multiview-panel" aria-label="3면 CAD 복원">
      <div className="section-heading">
        <div><span className="eyebrow">3 VIEW REVERSE CAD</span><h2>3면도에서 CAD 복원</h2></div>
        <span className="count-badge">BETA</span>
      </div>
      <p className="drawing-help">배경 없는 정면·평면·우측면 선 도면을 각각 올리세요. 세 실루엣의 직교 교집합으로 STEP/STL을 만듭니다.</p>

      <label className="projection-field">투상법
        <select value={projection} onChange={(event) => { setProjection(event.target.value as ProjectionMethod); setAnalysis(null); onReset(); }}>
          <option value="third_angle">제3각법</option>
          <option value="first_angle">제1각법</option>
        </select>
      </label>

      <div className="multiview-upload-grid">
        {VIEWS.map((view) => {
          const detected = analysis?.views[view];
          const image = analysis?.image_urls[view] ?? previews[view];
          return (
            <article className="multiview-card" key={view}>
              <strong>{VIEW_LABEL[view]}</strong>
              <label className="multiview-file">
                <span>{files[view]?.name ?? "이미지 선택"}</span>
                <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => choose(view, event.target.files?.[0] ?? null)} />
              </label>
              {image && (
                <div className="multiview-preview">
                  <img src={image} alt={`${VIEW_LABEL[view]} 미리보기`} />
                  {detected && (
                    <svg viewBox={`0 0 ${detected.image.width_px} ${detected.image.height_px}`}>
                      <polygon className="profile-outer" points={points(detected.outer.points_px)} />
                      {detected.holes.map((hole, index) => hole.kind === "circle" ? (
                        <circle key={index} className="profile-hole" cx={hole.center_px[0]} cy={hole.center_px[1]} r={hole.radius_px} />
                      ) : (
                        <polygon key={index} className="profile-hole" points={points(hole.points_px)} />
                      ))}
                    </svg>
                  )}
                </div>
              )}
              {detected && <small>외곽점 {detected.outer.points_px.length} · 구멍 {detected.holes.length}</small>}
            </article>
          );
        })}
      </div>

      {!analysis && <div className="drawing-actions"><button type="button" className="primary-button" onClick={analyze} disabled={!allFiles || busy}>{busy ? "3면 분석 중…" : "세 도면 분석 →"}</button></div>}

      {analysis && (
        <>
          <div className="profile-summary">
            <strong>공통 실물 치수</strong>
            <table><tbody><tr><th>가로 X</th><td>{width} mm</td><th>깊이 Y</th><td>{depth} mm</td></tr><tr><th>높이 Z</th><td>{height} mm</td><th>투상법</th><td>{projection === "third_angle" ? "제3각법" : "제1각법"}</td></tr></tbody></table>
          </div>
          <div className="multiview-dimensions">
            <label>가로 X (mm)<input type="number" min="0.1" value={width} onChange={(event) => setWidth(Number(event.target.value))} /></label>
            <label>깊이 Y (mm)<input type="number" min="0.1" value={depth} onChange={(event) => setDepth(Number(event.target.value))} /></label>
            <label>높이 Z (mm)<input type="number" min="0.1" value={height} onChange={(event) => setHeight(Number(event.target.value))} /></label>
            <label>설계 이름<input value={name} maxLength={120} onChange={(event) => setName(event.target.value)} /></label>
          </div>
          {blocked && <p className="drawing-blocked">한 개 이상의 뷰에 문자·무늬·복잡한 선이 너무 많아 생성이 차단되었습니다.</p>}
          <button type="button" className="drawing-generate" onClick={generate} disabled={busy || blocked}>{busy ? "3D 생성 중…" : blocked ? "도면을 정리한 뒤 다시 분석하세요" : "3면 교집합 CAD 생성 →"}</button>
        </>
      )}
    </section>
  );
}
