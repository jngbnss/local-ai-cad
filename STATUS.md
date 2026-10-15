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
- 상판이 다리를 덮는 공간 관계 수정은 LLM 없이 bounding box로 즉시 계산
- 텍스트·2D 생성 결과 모두 동일한 자연어 수정 입력과 버전 이력 사용

### Track D — 2D 도면 가져오기

- PNG/JPEG/WebP 검증, EXIF 보정, 분석 영역 crop, 외곽선·원형/다각형 구멍 후보 검출
- `DesignSpec 2.0`의 `sketch_extrusion`, 기존 1.0 이력 자동 마이그레이션
- SVG 외곽점 추가·선택 삭제·드래그·단순화, 구멍 편집, 기준점 2개 보정, undo/redo
- CPU RapidOCR 치수 후보와 명시적 사용자 선택·수정·거부
- 작은 인쇄 문자·무늬 필터, 복잡한 사진성 contour의 UI·API 생성 차단, 검출 요약표, 이전 결과 초기화
- 합성 30개 회귀 30/30. 사진성 입력은 자동 CAD 대상이 아니며 깨끗한 단일 정면 도면 10개는 아직 미검증

### Track V — 3면 CAD 복원 베타

- 정면(XZ)·평면(XY)·우측면(YZ) 고정 업로드와 제1각/제3각 선택
- 공통 가로·깊이·높이로 각 실루엣을 mm 좌표에 정합
- `orthographic_intersection` part와 CadQuery 직교 돌출·교집합
- 사진성 입력 차단, SQLite 이력, Three.js 미리보기, STEP/STL 다운로드 연결
- 뷰별 crop·기준점 축척, 재투영 IoU, 숨은선·포켓, 실제 3면도 10세트는 미구현

### Track P — 로컬 GPU 사진 3D 메시

- `C:\3-design`의 검증된 다중 뷰 계약을 기반으로 정면 필수, 후면·좌측·우측 선택 업로드 추가
- 불투명 사진의 단색 배경 분리, 로컬 Hunyuan3D-2mv 호출, 콘텐츠 주소 GLB 캐시 추가
- Three.js GLB 로딩과 Y-up 표시, GLB 다운로드, 메시/CAD 구분 문구 추가
- RTX 4050 6GB 실제 CUDA 생성: 98.086초, 2,742,784바이트 GLB
- Qwen과 Hunyuan 동시 상주는 지원하지 않으며 Hunyuan3D 비상업 라이선스를 적용

## 2. 현재 검증 상태

- 백엔드 테스트: **70개 통과**
- 프론트엔드 TypeScript 검사 및 프로덕션 빌드: 통과
- Track D 합성 회귀: analyze → confirm → CAD → STEP **30/30**
- 실제 Edge 브라우저: 자연어/2D/3면 경로와 사진 4장→로컬 GPU GLB→Three.js 표시·다운로드, 런타임 오류 없음
- 작업 브랜치: `main`

관련 문서:

- `docs/phase-2-6-report.md`
- `experiments/spec_accuracy_report.md`
- `docs/roadmap.md`
- `docs/track-d-checklist.md`
- `docs/track-v-cad-reverse-engineering-design.md`
- `docs/track-v-checklist.md`
- `docs/photo3d-local-checklist.md`
- `docs/photo3d-local-errors.md`
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

- 현재 파이프라인은 깨끗한 단일 정면 선 도면용이다. 원근·배경·인쇄 문자가 있는 제품 사진에서 정확한 CAD를 자동 복원하지 않는다.
- 실제 사용자 정면 도면 10개가 없어 합성 회귀셋이 제품 입력 분포를 대표하는지는 아직 검증하지 못했다.
- 복합 책상 2문항은 작은 모델이 중복 부품 ID를 교정하지 못한다.
- 앱 핵심 번들은 248KB로 분리했지만 Three.js Viewer chunk는 559KB 경고가 남는다.
- Windows pytest 임시 폴더는 외부 ESTsoft 프로세스 경합 시 정리 경고가 날 수 있다. 테스트 결과에는 영향이 없었다.

## 5. 앞으로 할 일

우선순위는 다음과 같다.

1. 실제 3면도+STEP 10세트를 확보하고 Track V 입력·평가 계약을 확정한다.
2. 정면·평면·우측면 업로드와 결정론적 교차 돌출·재투영 검증을 구현한다.
3. C: 여유 공간을 최소 35GB 이상 확보한 뒤 Drawing2CAD·COLMAP을 격리 환경에서 평가한다.
4. **Phase 7** Docker/WSL2 GPU 패키징과 실제 GPU E2E를 진행한다.
5. 필요하면 **트랙 Q**로 복합 가구 정확도를 90%에서 100%로 개선한다.

세부 체크리스트와 완료 조건은 [`TODO.md`](TODO.md)를 따른다.
