# Local AI CAD — 진행 현황 및 인수인계

기준일: 2026-10-15  
현재 상태: **Phase 1~6 및 Track D 구현 완료, 실제 사용자 도면 검증 대기**

## 1. 지금까지 완료한 것

### Phase 1 — 로컬 GPU LLM 기준선

- RTX 4060에서 `Qwen/Qwen2.5-1.5B-Instruct` FP16 추론 성공
- 프로세스당 모델 1회 적재와 추론 직렬화 구현
- CUDA 미인식, 모델 다운로드, GPU OOM 오류를 분리
- 적재 시간, 추론 시간, 토큰 수, 최대 VRAM 측정

### Phase 2 — FastAPI 서버

- 장수명 모델 provider를 FastAPI lifespan에 연결
- `/api/v1/health`, `/generate`, `/design` API 구현
- 요청 ID, 구조화 오류, 단일 워커 규칙 적용
- 동시 요청 직렬화 및 10회 요청 모델 재사용 테스트 완료

### Phase 3 — DesignSpec 생성·검증

- box/cylinder, 좌표, 불리언 연산을 표현하는 Pydantic 스키마 구현
- 단위를 mm로 통일하고 치수·ID·참조 무결성 검증
- 실패 원인을 모델에 돌려주는 최대 3회 교정 재시도 구현
- 실제 GPU 20문항 평가 완료
  - 1차 성공: **16/20(80%)**
  - 재시도 포함: **18/20(90%)**
  - 실패 2건: 네 다리 책상의 중복 부품 ID

### Phase 4 — CadQuery CAD 생성

- DesignSpec을 CadQuery 솔리드로 변환
- union/cut 연산과 기하 오류 경계 구현
- 닫힌 솔리드, 부피, 바운딩 박스, 치수 오차 검증
- STL 미리보기 파일과 STEP 제조용 파일 생성
- 실제 GPU E2E: 1회 시도, 추론 6.188초, STL/STEP 생성 및 치수 검사 통과

### Phase 5 — React·Three.js UI

- 자연어 프롬프트 입력과 SSE 단계 진행 표시
- STL 3D 회전·확대·축소 뷰어
- STEP/STL 다운로드, 추론 시간·부피 표시
- 오류 유형별 안내와 반응형 화면 구현
- 실제 브라우저에서 생성 진행 및 3D 렌더 검증

### Phase 6 — 수정·버전 이력

- 기존 설계와 수정 지시를 이용한 새 DesignSpec 생성
- 필드별 diff 기록 및 이전 버전 조회
- SQLite 영속 저장과 프로세스 재시작 후 복원
- 동시 수정 버전 번호 충돌 방지
- 미언급 필드 보존 테스트와 이력 UI 구현

### Track D — 2D 도면 가져오기

- PNG/JPEG/WebP 검증, EXIF 보정, 분석 영역 crop, 외곽선·원형/다각형 구멍 후보 검출
- `DesignSpec 2.0`의 `sketch_extrusion`, 기존 1.0 이력 자동 마이그레이션
- SVG 점·구멍 편집, 기준점 2개 보정, undo/redo, 기존 Three.js/다운로드 연결
- CPU RapidOCR 치수 후보와 명시적 사용자 선택·수정·거부
- 합성 30개 live HTTP E2E 30/30, OCR 포함 p95 1.3911초, 축 오차 0mm
- 실제 사용자가 제공한 도면 10개는 입력 부재로 미검증

## 2. 현재 검증 상태

- 백엔드 테스트: **57개 통과**
- 프론트엔드 TypeScript 검사 및 프로덕션 빌드: 통과
- Track D 합성 회귀: analyze → confirm → CAD → STEP **30/30**
- 실제 Edge 브라우저: 영역 선택, SVG 편집, undo/redo, OCR 확인, 3D Viewer, STEP download event 통과
- 작업 브랜치: `main`
- Track D 최신 구현 커밋: `838d0e7`

관련 문서:

- `docs/phase-2-6-report.md`
- `experiments/spec_accuracy_report.md`
- `docs/roadmap.md`
- `docs/track-d-checklist.md`
- `experiments/drawing-e2e/report.md`

## 3. 실행 방법

```powershell
# 백엔드
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m app.main

# 프론트엔드 — 별도 터미널
cd frontend
npm.cmd run dev
```

브라우저 주소: `http://127.0.0.1:5173`

GPU 모델 없이 경로만 검증할 때는 백엔드 실행 전에 다음을 설정한다.

```powershell
$env:LOCAL_AI_CAD_USE_MOCK = "1"
```

## 4. 현재 제약과 알려진 문제

- 실제 사용자 도면 10개가 없어 합성 회귀셋이 제품 입력 분포를 대표하는지는 아직 검증하지 못했다.
- 복합 책상 2문항은 작은 모델이 중복 부품 ID를 교정하지 못한다.
- 앱 핵심 번들은 244KB로 분리했지만 Three.js Viewer chunk는 559KB 경고가 남는다.
- Windows pytest 임시 폴더는 외부 ESTsoft 프로세스 경합 시 정리 경고가 날 수 있다. 테스트 결과에는 영향이 없었다.

## 5. 앞으로 할 일

우선순위는 다음과 같다.

1. 사용자 실제 정면 도면 10개를 확보해 Track D 수동 수정 횟수와 성공률을 검증한다.
2. C: 여유 공간을 최소 35GB 이상으로 확보한다.
3. **Phase 7** Docker/WSL2 GPU 패키징을 진행한다.
4. 컨테이너 실제 GPU E2E와 호스트 대비 성능을 측정한다.
5. 필요하면 **트랙 Q**로 복합 가구 정확도를 90%에서 100%로 개선한다.

세부 체크리스트와 완료 조건은 [`TODO.md`](TODO.md)를 따른다.
