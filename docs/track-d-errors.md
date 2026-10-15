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

## 단계별 추가 규칙

- 재현 명령, 입력 ID, 오류 타입을 기록한다.
- 코드로 해결한 오류는 해결 커밋과 검증 명령을 기록한다.
- 자동 보정으로 숨긴 오류는 해결로 처리하지 않는다.
- 외부 도구 장애와 제품 코드 오류를 구분한다.
