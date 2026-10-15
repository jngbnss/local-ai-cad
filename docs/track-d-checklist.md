# Track D 실행·검증 체크리스트

각 단계는 구현 → 해당 경로 스모크 → 오류 기록/정리 → 아래 완료 조건 확인 → 커밋·푸시 순서로 닫는다.

## 공통 규칙

- [ ] 실패를 성공으로 바꾸는 폴백이나 묵시적 형상 수정이 없다.
- [ ] 새 오류 타입이 API와 UI에서 원인별로 구분된다.
- [ ] 변경 경로를 실제 실행해 출력 또는 화면을 관찰한다.
- [ ] 영구 테스트는 사용자 가시 동작·경계·불변식만 검사한다.
- [ ] `docs/track-d-errors.md`에 발견·해결·잔존 오류를 기록한다.
- [ ] 단계별 커밋을 `main`에 푸시한다.

## D0 — 위험 우선 기술 스파이크

- [x] 독립 CLI가 이미지 입력과 출력 디렉터리를 받는다.
- [x] normalized PNG, SVG overlay, profile JSON, STEP을 생성한다.
- [x] 사각형, L/U형, 원형 구멍, 굵은 선, 역상 입력을 포함한 합성 평가 입력 10개가 있다.
- [x] 각 입력의 outer 후보 수, hole 수, 분석 시간, 경고를 기록한다.
- [x] 합성 입력 10개 모두 유효 STEP을 생성했다.
- [ ] 실제 사용자 도면 10개 검증 — 입력 미제공으로 합성 평가와 구분해 미완료 유지.

## D1 — 계약과 기하

- [x] px 검출 초안과 mm `ConfirmedProfile`이 분리된다.
- [x] calibration 확정 후 mm 좌표가 CAD 입력 정본이다.
- [x] box/cylinder/sketch_extrusion이 판별 공용체로 검증된다.
- [x] 기존 1.0 저장 데이터가 2.0으로 일회성 마이그레이션된다.
- [x] polygon/circle hole을 포함한 extrusion이 유효한 STL/STEP을 만든다.
- [x] self-intersection, 외부 hole, 겹친 hole을 명시적으로 거부한다.

## D2 — 이미지 분석

- [x] magic bytes, 디코딩, 파일 크기, 픽셀 상한을 검증한다.
- [x] EXIF 방향을 적용하고 메타데이터를 제거한다.
- [x] analysis region 밖 픽셀을 분석하지 않는다.
- [x] outer 후보와 circle/polygon hole 후보를 반환한다.
- [x] 자동 확정 불가 입력은 후보·경고를 반환하고 형상을 조용히 고치지 않는다.
- [x] 합성 30개 회귀셋에서 outer/hole/CAD 결과를 측정했다.

## D3 — 동기 API

- [x] `POST /api/v1/drawing/analyze`가 multipart 이미지를 분석한다.
- [x] 정규화 이미지를 안전한 analysis ID로 조회한다.
- [x] `POST /api/v1/drawing/generate`가 확인된 mm profile만 받는다.
- [x] OpenCV가 event loop 밖 threadpool에서 실행된다.
- [x] 이미지·프로파일·기하·export 오류가 서로 다른 API 오류다.
- [x] 임시 analysis 파일을 TTL로 정리한다.

## D4 — SVG UI

- [x] 텍스트/도면 입력 탭을 전환할 수 있다.
- [x] 이미지 업로드와 analysis region 선택이 동작한다.
- [x] SVG에서 outer, 점, 원형 hole을 선택·수정할 수 있다.
- [x] 기준 길이와 돌출 깊이를 입력할 수 있다.
- [x] undo/redo가 사용자 편집만 되돌린다.
- [x] 명시적 확인 전 3D 생성을 막는다.
- [x] 생성 결과를 기존 Three.js Viewer와 다운로드 패널에서 확인한다.

## D5 — E2E와 MVP 안정화

- [ ] 30개 회귀 입력이 analyze → confirm → CAD 경로를 돈다.
- [ ] 확인된 프로파일 30개가 유효한 단일 solid를 만든다.
- [ ] x/y/z 오차가 각 축 `max(0.5mm, 0.5%)` 이하다.
- [ ] 실제 브라우저에서 업로드 → 수정 → 생성 → 다운로드를 관찰한다.
- [ ] 분석 시간, 메모리, 디스크 사용량을 기록한다.
- [ ] 외부 네트워크 요청 없이 동작한다.

## D6 — 운영 기능 판단

- [ ] 분석 p95를 측정한다.
- [ ] p95가 3초 이하이면 비동기 job/SSE를 구현하지 않은 결정을 기록한다.
- [ ] 작업 복구 요구가 없으면 draft DB를 구현하지 않은 결정을 기록한다.
- [ ] 필요 조건을 충족한 기능만 구현·검증한다.

## D7 — OCR 치수 후보

- [ ] OCR은 CPU에서 실행되고 로컬 LLM GPU 메모리와 경쟁하지 않는다.
- [ ] 숫자와 mm/cm 단위 후보를 위치·confidence와 함께 반환한다.
- [ ] OCR 값을 자동 calibration으로 확정하지 않는다.
- [ ] 사용자가 후보를 선택·수정·거부할 수 있다.
- [ ] OCR 미설치/인식 실패가 기존 수동 흐름을 깨지 않는다.

## 최종 검증

- [ ] 백엔드 전체 테스트가 통과한다.
- [ ] 프론트엔드 TypeScript 검사와 프로덕션 빌드가 통과한다.
- [ ] 실제 로컬 서버 health와 drawing E2E가 통과한다.
- [ ] GitHub Actions가 최종 커밋에서 통과한다.
- [ ] README, STATUS, TODO, 설계, 오류 기록이 실제 상태와 일치한다.
- [ ] 실제 사용자 도면이 없어서 검증하지 못한 항목은 완료로 표시하지 않는다.
