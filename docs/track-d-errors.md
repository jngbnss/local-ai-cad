# Track D 오류 기록

기준: 재현된 사실만 기록한다. 미관찰 항목은 오류로 만들지 않는다.

| ID | 단계 | 상태 | 관찰 | 조치 또는 판정 |
|---|---|---|---|---|
| BASE-001 | 기존 CI | 해결 | 새 환경에서 Starlette TestClient가 `httpx2` 누락으로 수집 실패 | `requirements.lock`과 dev 의존성에 `httpx2==2.13.1` 추가. 로컬 40개 테스트와 CI 통과 |
| BASE-002 | D4 | 개선 | Vite 프로덕션 빌드에서 약 790KB 단일 chunk 경고 | Viewer lazy import로 앱 핵심 chunk를 242KB로 분리. Three.js 전용 chunk 559KB 경고는 잔존하나 최초 도면 편집 경로의 로딩을 막지 않음 |
| BASE-003 | 기존 LLM | 잔존 | 네 다리 책상 2문항이 중복 part ID로 실패, 재시도 포함 18/20 | Track Q 범위. Track D 이미지 파이프라인과 섞지 않음 |
| BASE-004 | 환경 | 관리됨 | RTX 4050 6GB에서 다른 GPU 프로세스가 모델과 VRAM 경합 가능 | 단일 추론 lock 유지. 이미지/OCR은 CPU 실행 |
| D0-INPUT-001 | D0 | 미충족 | 실제 사용자가 제공한 도면 이미지 10개가 저장소와 대화에 없음 | 합성 10개와 회귀 30개로 구현 경로를 검증하되 실제 도면 완료 조건은 별도 미완료로 유지 |
| D0-002 | D0 | 관리됨 | 굵은 외곽선 입력에서 내부 contour가 큰 hole처럼 검출됨 | 면적비 0.65 이상 child를 hole로 확정하지 않고 `double_contour_suspected` 경고. 합성 케이스는 유효 STEP 생성 |
| D3-001 | D3 | 해결 | `Exception` fallback handler만 등록했을 때 TestClient가 `UnsupportedImageError` 응답 후 예외를 재발생 | `DrawingError` 전용 handler를 등록하고 415 구조화 응답 회귀 테스트 통과 |
| D3-TOOL-001 | D3 | 해결 | Bash 서비스 명령에 Windows 역슬래시 경로를 써 실행 파일을 찾지 못함 | POSIX 형식 `.venv/Scripts/python.exe`로 재실행; 제품 코드 영향 없음 |
| D4-001 | D4 | 해결 | SVG drag 종료 시 React state closure가 시작 프로파일을 history에 넣지 않아 첫 undo가 이동을 되돌리지 못함 | drag 시작 시 history snapshot을 먼저 저장하도록 변경; 실제 브라우저에서 move → undo → redo 좌표 일치 확인 |
| D4-TOOL-001 | D4 | 우회 | 자동화 `browser.open`이 managed 옵션에서도 오래된 Browser Relay 오류로 실패 | QA 이슈 보고 후 설치된 Edge를 Puppeteer로 직접 구동해 실제 UI upload/edit/generate/Viewer를 검증 |
| D5-ENV-001 | D5 | 관리됨 | Windows 임시 디렉터리 정리 중 외부 ESTsoft 프로세스 경합으로 pytest `WinError 145` 경고 | 55개 테스트는 모두 통과했으며 제품·테스트 결과에 영향 없음. 외부 프로세스 소유 경로는 삭제하지 않음 |
| D7-001 | D7 | 해결 | 중단하지 않은 백엔드가 `cv2.pyd`를 점유해 기존 `rapidocr-onnxruntime` 설치가 `WinError 5`로 실패 | 서버를 중단하고 `opencv-python-headless`와 호환되는 유지보수 패키지 `rapidocr==3.10.0` 및 CPU `onnxruntime==1.31.0` 설치 |
| FINAL-CI-001 | 최종 CI | 해결 | GitHub hosted runner가 Node 20 기반 `checkout@v4`, `setup-node@v4` 폐기 경고를 출력 | `checkout@v5`, `setup-node@v5`, `setup-python@v6`으로 갱신 |
| FINAL-CI-002 | 최종 CI | 외부 공지 | `ubuntu-latest`가 2026-10-19부터 Ubuntu 26으로 이동 예정 | GitHub runner 이미지 공지이며 현재 빌드는 통과. 이동 후 CI에서 호환성을 계속 검증 |
| D8-INPUT-001 | 사용자 검증 | 관리됨 | 제품 사진의 인쇄 문자·무늬가 복잡한 polygon hole과 20점 외곽선으로 검출돼 로고가 뚫린 판처럼 생성됨 | 작은 후보 필터에 더해 전체 polygon 점이 32개를 넘으면 `detail_heavy_input`으로 분류. UI와 API 모두 3D 생성을 차단하며 실제 첨부 입력에서 경고·차단을 관찰 |
| D8-UI-001 | 사용자 검증 | 해결 | 새 파일 분석 실패 후 이전 설계의 3D·이력이 남아 현재 결과처럼 보였고 검출 수치 표가 없었음 | 파일 선택·재분석 시작 시 이전 결과와 이력을 초기화하고 외곽점·사용 hole·예상 치수·기준선·배율 표를 추가. 실제 브라우저에서 이전 결과 제거를 관찰 |
| D8-UI-002 | 사용자 검증 | 해결 | 과다 검출된 외곽점을 드래그만 할 수 있어 보정이 어려웠음 | 외곽점 추가, 선택 삭제, 불필요한 점 단순화를 추가. 실제 브라우저에서 4→5→4개 편집을 관찰 |
| D8-API-001 | 사용자 검증 | 해결 | self-intersection 등 생성 요청 검증 오류가 일반 백엔드 오류로 표시됨 | drawing API의 `RequestValidationError`를 `profile_invalid` 422로 구조화하고 오류 상세를 JSON-safe하게 반환하는 회귀 테스트 추가 |
| D9-REVISION-001 | 사용자 검증 | 해결 | “위에 판자가 다리를 다 덮어야지…” 수정에서 1.5B 모델 출력이 3회 모두 완결된 JSON을 만들지 못했고 범용 예외 처리로 프론트에는 `unknown` 오류가 표시됨 | 상판이 지지물을 덮는 명확한 공간 관계는 하부 bounding box로 결정론적으로 계산하고, `SpecGenerationError` 전용 422 handler를 등록. 동일 문장으로 상판 1200×600→1600×1000mm, v2 생성 확인 |

## 단계별 추가 규칙

- 재현 명령, 입력 ID, 오류 타입을 기록한다.
- 코드로 해결한 오류는 해결 커밋과 검증 명령을 기록한다.
- 자동 보정으로 숨긴 오류는 해결로 처리하지 않는다.
- 외부 도구 장애와 제품 코드 오류를 구분한다.
