import { useEffect, useRef, useState } from "react";
import { ApiError, generatePhoto3D, photo3dHealth } from "../api/client";
import type { Photo3DHealth, Photo3DResult, Photo3DView } from "../api/client";

const VIEWS: readonly { id: Photo3DView; label: string; required: boolean }[] = [
  { id: "front", label: "정면", required: true },
  { id: "back", label: "후면", required: false },
  { id: "left", label: "좌측", required: false },
  { id: "right", label: "우측", required: false },
];

interface Props {
  onGenerated: (result: Photo3DResult) => void;
  onError: (error: ApiError) => void;
  onReset: () => void;
}

export function Photo3DPanel({ onGenerated, onError, onReset }: Props) {
  const previewUrls = useRef(new Set<string>());
  const [files, setFiles] = useState<Partial<Record<Photo3DView, File>>>({});
  const [previews, setPreviews] = useState<Partial<Record<Photo3DView, string>>>({});
  const [server, setServer] = useState<Photo3DHealth | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    const refresh = () => {
      photo3dHealth()
        .then((status) => { if (active) setServer(status); })
        .catch(() => { if (active) setServer(null); });
    };
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
      previewUrls.current.forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);

  function select(view: Photo3DView, file: File | undefined) {
    const previous = previews[view];
    if (previous) {
      previewUrls.current.delete(previous);
      URL.revokeObjectURL(previous);
    }
    const next = file ? URL.createObjectURL(file) : undefined;
    if (next) previewUrls.current.add(next);
    setPreviews((current) => ({ ...current, [view]: next }));
    setFiles((current) => {
      const updated = { ...current };
      if (file) updated[view] = file;
      else delete updated[view];
      return updated;
    });
    onReset();
  }

  async function generate() {
    if (!files.front || busy) return;
    setBusy(true);
    try {
      const result = await generatePhoto3D(files);
      onGenerated(result);
    } catch (caught) {
      onError(caught instanceof ApiError ? caught : new ApiError(String(caught), { errorType: "unknown", status: 0 }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="drawing-card photo3d-card">
      <div className="section-heading">
        <div><span className="eyebrow">LOCAL GPU MESH</span><h2>사진에서 3D 만들기</h2></div>
        <span className={`local-model-state ${server?.ready ? "is-ready" : ""}`}>
          {server?.ready ? "GPU 준비됨" : "서버 꺼짐"}
        </span>
      </div>
      <p className="drawing-help">
        정면은 필수이고 후면·좌측·우측을 추가하면 형상 일관성이 좋아집니다. 단색 또는 투명 배경 사진을 사용하세요.
      </p>
      <p className="mesh-notice">
        Hunyuan3D-2mv가 로컬 GPU에서 만드는 결과는 삼각형 GLB 메시입니다. 치수 기반 CAD·STEP이 아닙니다.
      </p>
      <div className="photo3d-upload-grid">
        {VIEWS.map((view) => (
          <label className="photo3d-slot" key={view.id}>
            <strong>{view.label}{view.required ? " *" : ""}</strong>
            {previews[view.id] ? <img src={previews[view.id]} alt={`${view.label} 미리보기`} /> : <span>사진 선택</span>}
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(event) => select(view.id, event.target.files?.[0])}
            />
            <small>{files[view.id]?.name ?? (view.required ? "필수" : "선택")}</small>
          </label>
        ))}
      </div>
      {!server?.ready && (
        <p className="drawing-warning">로컬 Hunyuan 서버를 먼저 실행하세요. 실행 방법은 README의 `사진 3D · GPU` 절을 확인하세요.</p>
      )}
      <button className="drawing-generate" type="button" disabled={!files.front || !server?.ready || busy} onClick={generate}>
        {busy ? "로컬 GPU 생성 중…" : "사진으로 3D 메시 생성 →"}
      </button>
    </section>
  );
}
