import type { HistoryEntry } from "../api/client";

interface HistoryPanelProps {
  entries: HistoryEntry[];
  currentVersion: number | null;
  loading: boolean;
  onSelect: (version: number) => void;
}

export function HistoryPanel({ entries, currentVersion, loading, onSelect }: HistoryPanelProps) {
  return (
    <section className="history-panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">VERSIONS</span>
          <h2>설계 이력</h2>
        </div>
        <span className="count-badge">{entries.length}</span>
      </div>
      {loading ? (
        <p className="muted">이력을 불러오는 중…</p>
      ) : entries.length === 0 ? (
        <p className="muted">첫 설계를 만들면 버전이 여기에 쌓입니다.</p>
      ) : (
        <ol className="history-list">
          {entries.map((entry) => (
            <li key={entry.version}>
              <button
                className={entry.version === currentVersion ? "history-item is-current" : "history-item"}
                onClick={() => onSelect(entry.version)}
              >
                <span className="version-dot">v{entry.version}</span>
                <span className="history-copy">
                  <strong>{entry.name}</strong>
                  <small>{entry.instruction ?? entry.prompt ?? "최초 설계"}</small>
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
