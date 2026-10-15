import { useEffect, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { ApiError, analyzeDrawing, generateDrawing } from "../api/client";
import type {
  AnalysisRegion,
  DrawingAnalysis,
  DrawingGenerateResponse,
  DrawingHoleCandidate,
  ProfileHole,
} from "../api/client";

type Point = [number, number];
type EditableProfile = {
  outer: Point[];
  holes: Array<DrawingHoleCandidate | null>;
};
type DragTarget =
  | { kind: "outer"; point: number }
  | { kind: "polygon"; hole: number; point: number }
  | { kind: "circle"; hole: number };
type PointMode = "move" | "add";

interface DrawingPanelProps {
  onGenerated: (result: DrawingGenerateResponse) => void;
  onError: (error: ApiError) => void;
  onReset: () => void;
}

function apiError(caught: unknown): ApiError {
  return caught instanceof ApiError
    ? caught
    : new ApiError(String(caught), { errorType: "unknown", status: 0 });
}

function cloneProfile(profile: EditableProfile): EditableProfile {
  return structuredClone(profile);
}

function svgPoint(event: ReactPointerEvent<SVGSVGElement>, width: number, height: number): Point {
  const bounds = event.currentTarget.getBoundingClientRect();
  return [
    Math.max(0, Math.min(width, ((event.clientX - bounds.left) / bounds.width) * width)),
    Math.max(0, Math.min(height, ((event.clientY - bounds.top) / bounds.height) * height)),
  ];
}

function pointsAttribute(points: Point[]): string {
  return points.map(([x, y]) => `${x},${y}`).join(" ");
}

const WARNING_TEXT: Record<string, string> = {
  ambiguous_outer: "외곽선 후보가 여러 개입니다. 올바른 후보를 선택하세요.",
  double_contour_suspected: "굵은 이중선을 구멍에서 제외했습니다.",
  small_outer_candidates_ignored: "작은 글자·잡음 외곽 후보를 제외했습니다.",
  small_holes_ignored: "작은 글자·무늬를 구멍에서 제외했습니다.",
  detail_heavy_input: "세부 무늬가 많습니다. 실물 사진 대신 형상선만 있는 정면 도면을 권장합니다.",
  ocr_unavailable: "OCR을 사용할 수 없습니다. 기준 길이를 직접 입력하세요.",
};

function pointToSegmentDistance(point: Point, start: Point, end: Point): number {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const lengthSquared = dx * dx + dy * dy;
  if (lengthSquared === 0) return Math.hypot(point[0] - start[0], point[1] - start[1]);
  const projection = Math.max(
    0,
    Math.min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / lengthSquared),
  );
  return Math.hypot(
    point[0] - (start[0] + projection * dx),
    point[1] - (start[1] + projection * dy),
  );
}

function simplifyPolygon(points: Point[], tolerance: number): Point[] {
  let current = points.slice();
  let changed = true;
  while (changed && current.length > 3) {
    changed = false;
    const next = current.filter((point, index) => {
      if (current.length <= 3) return true;
      const previous = current[(index - 1 + current.length) % current.length]!;
      const following = current[(index + 1) % current.length]!;
      const keep = pointToSegmentDistance(point, previous, following) >= tolerance;
      changed ||= !keep;
      return keep;
    });
    if (next.length >= 3) current = next;
    else break;
  }
  return current;
}

export function DrawingPanel({ onGenerated, onError, onReset }: DrawingPanelProps) {

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewSize, setPreviewSize] = useState<{ width: number; height: number } | null>(null);
  const [region, setRegion] = useState<AnalysisRegion | null>(null);
  const [regionStart, setRegionStart] = useState<Point | null>(null);
  const [analysis, setAnalysis] = useState<DrawingAnalysis | null>(null);
  const [profile, setProfile] = useState<EditableProfile | null>(null);
  const [past, setPast] = useState<EditableProfile[]>([]);
  const [future, setFuture] = useState<EditableProfile[]>([]);
  const [drag, setDrag] = useState<DragTarget | null>(null);
  const [pointMode, setPointMode] = useState<PointMode>("move");
  const [selectedOuterPoint, setSelectedOuterPoint] = useState<number | null>(null);
  const [calibration, setCalibration] = useState<[Point, Point]>([[0, 0], [1, 0]]);
  const [calibrationStep, setCalibrationStep] = useState<0 | 1 | null>(null);
  const [referenceMm, setReferenceMm] = useState(100);
  const [depth, setDepth] = useState(10);
  const [name, setName] = useState("도면 가져오기");
  const [dimensionValues, setDimensionValues] = useState<number[]>([]);
  const [rejectedDimensions, setRejectedDimensions] = useState<number[]>([]);
  const [detailConfirmed, setDetailConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  function chooseFile(next: File | null) {
    onReset();
    if (preview) URL.revokeObjectURL(preview);
    setFile(next);
    setPreview(next ? URL.createObjectURL(next) : null);
    setPreviewSize(null);
    setRegion(null);
    setAnalysis(null);
    setProfile(null);
    setPast([]);
    setFuture([]);
    setDimensionValues([]);
    setRejectedDimensions([]);
    setPointMode("move");
    setDetailConfirmed(false);
    setSelectedOuterPoint(null);
  }

  function rawPoint(event: ReactPointerEvent<HTMLDivElement>): Point | null {
    const image = event.currentTarget.querySelector("img");
    if (!image?.naturalWidth || !image.naturalHeight) return null;
    const bounds = image.getBoundingClientRect();
    return [
      Math.max(0, Math.min(image.naturalWidth, ((event.clientX - bounds.left) / bounds.width) * image.naturalWidth)),
      Math.max(0, Math.min(image.naturalHeight, ((event.clientY - bounds.top) / bounds.height) * image.naturalHeight)),
    ];
  }

  function startRegion(event: ReactPointerEvent<HTMLDivElement>) {
    const point = rawPoint(event);
    if (point) {
      event.currentTarget.setPointerCapture(event.pointerId);
      setRegionStart(point);
      setRegion({ x: Math.round(point[0]), y: Math.round(point[1]), width: 1, height: 1 });
    }
  }

  function moveRegion(event: ReactPointerEvent<HTMLDivElement>) {
    if (!regionStart) return;
    const point = rawPoint(event);
    if (!point) return;
    const x = Math.min(regionStart[0], point[0]);
    const y = Math.min(regionStart[1], point[1]);
    setRegion({
      x: Math.round(x),
      y: Math.round(y),
      width: Math.max(1, Math.round(Math.abs(point[0] - regionStart[0]))),
      height: Math.max(1, Math.round(Math.abs(point[1] - regionStart[1]))),
    });
  }

  async function analyze() {
    if (!file) return;
    onReset();
    setBusy(true);
    try {
      const selected = region && region.width >= 5 && region.height >= 5 ? region : null;
      const result = await analyzeDrawing(file, selected);
      const editable: EditableProfile = {
        outer: result.profile.outer.points_px,
        holes: result.profile.holes,
      };
      const xs = editable.outer.map(([x]) => x);
      const ys = editable.outer.map(([, y]) => y);
      const middleY = (Math.min(...ys) + Math.max(...ys)) / 2;
      setCalibration([[Math.min(...xs), middleY], [Math.max(...xs), middleY]]);
      setAnalysis(result);
      setProfile(editable);
      setPast([]);
      setFuture([]);
      setDimensionValues(result.profile.dimensions.map((candidate) => candidate.value_mm));
      setRejectedDimensions([]);
      setDetailConfirmed(false);
      setSelectedOuterPoint(null);
    } catch (caught) {
      onError(apiError(caught));
    } finally {
      setBusy(false);
    }
  }

  function apply(next: EditableProfile) {
    if (!profile) return;
    setPast((items) => [...items, cloneProfile(profile)]);
    setProfile(next);
    setFuture([]);
  }

  function undo() {
    const previous = past.at(-1);
    if (!profile || !previous) return;
    setPast((items) => items.slice(0, -1));
    setFuture((items) => [cloneProfile(profile), ...items]);
    setProfile(previous);
  }

  function redo() {
    const next = future[0];
    if (!profile || !next) return;
    setPast((items) => [...items, cloneProfile(profile)]);
    setFuture((items) => items.slice(1));
    setProfile(next);
  }

  function beginDrag(target: DragTarget) {
    if (!profile) return;
    setPast((items) => [...items, cloneProfile(profile)]);
    setFuture([]);
    if (target.kind === "outer") setSelectedOuterPoint(target.point);
    setDrag(target);
  }

  function moveHandle(event: ReactPointerEvent<SVGSVGElement>) {
    if (!analysis || !profile || !drag) return;
    const point = svgPoint(event, analysis.profile.image.width_px, analysis.profile.image.height_px);
    const next = cloneProfile(profile);
    if (drag.kind === "outer") next.outer[drag.point] = point;
    if (drag.kind === "polygon") {
      const hole = next.holes[drag.hole];
      if (hole?.kind === "polygon") hole.points_px[drag.point] = point;
    }
    if (drag.kind === "circle") {
      const hole = next.holes[drag.hole];
      if (hole?.kind === "circle") hole.center_px = point;
    }
    setProfile(next);
  }

  function endDrag() {
    setDrag(null);
  }

  function handleCanvasClick(event: ReactPointerEvent<SVGSVGElement>) {
    if (!analysis || !profile || drag) return;
    const point = svgPoint(event, analysis.profile.image.width_px, analysis.profile.image.height_px);
    if (calibrationStep !== null) {
      setCalibration((current) => calibrationStep === 0 ? [point, current[1]] : [current[0], point]);
      setCalibrationStep(calibrationStep === 0 ? 1 : null);
      return;
    }
    if (pointMode !== "add") return;
    let nearestSegment = 0;
    let nearestDistance = Number.POSITIVE_INFINITY;
    for (let index = 0; index < profile.outer.length; index += 1) {
      const distance = pointToSegmentDistance(
        point,
        profile.outer[index]!,
        profile.outer[(index + 1) % profile.outer.length]!,
      );
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestSegment = index;
      }
    }
    const next = cloneProfile(profile);
    next.outer.splice(nearestSegment + 1, 0, point);
    apply(next);
    setSelectedOuterPoint(nearestSegment + 1);
    setPointMode("move");
  }

  function deleteOuterPoint(index: number) {
    if (!profile || profile.outer.length <= 3) return;
    const next = cloneProfile(profile);
    next.outer.splice(index, 1);
    apply(next);
    setSelectedOuterPoint(null);
  }

  function simplifyOuter() {
    if (!profile || !analysis) return;
    const tolerance = Math.max(
      analysis.profile.image.width_px,
      analysis.profile.image.height_px,
    ) * 0.006;
    const next = cloneProfile(profile);
    next.outer = simplifyPolygon(next.outer, tolerance);
    apply(next);
    setSelectedOuterPoint(null);
  }

  async function generate() {
    if (!analysis || !profile) return;
    if (analysis.profile.warnings.includes("detail_heavy_input") && !detailConfirmed) {
      onError(new ApiError("세부 무늬가 많은 입력입니다. 외곽선을 확인한 뒤 확인란을 선택하세요.", { errorType: "profile_invalid", status: 422 }));
      return;
    }
    const pixelLength = Math.hypot(
      calibration[1][0] - calibration[0][0],
      calibration[1][1] - calibration[0][1],
    );
    if (pixelLength <= 0 || referenceMm <= 0 || depth <= 0) {
      onError(new ApiError("기준 길이와 돌출 깊이는 양수여야 합니다.", { errorType: "profile_invalid", status: 422 }));
      return;
    }
    const scale = referenceMm / pixelLength;
    const minX = Math.min(...profile.outer.map(([x]) => x));
    const minY = Math.min(...profile.outer.map(([, y]) => y));
    const convert = ([x, y]: Point): Point => [(x - minX) * scale, (y - minY) * scale];
    const holes: ProfileHole[] = [];
    for (const hole of profile.holes) {
      if (hole?.kind === "circle") {
        holes.push({
          kind: "circle",
          center: convert(hole.center_px),
          radius: hole.radius_px * scale,
        });
      } else if (hole?.kind === "polygon") {
        holes.push({ kind: "polygon", points: hole.points_px.map(convert) });
      }
    }
    setBusy(true);
    try {
      onGenerated(await generateDrawing({
        analysis_id: analysis.analysis_id,
        name: name.trim() || "도면 가져오기",
        profile: { outer: profile.outer.map(convert), holes },
        depth,
      }));
    } catch (caught) {
      onError(apiError(caught));
    } finally {
      setBusy(false);
    }
  }

  const imageSize = analysis?.profile.image;
  const calibrationLength = Math.hypot(
    calibration[1][0] - calibration[0][0],
    calibration[1][1] - calibration[0][1],
  );
  const activeHoleCount = profile?.holes.filter((hole) => hole !== null).length ?? 0;
  const profileScale = calibrationLength > 0 ? referenceMm / calibrationLength : 0;
  const profileWidthMm = profile
    ? (Math.max(...profile.outer.map(([x]) => x)) - Math.min(...profile.outer.map(([x]) => x))) * profileScale
    : 0;
  const profileHeightMm = profile
    ? (Math.max(...profile.outer.map(([, y]) => y)) - Math.min(...profile.outer.map(([, y]) => y))) * profileScale
    : 0;

  return (
    <section className="drawing-card" aria-label="2D 도면 가져오기">
      <div className="section-heading">
        <div><span className="eyebrow">2D IMPORT</span><h2>도면에서 3D 만들기</h2></div>
        {analysis && <span className="count-badge">{profile?.outer.length ?? 0}점</span>}
      </div>
      <p className="drawing-help">형상선이 선명한 단일 정면 도면을 사용하세요. 실물 사진·원근 사진·라벨 무늬는 정확한 CAD로 변환할 수 없습니다.</p>
      <label className="file-picker">
        <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => chooseFile(event.target.files?.[0] ?? null)} />
        <span>{file ? file.name : "도면 이미지 선택"}</span>
      </label>

      {preview && !analysis && (
        <>
          <div className="region-editor" onPointerDown={startRegion} onPointerMove={moveRegion} onPointerUp={() => setRegionStart(null)}>
            <img src={preview} alt="업로드한 도면" draggable={false} onLoad={(event) => setPreviewSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} />
            {region && previewSize && <span className="region-box" style={{ left: `${region.x / previewSize.width * 100}%`, top: `${region.y / previewSize.height * 100}%`, width: `${region.width / previewSize.width * 100}%`, height: `${region.height / previewSize.height * 100}%` }} />}
          </div>
          <div className="drawing-actions">
            <button type="button" onClick={() => setRegion(null)} disabled={!region}>전체 이미지</button>
            <button type="button" className="primary-button" onClick={analyze} disabled={busy}>{busy ? "분석 중…" : "선택 영역 분석"}</button>
          </div>
        </>
      )}

      {analysis && profile && imageSize && (
        <>
          <div className="profile-editor">
            <img src={analysis.image_url} alt="정규화한 도면" />
            <svg
              className={pointMode === "add" || calibrationStep !== null ? "is-picking" : ""}
              viewBox={`0 0 ${imageSize.width_px} ${imageSize.height_px}`}
              aria-label="검출 프로파일 편집기"
              onPointerMove={moveHandle}
              onPointerUp={endDrag}
              onPointerCancel={endDrag}
              onClick={handleCanvasClick}
            >
              <polygon className="profile-outer" points={pointsAttribute(profile.outer)} />
              {profile.holes.map((hole, holeIndex) => hole && (hole.kind === "circle" ? (
                <circle key={`h-${holeIndex}`} className="profile-hole" cx={hole.center_px[0]} cy={hole.center_px[1]} r={hole.radius_px} />
              ) : (
                <polygon key={`h-${holeIndex}`} className="profile-hole" points={pointsAttribute(hole.points_px)} />
              )))}
              <line className="calibration-line" x1={calibration[0][0]} y1={calibration[0][1]} x2={calibration[1][0]} y2={calibration[1][1]} />
              {calibration.map(([x, y], index) => <circle key={`c-${index}`} className="calibration-point" cx={x} cy={y} r="8" />)}
              {profile.outer.map(([x, y], index) => <circle key={`o-${index}`} className={`point-handle${selectedOuterPoint === index ? " is-selected" : ""}`} cx={x} cy={y} r="8" onClick={(event) => { event.stopPropagation(); setSelectedOuterPoint(index); }} onPointerDown={(event) => { event.stopPropagation(); beginDrag({ kind: "outer", point: index }); }} />)}
              {profile.holes.map((hole, holeIndex) => hole?.kind === "polygon" ? hole.points_px.map(([x, y], point) => (
                <circle key={`hp-${holeIndex}-${point}`} className="hole-handle" cx={x} cy={y} r="7" onClick={(event) => event.stopPropagation()} onPointerDown={(event) => { event.stopPropagation(); beginDrag({ kind: "polygon", hole: holeIndex, point }); }} />
              )) : hole?.kind === "circle" ? (
                <circle key={`hc-${holeIndex}`} className="hole-handle" cx={hole.center_px[0]} cy={hole.center_px[1]} r="7" onClick={(event) => event.stopPropagation()} onPointerDown={(event) => { event.stopPropagation(); beginDrag({ kind: "circle", hole: holeIndex }); }} />
              ) : null)}
            </svg>
          </div>

          {analysis.profile.warnings.length > 0 && (
            <div className="drawing-warning">
              <strong>검출 확인 필요</strong>
              <ul>{analysis.profile.warnings.map((warning) => <li key={warning}>{WARNING_TEXT[warning] ?? warning}</li>)}</ul>
            </div>
          )}

          <div className="profile-summary">
            <strong>검출 결과</strong>
            <table>
              <tbody>
                <tr><th>외곽점</th><td>{profile.outer.length}개</td><th>사용 구멍</th><td>{activeHoleCount}개</td></tr>
                <tr><th>예상 폭</th><td>{profileWidthMm.toFixed(1)} mm</td><th>예상 높이</th><td>{profileHeightMm.toFixed(1)} mm</td></tr>
                <tr><th>기준선</th><td>{calibrationLength.toFixed(1)} px</td><th>배율</th><td>{profileScale.toFixed(4)} mm/px</td></tr>
              </tbody>
            </table>
          </div>
          {analysis.profile.warnings.includes("detail_heavy_input") && (
            <label className="detail-confirmation">
              <input type="checkbox" checked={detailConfirmed} onChange={(event) => setDetailConfirmed(event.target.checked)} />
              실물 사진이 아닌 단일 정면 형상이며, 작은 무늬가 제외된 외곽선을 직접 확인했습니다.
            </label>
          )}

          <div className="candidate-list">
            <strong>외곽 후보</strong>
            {analysis.profile.outer_candidates.map((candidate, index) => (
              <button type="button" key={index} onClick={() => apply({ ...cloneProfile(profile), outer: candidate.points_px })}>후보 {index + 1} · {(candidate.confidence * 100).toFixed(0)}%</button>
            ))}
          </div>

          <div className="hole-list">
            <strong>구멍 후보</strong>
            {analysis.profile.holes.length === 0 && <span className="muted">검출 없음</span>}
            {analysis.profile.holes.map((source, index) => {
              const selected = profile.holes[index] !== null;
              return <label key={index}><input type="checkbox" checked={selected} onChange={() => { const next = cloneProfile(profile); next.holes[index] = selected ? null : structuredClone(source); apply(next); }} /> 구멍 {index + 1} · {source.kind}</label>;
            })}
            {profile.holes.map((hole, index) => hole?.kind === "circle" && (
              <label key={`r-${index}`}>반경(px)<input type="number" min="1" step="0.5" value={hole.radius_px} onChange={(event) => { const next = cloneProfile(profile); const target = next.holes[index]; if (target?.kind === "circle") target.radius_px = Number(event.target.value); apply(next); }} /></label>
            ))}
          </div>

          {analysis.profile.dimensions.length > 0 && (
            <div className="dimension-list">
              <strong>OCR 치수 후보 — 확인 전에는 적용되지 않습니다</strong>
              {analysis.profile.dimensions.map((candidate, index) => (
                <div key={`${candidate.text}-${index}`} className={rejectedDimensions.includes(index) ? "is-rejected" : ""}>
                  <span>{candidate.text} · {(candidate.confidence * 100).toFixed(0)}%</span>
                  <input
                    aria-label={`OCR 치수 후보 ${index + 1}`}
                    type="number"
                    min="0.1"
                    step="0.1"
                    value={dimensionValues[index] ?? candidate.value_mm}
                    disabled={rejectedDimensions.includes(index)}
                    onChange={(event) => setDimensionValues((values) => values.map((value, item) => item === index ? Number(event.target.value) : value))}
                  />
                  <button type="button" disabled={rejectedDimensions.includes(index)} onClick={() => setReferenceMm(dimensionValues[index] ?? candidate.value_mm)}>기준 길이로 사용</button>
                  <button type="button" onClick={() => setRejectedDimensions((items) => items.includes(index) ? items.filter((item) => item !== index) : [...items, index])}>
                    {rejectedDimensions.includes(index) ? "복원" : "거부"}
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="editor-toolbar">
            <button type="button" onClick={undo} disabled={past.length === 0}>실행 취소</button>
            <button type="button" onClick={redo} disabled={future.length === 0}>다시 실행</button>
            <button type="button" className={pointMode === "add" ? "is-active" : ""} onClick={() => { setCalibrationStep(null); setPointMode(pointMode === "add" ? "move" : "add"); }}>외곽점 추가</button>
            <button type="button" onClick={simplifyOuter} disabled={profile.outer.length <= 3}>불필요한 점 정리</button>
            <button type="button" onClick={() => selectedOuterPoint !== null && deleteOuterPoint(selectedOuterPoint)} disabled={selectedOuterPoint === null || profile.outer.length <= 3}>선택 점 삭제</button>
            <button type="button" className={calibrationStep !== null ? "is-active" : ""} onClick={() => { setPointMode("move"); setCalibrationStep(0); }}>기준점 2개 선택</button>
            <button type="button" onClick={() => { setAnalysis(null); setProfile(null); setPointMode("move"); }}>영역 다시 선택</button>
          </div>
          <p className="editor-help">
            점을 클릭해 선택하고 드래그해 이동 · “선택 점 삭제”로 제거 · “외곽점 추가” 후 외곽선을 클릭 ·
            {calibrationStep === 0 ? " 기준선 첫 번째 점을 클릭하세요." : calibrationStep === 1 ? " 기준선 두 번째 점을 클릭하세요." : " 파란선 양 끝이 실제 길이의 기준입니다."}
          </p>

          <div className="drawing-fields">
            <label>기준 길이 (mm)<input type="number" min="0.1" step="0.1" value={referenceMm} onChange={(event) => setReferenceMm(Number(event.target.value))} /><small>{calibrationLength.toFixed(1)}px</small></label>
            <label>돌출 깊이 (mm)<input type="number" min="0.1" step="0.1" value={depth} onChange={(event) => setDepth(Number(event.target.value))} /></label>
            <label>설계 이름<input value={name} maxLength={120} onChange={(event) => setName(event.target.value)} /></label>
          </div>
          <button type="button" className="drawing-generate" onClick={generate} disabled={busy || (analysis.profile.warnings.includes("detail_heavy_input") && !detailConfirmed)}>{busy ? "3D 생성 중…" : "확정하고 3D 생성 →"}</button>
        </>
      )}
    </section>
  );
}
