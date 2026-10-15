# Track D 운영 기능 판정

판정일: 2026-10-15

## 관찰 근거

`python scripts/drawing_e2e.py --server-pid <uvicorn-pid>`로 실행 중인 동기 API에 합성 회귀 입력 30개를 순차 요청했다. 원자료는 [`experiments/drawing-e2e/results.json`](../experiments/drawing-e2e/results.json)에 있다.

| 지표 | 관찰값 | 도입 기준 | 판정 |
|---|---:|---:|---|
| analyze → CAD → STEP HTTP E2E p95 | 0.1831초 | 3초 초과 | 비동기 job 불필요 |
| API 분석 자체 p95 | 0.0105초 | 3초 초과 | SSE progress 불필요 |
| 30건 처리 중 서버 RSS 증가 | 5.72 MiB | 지속 증가 또는 OOM | 별도 worker 불필요 |
| 30건 처리 중 디스크 증가 | 1.51 MiB | 용량 압박 | 24시간 TTL 유지로 충분 |
| 세션 복구 요구 | 없음 | 명시적 복구 요구 | draft DB 불필요 |

## 결정

- 도면 analyze/generate는 동기 API를 유지한다. 현재 측정에서 job ID, 큐, polling, 취소 상태를 추가하면 실패 상태와 정리 경로만 늘어난다.
- 도면 경로에 SSE를 추가하지 않는다. 200ms 미만 p95에서는 연결 복구와 이벤트 순서 보장이 사용자 가치보다 복잡하다.
- 편집 draft는 브라우저 메모리에만 둔다. 확정한 결과만 기존 `design_versions`에 저장한다.
- 업로드 원본은 보관하지 않는다. 정규화 이미지, overlay, 후보 JSON만 안전한 analysis ID 아래 두고 24시간 TTL로 정리한다.

## 재검토 조건

다음 중 하나가 실제 입력에서 관찰되면 해당 기능만 다시 검토한다.

1. HTTP E2E p95가 3초를 넘는다.
2. 동시 요청 때문에 interactive 응답이 막힌다.
3. 사용자가 브라우저/서버 재시작 뒤 미확정 편집 복구를 요구한다.
4. 24시간 analysis 디스크 증가가 운영 저장공간의 10%를 넘는다.
