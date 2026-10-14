# Local AI CAD — 진행 현황 및 인수인계

기준일: 2026-10-14  
현재 상태: **Phase 1~6 완료, Phase 7 착수 전**

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

## 2. 현재 검증 상태

- 백엔드 테스트: **40개 통과**
- 프론트엔드 TypeScript 검사 및 프로덕션 빌드: 통과
- Mock E2E: 프롬프트 → DesignSpec → CAD → 3D → 이력 통과
- 실제 GPU E2E: 통과
- 작업 브랜치: `main`
- Phase 1~6 구현 커밋: `11d983e`

관련 문서:

- `docs/phase-2-6-report.md`
- `experiments/spec_accuracy_report.md`
- `docs/roadmap.md`

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

- C: 여유 공간은 마지막 측정 기준 **24.1GB**다.
- Phase 7은 추가 15~25GB를 사용할 수 있어 최소 35GB, 권장 40GB 이상의 여유 공간이 필요하다.
- 복합 책상 2문항은 작은 모델이 중복 부품 ID를 교정하지 못한다.
- 프론트엔드 번들은 약 790KB로 코드 분할 경고가 있다.
- Starlette TestClient에서 `httpx` 사용 중단 경고가 1건 발생한다.

## 5. 앞으로 할 일

우선순위는 다음과 같다.

1. C: 여유 공간을 최소 35GB 이상으로 확보한다.
2. **Phase 7** Docker/WSL2 GPU 패키징을 진행한다.
3. 컨테이너 실제 GPU E2E와 호스트 대비 성능을 측정한다.
4. 필요하면 **트랙 Q**로 복합 가구 정확도를 90%에서 100%로 개선한다.
5. 번들 분할, 테스트 경고, 요청 취소, 아티팩트 정리 정책을 보완한다.

세부 체크리스트와 완료 조건은 [`TODO.md`](TODO.md)를 따른다.
